# 本项目未装 pytest-asyncio，用标准库 asyncio.run 驱动异步断言 ——
# 这两个测试都是纯函数式的「发一次请求、看请求长什么样」，不需要事件循环 fixture。
import asyncio

import httpx
import pytest

from app.core.tmdb_client import (
    TmdbAuthError,
    TmdbClient,
    TmdbNotFoundError,
    TmdbUnavailableError,
)


def _transport(captured, payload=None, status=200):
    """返回一个记录请求的 MockTransport。payload 为响应 JSON。"""
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if isinstance(payload, Exception):
            raise payload
        return httpx.Response(status, json=payload or {})
    return httpx.MockTransport(handler)


def test_v3_key_goes_in_query_param():
    # Review Focus 1 的反面：32 位 hex 是 v3 Key，必须走 api_key 查询参数
    captured = []
    client = TmdbClient("abc123hex", transport=_transport(captured, {"results": []}))
    asyncio.run(client.search_tv("绝命毒师"))

    request = captured[0]
    assert "api_key=abc123hex" in str(request.url)
    assert request.headers.get("authorization") is None


def test_v4_token_goes_in_authorization_header():
    # Review Focus 1：用户从 TMDB 设置页抄来的是 "API Read Access Token"（JWT，eyJ 开头）。
    # 若它被当 v3 Key 拼进查询参数，TMDB 返回 401，用户完全无从判断原因。
    captured = []
    token = "eyJhbGciOiJIUzI1NiJ9.fake.token"
    client = TmdbClient(token, transport=_transport(captured, {"results": []}))
    asyncio.run(client.search_tv("绝命毒师"))

    request = captured[0]
    assert request.headers["authorization"] == f"Bearer {token}"
    assert "api_key" not in str(request.url)


def test_language_is_sent_on_every_request():
    captured = []
    client = TmdbClient("k", language="ja-JP", transport=_transport(captured, {"results": []}))
    asyncio.run(client.search_tv("進撃の巨人"))

    assert "language=ja-JP" in str(captured[0].url)


def test_year_uses_first_air_date_year_param():
    # spec §5.2：TMDB 的年份参数名是 first_air_date_year。
    # 传成 year 会被静默忽略 —— 不报错、不生效，最难查的一类 bug。
    captured = []
    client = TmdbClient("k", transport=_transport(captured, {"results": []}))
    asyncio.run(client.search_tv("绝命毒师", year=2008))

    url = str(captured[0].url)
    assert "first_air_date_year=2008" in url
    assert "year=2008" not in url.replace("first_air_date_year=2008", "")


def test_search_maps_response_to_models():
    payload = {"results": [
        {"id": 1396, "name": "绝命毒师", "original_name": "Breaking Bad",
         "first_air_date": "2008-01-20"},
        {"id": 999, "name": "无日期剧", "original_name": "No Date",
         "first_air_date": ""},
    ]}
    client = TmdbClient("k", transport=_transport([], payload))
    hits = asyncio.run(client.search_tv("绝命毒师"))

    assert [h.tv_id for h in hits] == [1396, 999]
    assert hits[0].name == "绝命毒师"
    assert hits[0].original_name == "Breaking Bad"
    assert hits[0].year == 2008
    assert hits[1].year is None


def test_get_season_indexes_episodes_by_number():
    payload = {
        "id": 3575, "name": "第 2 季", "overview": "s2", "air_date": "2009-03-08",
        "episodes": [
            {"id": 62084, "episode_number": 1, "name": "Seven Thirty-Seven",
             "overview": "e1", "air_date": "2009-03-08", "vote_average": 8.2},
            {"id": 62085, "episode_number": 5, "name": "Breakage",
             "overview": "e5", "air_date": "2009-04-05", "vote_average": 8.7},
        ],
    }
    client = TmdbClient("k", transport=_transport([], payload))
    season = asyncio.run(client.get_season(1396, 2))

    assert season.season_number == 2
    assert sorted(season.episodes.keys()) == [1, 5]
    assert season.episodes[5].name == "Breakage"
    assert season.episodes[5].air_date == "2009-04-05"
    assert season.episodes[5].tmdb_id == 62085


def test_get_season_skips_episodes_without_number():
    # TMDB 的特别篇偶尔缺 episode_number。缺了就跳过，不能用 None 当字典键。
    payload = {"episodes": [{"id": 1, "name": "无集号"}, {"id": 2, "episode_number": 3, "name": "有集号"}]}
    client = TmdbClient("k", transport=_transport([], payload))
    season = asyncio.run(client.get_season(1, 1))

    assert list(season.episodes.keys()) == [3]


def test_401_raises_auth_error():
    # Review Focus 2：Key 无效是配置错误，必须冒泡让用户看见，不可降级
    client = TmdbClient("bad", transport=_transport([], {"status_message": "Invalid API key"}, 401))
    with pytest.raises(TmdbAuthError):
        asyncio.run(client.search_tv("x"))


def test_404_raises_not_found():
    client = TmdbClient("k", transport=_transport([], {}, 404))
    with pytest.raises(TmdbNotFoundError):
        asyncio.run(client.get_season(1, 99))


def test_500_raises_unavailable():
    client = TmdbClient("k", transport=_transport([], {}, 500))
    with pytest.raises(TmdbUnavailableError):
        asyncio.run(client.search_tv("x"))


def test_429_retries_once_then_raises_unavailable(monkeypatch):
    # 限流退避 1 秒。测试里把 sleep 换掉，否则这个用例会真的挂 1 秒。
    # 注意：体里必须调「替换前」的真实 sleep —— 写成 asyncio.sleep(0) 会递归到
    # 被替换后的自身，直接 RecursionError。
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _s: real_sleep(0))

    captured = []
    client = TmdbClient("k", transport=_transport(captured, {}, 429))
    with pytest.raises(TmdbUnavailableError):
        asyncio.run(client.search_tv("x"))

    assert len(captured) == 2, "429 应重试一次（共 2 次请求）"


def test_429_then_success_returns_result(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _s: real_sleep(0))

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"results": [
            {"id": 1, "name": "剧", "original_name": "Show", "first_air_date": "2020-01-01"},
        ]})

    client = TmdbClient("k", transport=httpx.MockTransport(handler))
    hits = asyncio.run(client.search_tv("x"))

    assert [h.tv_id for h in hits] == [1]


def test_network_error_raises_unavailable():
    client = TmdbClient("k", transport=_transport([], httpx.ConnectError("boom")))
    with pytest.raises(TmdbUnavailableError):
        asyncio.run(client.search_tv("x"))


def test_cache_fingerprint_differs_per_key():
    assert TmdbClient("a").cache_fingerprint() != TmdbClient("b").cache_fingerprint()
    assert TmdbClient("a").cache_fingerprint() == TmdbClient("a").cache_fingerprint()
