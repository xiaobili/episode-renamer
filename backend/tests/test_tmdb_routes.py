import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _item(tv_id, name, original_name="", year=None):
    from app.models.tmdb import TmdbSearchItem
    return TmdbSearchItem(tv_id=tv_id, name=name, original_name=original_name, year=year)


def _stub_search(monkeypatch, *, hits=None, error=None, captured=None):
    """把 TmdbClient.search_tv 换成假实现 —— 这些用例一律不出网。"""
    from app.api import tmdb as tmdb_api

    async def fake_search(self, query, year=None):
        if captured is not None:
            captured["query"] = query
            captured["year"] = year
        if error is not None:
            raise error
        return list(hits or [])

    monkeypatch.setattr(tmdb_api.TmdbClient, "search_tv", fake_search)


def test_test_endpoint_reports_ok_with_v3_key(client, monkeypatch):
    # sample 取首条, 所以给两条不同名字的结果
    _stub_search(monkeypatch, hits=[
        _item(1396, "绝命毒师", "Breaking Bad", 2008),
        _item(60059, "风骚律师", "Better Call Saul", 2015),
    ])
    res = client.get("/api/tmdb/test", headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["status"] == "ok"
    assert body["auth_mode"] == "v3_api_key"
    assert body["sample"] == "绝命毒师"


def test_test_endpoint_reports_bearer_auth_for_v4_token(client, monkeypatch):
    # eyJ 开头 = v4 Read Access Token, 走 Authorization 头而非 api_key 参数
    _stub_search(monkeypatch, hits=[_item(1, "Breaking Bad", "Breaking Bad", 2008)])
    res = client.get("/api/tmdb/test", headers={"X-Tmdb-Key": "eyJhbGciOiJIUzI1NiJ9"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["status"] == "ok"
    assert body["auth_mode"] == "v4_bearer"


def test_test_endpoint_reports_ok_with_no_hits(client, monkeypatch):
    # 探针搜到 0 条也要算连通 —— Key 能用, 只是没结果。sample 不能 IndexError。
    _stub_search(monkeypatch, hits=[])
    res = client.get("/api/tmdb/test", headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["status"] == "ok"
    assert body["sample"] == ""


def test_test_endpoint_reports_invalid_key(client, monkeypatch):
    from app.core.tmdb_client import TmdbAuthError

    _stub_search(monkeypatch, error=TmdbAuthError("TMDB API Key 无效"))
    res = client.get("/api/tmdb/test", headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is False
    assert body["status"] == "invalid_key"


def test_test_endpoint_reports_unreachable(client, monkeypatch):
    from app.core.tmdb_client import TmdbUnavailableError

    _stub_search(monkeypatch, error=TmdbUnavailableError("TMDB 请求失败: boom"))
    res = client.get("/api/tmdb/test", headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is False
    assert body["status"] == "unreachable"


def test_test_endpoint_reports_unreachable_on_not_found(client, monkeypatch):
    # tmdb_client 对任何 404 都抛 TmdbNotFoundError, 包括 /search/tv。拦截式代理 /
    # DNS 屏蔽会对被封主机回 404 —— 让它逃到路由层就是 500 + traceback,
    # 而本端点存在的全部意义是给设置页一个可读状态。
    from app.core.tmdb_client import TmdbNotFoundError

    _stub_search(monkeypatch, error=TmdbNotFoundError("TMDB 无此资源: /search/tv"))
    res = client.get("/api/tmdb/test", headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is False
    assert body["status"] == "unreachable"


def test_test_endpoint_reports_disabled_even_with_key(client, monkeypatch):
    # 服务端总开关优先于用户填的 Key —— 否则「禁用」形同虚设
    from app.config import settings

    _stub_search(monkeypatch, hits=[_item(1, "Breaking Bad")])
    monkeypatch.setattr(settings, "tmdb_enabled", False)
    res = client.get("/api/tmdb/test", headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is False
    assert body["status"] == "disabled"


def test_search_endpoint_returns_item_shape(client, monkeypatch):
    captured = {}
    _stub_search(monkeypatch, captured=captured, hits=[
        _item(1396, "绝命毒师", "Breaking Bad", 2008),
    ])
    res = client.get("/api/tmdb/search", params={"q": "  绝命毒师  "},
                     headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    assert res.json() == {
        "success": True,
        "data": [{"tv_id": 1396, "name": "绝命毒师",
                  "original_name": "Breaking Bad", "year": 2008}],
    }
    # 首尾空白在路由层就去掉, 不能带着空格去打 TMDB
    assert captured["query"] == "绝命毒师"


def test_search_endpoint_passes_year_through(client, monkeypatch):
    # year 下不下传, 响应长得一模一样 —— 所以假客户端既记实参, 也按 year 分叉返回,
    # 两头都钉住, 单独看响应是分不出来的。
    captured = {}

    async def fake_search(self, query, year=None):
        captured["year"] = year
        label = f"with-year-{year}" if year is not None else "no-year"
        return [_item(1, label, label, year)]

    from app.api import tmdb as tmdb_api
    monkeypatch.setattr(tmdb_api.TmdbClient, "search_tv", fake_search)

    res = client.get("/api/tmdb/search", params={"q": "x", "year": 2008},
                     headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 200, res.text
    assert captured["year"] == 2008
    assert res.json()["data"][0]["name"] == "with-year-2008"


def test_search_endpoint_maps_unavailable_to_502(client, monkeypatch):
    from app.core.tmdb_client import TmdbUnavailableError

    _stub_search(monkeypatch, error=TmdbUnavailableError("TMDB 请求失败: boom"))
    res = client.get("/api/tmdb/search", params={"q": "x"},
                     headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 502, res.text
    assert res.json()["detail"] == "TMDB 请求失败: boom"


def test_search_endpoint_maps_not_found_to_502(client, monkeypatch):
    # 与 400 分开: 404 是 TMDB 侧/链路问题, 不是用户的 Key 问题。
    from app.core.tmdb_client import TmdbNotFoundError

    _stub_search(monkeypatch, error=TmdbNotFoundError("TMDB 无此资源: /search/tv"))
    res = client.get("/api/tmdb/search", params={"q": "x"},
                     headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 502, res.text
    assert res.json()["detail"] == "TMDB 无此资源: /search/tv"


def test_search_endpoint_maps_auth_error_to_400(client, monkeypatch):
    from app.core.tmdb_client import TmdbAuthError

    _stub_search(monkeypatch, error=TmdbAuthError("TMDB API Key 无效"))
    res = client.get("/api/tmdb/search", params={"q": "x"},
                     headers={"X-Tmdb-Key": "a" * 32})
    assert res.status_code == 400, res.text
    # 不要再拼前缀, 否则是「TMDB API Key 无效: TMDB API Key 无效」
    assert res.json()["detail"] == "TMDB API Key 无效"


def test_test_endpoint_reports_not_configured(client, monkeypatch):
    # 未配置 Key 时不能 500，要给出一个可读的状态
    from app.config import settings
    monkeypatch.setattr(settings, "tmdb_api_key", "")
    res = client.get("/api/tmdb/test")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "not_configured"


def test_search_endpoint_rejects_empty_query(client, monkeypatch):
    # 打桩不是为了这个分支本身: 它今天的密闭性是**有条件**的 —— 不出网只因 400 发生在
    # 构造客户端**之前**。空查询守卫一旦被移除, 这条就会真去打 TMDB。
    # 接上打桩缝, 密闭性才不依赖某个守卫恰好还在。
    _stub_search(monkeypatch)
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
