from __future__ import annotations

import asyncio
import hashlib
from typing import Optional

import httpx

from ..models.tmdb import TmdbEpisode, TmdbSearchItem, TmdbSeason, TmdbShow


TMDB_BASE_URL = "https://api.themoviedb.org/3"

# TMDB 的 v4 Read Access Token 是 JWT，恒以 eyJ 开头；v3 API Key 是 32 位 hex。
# 两套鉴权的差异全部收敛在 _auth() 里 —— 用户抄错哪一个是高频事件，
# 分流错了会拿到 401，而 401 的成因有四种，排查成本极高。
V4_TOKEN_PREFIX = "eyJ"

# 429 退避时长（秒）
RETRY_BACKOFF_SECONDS = 1.0


class TmdbAuthError(Exception):
    """Key 无效。属配置错误，必须让用户看见，不可降级。"""


class TmdbNotFoundError(Exception):
    """请求的资源在 TMDB 不存在。可降级。"""


class TmdbUnavailableError(Exception):
    """网络失败 / 超时 / 5xx / 限流重试后仍失败。可降级。"""


def _year_of(date_str: Optional[str]) -> Optional[int]:
    if not date_str or len(date_str) < 4:
        return None
    head = date_str[:4]
    return int(head) if head.isdigit() else None


class TmdbClient:
    def __init__(
        self,
        api_key: str,
        language: str = "zh-CN",
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key
        self.language = language
        self.timeout = timeout
        self._transport = transport

    def cache_fingerprint(self) -> str:
        """缓存键里用的 Key 指纹。

        必须进缓存键：用户换 Key 后若命中旧缓存, 表现为「改了设置却不生效」,
        与项目历史上那类缺陷同源。
        """
        return hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:12]

    def is_v4_token(self) -> bool:
        return self.api_key.startswith(V4_TOKEN_PREFIX)

    def _auth(self) -> tuple[dict, dict]:
        """返回 (额外查询参数, 额外请求头)。两条鉴权路径的唯一分叉点。"""
        if self.is_v4_token():
            return {}, {"Authorization": f"Bearer {self.api_key}"}
        return {"api_key": self.api_key}, {}

    async def _get(self, path: str, **params) -> dict:
        auth_params, auth_headers = self._auth()
        query = {"language": self.language, **auth_params, **params}
        headers = {"accept": "application/json", **auth_headers}

        # 429 退避重试一次。其余错误立即分级抛出。
        last_error: Optional[Exception] = None
        for _attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    base_url=TMDB_BASE_URL,
                    timeout=httpx.Timeout(self.timeout, connect=5.0),
                    transport=self._transport,
                ) as client:
                    response = await client.get(path, params=query, headers=headers)
            except httpx.RequestError as exc:
                raise TmdbUnavailableError(f"TMDB 请求失败: {exc}") from exc

            if response.status_code == 401:
                raise TmdbAuthError("TMDB API Key 无效")
            if response.status_code == 404:
                raise TmdbNotFoundError(f"TMDB 无此资源: {path}")
            if response.status_code == 429:
                last_error = TmdbUnavailableError("TMDB 限流")
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                continue
            if response.status_code >= 500:
                raise TmdbUnavailableError(f"TMDB 服务异常: {response.status_code}")
            if response.status_code >= 400:
                raise TmdbUnavailableError(f"TMDB 返回 {response.status_code}")

            try:
                return response.json()
            except ValueError as exc:
                # 代理 / captive portal 常回 200 + HTML 页面。JSONDecodeError 是
                # ValueError，不归类就会逃出错误分级体系 —— 下游只兜
                # NotFound / Unavailable，铁律「TMDB 故障绝不阻断重命名」会被打破。
                raise TmdbUnavailableError(f"TMDB 返回非 JSON 响应: {path}") from exc

        raise last_error or TmdbUnavailableError("TMDB 限流")

    async def search_tv(self, query: str, year: Optional[int] = None) -> list[TmdbSearchItem]:
        params: dict = {"query": query}
        if year is not None:
            # 参数名是 first_air_date_year，不是 year。传 year 会被静默忽略。
            params["first_air_date_year"] = year

        data = await self._get("/search/tv", **params)
        items = []
        for raw in data.get("results") or []:
            tv_id = raw.get("id")
            # 结果偶尔缺 id。缺了就跳过 —— 不能让 KeyError 逃出错误分级体系。
            if tv_id is None:
                continue
            air_date = raw.get("first_air_date")
            items.append(TmdbSearchItem(
                tv_id=tv_id,
                name=raw.get("name") or "",
                original_name=raw.get("original_name") or "",
                year=_year_of(air_date),
            ))
        return items

    async def get_tv_detail(self, tv_id: int) -> TmdbShow:
        data = await self._get(f"/tv/{tv_id}")
        premiered = data.get("first_air_date")
        return TmdbShow(
            tv_id=tv_id,
            name=data.get("name") or "",
            original_name=data.get("original_name") or "",
            year=_year_of(premiered),
            overview=data.get("overview") or "",
            rating=data.get("vote_average"),
            votes=data.get("vote_count"),
            genres=[g.get("name", "") for g in (data.get("genres") or [])],
            premiered=premiered,
            status=data.get("status") or "",
        )

    async def get_season(self, tv_id: int, season_number: int) -> TmdbSeason:
        data = await self._get(f"/tv/{tv_id}/season/{season_number}")

        episodes: dict[int, TmdbEpisode] = {}
        for raw in data.get("episodes") or []:
            number = raw.get("episode_number")
            # 特别篇偶尔缺 episode_number。缺了就跳过 —— 不能拿 None 当字典键。
            if number is None:
                continue
            number = int(number)
            episodes[number] = TmdbEpisode(
                episode_number=number,
                name=raw.get("name") or "",
                overview=raw.get("overview") or "",
                air_date=raw.get("air_date"),
                rating=raw.get("vote_average"),
                tmdb_id=raw.get("id"),
            )

        return TmdbSeason(
            season_number=season_number,
            name=data.get("name") or "",
            overview=data.get("overview") or "",
            air_date=data.get("air_date"),
            tmdb_id=data.get("id"),
            episodes=episodes,
        )
