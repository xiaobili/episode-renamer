"""STRM 的路由契约：预览落点、执行写盘、干跑不写、本地源拒绝。"""
import os

import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.core.strm import MISSING_LOCAL_ROOT, NOT_LANDED_STRM_REASON
from app.main import app
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
BASE = "http://ol:5244"
OVERRIDE = {"show_name": "Test Show", "season": 1, "episode": 2}


class _FakeOpenListClient:
    """记录调用的远端替身。connected 为真, 否则路由会先 401。"""

    connected = True
    server_url = BASE

    def __init__(self, fail_rename=False):
        self.calls: list = []
        self.fail_rename = fail_rename

    def apply_limits(self, max_concurrent=None, request_interval=None):
        pass

    async def rename(self, path, new_name):
        self.calls.append(("rename", path, new_name))
        if self.fail_rename:
            raise Exception("permission denied")
        return {"code": 200}

    async def move(self, src_dir, dst_dir, names):
        self.calls.append(("move", src_dir, dst_dir, tuple(names)))
        return {"code": 200}

    async def mkdir(self, parent_dir, dir_name):
        self.calls.append(("mkdir", parent_dir, dir_name))
        return {"code": 200}

    async def put_file(self, path, content):
        self.calls.append(("put", path, content))
        return {"code": 200}

    def puts(self):
        return [call for call in self.calls if call[0] == "put"]


def _video(name="Test.Show.S01E02.mkv", parent="/115/Test Show"):
    return FileInfo(
        id="f1", source="openlist", path=f"{parent}/{name}", filename=name,
        extension=".mkv", parent_dir=parent,
    )


def _subtitle(parent="/115/Test Show"):
    return FileInfo(
        id="s1", source="openlist",
        path=f"{parent}/Test.Show.S01E02.chs.srt",
        filename="Test.Show.S01E02.chs.srt", extension=".srt", parent_dir=parent,
        is_subtitle=True, subtitle_of="Test.Show.S01E02.mkv",
    )


@pytest.fixture
def client():
    cache_files([_video()])
    return TestClient(app)


def _common(**extra):
    body = {
        "template": TEMPLATE,
        "source": "openlist",
        "path": "/115",
        "generate_strm": True,
        "strm_mode": "remote_same",
        "strm_base_url": BASE,
    }
    body.update(extra)
    return body


def test_local_source_rejects_strm(client):
    res = client.post("/api/rename/preview", json={
        "file_ids": ["f1"], "template": TEMPLATE, "source": "local",
        "generate_strm": True,
    })
    assert res.status_code == 400
    assert "STRM" in res.json()["detail"]


def test_preview_plans_strm_landing(client):
    res = client.post("/api/rename/preview", json={
        **_common(), "file_ids": ["f1"], "overrides": {"f1": OVERRIDE},
    })
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    assert row["strm"] == {
        "mode": "remote_same",
        "path": "/115/Test Show/Test Show - S01E02.strm",
        "url": f"{BASE}/d/115/Test Show/Test Show - S01E02.mkv",
    }


def test_preview_remote_custom_includes_show_dir(client):
    # 预览与执行共用 strm_target_for_plan —— 这条钉住「预览里看到的剧名目录」
    # 就是执行时会建出来的那层。
    res = client.post("/api/rename/preview", json={
        **_common(
            strm_mode="remote_custom", strm_remote_root="/strm",
            strm_scan_root="/115/Test Show",
        ),
        "file_ids": ["f1"], "overrides": {"f1": OVERRIDE},
    })
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["strm"] == {
        "mode": "remote_custom",
        "path": "/strm/Test Show/Test Show - S01E02.strm",
        "url": f"{BASE}/d/115/Test Show/Test Show - S01E02.mkv",
    }


def test_preview_has_no_strm_when_disabled(client):
    res = client.post("/api/rename/preview", json={
        **_common(generate_strm=False), "file_ids": ["f1"], "overrides": {"f1": OVERRIDE},
    })
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["strm"] is None


def test_execute_writes_local_strm(tmp_path, monkeypatch, client):
    import app.api.renamer as renamer_mod

    # 源是 openlist, 执行路径先天要求已连接 —— 本地落盘只是 strm 的落点,
    # 视频本身仍在远端。
    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    target_root = tmp_path / "strm"
    res = client.post("/api/rename/execute", json={
        **_common(strm_mode="local", strm_local_root=str(target_root)),
        "file_id": "f1", "override": OVERRIDE,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    expected = str(target_root / "Test Show" / "Test Show - S01E02.strm")
    assert body["strm_written"] == [expected]
    assert body["strm_skipped"] == []
    with open(expected, "rb") as handle:
        assert handle.read() == (
            f"{BASE}/d/115/Test Show/Test Show - S01E02.mkv\n"
        ).encode()


def test_execute_writes_remote_strm_same_dir(monkeypatch, client):
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    body = client.post("/api/rename/execute", json={
        **_common(), "file_id": "f1", "override": OVERRIDE,
    }).json()

    expected = "/115/Test Show/Test Show - S01E02.strm"
    assert body["strm_written"] == [expected], body
    assert fake.puts() == [(
        "put", expected,
        f"{BASE}/d/115/Test Show/Test Show - S01E02.mkv\n".encode(),
    )]


def test_execute_remote_custom_creates_dirs(monkeypatch, client):
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    body = client.post("/api/rename/execute", json={
        **_common(strm_mode="remote_custom", strm_remote_root="/strm"),
        "file_id": "f1", "override": OVERRIDE,
    }).json()

    assert body["strm_written"] == ["/strm/Test Show/Test Show - S01E02.strm"]
    assert ("mkdir", "/", "strm") in fake.calls
    assert ("mkdir", "/strm", "Test Show") in fake.calls


def test_execute_remote_custom_creates_show_dir_when_root_is_show_dir(
    monkeypatch, client,
):
    """一次只扫一部剧（strm_scan_root = 剧目录）时, 仍必须建出剧集名目录。"""
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    body = client.post("/api/rename/execute", json={
        **_common(
            strm_mode="remote_custom", strm_remote_root="/strm",
            strm_scan_root="/115/Test Show",
        ),
        "file_id": "f1", "override": OVERRIDE,
    }).json()

    assert body["strm_written"] == ["/strm/Test Show/Test Show - S01E02.strm"]
    assert ("mkdir", "/strm", "Test Show") in fake.calls


def test_dry_run_reports_plan_without_writing(monkeypatch, client):
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    body = client.post("/api/rename/dry-run", json={
        **_common(), "file_ids": ["f1"], "overrides": {"f1": OVERRIDE},
    }).json()

    assert body["strm_written"] == ["/115/Test Show/Test Show - S01E02.strm"]
    assert fake.puts() == []


def test_subtitle_gets_no_strm(monkeypatch):
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)
    cache_files([_subtitle()])

    body = TestClient(app).post("/api/rename/execute", json={
        **_common(), "file_id": "s1",
        "override": {"show_name": "Test Show", "season": 1, "episode": 2},
    }).json()

    assert body["strm_written"] == []
    assert body["strm_skipped"] == []
    assert fake.puts() == []


def test_unlanded_video_reports_reason(monkeypatch, client):
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient(fail_rename=True)
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    body = client.post("/api/rename/execute", json={
        **_common(), "file_id": "f1", "override": OVERRIDE,
    }).json()

    assert body["result"]["status"] == "failed"
    assert body["strm_written"] == []
    assert body["strm_skipped"] == [{
        "path": "/115/Test Show/Test Show - S01E02.mkv",
        "reason": NOT_LANDED_STRM_REASON,
    }]


def test_missing_local_root_reports_reason(monkeypatch, client):
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    body = client.post("/api/rename/execute", json={
        **_common(strm_mode="local", strm_local_root=""),
        "file_id": "f1", "override": OVERRIDE,
    }).json()

    assert body["strm_written"] == []
    assert body["strm_skipped"] == [{
        "path": "/115/Test Show/Test Show - S01E02.mkv",
        "reason": MISSING_LOCAL_ROOT,
    }]


def test_base_url_falls_back_to_connected_server(monkeypatch, client):
    """对外地址留空时用客户端地址 —— 否则每个用户都得重复填一遍。"""
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    body = client.post("/api/rename/execute", json={
        **_common(strm_base_url=""), "file_id": "f1", "override": OVERRIDE,
    }).json()

    assert body["strm_written"] == ["/115/Test Show/Test Show - S01E02.strm"]
    assert fake.puts()[0][2].startswith(f"{BASE}/d/".encode())
