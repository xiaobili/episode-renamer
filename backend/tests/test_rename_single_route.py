"""单文件执行路由的契约判据。"""
import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
OVERRIDE = {"show_name": "Test Show", "season": 1, "episode": 2}


@pytest.fixture
def client():
    cache_files([
        FileInfo(
            id="f1", source="local",
            path="/media/Test Show/Test.Show.S01E02.mkv",
            filename="Test.Show.S01E02.mkv", extension=".mkv",
            parent_dir="/media/Test Show",
        )
    ])
    return TestClient(app)


def payload(**extra):
    body = {
        "file_id": "f1",
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "override": OVERRIDE,
        "conflict_strategy": "skip",
    }
    body.update(extra)
    return body


def test_contract_uses_singular_file_id(client):
    """契约是单数 —— 传 file_ids 必须被 Pydantic 拒绝（多的字段不静默吞掉）。"""
    res = client.post("/api/rename/execute", json={
        "file_ids": ["f1"], "template": TEMPLATE, "source": "local",
    })
    assert res.status_code == 422, res.text


def test_singular_override_reaches_the_plan(client):
    """override 必须真的进 plan —— 丢掉它会让文件名少一集/少一季且零报错。

    **用一份与文件名解析结果不同的 override**: 文件名 Test.Show.S01E02.mkv 解析出
    (Test Show, 1, 2), override 把它改成 (Other Show, 5, 9)。文件名随之变成
    Other Show - S05E09.mkv —— 只有 override 真的传到了 plan 才会这样。

    两个 pad 字段**都不传**: 免得把补零也搅进来（那会让本判据分不清是 override
    丢了还是 pad 算错了, 而补零已有自己的判据）。
    """
    res = client.post("/api/rename/execute", json=payload(
        override={"show_name": "Other Show", "season": 5, "episode": 9},
    ))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["file_id"] == "f1"
    assert body["result"]["new_filename"] == "Other Show - S05E09.mkv"
    assert body["result"]["new_path"] == "/media/Test Show/Other Show - S05E09.mkv"


def test_missing_source_file_counts_as_failed(client):
    """fixture 的源文件不在磁盘上 —— 如实报 failed, 且计数为 1。"""
    body = client.post("/api/rename/execute", json=payload()).json()
    assert body["result"]["success"] is False
    assert body["result"]["status"] == "failed"
    assert body["failed"] == 1
    assert body["executed"] == 0
    assert body["skipped"] == 0


def test_unknown_file_id_is_rejected(client):
    res = client.post("/api/rename/execute", json=payload(file_id="nope"))
    assert res.status_code == 400
    assert "未找到" in res.json()["detail"]


class _FakeOpenListClient:
    """OpenList 执行路径的最小替身。"""

    connected = True

    def __init__(self):
        self.calls: list = []

    def apply_limits(self, max_concurrent=None, request_interval=None):
        pass

    async def rename(self, path, new_name):
        self.calls.append(("rename", path, new_name))
        return {"code": 200}

    async def move(self, src_dir, dst_dir, names):
        self.calls.append(("move", src_dir, dst_dir, tuple(names)))
        return {"code": 200}

    async def mkdir(self, parent_dir, dir_name):
        self.calls.append(("mkdir", parent_dir, dir_name))
        return {"code": 200}


def test_openlist_execute_agrees_with_preview_on_the_target_path(monkeypatch):
    """OpenList 的**执行**目标必须与**预览**逐字一致。

    两个 builder **不等价**: build_rename_plan 在父目录已是季目录时会抑制建季目录
    （local_renamer._parent_is_season_dir）, build_openlist_rename_plan 不会。
    执行分支若借道 plan_files, 同一份输入下预览报一个落点、执行做另一个 ——
    「预览说一套、执行做另一套」, 本仓库最忌讳的一类。把 openlist 分支改回
    plan_files 本用例必红。

    这也是 OpenList **执行**路由的第一条判据（此前一条都没有）。
    """
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    # 父目录**本身**就是季目录 → 两个 builder 在这里分道扬镳
    cache_files([FileInfo(
        id="f1", source="openlist",
        path="/media/Show/Season 02/Show.S02E03.mkv",
        filename="Show.S02E03.mkv", extension=".mkv",
        parent_dir="/media/Show/Season 02",
    )])
    client = TestClient(app)
    common = {
        "template": TEMPLATE,
        # **故意发大写**: 单文件响应里的 source 必须与批量路径一样是**规范化后**
        # 的 "openlist"（批量路径在 BatchRenameResult 里硬编码小写）。直接透传
        # req.source 时本断言红 —— 那是这条字段唯一的判据。
        "source": "OpenList",
        "path": "/media/Show/Season 02",
        "folder_template": "Season {season_padded}",
        "create_season_folder": True,
    }
    override = {"show_name": "Show", "season": 2, "episode": 3}

    preview = client.post("/api/rename/preview", json={
        **common, "file_ids": ["f1"], "overrides": {"f1": override},
    })
    assert preview.status_code == 200, preview.text
    expected = preview.json()["results"][0]["new_path"]

    executed = client.post("/api/rename/execute", json={
        **common, "file_id": "f1", "override": override,
    })
    assert executed.status_code == 200, executed.text
    assert executed.json()["result"]["new_path"] == expected, (
        "执行落点与预览不一致 —— 两个 builder 被混用了"
    )
    assert executed.json()["source"] == "openlist", "响应里的 source 必须是规范化后的小写"


def test_generate_nfo_flag_controls_the_episode_decision(tmp_path):
    """generate_nfo=False 时**不该**产生任何每集 NFO 决策; 开了就必须有。

    判据用 `result.nfo_path`: None 表示「这条路径根本没进 NFO 管线」。

    夹具必须让文件**真的改名成功**: 源文件不存在时那一行本来就是 `failed`、
    本来就不写 NFO, 断言 `nfo_written == []` 近乎恒真 —— 实测把 `generate_nfo`
    恒置 True 时六条判据全绿, 即原来那条对「忽略开关」这个变异是失明的。

    两个方向各跑一个目录: 第一次 execute 会把文件改名, 同一目录再跑第二次就
    找不到源文件了。
    """
    def _run(dir_name, generate_nfo):
        d = tmp_path / dir_name
        d.mkdir()
        video = d / "Test.Show.S01E02.mkv"
        video.write_text("x", encoding="utf-8")
        cache_files([FileInfo(
            id="f1", source="local", path=str(video),
            filename="Test.Show.S01E02.mkv", extension=".mkv",
            parent_dir=str(d),
        )])
        return TestClient(app).post("/api/rename/execute", json={
            "file_id": "f1", "template": TEMPLATE, "source": "local",
            "path": str(d), "override": OVERRIDE, "conflict_strategy": "skip",
            "generate_nfo": generate_nfo,
        }).json()

    off = _run("off", False)
    assert off["result"]["status"] == "renamed", off["result"]
    assert off["result"]["nfo_path"] is None
    assert off["nfo_written"] == []

    # 对照: 开了就必须有决策。未配 TMDB → 内容为 None、写不出文件, 但**落点在**。
    # 少了这一半, 「忽略 generate_nfo」的变异不会红。
    on = _run("on", True)
    assert on["result"]["status"] == "renamed", on["result"]
    assert on["result"]["nfo_path"] is not None


def test_abort_marks_the_file_as_conflict(tmp_path):
    """abort 在单文件下是「这一个文件不执行」, 不是「整批中止」。

    计数沿用既有归法: abort 下的冲突行计入 **failed** 而非 skipped（batch_rename
    里那段注释写明了这点）。这条判据钉住 execute_one 里**合成冲突结果**那条分支 ——
    Task 2 结束时它还没有任何判据（夹具里没有冲突文件、也没有 abort 用例）。
    把 `aborted` 判断删掉（让它照常走 execute_rename_plan）本用例必红: 那时
    conflict_strategy="abort" 仍会给出 status="conflict", 但计数会落到 skipped。
    """
    video = tmp_path / "Test.Show.S01E02.mkv"
    video.write_text("x", encoding="utf-8")
    # 目标名已被占住 → 触发冲突
    (tmp_path / "Test Show - S01E02.mkv").write_text("occupied", encoding="utf-8")
    cache_files([FileInfo(
        id="f1", source="local", path=str(video),
        filename="Test.Show.S01E02.mkv", extension=".mkv",
        parent_dir=str(tmp_path),
    )])

    res = TestClient(app).post("/api/rename/execute", json={
        "file_id": "f1", "template": TEMPLATE, "source": "local",
        "path": str(tmp_path), "override": OVERRIDE,
        "conflict_strategy": "abort", "generate_nfo": True,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["result"]["status"] == "conflict"
    assert body["failed"] == 1
    assert body["skipped"] == 0
    assert body["nfo_written"] == []


def test_landed_path_is_the_real_landing_for_a_video(tmp_path):
    """落地文件必须在响应里给出**真实落点** —— 前端拿它构造 finalize 的 landed 表。

    前端不再自己按 result.status 判落地（那份判据会与 _NO_LANDING_STATUSES 漂移,
    见 workspace.js 的注释）, 所以这个字段是 /rename/finalize 不变量**唯一**的数据
    来源: 它为空 → 组级 NFO 一份都不写; 它错了 → 写到错误的位置上。
    """
    video = tmp_path / "Test.Show.S01E02.mkv"
    video.write_text("x", encoding="utf-8")
    cache_files([FileInfo(
        id="f1", source="local", path=str(video),
        filename="Test.Show.S01E02.mkv", extension=".mkv",
        parent_dir=str(tmp_path),
    )])

    body = TestClient(app).post("/api/rename/execute", json={
        "file_id": "f1", "template": TEMPLATE, "source": "local",
        "path": str(tmp_path), "override": OVERRIDE, "generate_nfo": True,
    }).json()

    assert body["result"]["status"] == "renamed", body["result"]
    assert body["landed_path"] == str(tmp_path / "Test Show - S01E02.mkv"), body["landed_path"]
    assert body["landed_path"] == body["result"]["new_path"]
    assert (tmp_path / "Test Show - S01E02.mkv").exists()


def test_landed_path_is_none_for_a_subtitle(tmp_path):
    """字幕**不算落地** —— 即便它自己改名成功。

    这是 F2 那条缺陷的后端一半: 字幕与视频共用同一套 status, 前端按 status 判落地
    时字幕会进 landed 表, 而 finalize 的 `_keep_decision` 只看「那个目录里有没有
    landed 路径」。混合批次里「视频失败、字幕落地」于是会把组级决策保留下来, 在
    一个没有任何剧集文件的目录里写出 tvshow.nfo（spec §9.4 的库根污染）。
    `execute_one` 里 `if is_video:` 那道守卫就是阻止它的地方。

    删掉那道守卫本用例必红（landed_path 会变成字幕的新路径）。**前端的判据抓不到
    这一点**: 它用的是假 adapter, 夹具里的 landed_path 由夹具自己写死。
    """
    video = tmp_path / "Test.Show.S01E02.mkv"
    sub = tmp_path / "Test.Show.S01E02.chs.ass"
    video.write_text("x", encoding="utf-8")
    sub.write_text("x", encoding="utf-8")
    cache_files([FileInfo(
        id="s1", source="local", path=str(sub),
        filename="Test.Show.S01E02.chs.ass", extension=".ass",
        parent_dir=str(tmp_path), is_subtitle=True,
        subtitle_of="Test.Show.S01E02.mkv",
    )])

    body = TestClient(app).post("/api/rename/execute", json={
        "file_id": "s1", "template": TEMPLATE, "source": "local",
        "path": str(tmp_path), "override": OVERRIDE,
    }).json()

    # 字幕本身确实改名成功了 —— 判据不是「它没落地」, 而是「它的落地**不算**
    # 组级 NFO 的依据」。
    assert body["result"]["status"] == "renamed", body["result"]
    assert body["landed_path"] is None, body["landed_path"]
    # 对照: 同一个响应的 new_path 仍如实报告它去了哪里（前端在别处要用）。
    assert body["result"]["new_path"] == str(tmp_path / "Test Show - S01E02.ass")
