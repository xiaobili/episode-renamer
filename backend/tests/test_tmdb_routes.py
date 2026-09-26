import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_test_endpoint_reports_not_configured(client, monkeypatch):
    # 未配置 Key 时不能 500，要给出一个可读的状态
    from app.config import settings
    monkeypatch.setattr(settings, "tmdb_api_key", "")
    res = client.get("/api/tmdb/test")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "not_configured"


def test_search_endpoint_rejects_empty_query(client):
    res = client.get("/api/tmdb/search", params={"q": "   "},
                     headers={"X-Tmdb-Key": "whatever"})
    assert res.status_code == 400, res.text


def test_search_endpoint_requires_key_when_not_configured(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "tmdb_api_key", "")
    res = client.get("/api/tmdb/search", params={"q": "绝命毒师"})
    assert res.status_code == 400, res.text
    assert "TMDB" in res.json()["detail"]


def test_header_key_overrides_env_key(client, monkeypatch):
    # Review Focus 1：设置页填的值必须能覆盖 .env 的默认值, 否则「设置不生效」
    from app.config import settings
    from app.api import tmdb as tmdb_api

    captured = {}

    async def fake_search(self, query, year=None):
        captured["key"] = self.api_key
        captured["language"] = self.language
        return []

    monkeypatch.setattr(settings, "tmdb_api_key", "from-env")
    monkeypatch.setattr(tmdb_api.TmdbClient, "search_tv", fake_search)

    res = client.get("/api/tmdb/search", params={"q": "x"},
                     headers={"X-Tmdb-Key": "from-settings", "X-Tmdb-Language": "ja-JP"})
    assert res.status_code == 200, res.text
    assert captured["key"] == "from-settings"
    assert captured["language"] == "ja-JP"


def test_env_key_is_used_when_header_absent(client, monkeypatch):
    from app.config import settings
    from app.api import tmdb as tmdb_api

    captured = {}

    async def fake_search(self, query, year=None):
        captured["key"] = self.api_key
        return []

    monkeypatch.setattr(settings, "tmdb_api_key", "from-env")
    monkeypatch.setattr(tmdb_api.TmdbClient, "search_tv", fake_search)

    res = client.get("/api/tmdb/search", params={"q": "x"})
    assert res.status_code == 200, res.text
    assert captured["key"] == "from-env"
