import os

import pytest
from fastapi.testclient import TestClient

from app.api.renamer import _nfo_supported, cache_files
from app.main import app
from app.models.file import FileInfo
from app.models.tmdb import TmdbEpisode, TmdbSearchItem, TmdbSeason, TmdbShow


TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
OVERRIDES = {"f1": {"show_name": "Test Show", "season": 1, "episode": 2}}


def _file(file_id, video):
    return FileInfo(
        id=file_id,
        source="local",
        path=str(video),
        filename=video.name,
        extension=".mkv",
        parent_dir=str(video.parent),
    )


@pytest.fixture
def client(tmp_path):
    video = tmp_path / "Test Show" / "Test.Show.S01E02.mkv"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")

    cache_files([_file("f1", video)])
    return TestClient(app)


def payload(**extra):
    data = {
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "",
        "overrides": OVERRIDES,
        "conflict_strategy": "skip",
    }
    data.update(extra)
    return data


def test_generate_nfo_off_writes_nothing(client, tmp_path):
    res = client.post("/api/rename/execute", json=payload(generate_nfo=False))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["nfo_written"] == []
    assert list(tmp_path.rglob("*.nfo")) == []
    # 「关掉」必须是**整个 NFO 环节都不参与**, 不只是「没写盘」: 未配 TMDB 时
    # 即使把 generate_nfo 读成恒真, 上面两条也照样成立（决策全是无内容）。
    # 断言跳过清单与落点为空, 才把「选项真的传下去了」这件事钉住。
    assert body["nfo_skipped"] == []
    assert body["results"][0]["nfo_path"] is None


def test_dry_run_lists_nfo_plan_without_writing(client, tmp_path):
    # Review Focus：干跑必须列出清单但绝不落盘
    res = client.post("/api/rename/dry-run", json=payload(generate_nfo=True))
    assert res.status_code == 200, res.text
    body = res.json()

    assert list(tmp_path.rglob("*.nfo")) == [], "干跑不得落盘"
    assert body["nfo_written"] == [], "未配 TMDB 时没有可写的 NFO"

    row = body["results"][0]
    assert row["nfo_path"] is not None
    assert row["nfo_path"].endswith("Test Show - S01E02.nfo")


def test_generate_nfo_without_tmdb_key_produces_no_files(client, tmp_path):
    # Review Focus 4：无 TMDB 数据时不写残缺 NFO, 但重命名照常完成
    res = client.post("/api/rename/execute", json=payload(generate_nfo=True))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["results"][0]["success"] is True
    assert body["nfo_written"] == []
    assert list(tmp_path.rglob("*.nfo")) == []
    assert any("TMDB" in item["reason"] for item in body["nfo_skipped"])


def test_openlist_source_refuses_nfo(client):
    # Review Focus：OpenList 本期不支持写 NFO。预览不依赖连接, 可以直接断言。
    res = client.post("/api/rename/preview", json=payload(source="openlist", generate_nfo=True))
    assert res.status_code == 200, res.text

    row = res.json()["results"][0]
    assert row["nfo_scope"] == "unsupported_source"
    assert row["nfo"] is None


def test_preview_reports_disabled_scope_without_tmdb(client):
    res = client.post("/api/rename/preview", json=payload(generate_nfo=True))
    assert res.status_code == 200, res.text

    row = res.json()["results"][0]
    assert row["nfo_scope"] == "disabled"
    assert row["nfo"] is None


def test_preview_scope_is_disabled_when_nfo_is_off(client):
    # 与上一条成对: 「根本没勾选」也是 disabled。两条一起才钉住 disabled 这个
    # 字面值不是随手可换的 —— 它同时是「未启用」与「启用但没内容」的答案。
    res = client.post("/api/rename/preview", json=payload(generate_nfo=False))
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["nfo_scope"] == "disabled"


def test_openlist_is_not_an_nfo_capable_source():
    # 本条与上面的预览用例是两处不同的执行点: 预览报 unsupported_source,
    # execute/dry-run 靠 _nfo_supported 决定传给 batch_rename 的选项。
    # 两侧共用这一个判定函数, 所以把它本身钉住。
    assert _nfo_supported("local") is True
    assert _nfo_supported("openlist") is False


# --- 以下为简报未给的用例：TMDB 匹配成功时的 scope 与干跑清单 -----------------
# 上面五条全跑在「未配 TMDB」的路径上, 于是它们**区分不了** scope 的
# full / episode_only 两个取值, 也区分不了干跑是否真的把 dry_run 传了下去
# （无 TMDB 时没有任何内容可写, 真写也不会在盘上留下东西）。
# 这一组用离线替身补齐这两处鉴别力。

class _FakeTmdbClient:
    """离线替身: 任意剧名都匹配到同一部剧, 第 1 季含第 2、3 集。"""

    language = "zh-CN"

    def cache_fingerprint(self):
        return "nfo-route-fake"

    async def search_tv(self, query, year=None):
        return [TmdbSearchItem(tv_id=1396, name=query, original_name=query, year=2008)]

    async def get_tv_detail(self, tv_id):
        return TmdbShow(tv_id=tv_id, name="Test Show", original_name="Test Show", year=2008)

    async def get_season(self, tv_id, season_number):
        return TmdbSeason(season_number=season_number, tmdb_id=3575, episodes={
            2: TmdbEpisode(episode_number=2, name="Breakage", tmdb_id=62085),
            3: TmdbEpisode(episode_number=3, name="Cancer Man", tmdb_id=62086),
        })


@pytest.fixture
def matched_client(tmp_path, monkeypatch):
    """两个文件、同一部剧、同一目录, 且 TMDB 命中 —— 也就是最常见的真实批次。"""
    from app.api import renamer as renamer_api

    show_dir = tmp_path / "Test Show"
    show_dir.mkdir(parents=True)
    videos = []
    for episode in (2, 3):
        video = show_dir / f"Test.Show.S01E0{episode}.mkv"
        video.write_bytes(b"")
        videos.append(video)

    cache_files([_file("f1", videos[0]), _file("f2", videos[1])])
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    return TestClient(app)


MATCHED_PAYLOAD = {
    "file_ids": ["f1", "f2"],
    "template": TEMPLATE,
    "source": "local",
    "path": "",
    "overrides": {
        "f1": {"show_name": "Test Show", "season": 1, "episode": 2},
        "f2": {"show_name": "Test Show", "season": 1, "episode": 3},
    },
    "generate_nfo": True,
}


def test_preview_reports_full_scope_for_a_multi_episode_batch(matched_client, tmp_path):
    """多集批次必须是 full。

    这条钉住一个**假阴性**: 剧集级决策按契约只挂在组内首个 file_id 上
    （见 nfo_writer.build_nfo_decisions 的归属契约）, 所以「逐文件查该行有没有
    tvshow 键」的写法在同一部剧选了两集时必然报 episode_only —— 而 tvshow.nfo
    明明在计划里。那正是 spec §9.4「让他看见」要防的静默: 前端据此显示的提示
    会把真实落点藏起来。
    """
    res = matched_client.post("/api/rename/preview", json=MATCHED_PAYLOAD)
    assert res.status_code == 200, res.text
    body = res.json()

    assert [row["nfo_scope"] for row in body["results"]] == ["full", "full"]

    # 剧集级只落在组内首行, 但三个键名是线上契约 —— 前端读的是 row.nfo.tvshow
    # （Task 5）, 改成 "show" 会让它能编译却永远不显示落点。
    show_dir = tmp_path / "Test Show"
    assert body["results"][0]["nfo"] == {
        "episode": str(show_dir / "Test Show - S01E02.nfo"),
        "tvshow": str(show_dir / "tvshow.nfo"),
        "season": str(show_dir / "season.nfo"),
    }
    assert set(body["results"][1]["nfo"]) == {"episode"}


def test_preview_reports_episode_only_when_the_show_level_nfo_is_refused(tmp_path, monkeypatch):
    """混放目录下剧集级 NFO 被守卫拒绝 —— 此时 scope 必须如实报 episode_only。

    与上一条成对: 没有这一条, 一个把 scope 恒写成 "full" 的实现全绿。
    """
    from app.api import renamer as renamer_api

    show_dir = tmp_path / "未分类"
    show_dir.mkdir(parents=True)
    videos = []
    for name in ("A.S01E02.mkv", "B.S01E02.mkv"):
        video = show_dir / name
        video.write_bytes(b"")
        videos.append(video)

    cache_files([_file("f1", videos[0]), _file("f2", videos[1])])
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    client = TestClient(app)

    res = client.post("/api/rename/preview", json={
        "file_ids": ["f1", "f2"],
        "template": TEMPLATE,
        "source": "local",
        "path": "",
        "overrides": {
            "f1": {"show_name": "剧甲", "season": 1, "episode": 2},
            "f2": {"show_name": "剧乙", "season": 1, "episode": 2},
        },
        "generate_nfo": True,
    })
    assert res.status_code == 200, res.text

    for row in res.json()["results"]:
        assert row["nfo_scope"] == "episode_only"
        # 只剩每集落点: 同目录混放两部剧, 剧集级与季级都被拒绝
        assert set(row["nfo"]) == {"episode"}


def test_preview_scope_is_episode_only_when_only_some_shows_are_refused(tmp_path, monkeypatch):
    """**中间态**: 剧甲干净且命中（tvshow 算得出来）, 剧乙被混放守卫拒绝。

    上面两条只钉住两个**端点**（「所有剧的剧集级都写得出」→ full、「一部都写不出」
    → episode_only）, 中间态此前无人管: 把判据换成「任一部剧有 tvshow 就报 full」,
    那两个端点照样全绿 —— 实测该变异下全套 192 passed、零转红（本条补上后 1 红）。

    断言两件不同粒度的事, 别把它们混为一谈:
    - `nfo_scope` 是**批次级**的一个值, 复制到每一行 —— 只要有一部剧的剧集级写不全,
      整批就是 episode_only;
    - `nfo` 是**每行**的自己的落点 —— 剧甲那一行的 nfo.tvshow 仍然在。
    混放目录里那两部剧只剩每集落点。
    """
    from app.api import renamer as renamer_api

    clean_dir = tmp_path / "剧甲目录"
    mixed_dir = tmp_path / "未分类"
    clean_dir.mkdir(parents=True)
    mixed_dir.mkdir(parents=True)

    videos = [clean_dir / "A.S01E02.mkv", mixed_dir / "B.S01E02.mkv",
              mixed_dir / "C.S01E02.mkv"]
    for video in videos:
        video.write_bytes(b"")

    # 剧乙必须与**另一部剧**同处一个目录才会被守卫拒绝, 所以批次里还得有剧丙 ——
    # 守卫判的是「该剧根目录及其子树里有没有别的剧」, 只有一部剧的目录永远是干净的。
    cache_files([_file(f"f{i}", video) for i, video in enumerate(videos, start=1)])
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    client = TestClient(app)

    res = client.post("/api/rename/preview", json={
        "file_ids": ["f1", "f2", "f3"],
        "template": TEMPLATE,
        "source": "local",
        "path": "",
        "overrides": {
            "f1": {"show_name": "剧甲", "season": 1, "episode": 2},
            "f2": {"show_name": "剧乙", "season": 1, "episode": 2},
            "f3": {"show_name": "剧丙", "season": 1, "episode": 2},
        },
        "generate_nfo": True,
    })
    assert res.status_code == 200, res.text
    rows = res.json()["results"]

    assert [row["nfo_scope"] for row in rows] == ["episode_only"] * 3
    # 剧甲自己那一行: 三份落点俱全 —— 批次报 episode_only 不等于把它的 tvshow 抹掉
    assert rows[0]["nfo"] == {
        "episode": str(clean_dir / "剧甲 - S01E02.nfo"),
        "tvshow": str(clean_dir / "tvshow.nfo"),
        "season": str(clean_dir / "season.nfo"),
    }
    for row in rows[1:]:
        assert set(row["nfo"]) == {"episode"}


def test_dry_run_with_tmdb_lists_the_plan_but_writes_nothing(matched_client, tmp_path):
    """干跑在**有内容可写**时也必须一字节不落 —— 这才是「dry_run 真的传下去了」。

    未配 TMDB 的干跑用例区分不了这件事: 决策全是无内容, 真写也留不下文件。
    """
    res = matched_client.post("/api/rename/dry-run", json=MATCHED_PAYLOAD)
    assert res.status_code == 200, res.text
    body = res.json()

    assert list(tmp_path.rglob("*.nfo")) == [], "干跑不得落盘"
    assert body["nfo_written"]  # 但有清单 —— 否则「不落盘」可以靠什么都不列来满足
    assert any(path.endswith("tvshow.nfo") for path in body["nfo_written"])
    assert body["nfo_skipped"] == []
    assert body["results"][0]["nfo_path"].endswith("Test Show - S01E02.nfo")


def test_execute_with_tmdb_writes_all_three_kinds(matched_client, tmp_path):
    """执行路径的端到端钉子: 三份 NFO 都真的落到盘上。

    路由若漏传 nfo_options / nfo_matches（或传成空字典）, 上面所有用例照样全绿,
    盘上却什么都没有 —— 这正是本仓库有前科的「预览说一套、执行做另一套」。
    """
    res = matched_client.post("/api/rename/execute", json=MATCHED_PAYLOAD)
    assert res.status_code == 200, res.text
    body = res.json()

    written = set(body["nfo_written"])
    show_dir = tmp_path / "Test Show"
    assert str(show_dir / "Test Show - S01E02.nfo") in written
    assert str(show_dir / "Test Show - S01E03.nfo") in written
    assert str(show_dir / "tvshow.nfo") in written
    assert str(show_dir / "season.nfo") in written
    for path in written:
        assert os.path.isfile(path), path

    # 每集 NFO 跟着**改名后**的视频路径走
    assert body["results"][0]["nfo_path"] == str(show_dir / "Test Show - S01E02.nfo")


def test_subtitle_is_excluded_from_both_preview_and_execute(tmp_path, monkeypatch):
    """字幕不得进 NFO 管线 —— 预览与执行**两条路都要滤掉**。

    解析器给字幕与视频**完全相同**的结果（实测 Test.Show.S01E02.chs.srt 与
    Test.Show.S01E02.mkv 的 show/season/episode 一字不差）, 而 episode_nfo_path
    只换扩展名; 且决策按 (show_name, season, episode, new_path) 排序,
    '….chs.srt' < '….mkv' —— 不滤掉的话字幕会抢到 group[0], tvshow.nfo 的落点
    会显示在字幕行上, 而视频行只有一个 episode 键（前端据此把「+ tvshow.nfo」
    显示在错误的那一行）。字幕那条还会各写一个无意义的 .chs.nfo。

    字幕也配了完整的 TMDB 匹配: 它现实中确实会有（解析结果与视频相同, 走同一次
    解析）。否则这条用例只在「一个本来就写不出内容的字幕」上有鉴别力。

    变异验证: 去掉 api/renamer.py 预览处的过滤 → 预览断言 FAILED;
    去掉 local_renamer 的过滤 → 盘上多出 .chs.nfo, 执行断言 FAILED。
    """
    from app.api import renamer as renamer_api

    show_dir = tmp_path / "Test Show"
    show_dir.mkdir(parents=True)
    video = show_dir / "Test.Show.S01E02.mkv"
    video.write_bytes(b"")
    subtitle = show_dir / "Test.Show.S01E02.chs.srt"
    subtitle.write_bytes(b"")
    # 扫描器会给字幕打上 is_subtitle=True（local_scanner 的 _build_file_info）
    sub_info = _file("f2", subtitle).model_copy(
        update={"is_subtitle": True, "extension": ".srt"}
    )

    cache_files([_file("f1", video), sub_info])
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    client = TestClient(app)

    payload = {
        "file_ids": ["f1", "f2"],
        "template": TEMPLATE,
        "source": "local",
        "path": "",
        "overrides": {
            "f1": {"show_name": "Test Show", "season": 1, "episode": 2},
            "f2": {"show_name": "Test Show", "season": 1, "episode": 2},
        },
        "generate_nfo": True,
    }

    res = client.post("/api/rename/preview", json=payload)
    assert res.status_code == 200, res.text
    rows = {row["original_filename"]: row for row in res.json()["results"]}

    # 字幕行: 一个落点都没有
    assert rows[subtitle.name]["nfo"] is None
    # 视频行: 三个键俱全 —— 剧集级/季级挂在**视频**上（排序本来会判给字幕）
    assert rows[video.name]["nfo"] == {
        "episode": str(show_dir / "Test Show - S01E02.nfo"),
        "tvshow": str(show_dir / "tvshow.nfo"),
        "season": str(show_dir / "season.nfo"),
    }
    # nfo_scope 是批次级的, 不受这道过滤影响（视频那行有 tvshow 计划 → full）
    assert rows[video.name]["nfo_scope"] == "full"
    assert rows[subtitle.name]["nfo_scope"] == "full"

    res = client.post("/api/rename/execute", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()

    # 字幕旁 0 个 .nfo: 目录里恰好只有该有的三个
    # （sorted 按码位: 'T'(84) < 's'(115), 故 "Test Show - …" 排在最前）
    assert sorted(p.name for p in show_dir.glob("*.nfo")) == [
        "Test Show - S01E02.nfo", "season.nfo", "tvshow.nfo",
    ]
    assert str(show_dir / "Test Show - S01E02.chs.nfo") not in body["nfo_written"]
    # 过滤只作用于 NFO: 字幕照常重命名
    assert sorted(p.name for p in show_dir.glob("*.srt")) == ["Test Show - S01E02.srt"]
    by_name = {row["original_filename"]: row for row in body["results"]}
    assert by_name[subtitle.name]["success"] is True
    assert by_name[subtitle.name]["nfo_path"] is None
    assert by_name[video.name]["nfo_path"] == str(show_dir / "Test Show - S01E02.nfo")


SUB_LANG_TEMPLATE = "{show} - S{season_padded}E{episode_padded}{sub_lang}{extension}"


def test_subtitle_sorted_before_the_video_does_not_take_the_show_level_row(tmp_path, monkeypatch):
    """字幕的新路径排在视频**之前**时, 剧集级决策仍必须落在视频行上。

    上一条用例的模板不含 {sub_lang}: 字幕的新名 "….srt" 排在 "….mkv" **之后**,
    所以「不过滤」在那种排序下也能蒙对 —— 鉴别力不足。这里用含 {sub_lang} 的模板
    把字幕排到前面（".chs" 使分岔点是 '.'='.' 后 'c'(99) < 'm'(109)）,
    这正是错挂真正会发生的那个形态, 也正是 R3-4 报告的排序证据。

    另: 第三个文件用**视频扩展名** .mkv 但 is_subtitle=True, 钉住「判据是
    FileInfo.is_subtitle 而不是嗅扩展名」—— 嗅扩展名的实现会在这里给它写出
    Test Show - S01E03.nfo。

    变异验证: 去掉 api/renamer.py 的过滤 → 预览断言 FAILED;
    去掉 local_renamer 的过滤 → 盘上多出 .chs.nfo → 执行断言 FAILED。
    """
    from app.api import renamer as renamer_api

    show_dir = tmp_path / "Test Show"
    show_dir.mkdir(parents=True)
    video = show_dir / "Test.Show.S01E02.mkv"
    video.write_bytes(b"")
    subtitle = show_dir / "Test.Show.S01E02.chs.srt"
    subtitle.write_bytes(b"")
    # 视频扩展名 + is_subtitle=True: 只有扫描器的判定能区分它
    mislabeled = show_dir / "Test.Show.S01E03.mkv"
    mislabeled.write_bytes(b"")

    sub_info = _file("f2", subtitle).model_copy(
        update={"is_subtitle": True, "extension": ".srt"}
    )
    mislabeled_info = _file("f3", mislabeled).model_copy(update={"is_subtitle": True})

    cache_files([_file("f1", video), sub_info, mislabeled_info])
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    client = TestClient(app)

    payload = {
        "file_ids": ["f1", "f2", "f3"],
        "template": SUB_LANG_TEMPLATE,
        "source": "local",
        "path": "",
        "overrides": {
            "f1": {"show_name": "Test Show", "season": 1, "episode": 2},
            "f2": {"show_name": "Test Show", "season": 1, "episode": 2},
            "f3": {"show_name": "Test Show", "season": 1, "episode": 3},
        },
        "generate_nfo": True,
    }

    # 前提本身也要钉住: 字幕的新路径必须排在视频之前, 否则这条用例测的是别的排序
    # （这正是「检查可能因为前提不成立而永远绿灯」的那类风险）。
    assert str(show_dir / "Test Show - S01E02.chs.srt") < str(show_dir / "Test Show - S01E02.mkv")

    res = client.post("/api/rename/preview", json=payload)
    assert res.status_code == 200, res.text
    rows = {row["original_filename"]: row for row in res.json()["results"]}

    # 排序把字幕放在前面, 但剧集级/季级三个键必须落在**视频**行上
    assert rows[video.name]["nfo"] == {
        "episode": str(show_dir / "Test Show - S01E02.nfo"),
        "tvshow": str(show_dir / "tvshow.nfo"),
        "season": str(show_dir / "season.nfo"),
    }
    assert rows[subtitle.name]["nfo"] is None
    # 视频扩展名 + is_subtitle=True: 一个落点都没有（判据不是扩展名）
    assert rows[mislabeled.name]["nfo"] is None

    res = client.post("/api/rename/execute", json=payload)
    assert res.status_code == 200, res.text
    assert sorted(p.name for p in show_dir.glob("*.nfo")) == [
        "Test Show - S01E02.nfo", "season.nfo", "tvshow.nfo",
    ], "字幕旁 0 个、伪字幕（.mkv + is_subtitle）也 0 个"
    # 两者都照常重命名（过滤只作用于 NFO）
    assert sorted(p.name for p in show_dir.glob("*.srt")) == ["Test Show - S01E02.chs.srt"]
    assert (show_dir / "Test Show - S01E03.mkv").is_file()


def test_preview_reports_no_nfo_plan_for_a_batch_without_videos(tmp_path, monkeypatch):
    """0 个视频条目时不得报 full / episode_only —— 那是从 0 行推出的事实。

    路由的 `all(...)` 判据原本直接在 `plans` 上跑: 空集上恒为 True, 所以
    `file_ids: []` 会算出 nfo_scope = "full"（那个分支连响应都进不去 ——
    results 为空, 没有行承载它; 真正能观察到的是**纯字幕批次**: plans 非空、
    video_ids 为空, 一个 NFO 都不会写, 却会走到 all(...) 的 else 报出
    "episode_only"）。修好后如实报 disabled。

    变异验证: 去掉 renamer.py 里 video_plans 的非空守卫（恢复在 plans 上 all）
    → 本用例 FAILED（row["nfo_scope"] == "episode_only"）。
    """
    from app.api import renamer as renamer_api

    show_dir = tmp_path / "Test Show"
    show_dir.mkdir(parents=True)
    subtitle = show_dir / "Test.Show.S01E02.chs.srt"
    subtitle.write_bytes(b"")
    sub_info = _file("f1", subtitle).model_copy(
        update={"is_subtitle": True, "extension": ".srt"}
    )

    cache_files([sub_info])
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    client = TestClient(app)

    res = client.post("/api/rename/preview", json=payload(
        file_ids=["f1"], generate_nfo=True,
    ))
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    assert row["nfo"] is None, "字幕不进 NFO 管线, 一行落点都没有"
    assert row["nfo_scope"] == "disabled"

    # 同一个批次的执行侧: 一个 NFO 文件都不该出现（判据一致性）
    res = client.post("/api/rename/execute", json=payload(
        file_ids=["f1"], generate_nfo=True,
    ))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["nfo_written"] == [] and body["nfo_skipped"] == []
    assert list(tmp_path.rglob("*.nfo")) == []
