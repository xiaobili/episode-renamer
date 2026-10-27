"""端到端：扫描 → 逐集改名 → NFO 收尾 → 剧集目录改名。

这条用例存在的唯一理由，是**顺序**：`tvshow.nfo` / `season.nfo` / 每集 `.nfo` 必须
先写在旧目录里，再由目录改名把它们带走。若有人在 `executeAction` 的链路上把
「改目录」挪到 finalize 之前，`write_nfo_files` 的 `mkdir(parents=True)` 会在旧名下
重建目录，媒体库里就会多出一个只有 NFO 的空文件夹 —— 而单测层面一切正常。
"""
import pytest
from fastapi.testclient import TestClient

from app.api.renamer import clear_cache
from app.main import app
from app.models.tmdb import TmdbEpisode, TmdbSearchItem, TmdbSeason, TmdbShow

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
OLD_DIR = "绝命毒师"
NEW_DIR = "绝命毒师 (2008) [tmdbid-1396]"


class _FakeTmdbClient:
    language = "zh-CN"

    def cache_fingerprint(self):
        return "show-folder-e2e-fake"

    async def search_tv(self, query, year=None):
        return [TmdbSearchItem(tv_id=1396, name=query, original_name=query, year=2008)]

    async def get_tv_detail(self, tv_id):
        return TmdbShow(tv_id=tv_id, name="绝命毒师", original_name="Breaking Bad", year=2008)

    async def get_season(self, tv_id, season_number):
        return TmdbSeason(season_number=season_number, tmdb_id=3575, episodes={
            1: TmdbEpisode(episode_number=1, name="Pilot", tmdb_id=62084),
            2: TmdbEpisode(episode_number=2, name="Cat's in the Bag", tmdb_id=62085),
        })


@pytest.fixture
def library(tmp_path):
    season_dir = tmp_path / OLD_DIR / "Season 01"
    season_dir.mkdir(parents=True)
    for episode in (1, 2):
        (season_dir / f"Breaking.Bad.S01E0{episode}.mkv").write_bytes(b"")
    clear_cache()
    return tmp_path


def test_full_pipeline_puts_nfo_inside_the_renamed_folder(library, monkeypatch):
    from app.api import renamer as renamer_api

    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
    client = TestClient(app)

    scan = client.post("/api/scan", json={
        "source": "local", "path": str(library), "recursive": True,
    })
    assert scan.status_code == 200, scan.text
    file_ids = [f["id"] for f in scan.json()["files"]]
    assert len(file_ids) == 2

    common = {
        "template": TEMPLATE,
        "source": "local",
        "path": str(library),
        "create_season_folder": True,
        "folder_template": "Season {season_padded}",
        "rename_folders": True,
        "generate_nfo": True,
    }

    preview = client.post("/api/rename/preview", json={**common, "file_ids": file_ids})
    assert preview.status_code == 200, preview.text
    rows = preview.json()["results"]
    assert {r["folder"]["new_path"] for r in rows} == {str(library / NEW_DIR)}

    # 1) 逐集改名
    landed = {}
    for file_id in file_ids:
        res = client.post("/api/rename/execute", json={
            **common, "file_id": file_id, "conflict_strategy": "skip",
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["result"]["success"] is True, body
        landed[file_id] = body["landed_path"]

    # 2) 剧集级 / 季级 NFO（此时目录仍是旧名）
    fin = client.post("/api/rename/finalize", json={
        **common, "file_ids": file_ids, "landed": landed,
    })
    assert fin.status_code == 200, fin.text
    assert {p.split("/")[-1] for p in fin.json()["nfo_written"]} == {
        "tvshow.nfo", "season.nfo",
    }

    # 3) 目录改名
    folders = client.post("/api/rename/folders", json={**common, "file_ids": file_ids})
    assert folders.status_code == 200, folders.text
    assert folders.json()["renamed"] == [{
        "old_path": str(library / OLD_DIR),
        "new_path": str(library / NEW_DIR),
        "show_name": OLD_DIR,
    }]

    # 终态：旧目录消失, 新目录下有剧集文件 + 三级 NFO
    assert not (library / OLD_DIR).exists()
    final = library / NEW_DIR
    assert (final / "Season 01" / "绝命毒师 - S01E01.mkv").exists()
    assert (final / "Season 01" / "绝命毒师 - S01E01.nfo").exists()
    assert (final / "tvshow.nfo").exists()
    assert (final / "Season 01" / "season.nfo").exists()
