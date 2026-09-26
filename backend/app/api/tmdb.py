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


# 「这次不启用 TMDB」的两种成因。它们同时是 /api/tmdb/test 的 status 字面值
# 与前端设置页分支的键, 所以是线上契约, 不要顺手改名。
REASON_DISABLED = "disabled"
REASON_NOT_CONFIGURED = "not_configured"

# 各端点自己的文案（spec §5.3 错误分级: 用户要做的事不同 ——「去开服务端总开关」
# 还是「去填 Key」）。文案按端点分, 但**成因只有一个来源**, 见 resolve_tmdb_client。
_UNAVAILABLE_MESSAGES = {
    "rename": {
        REASON_DISABLED: "TMDB 已被服务端禁用",
        REASON_NOT_CONFIGURED: "TMDB 未配置 API Key",
    },
    "test": {
        REASON_DISABLED: "TMDB 已被服务端禁用",
        REASON_NOT_CONFIGURED: "未配置 API Key",
    },
}


def resolve_tmdb_client(
    header_key: Optional[str] = None,
    header_language: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> tuple[Optional[TmdbClient], Optional[str]]:
    """TMDB 生效配置的**唯一**决策点 —— /api/tmdb/* 与 /api/rename/* 共用。

    返回 `(client, None)`, 或 `(None, 成因)`。成因是 REASON_* 之一, **只在这里
    判定** —— 调用点拿到的不是「又一个需要自己再读一次 settings 的问题」, 而是一个
    已经分好类的字符串。复制这份判定曾经就是本仓库出现过的真实缺陷形态（同一次
    运行里已经修掉一个）。

    调用方怎么表达由自己决定:
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
        return None, REASON_DISABLED

    key = header_key or settings.tmdb_api_key
    if not key:
        return None, REASON_NOT_CONFIGURED

    return (
        TmdbClient(
            api_key=key,
            language=header_language or settings.tmdb_language,
            timeout=settings.tmdb_timeout,
        ),
        None,
    )


def build_tmdb_client(
    header_key: Optional[str] = None,
    header_language: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[TmdbClient]:
    """只要「能不能用」的调用点（/api/rename/*）用的薄封装。

    判定本身在 resolve_tmdb_client 里, 只有一处 —— 这里不复制任何判断,
    也不该再长出第二套（test_tmdb_routes 有一条用例逐条钉死那些优先级）。
    """
    client, _ = resolve_tmdb_client(header_key, header_language, enabled)
    return client


def _client(header_key: Optional[str], header_language: Optional[str]) -> TmdbClient:
    # /api/tmdb/* 是用户主动调用的端点: 拿不到可用配置必须报错, 不能像
    # /api/rename/* 那样静默降级。判定本身在 resolve_tmdb_client 里, 只有一处。
    client, reason = resolve_tmdb_client(header_key, header_language)
    if client is None:
        raise HTTPException(
            status_code=400, detail=_UNAVAILABLE_MESSAGES["rename"][reason]
        )
    return client


@router.get("/test")
async def test_tmdb(
    x_tmdb_key: Optional[str] = Header(default=None),
    x_tmdb_language: Optional[str] = Header(default=None),
):
    client, reason = resolve_tmdb_client(x_tmdb_key, x_tmdb_language)
    if client is None:
        # 本端点不抛错, 而是把成因作为可读状态返回给设置页（「测试连接」）。
        # status 直接就是那个成因 —— 设置页按它分支, 所以成因只有一个来源。
        return {
            "success": False,
            "status": reason,
            "message": _UNAVAILABLE_MESSAGES["test"][reason],
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
