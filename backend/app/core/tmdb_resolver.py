from __future__ import annotations

import asyncio
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional

from ..config import settings
from ..models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow
from .tmdb_client import (
    TmdbAuthError,
    TmdbNotFoundError,
    TmdbUnavailableError,
)


STATUS_MATCHED = "matched"
STATUS_DISABLED = "disabled"
STATUS_SHOW_NOT_FOUND = "show_not_found"
STATUS_SEASON_NOT_FOUND = "season_not_found"
STATUS_EPISODE_NOT_FOUND = "episode_not_found"
STATUS_UNAVAILABLE = "unavailable"

# 归一化时抹去的字符。它们是同一个剧名在真实目录里最常见的几种写法差异。
_STRIPPED_CHARS = (" ", "\t", ".", "_", "-", "·", ":", "：")


def normalize_show_name(name: str) -> str:
    """归一化剧名, 只用于分组与缓存键, **不用于展示**。

    展示始终用 ParsedInfo.show_name 原文 —— 归一化会抹掉空格与大小写,
    展示出来就不是用户认识的剧名了。
    """
    if not name:
        return ""
    folded = unicodedata.normalize("NFKC", name).casefold()
    for ch in _STRIPPED_CHARS:
        folded = folded.replace(ch, "")
    return folded


@dataclass(frozen=True)
class ResolveRequest:
    show_name: str
    season: Optional[int]
    episode: Optional[int]


@dataclass
class EpisodeMatch:
    status: str
    show: Optional[TmdbShow] = None
    season: Optional[TmdbSeason] = None
    episode: Optional[TmdbEpisode] = None


class TmdbCache:
    """进程级缓存, 跨请求共享。

    这不是优化而是前提: 预览接口被前端模板输入框的每次按键触发
    （frontend/src/stores/workspace.js 的 watch 依赖 currentTemplate），
    无缓存则每敲一键打十几次 TMDB。
    """

    def __init__(self, ttl: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._store: dict[tuple, tuple[float, object]] = {}
        self._lock = asyncio.Lock()

    def get(self, key: tuple):
        hit = self._store.get(key)
        if hit is None:
            return None
        stored_at, value = hit
        if self._clock() - stored_at > self._ttl:
            del self._store[key]
            return None
        return value

    def put(self, key: tuple, value) -> None:
        self._store[key] = (self._clock(), value)

    async def get_or_create(self, key: tuple, factory: Callable):
        """命中直接返回; 未命中则调用 factory。同键的并发未命中会被合并成一次外部调用。

        `factory` 抛异常时不写入缓存 —— 失败不缓存, 下次重试。
        """
        hit = self.get(key)
        if hit is not None:
            return hit

        async with self._lock:
            # 双检: 等锁期间同键可能已被填充
            hit = self.get(key)
            if hit is not None:
                return hit
            value = await factory()
            self.put(key, value)
            return value

    def clear(self) -> None:
        self._store.clear()


_DEFAULT_CACHE = TmdbCache(ttl=settings.tmdb_cache_ttl)


class TmdbResolver:
    def __init__(
        self,
        client,
        overrides: Optional[dict[str, int]] = None,
        cache: Optional[TmdbCache] = None,
    ) -> None:
        self._client = client
        self._cache = cache if cache is not None else _DEFAULT_CACHE
        # 键归一化后再存。前端传来的键是 show_name 原文, 与分组用的归一化形式不同,
        # 不归一化就会静默失效 —— 用户点了重选却什么都没变。
        self._overrides = {
            normalize_show_name(k): int(v) for k, v in (overrides or {}).items()
        }

    def _scope(self) -> tuple:
        """缓存键的公共前缀。含 Key 指纹与语言 —— 换 Key、换语言都必须失效。"""
        return (self._client.cache_fingerprint(), self._client.language)

    @staticmethod
    async def _guarded(call: Callable):
        """外部数据边界：把客户端调用里**未分类**的异常归为 unavailable。

        这里用宽捕获是正确且惯用的做法, 因为这里是**外部数据边界**, 不是内部逻辑。
        铁律「TMDB 故障绝不阻断重命名」的措辞是分类性的, 而不是枚举性的 —— 它要求
        任何未预料的故障都不能冒到路由层, 而不是只兜住我们列得出的那几种。TMDB 的
        响应是外部输入, 畸形 payload 会以枚举不完的方式炸出来: `int(number)` 的
        ValueError、genres 数组里的 null、200 却回非对象……客户端在请求边界
        (tmdb_client._get) 已经分类了它看得见的那些, 但**映射层**的异常它看不到,
        逐个枚举必然漏, 漏一个就是整个预览请求 500。

        两个例外, 顺序与语义都不能动:
        - `TmdbAuthError` 必须原样冒泡: 那是配置错误, 是这条铁律唯一的例外。
          吞成 unavailable 会让「Key 填错了」伪装成「TMDB 挂了」, 用户永远查不出来。
        - `TmdbNotFoundError` 不能被压成 unavailable: 它是**已分类**的结果
          (剧/季不存在), 六态降级要靠它把 season_not_found 与 unavailable 分开。
          压掉它等于把「没这一季」误报成「TMDB 挂了」。

        （不要为了「干净」删掉这个宽捕获或那两个 re-raise。）
        """
        try:
            return await call()
        except TmdbAuthError:
            raise  # 配置错误: 绝不降级
        except (TmdbNotFoundError, TmdbUnavailableError):
            raise  # 已分类的降级语义: 原样保留, 不要压成 unavailable
        except Exception as exc:  # 外部数据边界, 见上文 docstring
            raise TmdbUnavailableError(
                f"TMDB 响应无法解析: {type(exc).__name__}"
            ) from exc

    async def resolve_many(self, requests: list[ResolveRequest]) -> list[EpisodeMatch]:
        results: list[Optional[EpisodeMatch]] = [None] * len(requests)

        # 第一层分组：归一化剧名 -> 该剧名下的入参下标（保留首个原文作搜索词）
        by_show: dict[str, dict] = {}
        for index, request in enumerate(requests):
            key = normalize_show_name(request.show_name)
            group = by_show.setdefault(key, {"query": request.show_name, "indexes": []})
            group["indexes"].append(index)

        for normalized, group in by_show.items():
            show = await self._resolve_show(normalized, group["query"])

            if isinstance(show, str):  # 降级状态
                for index in group["indexes"]:
                    results[index] = EpisodeMatch(status=show)
                continue

            # 第二层分组：该剧下按季
            by_season: dict[Optional[int], list[int]] = {}
            for index in group["indexes"]:
                by_season.setdefault(requests[index].season, []).append(index)

            for season_number, indexes in by_season.items():
                if season_number is None:
                    for index in indexes:
                        results[index] = EpisodeMatch(
                            status=STATUS_SEASON_NOT_FOUND, show=show,
                        )
                    continue

                try:
                    season = await self._resolve_season(show.tv_id, season_number)
                except TmdbUnavailableError:
                    # 单季失败不拖垮其余分组 —— 「TMDB 故障不阻断重命名」的落点
                    for index in indexes:
                        results[index] = EpisodeMatch(
                            status=STATUS_UNAVAILABLE, show=show,
                        )
                    continue

                if season is None:
                    for index in indexes:
                        results[index] = EpisodeMatch(
                            status=STATUS_SEASON_NOT_FOUND, show=show,
                        )
                    continue

                for index in indexes:
                    episode_number = requests[index].episode
                    if episode_number is None or episode_number not in season.episodes:
                        # 绝不猜测: 番剧绝对集号对不上 TMDB 季内集号时就是这一支。
                        # 静默写错标题比明确报错危险得多。
                        results[index] = EpisodeMatch(
                            status=STATUS_EPISODE_NOT_FOUND, show=show, season=season,
                        )
                    else:
                        results[index] = EpisodeMatch(
                            status=STATUS_MATCHED,
                            show=show,
                            season=season,
                            episode=season.episodes[episode_number],
                        )

        return [r if r is not None else EpisodeMatch(status=STATUS_UNAVAILABLE) for r in results]

    async def _resolve_show(self, normalized: str, query: str):
        """返回 TmdbShow，或一个降级状态字符串。TmdbAuthError 向上冒泡。"""
        if not normalized:
            return STATUS_SHOW_NOT_FOUND

        scope = self._scope()
        tv_id = self._overrides.get(normalized)

        if tv_id is None:
            key = ("search",) + scope + (normalized,)

            async def fetch_search():
                return await self._guarded(lambda: self._client.search_tv(query))

            try:
                hits = await self._cache.get_or_create(key, fetch_search)
            except TmdbUnavailableError:
                return STATUS_UNAVAILABLE

            if not hits:
                return STATUS_SHOW_NOT_FOUND
            tv_id = hits[0].tv_id

        detail_key = ("show",) + scope + (tv_id,)

        async def fetch_detail():
            return await self._guarded(lambda: self._client.get_tv_detail(tv_id))

        try:
            return await self._cache.get_or_create(detail_key, fetch_detail)
        except TmdbNotFoundError:
            return STATUS_SHOW_NOT_FOUND
        except TmdbUnavailableError:
            return STATUS_UNAVAILABLE

    async def _resolve_season(self, tv_id: int, season_number: int) -> Optional[TmdbSeason]:
        """返回 TmdbSeason，或 None 表示该季在 TMDB 不存在。TmdbUnavailableError 向上冒泡。"""
        key = ("season",) + self._scope() + (tv_id, season_number)

        async def fetch_season():
            return await self._guarded(
                lambda: self._client.get_season(tv_id, season_number)
            )

        try:
            return await self._cache.get_or_create(key, fetch_season)
        except TmdbNotFoundError:
            return None
        except TmdbUnavailableError:
            raise
