from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..core.tmdb_client import (
    TmdbAuthError,
    TmdbClient,
    TmdbNotFoundError,
    TmdbUnavailableError,
)


router = APIRouter(prefix="/api/tmdb", tags=["tmdb"])

# 用一次已知存在的搜索作连通性探针。选 "Breaking Bad" 是因为它在任何语言下
# 都返回结果，不会因 locale 差异出现假阴性。
PROBE_QUERY = "Breaking Bad"


def _client(header_key: Optional[str], header_language: Optional[str]) -> TmdbClient:
    # 优先级: 请求头 > .env。设置页填的值必须能盖掉 .env, 否则就是「设置不生效」。
    key = header_key if header_key else settings.tmdb_api_key
    if not key:
        raise HTTPException(status_code=400, detail="TMDB 未配置 API Key")
    return TmdbClient(
        api_key=key,
        language=header_language or settings.tmdb_language,
        timeout=settings.tmdb_timeout,
    )


@router.get("/test")
async def test_tmdb(
    x_tmdb_key: Optional[str] = Header(default=None),
    x_tmdb_language: Optional[str] = Header(default=None),
):
    key = x_tmdb_key if x_tmdb_key else settings.tmdb_api_key
    if not settings.tmdb_enabled:
        return {"success": False, "status": "disabled", "message": "TMDB 已被服务端禁用"}
    if not key:
        return {
            "success": False,
            "status": "not_configured",
            "message": "未配置 API Key",
        }

    client = _client(x_tmdb_key, x_tmdb_language)
    try:
        hits = await client.search_tv(PROBE_QUERY)
    except TmdbAuthError as exc:
        return {"success": False, "status": "invalid_key", "message": str(exc)}
    except TmdbNotFoundError as exc:
        # tmdb_client 对**任何** HTTP 404 都抛它, 包括 /search/tv。拦截式代理 / DNS
        # 屏蔽会对被封主机回 404 —— 在这条端点里它就是「连不上 TMDB」的一种,
        # 而本端点存在的全部意义是给设置页一个可读状态, 不是吐 500 + traceback。
        return {"success": False, "status": "unreachable", "message": str(exc)}
    except TmdbUnavailableError as exc:
        return {"success": False, "status": "unreachable", "message": str(exc)}

    return {
        "success": True,
        "status": "ok",
        "auth_mode": "v4_bearer" if client.is_v4_token() else "v3_api_key",
        "sample": hits[0].name if hits else "",
    }


@router.get("/search")
async def search_tv(
    q: str,
    year: Optional[int] = None,
    x_tmdb_key: Optional[str] = Header(default=None),
    x_tmdb_language: Optional[str] = Header(default=None),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="搜索词不能为空")

    client = _client(x_tmdb_key, x_tmdb_language)
    try:
        hits = await client.search_tv(q.strip(), year=year)
    except TmdbAuthError as exc:
        # 不要在这里再拼一次前缀 —— TmdbAuthError 的消息本身就是
        # 「TMDB API Key 无效」, 拼出来会是「TMDB API Key 无效: TMDB API Key 无效」。
        raise HTTPException(status_code=400, detail=str(exc))
    except TmdbNotFoundError as exc:
        # 与 400 分开: 404 是 TMDB 侧 / 链路的问题, 不是用户的 Key 问题。
        raise HTTPException(status_code=502, detail=str(exc))
    except TmdbUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"success": True, "data": [h.model_dump() for h in hits]}
