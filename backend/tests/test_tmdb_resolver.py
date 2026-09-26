import asyncio

import pytest

from app.core import tmdb_resolver
from app.core.tmdb_client import (
    TmdbAuthError,
    TmdbNotFoundError,
    TmdbUnavailableError,
)
from app.core.tmdb_resolver import (
    STATUS_EPISODE_NOT_FOUND,
    STATUS_MATCHED,
    STATUS_SEASON_NOT_FOUND,
    STATUS_SHOW_NOT_FOUND,
    STATUS_UNAVAILABLE,
    ResolveRequest,
    TmdbCache,
    TmdbResolver,
    normalize_show_name,
)
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbSearchItem, TmdbShow


@pytest.fixture(autouse=True)
def _isolate_default_cache():
    """逐例清空进程级默认缓存, 否则用例之间会互相污染。

    `_DEFAULT_CACHE` 是刻意的进程级共享（生产里预览接口每次按键都会调 resolve_many,
    缓存不跨 resolver 实例就等于没有）。但测试里它是跨用例的全局状态: 凡是不传
    `cache=` 的用例都写同一批键（FakeClient 的指纹与语言是常量), 于是先跑的用例
    填充的命中会让后跑的用例根本打不到假客户端 —— 断言请求次数的用例会以
    「结果看着合理但其实是旧的」的方式失败, 而不是报错。

    monkeypatch 在这里帮不上忙: 缓存对象在模块导入时就已绑定, 测试要清的是它的内容。
    """
    tmdb_resolver._DEFAULT_CACHE.clear()
    yield
    tmdb_resolver._DEFAULT_CACHE.clear()


SHOW = TmdbShow(tv_id=1396, name="绝命毒师", original_name="Breaking Bad", year=2008)


def make_season(number=2, episodes=(5, 6)):
    return TmdbSeason(
        season_number=number,
        name=f"第 {number} 季",
        episodes={
            n: TmdbEpisode(episode_number=n, name=f"第{n}集", air_date=f"2009-04-0{n}")
            for n in episodes
        },
    )


class FakeClient:
    """计数器 + 固定响应的假客户端。断言请求次数靠它，不碰网络。

    `search_tv`、`get_tv_detail`、`get_season` 三处开头各让出一次控制权，
    忠实模拟「真实网络调用一定会挂起」。目前只有
    test_concurrent_same_key_is_merged 用到了这个交错能力（它断言 search 次数），
    另两处让出点不为任何断言服务 —— 保留它们是为了忠实：真实调用三者都会挂起。
    不要以「没人断言」为由删掉。

    该用例为什么依赖让出点：`asyncio.gather` 只在协程被 await 真正挂起时才会
    交错执行 —— 没有让出点，两个并发任务永远一前一后跑完，把 TmdbCache 的锁
    整个删掉该用例照样通过（实测过）。守护「同键并发只打一次外部请求」这个
    承诺的只有这一条用例，所以这些让出点不能删。

    `fail=` 可选值：`"search"` / `"season"` 抛 TmdbUnavailableError，
    `"auth"` 在 search_tv 里抛 TmdbAuthError，`"value"` 在 search_tv 里抛
    ValueError（模拟畸形 payload 在映射层炸出的未分类异常）。
    """

    def __init__(self, hits=None, show=SHOW, seasons=None, fail=None):
        self.api_key = "fake"
        self.language = "zh-CN"
        self.calls = {"search": [], "detail": [], "season": []}
        self._hits = hits if hits is not None else [TmdbSearchItem(tv_id=1396, name="绝命毒师")]
        self._show = show
        self._seasons = seasons if seasons is not None else {2: make_season(2), 3: make_season(3)}
        self._fail = fail

    def cache_fingerprint(self):
        return "fake-fp"

    async def search_tv(self, query, year=None):
        await asyncio.sleep(0)  # 让出控制权，使并发任务可交错（见类 docstring）
        self.calls["search"].append(query)
        if self._fail == "search":
            raise TmdbUnavailableError("boom")
        if self._fail == "auth":
            raise TmdbAuthError("TMDB API Key 无效")
        if self._fail == "value":
            # 畸形 payload 在映射层炸出的未分类异常，如 int(None)
            raise ValueError("invalid literal for int() with base 10: None")
        return list(self._hits)

    async def get_tv_detail(self, tv_id):
        await asyncio.sleep(0)  # 同上：让出控制权，使并发任务可交错
        self.calls["detail"].append(tv_id)
        return self._show

    async def get_season(self, tv_id, season_number):
        await asyncio.sleep(0)  # 同上：让出控制权，使并发任务可交错
        self.calls["season"].append((tv_id, season_number))
        if self._fail == "season":
            raise TmdbUnavailableError("boom")
        if season_number not in self._seasons:
            raise TmdbNotFoundError("no such season")
        return self._seasons[season_number]


def resolve(requests, **kwargs):
    client = kwargs.pop("client", None) or FakeClient(**kwargs)
    return asyncio.run(TmdbResolver(client, **{k: v for k, v in kwargs.items() if k == "overrides"}).resolve_many(requests)), client


# --- 归一化 ---

def test_normalize_folds_case_and_width():
    assert normalize_show_name("Breaking Bad") == normalize_show_name("breaking bad")
    assert normalize_show_name("ＢＲＥＡＫＩＮＧ") == normalize_show_name("breaking")


def test_normalize_strips_separators():
    assert normalize_show_name("Breaking.Bad") == normalize_show_name("Breaking Bad")
    assert normalize_show_name("Breaking_Bad") == normalize_show_name("Breaking-Bad")


def test_normalize_keeps_different_shows_apart():
    # Review Focus 4 的另一半：归一化不能把不同剧合并 —— 合并了标题会串到别的剧上
    assert normalize_show_name("绝命毒师") != normalize_show_name("绝命律师")
    assert normalize_show_name("") == ""


# --- 分组去重 ---

def test_ten_files_issue_three_requests():
    # 核心断言：10 个文件 → 1 次 search + 2 次 season = 3 次请求，而非 10 次
    client = FakeClient()
    requests = (
        [ResolveRequest("绝命毒师", 2, n) for n in (5, 6)] * 3
        + [ResolveRequest("绝命毒师", 3, n) for n in (5, 6)] * 2
    )
    matches = asyncio.run(TmdbResolver(client).resolve_many(requests))

    assert len(matches) == 10
    assert len(client.calls["search"]) == 1
    assert len(client.calls["season"]) == 2
    assert all(m.status == STATUS_MATCHED for m in matches)


def test_case_variant_show_names_share_one_query():
    # Review Focus 4：同一部剧因大小写差异必须命中同一分组，否则每集重复打 TMDB
    client = FakeClient()
    matches = asyncio.run(TmdbResolver(client).resolve_many([
        ResolveRequest("Breaking Bad", 2, 5),
        ResolveRequest("breaking bad", 2, 6),
        ResolveRequest("BREAKING.BAD", 2, 5),
    ]))

    assert len(client.calls["search"]) == 1
    assert len(client.calls["season"]) == 1
    assert all(m.status == STATUS_MATCHED for m in matches)


def test_distinct_shows_are_resolved_separately():
    # Review Focus 4：不同剧必须分开，标题不能串
    client = FakeClient()
    asyncio.run(TmdbResolver(client).resolve_many([
        ResolveRequest("绝命毒师", 2, 5),
        ResolveRequest("绝命律师", 2, 5),
    ]))

    assert len(client.calls["search"]) == 2


# --- 缓存 ---

def test_cache_survives_across_resolver_instances():
    # 预览接口每个按键都调一次 —— 缓存必须是进程级的，否则功能不可用
    cache = TmdbCache(ttl=3600)
    client = FakeClient()

    asyncio.run(TmdbResolver(client, cache=cache).resolve_many([ResolveRequest("绝命毒师", 2, 5)]))
    asyncio.run(TmdbResolver(client, cache=cache).resolve_many([ResolveRequest("绝命毒师", 2, 5)]))

    assert len(client.calls["search"]) == 1
    assert len(client.calls["season"]) == 1


def test_cache_key_includes_api_key_fingerprint():
    # 用户换 Key 后必须重新查。否则表现为「改了设置却不生效」。
    cache = TmdbCache(ttl=3600)
    client_a = FakeClient()
    client_b = FakeClient()
    client_b.cache_fingerprint = lambda: "other-fp"

    asyncio.run(TmdbResolver(client_a, cache=cache).resolve_many([ResolveRequest("绝命毒师", 2, 5)]))
    asyncio.run(TmdbResolver(client_b, cache=cache).resolve_many([ResolveRequest("绝命毒师", 2, 5)]))

    assert len(client_a.calls["search"]) == 1
    assert len(client_b.calls["search"]) == 1


def test_cache_language_is_part_of_the_key():
    cache = TmdbCache(ttl=3600)
    client_a = FakeClient()
    client_b = FakeClient()
    client_b.language = "ja-JP"

    asyncio.run(TmdbResolver(client_a, cache=cache).resolve_many([ResolveRequest("X", 1, 1)]))
    asyncio.run(TmdbResolver(client_b, cache=cache).resolve_many([ResolveRequest("X", 1, 1)]))

    assert len(client_a.calls["search"]) == 1
    assert len(client_b.calls["search"]) == 1


def test_cache_expires_after_ttl():
    now = {"t": 1000.0}
    cache = TmdbCache(ttl=60, clock=lambda: now["t"])
    client = FakeClient()

    asyncio.run(TmdbResolver(client, cache=cache).resolve_many([ResolveRequest("绝命毒师", 2, 5)]))
    now["t"] += 61
    asyncio.run(TmdbResolver(client, cache=cache).resolve_many([ResolveRequest("绝命毒师", 2, 5)]))

    assert len(client.calls["search"]) == 2


def test_concurrent_same_key_is_merged(monkeypatch):
    # 同一分组的并发请求应合并为一次外部调用
    cache = TmdbCache(ttl=3600)
    client = FakeClient()

    async def run():
        resolver = TmdbResolver(client, cache=cache)
        return await asyncio.gather(
            resolver.resolve_many([ResolveRequest("绝命毒师", 2, 5)]),
            resolver.resolve_many([ResolveRequest("绝命毒师", 2, 5)]),
        )

    asyncio.run(run())
    assert len(client.calls["search"]) == 1


# --- 降级状态 ---

def test_show_not_found():
    matches, _ = resolve([ResolveRequest("不存在的剧", 1, 1)], hits=[])
    assert matches[0].status == STATUS_SHOW_NOT_FOUND
    assert matches[0].episode is None


def test_season_not_found():
    matches, _ = resolve([ResolveRequest("绝命毒师", 99, 1)])
    assert matches[0].status == STATUS_SEASON_NOT_FOUND
    assert matches[0].show.tv_id == 1396


def test_episode_not_found():
    # Review Focus 5：番剧用绝对集号（如第 30 集），TMDB 该季只有 5、6 两集。
    # 必须标 episode_not_found，绝不猜、绝不写错标题。
    matches, _ = resolve([ResolveRequest("绝命毒师", 2, 30)])
    assert matches[0].status == STATUS_EPISODE_NOT_FOUND
    assert matches[0].episode is None
    assert matches[0].season.season_number == 2


def test_season_none_is_season_not_found():
    matches, _ = resolve([ResolveRequest("绝命毒师", None, 5)])
    assert matches[0].status == STATUS_SEASON_NOT_FOUND


def test_episode_none_is_episode_not_found():
    matches, _ = resolve([ResolveRequest("绝命毒师", 2, None)])
    assert matches[0].status == STATUS_EPISODE_NOT_FOUND


def test_unavailable_on_search_failure():
    matches, _ = resolve([ResolveRequest("绝命毒师", 2, 5)], fail="search")
    assert matches[0].status == STATUS_UNAVAILABLE


def test_unavailable_on_season_failure():
    matches, _ = resolve([ResolveRequest("绝命毒师", 2, 5)], fail="season")
    assert matches[0].status == STATUS_UNAVAILABLE


def test_one_bad_group_does_not_poison_the_others():
    # 单组失败不能拖垮整批 —— 这正是「TMDB 故障不阻断重命名」的实现落点
    client = FakeClient()
    original = client.get_season

    async def flaky(tv_id, season_number):
        if season_number == 2:
            raise TmdbUnavailableError("boom")
        return await original(tv_id, season_number)

    client.get_season = flaky
    matches = asyncio.run(TmdbResolver(client).resolve_many([
        ResolveRequest("绝命毒师", 2, 5),
        ResolveRequest("绝命毒师", 3, 5),
    ]))

    assert matches[0].status == STATUS_UNAVAILABLE
    assert matches[1].status == STATUS_MATCHED


# --- 外部数据边界守卫：未分类异常必须降级，配置错误必须冒泡 ---

def test_auth_error_propagates_out_of_resolve_many():
    # 唯一的例外。Key 无效是配置错误，必须让用户看见 —— 吞成 unavailable 会让
    # 「Key 填错了」伪装成「TMDB 挂了」，用户永远查不出来。
    # 这条断言是唯一拦得住它的东西：把守卫改成 except TmdbAuthError 后返回
    # unavailable（变异 C），只有本用例失败（DID NOT RAISE），其余 25 条全绿。
    with pytest.raises(TmdbAuthError):
        resolve([ResolveRequest("绝命毒师", 2, 5)], fail="auth")


def test_unclassified_error_is_degraded_not_raised():
    # 外部数据边界的兜底：畸形 payload 抛的 ValueError（如 int(number) 拿到 null）
    # 不属于任何已分类异常。它若逃出 resolve_many，整个预览请求就 500 了 ——
    # 与铁律「TMDB 故障绝不阻断重命名」冲突。必须降级成 unavailable。
    matches, _ = resolve([ResolveRequest("绝命毒师", 2, 5)], fail="value")
    assert matches[0].status == STATUS_UNAVAILABLE


def test_failed_lookup_is_not_cached():
    # 失败不缓存：第一次失败、第二次成功 —— 必须真的重试，而不是把失败存下来。
    cache = TmdbCache(ttl=3600)
    client = FakeClient()
    original = client.search_tv
    attempts = {"n": 0}

    async def flaky(query, year=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TmdbUnavailableError("boom")
        return await original(query, year)

    client.search_tv = flaky
    resolver = TmdbResolver(client, cache=cache)
    first = asyncio.run(resolver.resolve_many([ResolveRequest("绝命毒师", 2, 5)]))
    second = asyncio.run(resolver.resolve_many([ResolveRequest("绝命毒师", 2, 5)]))

    assert first[0].status == STATUS_UNAVAILABLE
    assert attempts["n"] == 2, "失败不该被缓存，第二次必须重新请求"
    assert second[0].status == STATUS_MATCHED


# --- overrides ---

def test_manual_tv_id_override_skips_search():
    client = FakeClient()
    matches = asyncio.run(TmdbResolver(client, overrides={"绝命毒师": 999}).resolve_many([
        ResolveRequest("绝命毒师", 2, 5),
    ]))

    assert client.calls["search"] == [], "给了 override 就不该再搜"
    assert client.calls["detail"] == [999]
    assert matches[0].status == STATUS_MATCHED


def test_override_key_is_normalized_before_matching():
    # 前端传来的键是 show_name 原文，可能与分组后的归一化形式不同。
    # 不做归一化就会静默失效 —— 用户点了重选却没有任何变化。
    client = FakeClient()
    asyncio.run(TmdbResolver(client, overrides={"Breaking.Bad": 999}).resolve_many([
        ResolveRequest("Breaking Bad", 2, 5),
    ]))

    assert client.calls["detail"] == [999]


def test_empty_show_name_is_show_not_found():
    client = FakeClient()
    matches = asyncio.run(TmdbResolver(client).resolve_many([ResolveRequest("", 1, 1)]))
    assert matches[0].status == STATUS_SHOW_NOT_FOUND
    assert client.calls["search"] == []


def test_resolve_many_preserves_input_order():
    matches, _ = resolve([
        ResolveRequest("绝命毒师", 2, 6),
        ResolveRequest("绝命毒师", 2, 5),
    ])
    assert matches[0].episode.episode_number == 6
    assert matches[1].episode.episode_number == 5
