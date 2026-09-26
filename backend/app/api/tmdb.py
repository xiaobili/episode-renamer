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


def build_tmdb_client(
    header_key: Optional[str] = None,
    header_language: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[TmdbClient]:
    """TMDB 生效配置的**唯一**决策点 —— /api/tmdb/* 与 /api/rename/* 共用。

    返回 None 表示「这次不启用 TMDB」, 怎么表达由调用方决定:
    /api/tmdb/* 抛 400（用户主动点的端点, 必须报错不降级）,
    /api/rename/* 降级为 disabled（spec §5.4: TMDB 永不阻断重命名）。

    优先级（spec §10.1 / §10.3）:
      key:      请求体/请求头 > .env
      language: 请求体/请求头 > .env
      enabled:  显式关闭(请求) > 服务端开关 > 开

    **空串一律算「未提供」**, 所以这里用真值判断而不是 `is not None`:
    设置页的提示写着「留空则用服务端 .env 的配置」, 前端留空时发的是 `""`;
    若这里写成 `is not None`, `""` 会被当成「用户提供了空 Key」→ key 为空 →
    返回 None → **TMDB 被静默禁用, 而界面说它会回退到 .env**。Docker 部署
    （只配 .env、不经界面填 Key）正是这么被破坏的。

    别把这个判断与 `renamer._pad_from_request` 的 `is not None` 互相对齐:
    那里 `0` 是合法补零位数, 短路它会静默改掉补零行为; 这里 `''` 本身就是
    「未提供」, 两者语义不同, 不是笔误。
    """
    # 任意一侧关闭都返回 None。用户显式取消勾选优先; 服务端的 tmdb_enabled
    # 为假时同样压过请求 —— 与 /api/tmdb/test 报的 disabled 是同一语义。
    if enabled is False or not settings.tmdb_enabled:
        return None

    key = header_key or settings.tmdb_api_key
    if not key:
        return None

    return TmdbClient(
        api_key=key,
        language=header_language or settings.tmdb_language,
        timeout=settings.tmdb_timeout,
    )


def _client(header_key: Optional[str], header_language: Optional[str]) -> TmdbClient:
    # /api/tmdb/* 是用户主动调用的端点: 拿不到可用配置必须报错, 不能像
    # /api/rename/* 那样静默降级。判定本身在 build_tmdb_client 里, 只有一处。
    client = build_tmdb_client(header_key, header_language)
    if client is None:
        # 两种成因给两种文案（spec §5.3 错误分级）: 用户要做的事完全不同 ——
        # 「去填 Key」还是「去开服务端总开关」。
        if not settings.tmdb_enabled:
            raise HTTPException(status_code=400, detail="TMDB 已被服务端禁用")
        raise HTTPException(status_code=400, detail="TMDB 未配置 API Key")
    return client


@router.get("/test")
async def test_tmdb(
    x_tmdb_key: Optional[str] = Header(default=None),
    x_tmdb_language: Optional[str] = Header(default=None),
):
    client = build_tmdb_client(x_tmdb_key, x_tmdb_language)
    if client is None:
        # 本端点不抛错, 而是把成因作为可读状态返回给设置页（「测试连接」）。
        if not settings.tmdb_enabled:
            return {"success": False, "status": "disabled", "message": "TMDB 已被服务端禁用"}
        return {
            "success": False,
            "status": "not_configured",
            "message": "未配置 API Key",
        }

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
