"""剧集文件夹重命名的路由契约：预览可见、干跑列出、接口真改。"""
import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.core.show_folder import (
    ALREADY_NAMED_REASON,
    NO_TMDB_REASON,
    TARGET_EXISTS_REASON,
)
from app.main import app
from app.models.file import FileInfo
from app.models.tmdb import TmdbEpisode, TmdbSearchItem, TmdbSeason, TmdbShow

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
SHOW_NAME = "绝命毒师"
TARGET_NAME = "绝命毒师 (2008) [tmdbid-1396]"

OVERRIDES = {
    "f1": {"show_name": SHOW_NAME, "season": 1, "episode": 1},
    "f2": {"show_name": SHOW_NAME, "season": 1, "episode": 2},
}


def _file(file_id, video):
    return FileInfo(
        id=file_id,
        source="local",
        path=str(video),
        filename=video.name,
        extension=".mkv",
        parent_dir=str(video.parent),
    )


class _FakeTmdbClient:
    """离线替身：任意剧名都匹配到同一部剧, 第 1 季含第 1、2 集。"""

    language = "zh-CN"

    def cache_fingerprint(self):
        return "show-folder-fake"

    async def search_tv(self, query, year=None):
        return [TmdbSearchItem(tv_id=1396, name=query, original_name=query, year=2008)]

    async def get_tv_detail(self, tv_id):
        return TmdbShow(tv_id=tv_id, name=SHOW_NAME, original_name="Breaking Bad", year=2008)

    async def get_season(self, tv_id, season_number):
        return TmdbSeason(season_number=season_number, tmdb_id=3575, episodes={
            1: TmdbEpisode(episode_number=1, name="Pilot", tmdb_id=62084),
            2: TmdbEpisode(episode_number=2, name="Cat's in the Bag", tmdb_id=62085),
        })


@pytest.fixture
def show_dir(tmp_path):
    """`绝命毒师/Season 01/` 两集 —— 带季子目录的真实布局。"""
    season_dir = tmp_path / SHOW_NAME / "Season 01"
    season_dir.mkdir(parents=True)
    for episode in (1, 2):
        (season_dir / f"Breaking.Bad.S01E0{episode}.mkv").write_bytes(b"")
    return tmp_path


@pytest.fixture
def client(show_dir, monkeypatch):
    from app.api import renamer as renamer_api

    season_dir = show_dir / SHOW_NAME / "Season 01"
    cache_files([
        _file("f1", season_dir / "Breaking.Bad.S01E01.mkv"),
        _file("f2", season_dir / "Breaking.Bad.S01E02.mkv"),
    ])
    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    return TestClient(app)


def payload(**extra):
    data = {
        "file_ids": ["f1", "f2"],
        "template": TEMPLATE,
        "source": "local",
        "path": str(""),
        "overrides": OVERRIDES,
        "conflict_strategy": "skip",
        "rename_folders": True,
    }
    data.update(extra)
    return data


# --- 预览 ------------------------------------------------------------------

def test_preview_shows_the_target_folder_for_every_row(client):
    res = client.post("/api/rename/preview", json=payload())
    assert res.status_code == 200, res.text
    body = res.json()

    for row in body["results"]:
        # 同一部剧的两行看到同一个目标目录 —— 折叠由 show_root 决定, 不是按行各算一遍
        assert set(row["folder"]) == {"path", "new_path"}
        assert row["folder"]["new_path"].endswith(TARGET_NAME)
        # 季目录不能被当成剧目录: 目标是 …/绝命毒师 (2008) […], 不是 …/Season 01 (2008) […]
        assert "/Season 01" not in row["folder"]["new_path"]


def test_preview_omits_folder_when_not_requested(client):
    res = client.post("/api/rename/preview", json=payload(rename_folders=False))
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["folder"] is None


def test_preview_reports_why_the_folder_will_not_be_renamed(show_dir, monkeypatch):
    """未配 TMDB 时, 预览必须给出**原因**而不是静默的 null。"""
    from app.api import renamer as renamer_api

    season_dir = show_dir / SHOW_NAME / "Season 01"
    cache_files([_file("f1", season_dir / "Breaking.Bad.S01E01.mkv")])
    monkeypatch.setattr(renamer_api, "_tmdb_client_from_request", lambda req: None)

    res = TestClient(app).post("/api/rename/preview", json=payload(file_ids=["f1"]))
    assert res.status_code == 200, res.text

    folder = res.json()["results"][0]["folder"]
    assert folder["new_path"] is None
    assert folder["reason"] == NO_TMDB_REASON


# --- 干跑 ------------------------------------------------------------------

def test_dry_run_lists_the_planned_folder_rename(client, show_dir):
    res = client.post("/api/rename/dry-run", json=payload())
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["folders_renamed"] == [{
        "old_path": str(show_dir / SHOW_NAME),
        "new_path": str(show_dir / TARGET_NAME),
        "show_name": SHOW_NAME,
    }]
    assert body["folders_skipped"] == []


def test_dry_run_does_not_touch_the_disk(client, show_dir):
    client.post("/api/rename/dry-run", json=payload())
    assert (show_dir / SHOW_NAME).is_dir()
    assert not (show_dir / TARGET_NAME).exists()


# --- 执行 ------------------------------------------------------------------

def test_folders_route_renames_the_directory_tree(client, show_dir):
    res = client.post("/api/rename/folders", json=payload())
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["success"] is True
    assert body["renamed"] == [{
        "old_path": str(show_dir / SHOW_NAME),
        "new_path": str(show_dir / TARGET_NAME),
        "show_name": SHOW_NAME,
    }]
    assert body["skipped"] == []
    # 季子目录与文件跟着父目录一起走
    assert (show_dir / TARGET_NAME / "Season 01" / "Breaking.Bad.S01E01.mkv").exists()
    assert not (show_dir / SHOW_NAME).exists()


def test_folders_route_is_idempotent(client, show_dir):
    """改完之后再跑一次：不能报错, 也不能把目录再套一层。"""
    client.post("/api/rename/folders", json=payload())
    res = client.post("/api/rename/folders", json=payload())

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["renamed"] == []
    assert body["skipped"][0]["reason"] == ALREADY_NAMED_REASON
    assert (show_dir / TARGET_NAME).is_dir()
    assert not (show_dir / f"{TARGET_NAME}_1").exists()


def test_folders_route_refuses_when_target_exists(client, show_dir):
    (show_dir / TARGET_NAME).mkdir()

    res = client.post("/api/rename/folders", json=payload())
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["renamed"] == []
    assert body["skipped"][0]["reason"] == TARGET_EXISTS_REASON
    assert (show_dir / SHOW_NAME).is_dir(), "源目录不得被动过"


def test_folders_route_requires_known_files(client):
    res = client.post("/api/rename/folders", json=payload(file_ids=["nope"]))
    assert res.status_code == 400, res.text
    assert "未找到" in res.json()["detail"]


class _FakeOpenListClient:
    connected = True

    def __init__(self, names):
        self._names = list(names)
        self.renamed = []
        self.listed = []

    def apply_limits(self, max_concurrent=None, request_interval=None):
        pass

    async def list_directory(self, path, refresh=False):
        self.listed.append(path)
        from app.models.openlist import OpenListFile
        return [OpenListFile(name=n, is_dir=True) for n in self._names], True

    async def rename(self, path, new_name):
        self.renamed.append((path, new_name))
        return {"code": 200}


def test_folders_route_works_for_openlist(client, monkeypatch):
    from app.api import renamer as renamer_api

    fake = _FakeOpenListClient(names=["绝命毒师"])
    monkeypatch.setattr(renamer_api, "get_default_client", lambda: fake)

    res = client.post("/api/rename/folders", json=payload(
        source="openlist",
        file_ids=["f1"],
        overrides={"f1": OVERRIDES["f1"]},
        path="/115/绝命毒师/Season 01",
    ))
    assert res.status_code == 200, res.text
    body = res.json()

    # 远端路径用 `/` 分隔, 且改名请求带的是「新名字」而不是新路径
    assert body["renamed"][0]["new_path"].endswith(TARGET_NAME)
    assert "\\" not in body["renamed"][0]["new_path"]
    assert fake.renamed[0][1] == TARGET_NAME
    # 撞名检查问的是父目录
    assert fake.listed == [fake.renamed[0][0].rsplit("/", 1)[0]]


def test_folders_route_requires_openlist_connection(client, monkeypatch):
    from app.api import renamer as renamer_api

    monkeypatch.setattr(renamer_api, "get_default_client", lambda: None)
    res = client.post("/api/rename/folders", json=payload(source="openlist", file_ids=["f1"]))
    assert res.status_code == 401, res.text
