"""`/api/rename/batch-execute` 的契约判据。

这个接口的形状有两处是本仓库的硬约束, 两条都在这里钉住:
  · **一次请求跑完整批** —— 不是「N 次请求少一点往返」, 而是批次级事实（并发、
    顺序、landed）不再由调用方拥有;
  · **SSE 逐帧回传** —— 前端单请求但进度条不能退化成转圈, 帧序列是它唯一的来源。
"""
import json
import posixpath

import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"

FILES = [
    FileInfo(
        id=f"f{i}", source="openlist",
        path=f"/media/Show/Show.S01E0{i}.mkv",
        filename=f"Show.S01E0{i}.mkv", extension=".mkv",
        parent_dir="/media/Show",
    )
    for i in (1, 2, 3)
]


class FakeOpenListClient:
    """够用的 OpenList 替身：记录调用序列，可指定某个文件改名失败。"""

    connected = True
    server_url = "http://ol:5244"
    max_concurrent = 2

    def __init__(self, fail_names: set[str] | None = None):
        self.calls: list[tuple] = []
        self.fail_names = fail_names or set()
        self.limits: dict = {}

    def apply_limits(self, max_concurrent=None, request_interval=None):
        self.limits = {
            "max_concurrent": max_concurrent,
            "request_interval": request_interval,
        }

    async def rename(self, path, new_name):
        name = posixpath.basename(path)
        if name in self.fail_names:
            raise Exception("重命名失败")
        self.calls.append(("rename", path, new_name))
        return {"code": 200}

    async def move(self, src_dir, dst_dir, names):
        self.calls.append(("move", src_dir, dst_dir, tuple(names)))
        return {"code": 200}

    async def mkdir(self, parent_dir, dir_name):
        self.calls.append(("mkdir", parent_dir, dir_name))
        return {"code": 200}

    async def list_directory(self, path, refresh=False):
        return [], True

    async def put_file(self, path, content):
        self.calls.append(("put_file", path))
        return {"code": 200}


@pytest.fixture
def fake(monkeypatch):
    import app.api.renamer as renamer_mod

    client = FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: client)
    cache_files(FILES)
    return client


def payload(**extra):
    body = {
        "file_ids": ["f1", "f2", "f3"],
        "template": TEMPLATE,
        "source": "openlist",
        "path": "/media/Show",
        "overrides": {},
    }
    body.update(extra)
    return body


def events(response) -> list[dict]:
    """把 SSE 响应体拆成事件列表。

    只认 `data:` 行: 服务端不额外发 `event:` 行（类型在 JSON 的 `type` 里）,
    解析端也就不该有两套分派。
    """
    out = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[len("data: "):]))
    return out


def run_batch(client: TestClient, **extra):
    res = client.post("/api/rename/batch-execute", json=payload(**extra))
    assert res.status_code == 200, res.text
    return events(res)


def test_rejects_local_source(fake):
    """本地源走逐文件接口 —— 语义不同, 不在这个接口里偷偷兼容。"""
    res = TestClient(app).post(
        "/api/rename/batch-execute", json=payload(source="local"),
    )
    assert res.status_code == 400
    assert "仅支持 OpenList" in res.json()["detail"]


def test_requires_connection(fake):
    fake.connected = False
    res = TestClient(app).post("/api/rename/batch-execute", json=payload())
    assert res.status_code == 401
    assert "请先连接 OpenList" in res.json()["detail"]


def test_unknown_file_id_rejects_the_batch(fake):
    """静默跳过缺 id 会让 total 与实际行数对不上, 用户只看到「少了一集」。"""
    res = TestClient(app).post(
        "/api/rename/batch-execute", json=payload(file_ids=["f1", "nope"]),
    )
    assert res.status_code == 400
    assert "未找到" in res.json()["detail"]


def test_single_request_renames_the_whole_batch_and_reports_progress(fake):
    """一次 POST 跑完 3 个文件: start → progress×3 → result。"""
    res = TestClient(app).post("/api/rename/batch-execute", json=payload())
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    frames = events(res)
    assert frames[0]["type"] == "start" and frames[0]["total"] == 3
    progress = [f for f in frames if f["type"] == "progress"]
    assert [f["done"] for f in progress] == [1, 2, 3]
    assert all(f["total"] == 3 for f in progress)
    assert frames[-1]["type"] == "result"

    result = frames[-1]["result"]
    assert result["source"] == "openlist"
    assert result["total"] == 3
    assert result["executed"] == 3
    assert result["failed"] == 0
    assert result["success"] is True
    # 结果顺序 = 请求里的 file_ids 顺序（表格按行对回去的唯一根据）
    assert [row["original_filename"] for row in result["results"]] == [
        "Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E03.mkv",
    ]
    # 每个文件都真的改了名 —— 不是「接口跑通但什么都没做」
    assert len([c for c in fake.calls if c[0] == "rename"]) == 3


def test_duplicate_file_ids_are_renamed_once(fake):
    """同一个 id 传两遍不能让文件被改两次名（第二次必然失败）。"""
    frames = run_batch(TestClient(app), file_ids=["f1", "f1"])
    result = frames[-1]["result"]
    assert result["total"] == 1
    assert len([c for c in fake.calls if c[0] == "rename"]) == 1


def test_one_bad_file_does_not_fail_the_batch(fake):
    """单个文件失败只占自己那一行, 其余照旧, 且响应仍是一次完整的 result。"""
    fake.fail_names = {"Show.S01E02.mkv"}
    result = run_batch(TestClient(app))[-1]["result"]

    assert result["executed"] == 2
    assert result["failed"] == 1
    assert result["results"][1]["status"] == "failed"
    assert "重命名失败" in result["results"][1]["error"]


def test_limits_from_the_request_reach_the_client(fake):
    """设置页的限流值必须真的落到客户端上（死设置是本仓库的前科）。"""
    run_batch(
        TestClient(app),
        openlist_max_concurrent=5,
        openlist_request_interval=0.25,
    )
    assert fake.limits == {"max_concurrent": 5, "request_interval": 0.25}


def test_finalize_runs_after_every_file_with_real_landed_paths(fake, monkeypatch):
    """剧集级 NFO 的收尾在全部文件之后, 且 landed 是**真实落点**。"""
    import app.api.renamer as renamer_mod

    order: list[tuple] = []
    captured: dict = {}

    async def fake_finalize(client, plans, landed_paths, matches, options):
        order.append(("finalize",))
        captured["landed"] = list(landed_paths)
        captured["plans"] = [p.original_filename for p in plans]
        return ["/media/Show/tvshow.nfo"], []

    real_rename = fake.rename

    async def rename(path, new_name):
        order.append(("rename",))
        return await real_rename(path, new_name)

    fake.rename = rename
    monkeypatch.setattr(renamer_mod, "finalize_openlist_nfo", fake_finalize)

    result = run_batch(TestClient(app), generate_nfo=True)[-1]["result"]

    assert [step[0] for step in order] == ["rename", "rename", "rename", "finalize"]
    assert captured["plans"] == [
        "Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E03.mkv",
    ]
    # 三个文件都落地了, landed 就是它们的目标路径（不是原路径、不是空）
    assert captured["landed"] == [
        f"/media/Show/Show - S01E0{i}.mkv" for i in (1, 2, 3)
    ]
    assert result["nfo_written"] == ["/media/Show/tvshow.nfo"]
    assert result["nfo_error"] is None


def test_finalize_failure_is_non_fatal(fake, monkeypatch):
    """收尾炸了不得吞掉已经完成的重命名结果。"""
    import app.api.renamer as renamer_mod

    async def boom(*args, **kwargs):
        raise RuntimeError("收尾炸了")

    monkeypatch.setattr(renamer_mod, "finalize_openlist_nfo", boom)

    result = run_batch(TestClient(app), generate_nfo=True)[-1]["result"]

    assert result["executed"] == 3
    assert result["failed"] == 0
    assert result["nfo_error"] == "收尾炸了"
    assert result["nfo_written"] == []


def test_folders_rename_runs_after_finalize(fake, monkeypatch):
    """目录改名必须排在 NFO 收尾之后 —— 反过来会在旧名下重建目录。"""
    import app.api.renamer as renamer_mod

    order: list[str] = []

    async def fake_finalize(*args, **kwargs):
        order.append("finalize")
        return [], []

    async def fake_folders(client, folder_plans):
        order.append("folders")
        assert folder_plans, "目录计划不该是空的（勾了改名就必须算）"
        return [], [{"path": "/media/Show", "reason": "未匹配 TMDB"}]

    monkeypatch.setattr(renamer_mod, "finalize_openlist_nfo", fake_finalize)
    monkeypatch.setattr(renamer_mod, "apply_openlist_show_folders", fake_folders)

    result = run_batch(
        TestClient(app), generate_nfo=True, rename_folders=True,
    )[-1]["result"]

    assert order == ["finalize", "folders"]
    assert result["folders_error"] is None
    assert result["folders_skipped"] == [{"path": "/media/Show", "reason": "未匹配 TMDB"}]


def test_folders_run_even_without_nfo(fake, monkeypatch):
    """目录改名与 NFO 开关无关 —— 没勾 NFO 时它照样要跑。"""
    import app.api.renamer as renamer_mod

    called: list[int] = []

    async def fake_folders(client, folder_plans):
        called.append(len(folder_plans))
        return [], []

    monkeypatch.setattr(renamer_mod, "apply_openlist_show_folders", fake_folders)

    run_batch(TestClient(app), rename_folders=True)
    assert called, "没勾 NFO 时目录改名被跳过了"
