"""批次收尾的判据。核心是**只认真实落点**。"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo
# 离线 TMDB 替身**直接复用 test_rename_nfo_route.py 里 matched_client 用的那一个**
# （import 而不是复制）: 它已被那个文件的多条用例钉住（剧名/季/集号的对应关系）,
# 复制一份必然在下次改动时漂移成「两个假 TMDB 说的不一样」。
from tests.test_rename_nfo_route import _FakeTmdbClient

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


def _video(tmp_path, name, file_id):
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")
    return FileInfo(
        id=file_id, source="local", path=str(path), filename=name,
        extension=".mkv", parent_dir=str(tmp_path),
    )


@pytest.fixture
def env(tmp_path):
    files = [
        _video(tmp_path, "Show.S01E01.mkv", "f1"),
        _video(tmp_path, "Show.S01E02.mkv", "f2"),
    ]
    cache_files(files)
    return {"client": TestClient(app), "files": files, "dir": str(tmp_path)}


@pytest.fixture
def matched_env(env, monkeypatch):
    """在 env 之上加一个 TMDB 命中 —— 夹具形状与 test_rename_nfo_route.py 的
    matched_client 一致（同一个离线替身、同一套「一部剧两集」的批次）。

    landed 就是**重命名后**的真实落点（模板 {show} - S{season_padded}E{episode_padded}
    配上 overrides 里的 Show / 1 / 1..2）—— 正是前端从单文件响应里收回来再回传的
    那个映射, 不是「假定都成功」重算出来的。
    """
    from app.api import renamer as renamer_api

    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    env["landed"] = {
        f.id: os.path.join(env["dir"], f"Show - S01E0{i + 1}.mkv")
        for i, f in enumerate(env["files"])
    }
    return env


def _payload(env, landed, **extra):
    body = {
        "file_ids": [f.id for f in env["files"]],
        "template": TEMPLATE,
        "source": "local",
        "path": env["dir"],
        "overrides": {
            f.id: {"show_name": "Show", "season": 1, "episode": i + 1}
            for i, f in enumerate(env["files"])
        },
        "generate_nfo": True,
        "landed": landed,
    }
    body.update(extra)
    return body


def test_no_landed_files_writes_no_group_nfo(matched_env):
    """**核心判据**：一个文件都没落地 → 一份 tvshow.nfo 都不许写。

    把 landed 过滤删掉（改成「假定全部落地」）本用例必然红 —— 那正是 spec §9.4
    的库根污染: 在一个没有任何剧集文件的目录里放一份 tvshow.nfo。

    **必须跑在 TMDB 命中的夹具上**（实测结论, 别改回 env）: 未配 TMDB 时组级
    决策的 content 恒为 None, 无论 landed 怎么算都不会有文件被写 —— 那种「不落盘」
    是空断言。实测把 landed 换成「假定全部落地」重算, 未配 TMDB 的版本**照样全绿**,
    只有本版本（有内容可写）才会红。少一条都不算钉住。
    """
    res = matched_env["client"].post(
        "/api/rename/finalize", json=_payload(matched_env, landed={})
    )
    assert res.status_code == 200, res.text
    assert res.json()["nfo_written"] == []
    assert not os.path.exists(os.path.join(matched_env["dir"], "tvshow.nfo"))
    # 季级是**另一条**组级决策, 一起钉住: 只滤 tvshow 的实现过不了这一条。
    assert not os.path.exists(os.path.join(matched_env["dir"], "season.nfo"))


def test_partial_landing_still_writes_group_nfo(matched_env):
    """**部分落地**（只有一集真的改名成功）→ 组级 NFO 照写。

    与 test_no_landed_files_writes_no_group_nfo 成对, 两条合起来才是完整的判据:
    「有的落地 → 写」「一个都没落地 → 不写」。此前所有 finalize 夹具非「全都落地」
    即「一个都没落地」, 「部分落地」这个**不变量真正针对的场景**没有任何夹具。

    这里落地的偏偏是**第二集**（f2）: tvshow / season 决策按契约挂在组内首个
    file_id（f1）上, 而 f1 没落地。于是本用例同时钉住「组级判据是**目录里有视频
    落地**, 不是**组代表落地**」—— 改成后者时 f1 不在 landed 里, 决策被丢,
    tvshow.nfo 不落盘, 前两条断言必红。（未配 TMDB 的版本只能断言跳过清单里的
    reason, 见 test_group_nfo_planned_when_any_file_landed; 这条断言的是**真的写到
    盘上**, 更强。）
    """
    landed = {"f2": matched_env["landed"]["f2"]}
    res = matched_env["client"].post(
        "/api/rename/finalize", json=_payload(matched_env, landed=landed)
    )
    assert res.status_code == 200, res.text
    written = res.json()["nfo_written"]
    assert os.path.join(matched_env["dir"], "tvshow.nfo") in written
    assert os.path.join(matched_env["dir"], "season.nfo") in written
    # 盘上也得有 —— 只查响应会漏掉「报了但没写」。
    for path in written:
        assert os.path.exists(path), path


# --- 子树几何：落点在 `Season 01/` 子目录里, 组级决策仍须保留 --------------------


@pytest.fixture
def season_env(tmp_path, monkeypatch):
    """文件会落进 `Season 01/` 子目录的布局（folder_template + 建季目录）。

    剧集根会因此**上溯一层**: new_path 的公共父目录是 `tmp/Season 01`, 而它自己
    匹配季目录模式 → tvshow.nfo 落在 `tmp/`, season.nfo 落在 `tmp/Season 01/`。
    这正是 `_keep_decision` 里那段前缀判据（`p == directory or p.startswith(prefix)`）
    存在的理由 —— 落点与决策目录**不相等**, 而是在它的子树里。
    """
    from app.api import renamer as renamer_api

    files = [
        _video(tmp_path, "Show.S01E01.mkv", "f1"),
        _video(tmp_path, "Show.S01E02.mkv", "f2"),
    ]
    cache_files(files)
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    return {"client": TestClient(app), "files": files, "dir": str(tmp_path)}


def test_group_decision_kept_when_landing_is_in_subtree(season_env):
    """落点在 `Season 01/` 子目录里 → 组级决策**仍然保留**（前缀判据, 不是相等判据）。

    把 `_keep_decision` 的组级分支换成 `any(p == directory for p in landed_paths)`
    （「落点必须**就是**那个目录」）本用例必红: tvshow 决策的目录是 `tmp/`,
    而落点是 `tmp/Season 01/Show - S01E01.mkv` —— 目录里**确实**有剧集文件,
    却会被判成「没有文件落地」, tvshow.nfo 静默不写。这条判据此前没有任何夹具
    钉住（现有 finalize 夹具全是单层平铺目录, 落点与决策目录恒相等）。
    """
    landed = {"f1": os.path.join(season_env["dir"], "Season 01", "Show - S01E01.mkv")}
    res = season_env["client"].post(
        "/api/rename/finalize",
        json=_payload(
            season_env, landed=landed,
            folder_template="Season {season_padded}", create_season_folder=True,
        ),
    )
    assert res.status_code == 200, res.text
    written = res.json()["nfo_written"]
    # 剧集根上溯到 tmp/, 季级落在季目录里 —— 两条落点都不等于决策目录本身。
    assert os.path.join(season_env["dir"], "tvshow.nfo") in written, written
    assert os.path.join(season_env["dir"], "Season 01", "season.nfo") in written, written
    for path in written:
        assert os.path.exists(path), path


def test_group_decision_dropped_when_landing_is_in_another_shows_dir(tmp_path, monkeypatch):
    """落点在**另一部剧**的目录里 → 本剧的组级决策必须丢弃（不许写成「landed 非空」）。

    这条补的是前缀判据的**另一半**: `_keep_decision` 的组级分支若被换成「landed
    非空就保留」（一个看起来等价、且现有全部 finalize 用例都对它全绿的写法）,
    本用例必红 —— 一个只有 A 剧文件的批次里, 只因 B 剧的某个文件落了地, 就会在
    A 剧的目录里写出 tvshow.nfo, 而那个目录**一个剧集文件都没有**: 正是 spec §9.4
    的库根污染, 也正是 batch_rename 的 `landed_paths` 按目录判的原因。

    用 TMDB 命中的夹具: 只有内容可写时「写不写」才是个真判断（未配 TMDB 时两种
    实现都写不出文件, 断言会变成恒真）。
    """
    from app.api import renamer as renamer_api

    dir_a = tmp_path / "ShowA"
    dir_b = tmp_path / "ShowB"
    dir_a.mkdir()
    dir_b.mkdir()
    video_a = dir_a / "ShowA.S01E02.mkv"
    video_b = dir_b / "ShowB.S01E02.mkv"
    video_a.write_text("x", encoding="utf-8")
    video_b.write_text("x", encoding="utf-8")
    files = [
        FileInfo(id="fa", source="local", path=str(video_a), filename=video_a.name,
                 extension=".mkv", parent_dir=str(dir_a)),
        FileInfo(id="fb", source="local", path=str(video_b), filename=video_b.name,
                 extension=".mkv", parent_dir=str(dir_b)),
    ]
    cache_files(files)
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )

    body = {
        "file_ids": ["fa", "fb"],
        "template": TEMPLATE,
        "source": "local",
        "path": str(tmp_path),
        "overrides": {
            "fa": {"show_name": "ShowA", "season": 1, "episode": 2},
            "fb": {"show_name": "ShowB", "season": 1, "episode": 2},
        },
        "generate_nfo": True,
        # 只有 **B 剧**的文件落地。
        "landed": {"fb": str(dir_b / "ShowB - S01E02.mkv")},
    }
    res = TestClient(app).post("/api/rename/finalize", json=body)
    assert res.status_code == 200, res.text
    body_out = res.json()

    # B 剧: 目录里有剧集文件落地 → 照写。
    assert str(dir_b / "tvshow.nfo") in body_out["nfo_written"], body_out["nfo_written"]
    assert os.path.exists(dir_b / "tvshow.nfo")
    # A 剧: 一个文件都没落地 → 不许写, 且必须**报出来**。
    assert not os.path.exists(dir_a / "tvshow.nfo")
    assert not os.path.exists(dir_a / "season.nfo")
    reasons = {d["path"]: d["reason"] for d in body_out["nfo_skipped"]}
    assert reasons[str(dir_a / "tvshow.nfo")] == (
        "该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO"
    ), reasons


def test_finalize_never_writes_episode_nfo(matched_env):
    """每集 NFO 由单文件接口写, 收尾**不得**再写一遍。

    去掉 kind != "episode" 的过滤本用例必然红（实测: 报出并写下
    Show - S01E02.nfo）—— 但**必须跑在 TMDB 命中的夹具上**: 未配 TMDB 时每集
    决策的 content 也是 None, 不滤也写不出文件, 那种版本全绿（空断言）。

    同时钉住「收尾确实写了组级 NFO」, 否则「一份每集 NFO 都没有」可以靠
    「收尾什么都没写」来满足 —— 那是与实现无关的绿。
    """
    res = matched_env["client"].post("/api/rename/finalize", json=_payload(
        matched_env, landed=matched_env["landed"]))
    assert res.status_code == 200, res.text
    written = res.json()["nfo_written"]
    assert written, "收尾一个文件都没写 —— 下面两条断言失去鉴别力"
    assert not any(w.endswith("Show - S01E01.nfo") for w in written)
    assert not any(w.endswith("Show - S01E02.nfo") for w in written)
    # 盘上也只能有那两份组级 NFO: 只查响应会漏掉「写了但没报」。
    assert sorted(p.name for p in Path(matched_env["dir"]).glob("*.nfo")) == [
        "season.nfo", "tvshow.nfo",
    ]


def test_finalize_skips_when_nfo_disabled(matched_env):
    """关掉「生成 NFO」→ 收尾连决策都不该有（不只是「没写盘」）。

    **必须跑在 TMDB 命中的夹具上**: 未配 TMDB 时「没写盘」是恒真的, 把
    generate_nfo 读成恒真也照样全绿。这里 landed 落在真实目录里, 于是只要
    选项没传下去, 两份组级 NFO 就会被写出来 —— 断言才咬得住。
    断言 nfo_skipped 为空, 钉住「整个 NFO 环节都没参与」。
    """
    res = matched_env["client"].post("/api/rename/finalize", json=_payload(
        matched_env, landed=matched_env["landed"], generate_nfo=False))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["nfo_written"] == []
    assert body["nfo_skipped"] == []
    assert list(Path(matched_env["dir"]).glob("*.nfo")) == []


def test_finalize_writes_group_nfo_to_disk_when_tmdb_matched(matched_env):
    """TMDB 命中时, 收尾必须把 tvshow.nfo / season.nfo **真的写到盘上**。

    这是「组级 NFO 确实会落盘」在全套里唯一的端到端判据 —— Task 5 把原来那三条
    从 execute 侧删掉了, 少了它, 这条覆盖就只剩 `nfo_skipped` 的间接证据。
    把 finalize_show_nfo 的写盘删掉（只返回跳过）本用例必红。
    """
    res = matched_env["client"].post("/api/rename/finalize", json=_payload(
        matched_env, landed=matched_env["landed"]))
    assert res.status_code == 200, res.text
    written = res.json()["nfo_written"]
    assert os.path.join(matched_env["dir"], "tvshow.nfo") in written
    assert os.path.join(matched_env["dir"], "season.nfo") in written
    for path in written:
        assert os.path.exists(path), path


def test_group_nfo_planned_when_any_file_landed(env):
    """只落地第二集也要为整剧算出 tvshow 决策 —— 判据是「目录里有视频落地」。

    未配 TMDB 时它报成跳过（"TMDB 未匹配, 不写残缺 NFO"）而不是落盘, 所以这里
    断言的是**跳过清单里出现了 tvshow.nfo 这个路径**, 而不是文件真的写了。

    **光断言路径不够, 必须连 reason 一起钉**: 组级决策被**丢弃**时也会把同一个
    路径写进 nfo_skipped（只是原因不同）。只查路径存在的话, 一个「按**组代表**
    判落地」的实现照样全绿 —— tvshow 决策按契约挂在组内首个 file_id（这里是
    **没落地**的 f1）上, 而落地的是 f2。实测: 把 _keep_decision 换成「组代表也
    得落地」→ 只查路径的版本绿, 本条（reason 变成「没有文件真正改名落地」）红。
    本条的 reason 与下一条的 reason 正好是两个不同的值, 两条合起来才说明
    landed 是**按目录**判的。
    """
    landed = {"f2": os.path.join(env["dir"], "Show - S01E02.mkv")}
    res = env["client"].post("/api/rename/finalize", json=_payload(env, landed=landed))
    assert res.status_code == 200, res.text
    body = res.json()
    tvshow = os.path.join(env["dir"], "tvshow.nfo")
    assert tvshow in [d["path"] for d in body["nfo_skipped"]]
    # 决策被**算出**（走到了写盘那一步才发现没有内容）, 而不是被落地过滤丢掉
    reasons = {d["path"]: d["reason"] for d in body["nfo_skipped"]}
    assert reasons[tvshow] == "TMDB 未匹配, 不写残缺 NFO"


def test_no_landed_files_drops_the_group_decision(env):
    """landed 为空 → 组级决策在**落地过滤**那一步就被丢弃, 且必须如实报出来。

    与上一条成对, 两条一起才钉住「landed 真的被当判据用」:
    - 上一条: 目录里有一个视频落地 → 决策被算出（报「TMDB 未匹配」）;
    - 本条: 一条都没落地 → 决策被**丢弃**（报「没有文件真正改名落地」）。
    把 landed 换成「假定全部落地」重算, 本条的 reason 会变成「TMDB 未匹配,
    不写残缺 NFO」→ 红; 把丢弃那条 skipped 记录删掉（只丢不报）→ 红。

    原简报此处的断言是 `tvshow not in nfo_skipped`（「一条决策都没有」）——
    那与本仓库既有的、带变异验证的裁定**直接冲突**: 丢弃组级决策必须报出来
    （tests/test_nfo_write.py:1041 test_dropped_group_nfo_is_reported_as_skipped,
    「留白等于静默」）。实测该断言在正确实现与错误实现下**都**为红 ——
    没有任何实现改动能让它变绿, 即零鉴别力, 故按既定语义改正为断言丢弃原因。
    """
    res = env["client"].post("/api/rename/finalize", json=_payload(env, landed={}))
    assert res.status_code == 200, res.text
    body = res.json()
    tvshow = os.path.join(env["dir"], "tvshow.nfo")

    assert tvshow not in body["nfo_written"]
    assert not os.path.exists(tvshow)
    # 字面值与 tests/test_nfo_write.py 的 DROPPED_GROUP_REASON 同一串
    # （local_renamer._DROPPED_GROUP_NFO_REASON）—— 两处报的是同一件事。
    reasons = {d["path"]: d["reason"] for d in body["nfo_skipped"]}
    assert reasons[tvshow] == "该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO"


def test_openlist_source_returns_empty_without_error(env):
    """OpenList 本期不写 NFO（spec §2）—— 收尾必须**如实返回空**, 而不是报错。

    前端本来就只在 local 时调它, 这里防的是手工调用。去掉路由里
    `_nfo_supported` 那道守卫本用例必红: 它会走到 local 的落盘逻辑。
    """
    res = env["client"].post("/api/rename/finalize", json=_payload(
        env, landed={"f1": "/x"}, source="openlist"))
    assert res.status_code == 200, res.text
    assert res.json() == {"success": True, "nfo_written": [], "nfo_skipped": []}


def test_unknown_file_ids_are_rejected(env):
    """file_ids 一个都找不到时如实报 400, 不要静默返回空。

    静默返回空会让前端以为「收尾成功、只是没有组级 NFO 可写」—— 那是假话。
    """
    body = _payload(env, landed={})
    body["file_ids"] = ["nope"]
    res = env["client"].post("/api/rename/finalize", json=body)
    assert res.status_code == 400, res.text
    assert "未找到" in res.json()["detail"]
