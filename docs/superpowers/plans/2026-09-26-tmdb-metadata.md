# TMDB 单集元数据集成 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每集标题真正来自 TMDB —— 解析出 `(剧名, 季, 集)` 后查该集真实标题，填入 `ParsedInfo.title`，使模板变量 `{title}` 从死字段（`backend/app/models/file.py:26` 定义、`parser.py` 从不赋值、`template.py:49-50` 永远渲染空串）变成可用字段。

**Architecture:** 三层分离 —— `tmdb_client` 只管 HTTP 与鉴权分流，`tmdb_resolver` 负责按 `(剧名, 季)` 分组去重、缓存与降级判定，API 层把解析结果与覆盖项合并后交给 resolver。TMDB 的标题必须在**模板渲染之前**到手（`{title}` 是渲染输入之一），因此预览路由改为两遍：先解析拿 `(剧名, 季, 集)`，批量查 TMDB，再把标题并进 `overrides` 交给 `build_rename_plan` 渲染。

**Tech Stack:** Python 3.9+ / FastAPI / Pydantic 2 / httpx / pytest；Vue 3 + Pinia

**Spec:** `docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md`（§4–§7、§10–§12、§13 的前五组测试）

**本条计划是两期中的第一期。** 第二期（NFO 生成）在 `docs/superpowers/plans/2026-09-26-nfo-generation.md`，依赖本期的 `TmdbResolver` 输出。本期交付后应可独立验证「每集标题确实来自 TMDB」。

## Global Constraints

- **`first_air_date_year` 是 TMDB `/search/tv` 的年份参数名，不是 `year`**（spec §5.2）。传 `year` 会被静默忽略，年份消歧失效且无任何报错。
- **TMDB 故障绝不阻断重命名**（spec §5.4）。除 401（配置错误，必须让用户看见）外，一切异常在文件级被捕获并转为降级状态。
- **绝不猜测**（spec §7）。状态非 `matched` 时不回填 `title`。静默写错标题比明确报错危险得多。
- **默认配置下不发起任何网络请求**：`tmdb_api_key` 默认空字符串 → 功能降级为 `disabled` → 现有测试与现有行为零影响。
- 缓存键必须含 API Key 指纹（spec §6.2），否则用户换 Key 后会命中旧缓存，表现为「改了设置却不生效」。
- **不新增运行时依赖**。`httpx` 已在 `requirements.txt`。测试用 `httpx.MockTransport`，异步测试用标准库 `asyncio.run`，**不引入 `pytest-asyncio`**。
- 不得改动 API 路径、方法，或既有响应字段的语义。新字段一律追加。
- 所有新请求字段默认 `None` / `False`，老客户端不传时行为与改动前逐字节一致。

## Review Focus

以下是 spec 隐含、但容易被实现者漏掉、且最可能咬到真实用户的输入。每条对应的测试已挂在拥有该代码的任务里：

1. **用户填的是 v4 Read Access Token（`eyJ` 开头）而非 v3 hex Key** —— TMDB 设置页上「API Read Access Token」和「API Key」并排显示，用户抄错是高频事件。期望：自动走 `Authorization: Bearer` 路径并成功；若错填 v4 token 到 v3 分支，服务端返回 401 而用户完全无从判断原因。
2. **Key 完全无效** —— 期望：预览返回 400 与中文说明。**不得**静默降级成 `disabled`（用户会以为功能没做），也**不得** 500。
3. **完全未配置 Key** —— 期望：功能降级为 `disabled`，预览照常返回全部既有字段、重命名照常可用、不报错、不发任何网络请求。
4. **剧名归一化既不能误合并、也不能重复查询** —— 同一部剧因大小写或全角半角差异必须命中同一缓存（否则每集都重复打 TMDB）；不同剧必须分开（否则标题会串到别的剧上）。
5. **番剧绝对集号导致 `episode_not_found`** —— 期望：标该状态、`{title}` 渲染为空串、文件名照常生成、**不**写错标题、重命名仍成功。

## File Structure

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `backend/app/models/tmdb.py` | TMDB 领域模型（纯数据，无行为） | 新建 |
| `backend/app/core/tmdb_client.py` | TMDB HTTP 客户端：鉴权分流、错误分级 | 新建 |
| `backend/app/core/tmdb_resolver.py` | 分组去重、进程级缓存、六态降级 | 新建 |
| `backend/app/core/parser.py` | 文件名解析 | 新增 `apply_override`（从两个 renamer 中提取，消除重复） |
| `backend/app/core/local_renamer.py` | 本地重命名计划与执行 | 用 `apply_override` 替换内联的覆盖逻辑 |
| `backend/app/core/openlist_renamer.py` | OpenList 重命名计划 | 同上；**并补上缺失的 `override.title` 处理** |
| `backend/app/config.py` | 全局配置 | 新增 5 个 `tmdb_*` 项 |
| `backend/app/models/api.py` | 请求模型 | 两个 Request 各加 3 个可选字段 |
| `backend/app/api/tmdb.py` | TMDB 辅助端点 | 新建（`/test`、`/search`） |
| `backend/app/api/renamer.py` | 三个重命名路由 | 预览改两遍解析；执行/干跑合并标题 |
| `backend/app/main.py` | 应用装配 | 注册 tmdb 路由 |
| `frontend/src/stores/settingsSchema.js` | 设置默认值 / 归一化 | 新增 `tmdb` 分组 |
| `frontend/src/stores/settings.js` | 设置 store | `apply` / `toObject` 带 tmdb |
| `frontend/src/views/SettingsView.vue` | 设置页 | 新增 TMDB 面板 |
| `frontend/src/api/tmdb.js` | axios 封装 | 新建 |
| `frontend/src/components/TmdbMatchDialog.vue` | 剧集搜索重选 | 新建 |
| `frontend/src/stores/workspace.js` | 工作区状态 | 下发 tmdb 配置、预览行扩展、`rematchShow` |
| `frontend/src/components/FileTable.vue` | 预览表 | 新增「标题」列与「TMDB」列 |
| `frontend/src/views/HomeView.vue` | 页面装配 | 挂载 `TmdbMatchDialog` |
| `frontend/scripts/check-settings-schema.mjs` | 前端设置断言脚本 | 扩展 tmdb 断言 |

---

### Task 1: TMDB 领域模型与客户端

建立 TMDB 的全部数据形状与网络层。鉴权分流与错误分级是本任务的核心 —— 它们是后续所有任务的依赖。

**Files:**
- Create: `backend/app/models/tmdb.py`
- Create: `backend/app/core/tmdb_client.py`
- Create: `backend/tests/test_tmdb_client.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces:
  - `app.models.tmdb.TmdbSearchItem` —— 字段 `tv_id: int`、`name: str`、`original_name: str`、`year: Optional[int]`
  - `app.models.tmdb.TmdbEpisode` —— 字段 `episode_number: int`、`name: str`、`overview: str`、`air_date: Optional[str]`、`rating: Optional[float]`、`tmdb_id: Optional[int]`
  - `app.models.tmdb.TmdbSeason` —— 字段 `season_number: int`、`name: str`、`overview: str`、`air_date: Optional[str]`、`tmdb_id: Optional[int]`、`episodes: dict[int, TmdbEpisode]`
  - `app.models.tmdb.TmdbShow` —— 字段 `tv_id: int`、`name: str`、`original_name: str`、`year: Optional[int]`、`overview: str`、`rating: Optional[float]`、`votes: Optional[int]`、`genres: list[str]`、`premiered: Optional[str]`、`status: str`
  - `app.core.tmdb_client.TmdbAuthError` / `TmdbNotFoundError` / `TmdbUnavailableError` —— 三个异常类
  - `app.core.tmdb_client.TmdbClient(api_key, language="zh-CN", timeout=10.0, transport=None)`
    - `cache_fingerprint() -> str`
    - `is_v4_token() -> bool`
    - `async search_tv(query: str, year: Optional[int] = None) -> list[TmdbSearchItem]`
    - `async get_tv_detail(tv_id: int) -> TmdbShow`
    - `async get_season(tv_id: int, season_number: int) -> TmdbSeason`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_tmdb_client.py`：

```python
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
    #
    # 必须先捕获原函数：lambda 体内的 `asyncio.sleep` 是运行时按模块属性查找的，
    # 一旦 patch 生效它就指向 lambda 自己 —— 直接写 lambda _s: asyncio.sleep(0)
    # 会无限递归（RecursionError），且请求只发出 1 次，测试以错误的方式失败。
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _s: real_sleep(0))

    captured = []
    client = TmdbClient("k", transport=_transport(captured, {}, 429))
    with pytest.raises(TmdbUnavailableError):
        asyncio.run(client.search_tv("x"))

    assert len(captured) == 2, "429 应重试一次（共 2 次请求）"


def test_429_then_success_returns_result(monkeypatch):
    real_sleep = asyncio.sleep  # 同上：先捕获，否则无限递归
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tmdb_client.py -v
```

预期：全部 FAIL，报 `ModuleNotFoundError: No module named 'app.models.tmdb'`

- [ ] **Step 3: 建立 TMDB 领域模型**

创建 `backend/app/models/tmdb.py`：

```python
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TmdbSearchItem(BaseModel):
    tv_id: int
    name: str = ""
    original_name: str = ""
    year: Optional[int] = None


class TmdbEpisode(BaseModel):
    episode_number: int
    name: str = ""
    overview: str = ""
    air_date: Optional[str] = None
    rating: Optional[float] = None
    tmdb_id: Optional[int] = None


class TmdbSeason(BaseModel):
    season_number: int
    name: str = ""
    overview: str = ""
    air_date: Optional[str] = None
    tmdb_id: Optional[int] = None
    episodes: dict[int, TmdbEpisode] = Field(default_factory=dict)


class TmdbShow(BaseModel):
    tv_id: int
    name: str = ""
    original_name: str = ""
    year: Optional[int] = None
    overview: str = ""
    rating: Optional[float] = None
    votes: Optional[int] = None
    genres: list[str] = Field(default_factory=list)
    premiered: Optional[str] = None
    status: str = ""
```

- [ ] **Step 4: 实现客户端**

创建 `backend/app/core/tmdb_client.py`：

```python
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

            return response.json()

        raise last_error or TmdbUnavailableError("TMDB 限流")

    async def search_tv(self, query: str, year: Optional[int] = None) -> list[TmdbSearchItem]:
        params: dict = {"query": query}
        if year is not None:
            # 参数名是 first_air_date_year，不是 year。传 year 会被静默忽略。
            params["first_air_date_year"] = year

        data = await self._get("/search/tv", **params)
        items = []
        for raw in data.get("results") or []:
            air_date = raw.get("first_air_date")
            items.append(TmdbSearchItem(
                tv_id=raw["id"],
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
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_tmdb_client.py -v
```

预期：14 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/tmdb.py backend/app/core/tmdb_client.py backend/tests/test_tmdb_client.py
git commit -m "feat(backend): TMDB 客户端与领域模型（鉴权自动分流 / 错误分级 / 429 退避）"
```

---

### Task 2: 解析器 —— 分组去重、缓存与六态降级

本任务实现本期最核心的逻辑。请求数必须从 O(文件数) 降到 O(剧数 + 季数)，且六种降级状态全部显式。

**Files:**
- Create: `backend/app/core/tmdb_resolver.py`
- Create: `backend/tests/test_tmdb_resolver.py`

**Interfaces:**
- Consumes: `TmdbClient` 与三个异常类（Task 1）；`TmdbShow` / `TmdbSeason` / `TmdbEpisode`（Task 1）
- Produces:
  - `app.core.tmdb_resolver.normalize_show_name(name: str) -> str`
  - 六个状态常量：`STATUS_MATCHED` / `STATUS_DISABLED` / `STATUS_SHOW_NOT_FOUND` / `STATUS_SEASON_NOT_FOUND` / `STATUS_EPISODE_NOT_FOUND` / `STATUS_UNAVAILABLE`
  - `app.core.tmdb_resolver.ResolveRequest(show_name: str, season: Optional[int], episode: Optional[int])` —— frozen dataclass
  - `app.core.tmdb_resolver.EpisodeMatch(status: str, show: Optional[TmdbShow], season: Optional[TmdbSeason], episode: Optional[TmdbEpisode])` —— dataclass
  - `app.core.tmdb_resolver.TmdbCache(ttl: int, clock=time.monotonic)` —— `get(key)` / `put(key, value)` / `async get_or_create(key, factory)` / `clear()`
  - `app.core.tmdb_resolver.TmdbResolver(client, overrides=None, cache=None)`
    - `async resolve_many(requests: list[ResolveRequest]) -> list[EpisodeMatch]`
  - **假客户端契约**：`TmdbResolver` 依赖 `client` 暴露 `cache_fingerprint() -> str`、`language: str`、`async search_tv(query, year=None)`、`async get_tv_detail(tv_id)`、`async get_season(tv_id, season_number)`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_tmdb_resolver.py`：

```python
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
    """计数器 + 固定响应的假客户端。断言请求次数靠它，不碰网络。"""

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
        # 这个让出点不是装饰。没有它，`test_concurrent_same_key_is_merged` 里
        # asyncio.gather 的两个任务无法交错 —— 整个 TmdbCache 的锁被删掉该测试
        # 依然通过，即它零鉴别力。有了它，无锁版本会观察到 2 次 search 调用。
        await asyncio.sleep(0)
        self.calls["search"].append(query)
        if self._fail == "search":
            raise TmdbUnavailableError("boom")
        return list(self._hits)

    async def get_tv_detail(self, tv_id):
        await asyncio.sleep(0)
        self.calls["detail"].append(tv_id)
        return self._show

    async def get_season(self, tv_id, season_number):
        await asyncio.sleep(0)
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
    # 同一分组的并发请求应合并为一次外部调用（spec §6.3）。
    #
    # 这条测试的有效性依赖 FakeClient 里的 `await asyncio.sleep(0)`：
    # 假客户端若从不让出控制权，gather 的两个任务无法交错，把 TmdbCache 的锁
    # 整个删掉测试照样通过。改动 FakeClient 时不要把那个让出点去掉。
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tmdb_resolver.py -v
```

预期：全部 FAIL，报 `ModuleNotFoundError: No module named 'app.core.tmdb_resolver'`

- [ ] **Step 3: 实现解析器**

创建 `backend/app/core/tmdb_resolver.py`：

```python
from __future__ import annotations

import asyncio
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional

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


# Task 3 会改为 settings.tmdb_cache_ttl —— 那里才给 config.py 加上这个字段
_DEFAULT_CACHE = TmdbCache(ttl=3600)


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
                return await self._client.search_tv(query)

            try:
                hits = await self._cache.get_or_create(key, fetch_search)
            except TmdbUnavailableError:
                return STATUS_UNAVAILABLE

            if not hits:
                return STATUS_SHOW_NOT_FOUND
            tv_id = hits[0].tv_id

        detail_key = ("show",) + scope + (tv_id,)

        async def fetch_detail():
            return await self._client.get_tv_detail(tv_id)

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
            return await self._client.get_season(tv_id, season_number)

        try:
            return await self._cache.get_or_create(key, fetch_season)
        except TmdbNotFoundError:
            return None
        except TmdbUnavailableError:
            raise
```

**注意 `_DEFAULT_CACHE` 的一处临时写法**：`settings.tmdb_cache_ttl` 要到 Task 3 Step 1 才存在，本任务先用字面量：

```python
# Task 3 会改为 settings.tmdb_cache_ttl —— 那里才给 config.py 加上这个字段
_DEFAULT_CACHE = TmdbCache(ttl=3600)
```

Task 3 Step 1 除了加配置项，还会把这一行改回 `settings.tmdb_cache_ttl`。照着走即可，不要在本任务提前去改 `config.py`（Task 1 的边界是客户端，配置项属于 Task 3）。

- [ ] **Step 4: 运行测试确认通过，并用变异验证并发测试真的有效**

```bash
cd backend && python -m pytest tests/test_tmdb_resolver.py -v
```

预期：23 passed

接着必须做一次变异验证 —— 这是本任务唯一一处「测试的有效性无法从通过与否看出来」的地方：

1. 临时把 `TmdbCache.get_or_create` 里的 `async with self._lock:` 去掉（连同其下的双检 `get`，改为直接 `value = await factory()`），
2. 重跑本文件 → `test_concurrent_same_key_is_merged` **必须 FAILED**（观察到 2 次 search 调用），
3. 恢复实现，确认 sha1 未变，重跑 → 23 passed。

若第 2 步没有失败，说明 `FakeClient` 的让出点丢了或锁的作用被绕过，必须先修测试再继续。
把变异前、变异中、恢复后三次的输出都写进报告。

**注意 stale `.pyc`**：变异版与恢复版若大小相同且在同一秒内写回，CPython 按「源文件 mtime 整秒 + 大小」判失效，会继续跑变异字节码。变异前后各清一次 `__pycache__` 与 `.pytest_cache`，并用 sha1 确认恢复到位。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/tmdb_resolver.py backend/tests/test_tmdb_resolver.py
git commit -m "feat(backend): TMDB 解析器（分组去重 / 进程级缓存 / 六态降级）"
```

---

### Task 2 补充：外部数据边界守卫（审查轮追加）

**这一节是审查的产物，不在原始计划里。** 三个独立审查者在不同轮次指出同一件事：TMDB 的响应是外部输入，畸形 payload 会以枚举不完的方式抛出未分类异常 —— `get_season` 里 `int(number)` 的 `ValueError`、`genres` 数组里的 `null`、200 却回非对象……这些都不属于 `TmdbAuthError` / `TmdbNotFoundError` / `TmdbUnavailableError` 三者，因此会穿过 `resolve_many` 一路到路由，让**整个预览请求 500**，违反全局约束「TMDB 故障绝不阻断重命名」。

早先的应对思路是在 `tmdb_client._get` 的 return 处加一处 `isinstance(data, dict)` 守卫来单点关闭整类。**那个思路是错的**：`int(number)` 在**映射层**，不在请求层，`_get` 的守卫覆盖不到它。要满足措辞为「绝不」的分类性要求，只能在外来数据进入 resolver 的那一层做宽捕获 —— 而外部数据边界正是宽捕获惯用且正确的地方（不同于在内部逻辑里吞异常）。

**Files:**
- Modify: `backend/app/core/tmdb_resolver.py`
- Modify: `backend/tests/test_tmdb_resolver.py`

**Interfaces:**
- Produces: `TmdbResolver._guarded(call: Callable)` —— `@staticmethod`，await 传入的无参协程工厂；`TmdbAuthError` 与 `TmdbNotFoundError` / `TmdbUnavailableError` 原样 re-raise，其余异常包成 `TmdbUnavailableError`（`from exc` 保留原因链）
- **不得**修改 `backend/app/core/tmdb_client.py` —— 分类发生在请求边界，降级语义属于 resolver

- [ ] **Step A: 加守卫**

在 `TmdbResolver` 里加：

```python
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
```

`Callable` 已在该文件顶部从 `typing` 导入（`TmdbCache` 用作 clock 的类型），无需新增 import。

再把三处客户端调用改为经守卫：

```python
            return await self._guarded(lambda: self._client.search_tv(query))
```

```python
            return await self._guarded(lambda: self._client.get_tv_detail(tv_id))
```

```python
            return await self._guarded(
                lambda: self._client.get_season(tv_id, season_number)
            )
```

**不要按字面理解成「除 `TmdbAuthError` 外任何异常都压平」。** 那会连 `TmdbNotFoundError` 一起压掉，`season_not_found` 与 `unavailable` 的区分随之消失 —— 实测该做法会让 `test_season_not_found` 以 `assert 'unavailable' == 'season_not_found'` 失败。要归并的是**未分类**的异常。

- [ ] **Step B: 写失败的三条契约测试**

这三条钉住守卫的两端边界。

先给 `FakeClient` 的 `fail` 增加两个取值，并在类 docstring 里登记（现有 `"search"` / `"season"` 抛 `TmdbUnavailableError`）：

```python
        if self._fail == "auth":
            raise TmdbAuthError("TMDB API Key 无效")
        if self._fail == "value":
            # 畸形 payload 在映射层炸出的未分类异常，如 int(None)
            raise ValueError("invalid literal for int() with base 10: None")
```

（加在 `search_tv` 里 `"search"` 分支之后。`FakeClient` 的 `__init__` 签名不变。）

测试文件的 import 区要把 `TmdbAuthError` 一并引入：

```python
from app.core.tmdb_client import (
    TmdbAuthError,
    TmdbNotFoundError,
    TmdbUnavailableError,
)
```

再补三条用例（沿用文件里既有的 `resolve()` 辅助函数）：

```python
def test_auth_error_propagates_out_of_resolve_many():
    # 唯一的例外。Key 无效是配置错误，必须让用户看见 —— 吞成 unavailable 会让
    # 「Key 填错了」伪装成「TMDB 挂了」，用户永远查不出来。
    # 这条断言是唯一拦得住它的东西：把守卫改成 except TmdbAuthError 后返回
    # unavailable（变异 C），只有本用例失败（DID NOT RAISE），其余全绿。
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
```

注意第三条自己传了显式 `cache=`，因此不受 autouse fixture 的影响路径干扰 —— 它要断言的正是「同一个 cache 实例上失败不留下痕迹」，必须与 fixture 隔离的默认缓存放开。

- [ ] **Step C: 跑测试**

```bash
cd backend && python -m pytest tests/test_tmdb_resolver.py -v
```

预期：26 passed（23 原有 + 3 新增）

- [ ] **Step D: 变异验证**

守卫的价值无法从「测试通过」看出来 —— 必须证明它在被移除时会失败。做三组：

| 变异 | 期望 |
|---|---|
| A 去掉宽捕获分支 | `test_unclassified_error_is_degraded_not_raised` FAILED |
| B 把 `TmdbNotFoundError` 也压成 unavailable | `test_season_not_found` FAILED（`assert 'unavailable' == 'season_not_found'`） |
| C 让守卫吞掉 `TmdbAuthError` | `test_auth_error_propagates_out_of_resolve_many` FAILED（DID NOT RAISE） |

每组记录：变异前 sha1 → 变异后 sha1 → 观察到的失败输出 → 恢复后 sha1（须与变异前一致）。
变异前后各清一次 `__pycache__` 与 `.pytest_cache` —— 变异版与恢复版大小相同且同一秒写回时，CPython 会继续跑变异字节码。

- [ ] **Step E: 提交**

```bash
git add backend/app/core/tmdb_resolver.py backend/tests/test_tmdb_resolver.py
git commit -m "fix(backend): 外部数据边界加守卫，未分类异常降级为 unavailable"
```

---

### Task 3: 配置、请求模型与预览路由接入

把解析器接进请求链路。关键约束：TMDB 标题必须在模板渲染**之前**到手，因此预览改两遍解析。

**Files:**
- Modify: `backend/app/config.py:32`（在 `openlist_request_interval` 之后）
- Modify: `backend/app/models/api.py:34-56`（两个 Request）
- Modify: `backend/app/core/parser.py`（新增 `apply_override`）
- Modify: `backend/app/core/local_renamer.py:40-52`
- Modify: `backend/app/core/openlist_renamer.py:24-34`
- Modify: `backend/app/api/renamer.py:1-105`
- Create: `backend/tests/test_template_title.py`
- Modify: `backend/tests/test_rename_routes.py`（追加用例）

**Interfaces:**
- Consumes: `TmdbClient` / `TmdbAuthError`（Task 1）；`TmdbResolver` / `ResolveRequest` / 六个状态常量（Task 2）
- Produces:
  - `app.config.settings.tmdb_api_key` / `tmdb_language` / `tmdb_enabled` / `tmdb_timeout` / `tmdb_cache_ttl`
  - `app.core.parser.apply_override(info: ParsedInfo, override: Optional[OverrideInfo]) -> ParsedInfo`
  - `RenamePreviewRequest` / `RenameExecuteRequest` 新增 `tmdb_api_key` / `tmdb_language` / `tmdb_overrides`
  - `app.api.renamer._tmdb_client_from_request(req) -> Optional[TmdbClient]`
  - `app.api.renamer._with_tmdb_titles(req, files) -> tuple[dict[str, dict], dict[str, dict]]`
  - 预览响应行新增 `title` / `tmdb_status` / `tmdb_match`

- [ ] **Step 1: 加配置项，并把缓存 TTL 接上配置**

编辑 `backend/app/config.py`，在 `openlist_request_interval: float = 0.5` 之后插入：

```python

    # TMDB 集成。api_key 为空 = 未配置 = 功能整体降级为 disabled,
    # 不发任何网络请求, 重命名行为与改动前完全一致。
    tmdb_api_key: str = ""
    tmdb_language: str = "zh-CN"
    tmdb_enabled: bool = True
    tmdb_timeout: float = 10.0
    tmdb_cache_ttl: int = 3600
```

编辑 `backend/app/core/tmdb_resolver.py`，把 Task 2 里那处临时的字面量改回配置：

```python
# 改前
# Task 3 会改为 settings.tmdb_cache_ttl —— 那里才给 config.py 加上这个字段
_DEFAULT_CACHE = TmdbCache(ttl=3600)

# 改后
_DEFAULT_CACHE = TmdbCache(ttl=settings.tmdb_cache_ttl)
```

并在该文件的 import 区把 `settings` 加回来（放在 `from ..models.tmdb import ...` 之前）：

```python
from ..config import settings
from ..models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow
```

- [ ] **Step 2: 给请求模型加字段**

编辑 `backend/app/models/api.py`，把 `RenamePreviewRequest` 与 `RenameExecuteRequest` 替换为：

```python
class RenamePreviewRequest(BaseModel):
    file_ids: list[str]
    template: str
    folder_template: str = ""
    create_season_folder: bool = False
    overrides: dict[str, dict] = Field(default_factory=dict)
    source: str = "local"
    path: str = ""
    episode_pad_digits: Optional[int] = None
    season_pad_digits: Optional[int] = None
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)


class RenameExecuteRequest(BaseModel):
    file_ids: list[str]
    template: str
    folder_template: str = ""
    create_season_folder: bool = False
    overrides: dict[str, dict] = Field(default_factory=dict)
    source: str = "local"
    path: str = ""
    conflict_strategy: str = "skip"
    episode_pad_digits: Optional[int] = None
    season_pad_digits: Optional[int] = None
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 3: 写失败的测试（`{title}` 与覆盖优先级）**

创建 `backend/tests/test_template_title.py`：

```python
from app.core.template import apply_template
from app.models.file import ParsedInfo


TEMPLATE = "{show} - S{season_padded}E{episode_padded} - {title}{extension}"


def make_info(title=None):
    return ParsedInfo(
        show_name="绝命毒师",
        season=2,
        episode=5,
        title=title,
        extension=".mkv",
        original_filename="Breaking.Bad.S02E05.mkv",
    )


def test_title_renders_when_present():
    result = apply_template(TEMPLATE, make_info("Breakage"))
    assert result == "绝命毒师 - S02E05 - Breakage.mkv"


def test_title_renders_empty_when_absent():
    # Review Focus 5：TMDB 没查到时 title 为 None。
    # 期望是文件名照常生成、标题位留空 —— 而不是整个重命名失败。
    result = apply_template(TEMPLATE, make_info(None))
    assert result == "绝命毒师 - S02E05 - .mkv"


def test_template_without_title_variable_is_unaffected():
    result = apply_template("{show} - S{season_padded}E{episode_padded}{extension}", make_info("Breakage"))
    assert result == "绝命毒师 - S02E05.mkv"
```

- [ ] **Step 4: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_template_title.py -v
```

预期：**三个用例全部 PASS**。

注意这里**不是** RED：`{title}` 自 `d6f01a7` 起就已在 `template.py` 的 `_resolve_variable` 里实现（`return info.title or ""`），本文件是**刻画测试**，钉住既有渲染行为。真正的缺口不在模板层，而在**解析器从不给 `ParsedInfo.title` 赋值**（`parse_filename` 全文不写 `title`）—— 那个缺口由本任务的路由层（Step 8 的两遍解析）补上，并在 `test_rename_routes.py` 的新用例里验证。

不要因为「RED 阶段没红」而以为实现错了。

- [ ] **Step 5: 抽取 `apply_override`**

编辑 `backend/app/core/parser.py`，在 `batch_parse_filenames` 之后追加：

```python
def apply_override(
    info: ParsedInfo,
    override: Optional[OverrideInfo] = None,
) -> ParsedInfo:
    """把用户覆盖写进解析结果。就地修改并返回。

    提取自 local_renamer / openlist_renamer 里两份逐字重复的内联代码 ——
    预览路由现在也要走这一步（两遍解析的第一遍）, 第四份复制粘贴就该收敛了。
    """
    if not override:
        return info
    for field in ("show_name", "season", "episode", "title"):
        value = getattr(override, field)
        if value is not None:
            setattr(info, field, value)
    return info
```

并在文件顶部的 import 中加入 `OverrideInfo`：

```python
from ..models.file import ParsedInfo, OverrideInfo
```

- [ ] **Step 6: 两个 renamer 改用 `apply_override`**

编辑 `backend/app/core/local_renamer.py`：

把第 13 行的 import 改为（只是加上 `apply_override`，另外两个名字仍在使用，必须保留）：

```python
from .parser import apply_override, parse_filename, _SEASON_DIR_PATTERNS
```

把 `build_rename_plan` 中第 40-50 行替换为：

```python
    parsed = apply_override(parse_filename(file.filename, file.parent_dir), override)
```

编辑 `backend/app/core/openlist_renamer.py`：

把第 10 行的 import 改为：

```python
from .parser import apply_override, parse_filename
```

把 `build_openlist_rename_plan` 中第 24-32 行替换为：

```python
    # 注意: 这里此前漏了 override.title —— 于是 OpenList 源下手动填的标题
    # 永远进不了文件名。apply_override 一并修好。
    parsed = apply_override(parse_filename(file.filename, file.parent_dir), override)
```

- [ ] **Step 7: 运行既有测试确认无回归**

```bash
cd backend && python -m pytest tests/ -v
```

预期：既有用例全部 PASS（`test_rename_routes.py` 的 10 个、`test_template_pad.py` 的 7 个、`test_pad_config.py` 的 9 个）。`test_template_title.py` 中 `test_title_renders_when_present` 现在应 PASS。

若有 FAIL，先修本步骤的改动，**不要**进入 Step 8 —— 覆盖逻辑被两个 renamer 共用，这里坏了会波及所有重命名。

- [ ] **Step 8: 预览路由改两遍解析**

编辑 `backend/app/api/renamer.py`。

在 import 区加入：

```python
from ..core.parser import apply_override, parse_filename
from ..core.tmdb_client import TmdbAuthError, TmdbClient
from ..core.tmdb_resolver import (
    STATUS_DISABLED,
    STATUS_MATCHED,
    EpisodeMatch,
    ResolveRequest,
    TmdbResolver,
)
```

在 `_pad_from_request` 之后加入两个辅助函数：

```python
def _tmdb_client_from_request(req) -> Optional[TmdbClient]:
    """未启用或未配置 Key 时返回 None —— 调用方据此降级为 disabled, 不发任何请求。"""
    if not settings.tmdb_enabled:
        return None
    key = req.tmdb_api_key if req.tmdb_api_key is not None else settings.tmdb_api_key
    if not key:
        return None
    return TmdbClient(
        api_key=key,
        language=req.tmdb_language or settings.tmdb_language,
        timeout=settings.tmdb_timeout,
    )


def _tmdb_summary(status: str, match: Optional[EpisodeMatch] = None) -> dict:
    show = match.show if match else None
    return {
        "status": status,
        "tv_id": show.tv_id if show else None,
        "name": show.name if show else None,
        "original_name": show.original_name if show else None,
        "year": show.year if show else None,
    }


async def _with_tmdb_titles(
    req, files: list[FileInfo]
) -> tuple[dict[str, dict], dict[str, dict]]:
    """查 TMDB 并把标题并进 overrides。

    返回 (合并后的 overrides, 每文件的 TMDB 摘要)。

    **手动指定的 title 永远优先于 TMDB** —— 这也是 episode_not_found 的兜底手段。
    """
    merged: dict[str, dict] = {
        f.id: dict(req.overrides.get(f.id) or {}) for f in files
    }
    summaries: dict[str, dict] = {}

    client = _tmdb_client_from_request(req)
    if client is None:
        for f in files:
            summaries[f.id] = _tmdb_summary(STATUS_DISABLED)
        return merged, summaries

    # 用「覆盖之后」的解析结果去查 TMDB：用户手改的剧名/季/集才是他想要的那一部
    parsed: dict[str, ParsedInfo] = {}
    for f in files:
        raw = req.overrides.get(f.id) or {}
        parsed[f.id] = apply_override(
            parse_filename(f.filename, f.parent_dir),
            OverrideInfo(**raw) if raw else None,
        )

    resolver = TmdbResolver(client, overrides=req.tmdb_overrides)
    try:
        matches = await resolver.resolve_many([
            ResolveRequest(
                show_name=parsed[f.id].show_name,
                season=parsed[f.id].season,
                episode=parsed[f.id].episode,
            )
            for f in files
        ])
    except TmdbAuthError as exc:
        # 401 是配置错误, 必须让用户看见 —— 不可静默降级成 disabled。
        # 直接用异常自带的消息: 它已经是「TMDB API Key 无效」, 再拼前缀会重复一遍。
        raise HTTPException(status_code=400, detail=str(exc))

    for f, match in zip(files, matches):
        summaries[f.id] = _tmdb_summary(match.status, match)
        if match.status == STATUS_MATCHED and match.episode and match.episode.name:
            if not merged[f.id].get("title"):
                merged[f.id]["title"] = match.episode.name

    return merged, summaries
```

把 `/rename/preview` 路由函数体替换为：

```python
@router.post("/rename/preview")
async def preview_rename(req: RenamePreviewRequest):
    files = find_files_by_ids(req.file_ids)
    pad = _pad_from_request(req)
    source = req.source.lower()

    # 两遍解析的原因: {title} 是模板的渲染输入之一, 所以 TMDB 的标题必须在
    # build_rename_plan 渲染之前到手。第一遍只解析拿 (剧名, 季, 集), 批量查完
    # TMDB 后再把标题并进 overrides, 第二遍才渲染。
    merged, summaries = await _with_tmdb_titles(req, files)

    results: list[dict] = []
    for f in files:
        overrides = merged.get(f.id) or {}
        override = OverrideInfo(**overrides) if overrides else None

        if source == "local":
            from ..core.local_renamer import build_rename_plan
            plan = build_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
        elif source == "openlist":
            plan = build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
        else:
            raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

        summary = summaries.get(f.id) or _tmdb_summary(STATUS_DISABLED)
        results.append({
            "original_path": plan.original_path,
            "original_filename": plan.original_filename,
            "new_path": plan.new_path,
            "new_filename": plan.new_filename,
            "has_conflict": plan.original_filename == plan.new_filename,
            "conflicts": plan.conflicts,
            "show_name": plan.parsed.show_name if plan.parsed else None,
            "season": plan.parsed.season if plan.parsed else None,
            "episode": plan.parsed.episode if plan.parsed else None,
            "title": plan.parsed.title if plan.parsed else None,
            "confidence": plan.parsed.parse_confidence if plan.parsed else 0,
            "needs_review": plan.parsed.needs_manual_review if plan.parsed else False,
            "tmdb_status": summary["status"],
            "tmdb_match": {
                "tv_id": summary["tv_id"],
                "name": summary["name"],
                "original_name": summary["original_name"],
                "year": summary["year"],
            } if summary["tv_id"] else None,
        })

    return {
        "success": True,
        "source": req.source,
        "total": len(results),
        "results": results,
    }
```

在文件顶部 import 区把 `from ..models.file import (...)` 补上 `ParsedInfo`：

```python
from ..models.file import (
    FileInfo, ParsedInfo, RenamePlan, BatchRenameResult, OverrideInfo,
)
```

- [ ] **Step 9: 执行与干跑路由合并标题**

在 `/rename/execute` 路由中，把 `if source == "local":` 之前插入：

```python
    merged, _summaries = await _with_tmdb_titles(req, files)
    effective_overrides = merged
```

并把 `local_batch_rename(...)` 的 `overrides=req.overrides` 改为 `overrides=effective_overrides`。

该路由内 OpenList 分支的 `ov = req.overrides.get(f.id)` 改为：

```python
            ov = effective_overrides.get(f.id)
```

在 `/rename/dry-run` 路由中做同样的三处改动。

- [ ] **Step 10: 写路由测试**

在 `backend/tests/test_rename_routes.py` 末尾追加下面的用例，并在文件顶部 import 区加上：

```python
from app.core.tmdb_client import TmdbAuthError, TmdbClient
```

```python
TITLE_TEMPLATE = "{show} - S{season_padded}E{episode_padded} - {title}{extension}"


def test_no_tmdb_key_degrades_to_disabled(client):
    # Review Focus 3：完全未配置 Key。功能降级, 重命名与既有字段完全不受影响。
    row = preview(client, template=TITLE_TEMPLATE)
    assert row["tmdb_status"] == "disabled"
    assert row["tmdb_match"] is None
    assert row["new_filename"] == "Test Show - S01E02 - .mkv"


def test_manual_title_override_wins_over_tmdb(client):
    # 手动填的 title 优先 —— 也是 episode_not_found 的兜底手段
    row = preview(client, template=TITLE_TEMPLATE,
                  overrides={"f1": {"show_name": "Test Show", "season": 1,
                                    "episode": 2, "title": "手工标题"}})
    assert row["title"] == "手工标题"
    assert row["new_filename"] == "Test Show - S01E02 - 手工标题.mkv"


def test_invalid_tmdb_key_returns_400_not_silent_disabled(client, monkeypatch):
    # Review Focus 2：Key 无效必须报错, 不得静默降级成 disabled ——
    # 静默会让用户以为「功能没做」而不是「我填错了」。
    #
    # 本用例**密闭, 不发起任何网络调用**。链路两端各有归属:
    # 「真实 401 → TmdbAuthError」由 Task 1 的 test_401_raises_auth_error
    # （MockTransport 回 401）覆盖; 这里只证明后半段「TmdbAuthError → 400」。
    # 之前那版直接打真 TMDB, 换台机器或断网就会红, 在单元套件里是
    # 构造性的不稳定, 故改为让客户端在鉴权点抛同名异常。
    async def fake_search_tv(self, query, year=None):
        raise TmdbAuthError("TMDB API Key 无效")

    monkeypatch.setattr(TmdbClient, "search_tv", fake_search_tv)

    res = client.post("/api/rename/preview", json={
        "file_ids": ["f1"],
        "template": TITLE_TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
        "tmdb_api_key": "definitely-invalid",
    })
    assert res.status_code == 400, res.text
    assert "TMDB" in res.json()["detail"]
    # 文案不再重复前缀（异常自带的这句已含 "TMDB" 与「无效」）
    assert res.json()["detail"] == "TMDB API Key 无效"


def test_tmdb_overrides_are_accepted_by_the_request_model(client):
    # 只验证请求模型接受字段且不 422（未配 Key 时不会真的去查）
    res = client.post("/api/rename/preview", json={
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
        "tmdb_overrides": {"Test Show": 1396},
    })
    assert res.status_code == 200, res.text
```

- [ ] **Step 11: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/ -v
```

预期：全部 PASS，且**整套不发起任何外部网络请求** —— 本任务的所有新用例都用 monkeypatch 或 fixture 隔离了 TMDB。

若某个用例在离线环境下失败，那是缺陷而不是环境问题：把它改成密闭的，**不要**放宽断言、**不要**加 `@pytest.mark.network`、**不要**为测试给生产代码加注入口。

- [ ] **Step 12: 确认服务仍可导入**

```bash
cd backend && python -c "from app.main import app; print('路由数:', len(app.routes))"
```

预期：正常输出，无 ImportError

- [ ] **Step 13: 提交**

```bash
git add backend/app/config.py backend/app/models/api.py backend/app/core/parser.py \
        backend/app/core/local_renamer.py backend/app/core/openlist_renamer.py \
        backend/app/api/renamer.py backend/tests/test_template_title.py \
        backend/tests/test_rename_routes.py
git commit -m "feat(backend): 预览与执行接入 TMDB 单集标题（两遍解析 + 手动覆盖优先）"
```

---

### Task 3 补充：三条有鉴别力的用例（审查轮追加）

**这一节是审查的产物。** 上面 Step 10 那四条用例有一个盲区：它们在两种**坏实现**下**全部通过** ——

- **退回单遍解析**（先渲染文件名、再查 TMDB）：四条全绿，因为断言只看 `tmdb_status` 与 `title` 字段，不看**渲染出的文件名**。
- **无条件覆盖**（忽略手动标题、TMDB 有结果就写）：`test_manual_title_override_wins_over_tmdb` 依然绿，因为那个用例**没有配置 TMDB**（`tmdb_status` 是 `disabled`，压根没东西可覆盖）。

也就是说，「`{title}` 真的来自 TMDB」与「手动标题真的优先」这两条**本任务的核心承诺**，当时没有任何东西守着。下面三条补上。

同时补上状态常量的**字面值**断言：别处的测试全部引用常量本身，互换任意两个常量的值一个测试都不会红，而这六个字符串是预览响应字段与前端分支共享的线上契约。

**Files:**
- Modify: `backend/tests/test_rename_routes.py`

**Interfaces:**
- Consumes: `app.api.renamer._tmdb_client_from_request`（Step 8 定义）、`app.core.tmdb_resolver` 的六个状态常量、`app.models.tmdb` 的四个模型

- [ ] **Step A: 补 import**

测试文件需要新增：

```python
from app.core.tmdb_resolver import (
    STATUS_DISABLED,
    STATUS_EPISODE_NOT_FOUND,
    STATUS_MATCHED,
    STATUS_SEASON_NOT_FOUND,
    STATUS_SHOW_NOT_FOUND,
    STATUS_UNAVAILABLE,
)
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbSearchItem, TmdbShow
```

（`STATUS_EPISODE_NOT_FOUND` 等未在本文件直接使用的常量也要导入 —— 字面值断言要的就是「六个都钉住」，缺一个就等于没钉。）

- [ ] **Step B: 加离线替身与 fixture**

```python
class _FakeTmdbClient:
    """离线替身: 固定返回「Test Show」第 1 季第 2 集「Breakage」, 不碰网络。"""

    language = "zh-CN"

    def cache_fingerprint(self):
        return "fake-client"

    async def search_tv(self, query, year=None):
        return [TmdbSearchItem(tv_id=1396, name=query, original_name=query, year=2008)]

    async def get_tv_detail(self, tv_id):
        return TmdbShow(tv_id=tv_id, name="Test Show", original_name="Test Show", year=2008)

    async def get_season(self, tv_id, season_number):
        return TmdbSeason(season_number=season_number, episodes={
            2: TmdbEpisode(episode_number=2, name="Breakage"),
        })


@pytest.fixture
def fake_tmdb(monkeypatch):
    from app.api import renamer as renamer_api

    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )
```

替身同时提供 `language` 与 `cache_fingerprint()` —— 那是 `TmdbResolver._scope()` 组装缓存键时要的两个成员，缺了会在构造缓存键时 `AttributeError`。

- [ ] **Step C: 加三条用例**

```python
def test_tmdb_title_reaches_the_rendered_filename(client, fake_tmdb):
    # 这是本任务的核心断言: {title} 是模板输入, 所以标题必须在渲染之前拿到。
    # 单遍解析（先渲染再查 TMDB）会让这一条红 —— 上面那些用例全都不会。
    row = preview(client, template=TITLE_TEMPLATE)
    assert row["tmdb_status"] == "matched"
    assert row["title"] == "Breakage"
    assert row["new_filename"] == "Test Show - S01E02 - Breakage.mkv"
    assert row["tmdb_match"]["tv_id"] == 1396
    assert row["tmdb_match"]["year"] == 2008


def test_tmdb_title_does_not_override_a_manual_title(client, fake_tmdb):
    # 与上一个用例的区别: TMDB 确实查到了 (matched), 手动标题仍然赢。
    row = preview(client, template=TITLE_TEMPLATE,
                  overrides={"f1": {"show_name": "Test Show", "season": 1,
                                    "episode": 2, "title": "手工标题"}})
    assert row["tmdb_status"] == "matched"
    assert row["new_filename"] == "Test Show - S01E02 - 手工标题.mkv"


def test_tmdb_status_literals_are_the_wire_contract():
    # 这六个字符串是前后端共享的线上契约: 预览响应的 tmdb_status 字段与前端分支
    # 都按字面值判等, 而别处的测试全部引用常量本身 —— 互换任意两个常量的值
    # 一个测试都不会红。所以在这里逐字钉死。
    # "disabled" 尤其重要: 它不由解析器产出, 只由路由在未配置 Key 时产出,
    # 是最容易被顺手改名的一个。
    assert STATUS_MATCHED == "matched"
    assert STATUS_DISABLED == "disabled"
    assert STATUS_SHOW_NOT_FOUND == "show_not_found"
    assert STATUS_SEASON_NOT_FOUND == "season_not_found"
    assert STATUS_EPISODE_NOT_FOUND == "episode_not_found"
    assert STATUS_UNAVAILABLE == "unavailable"
```

- [ ] **Step D: 变异验证**

这三条的价值同样无法从「测试通过」看出来。做两组变异并记录 sha1 往返：

| 变异 | 期望 |
|---|---|
| A 去掉标题合并（`_with_tmdb_titles` 里不把 `match.episode.name` 写进 `merged`） | `test_tmdb_title_reaches_the_rendered_filename` FAILED（`None == 'Breakage'`） |
| B 改成无条件覆盖（`merged[f.id]["title"] = ...`，去掉「已有则不填」的判断） | `test_tmdb_title_does_not_override_a_manual_title` FAILED（保留 Breakage 而非「手工标题」） |

- [ ] **Step E: 跑测试并提交**

```bash
cd backend && python -m pytest tests/ -v
```

预期：全部 PASS，且整套**不发起任何外部网络请求**。

```bash
git add backend/tests/test_rename_routes.py
git commit -m "test(backend): 补三条有鉴别力的用例（{title} 真来自 TMDB / 手动标题优先 / 状态字面值契约）"
```

---

### Task 4: TMDB 辅助端点

设置页的「测试连接」与重选对话框的搜索都要用。Key 走请求头而非查询串 —— 查询串会进访问日志。

**Files:**
- Create: `backend/app/api/tmdb.py`
- Modify: `backend/app/main.py:25-31`
- Create: `backend/tests/test_tmdb_routes.py`

**Interfaces:**
- Consumes: `TmdbClient` / 三个异常类（Task 1）
- Produces:
  - `GET /api/tmdb/test` —— 请求头 `X-Tmdb-Key`、`X-Tmdb-Language`；返回 `{success, status, auth_mode, sample}`，`status` 取 `ok` / `invalid_key` / `unreachable` / `not_configured`
  - `GET /api/tmdb/search?q=&year=` —— 同上请求头；返回 `{success, data: [TmdbSearchItem]}`
  - `app.api.tmdb.router`（`prefix="/api/tmdb"`），已在 `main.py` 注册

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_tmdb_routes.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tmdb_routes.py -v
```

预期：全部 FAIL，报 404（路由不存在）

- [ ] **Step 3: 实现路由**

创建 `backend/app/api/tmdb.py`：

```python
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..core.tmdb_client import (
    TmdbAuthError,
    TmdbClient,
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
    except TmdbUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"success": True, "data": [h.model_dump() for h in hits]}
```

- [ ] **Step 4: 注册路由**

编辑 `backend/app/main.py`，把第 25 行的 import 改为：

```python
from .api import scanner, parser, renamer, template, openlist, tmdb
```

并在 `app.include_router(openlist.router)` 之后加：

```python
app.include_router(tmdb.router)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_tmdb_routes.py -v
```

预期：5 passed

- [ ] **Step 6: 运行全量测试确认无回归**

```bash
cd backend && python -m pytest tests/ -v
```

预期：全部 PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/api/tmdb.py backend/app/main.py backend/tests/test_tmdb_routes.py
git commit -m "feat(backend): TMDB 测试连接与剧集搜索端点（Key 走请求头, 不落访问日志）"
```

---

### Task 5: 前端设置存储与断言

把 TMDB 三项设置纳入既有的「localStorage → 随请求下发」链路（spec §10.4）。这个项目有过「设置写进去没人读」的前科，故本任务的断言脚本是必需的，不是可选的。

**Files:**
- Modify: `frontend/src/stores/settingsSchema.js:15-27,44-71`
- Modify: `frontend/src/stores/settings.js:31-56`
- Modify: `frontend/scripts/check-settings-schema.mjs`

**Interfaces:**
- Consumes: 无（纯前端）
- Produces:
  - `defaultSettings().tmdb` —— `{ apiKey: '', language: 'zh-CN', enabled: true }`
  - `normalizeSettings(raw).tmdb` —— 三项各自类型防御后归一
  - `settingsStore.tmdb` —— reactive 对象，字段同上，由 `apply` / `toObject` 同步

- [ ] **Step 1: 扩展断言脚本（先写失败断言）**

在 `frontend/scripts/check-settings-schema.mjs` 的 `// --- 旧字段名迁移` 之前插入：

```javascript
// --- TMDB 分组 ---
assert('tmdb 默认未配置', defaultSettings().tmdb, { apiKey: '', language: 'zh-CN', enabled: true })
assert('tmdb 半残缺也能补全', normalizeSettings({ tmdb: { apiKey: 'k' } }).tmdb,
  { apiKey: 'k', language: 'zh-CN', enabled: true })
assert('只给一个字段不影响 tmdb 完整性',
  normalizeSettings({ conflictStrategy: 'abort' }).tmdb,
  { apiKey: '', language: 'zh-CN', enabled: true })

// --- tmdb 字段的类型防御（localStorage 里的值可能被手工改坏）---
assert('apiKey 非字符串回落空串', normalizeSettings({ tmdb: { apiKey: 123 } }).tmdb.apiKey, '')
assert('apiKey 为空串时保持空串', normalizeSettings({ tmdb: { apiKey: '' } }).tmdb.apiKey, '')
assert('language 非字符串回落 zh-CN', normalizeSettings({ tmdb: { language: 42 } }).tmdb.language, 'zh-CN')
assert('language 为空串回落 zh-CN', normalizeSettings({ tmdb: { language: '   ' } }).tmdb.language, 'zh-CN')
assert('enabled 非布尔回落 true', normalizeSettings({ tmdb: { enabled: 'yes' } }).tmdb.enabled, true)
assert('enabled false 被保留', normalizeSettings({ tmdb: { enabled: false } }).tmdb.enabled, false)

// --- tmdb 往返读写 ---
const tmdbStorage = fakeStorage()
writeSettings(tmdbStorage, { ...defaultSettings(), tmdb: { apiKey: 'secret', language: 'ja-JP', enabled: false } })
assert('写盘后读回 apiKey', readSettings(tmdbStorage).tmdb.apiKey, 'secret')
assert('写盘后读回 language', readSettings(tmdbStorage).tmdb.language, 'ja-JP')
assert('写盘后读回 enabled', readSettings(tmdbStorage).tmdb.enabled, false)
```

- [ ] **Step 2: 运行断言脚本确认失败**

```bash
cd frontend && node scripts/check-settings-schema.mjs
```

预期：新增断言 FAIL，报 `得到 {"apiKey":..., "language":...}` 之类与期望不符；脚本以退出码 1 结束。

- [ ] **Step 3: 实现 `settingsSchema.js`**

编辑 `frontend/src/stores/settingsSchema.js`。

把 `defaultSettings` 替换为：

```javascript
export function defaultSettings() {
  return {
    defaultTemplateId: 'emby_standard',
    episodePadDigits: 2,
    seasonPadDigits: 2,
    conflictStrategy: 'skip',
    // TMDB 未配置时 enabled 仍为 true —— 后端在 api_key 为空时自行降级为 disabled。
    // 前端把「未配置」与「已禁用」当成两件事，用户才知道该去填 Key 还是该去打开开关。
    tmdb: {
      apiKey: '',
      language: 'zh-CN',
      enabled: true,
    },
    openlist: {
      serverUrl: '',
      concurrency: 3,
      requestInterval: 0.5,
    },
  }
}
```

把 `normalizeSettings` 中的 `const openlist = ...` 之后、`const templateId = ...` 之前插入：

```javascript
  const tmdb = (raw.tmdb && typeof raw.tmdb === 'object' && !Array.isArray(raw.tmdb))
    ? raw.tmdb
    : {}
```

并把 `return { ... }` 替换为：

```javascript
  return {
    defaultTemplateId: templateId,
    episodePadDigits: clampNumber(raw.episodePadDigits, PAD_MIN, PAD_MAX, def.episodePadDigits, true),
    seasonPadDigits: clampNumber(raw.seasonPadDigits, PAD_MIN, PAD_MAX, def.seasonPadDigits, true),
    conflictStrategy: CONFLICT_STRATEGIES.includes(raw.conflictStrategy)
      ? raw.conflictStrategy
      : def.conflictStrategy,
    tmdb: {
      apiKey: asString(tmdb.apiKey, def.tmdb.apiKey),
      // 只有「非空字符串」才算有效语言。空串与纯空白都回落到默认，
      // 否则会把空语言下发给 TMDB，拿到的是原语言数据而用户以为设置了中文。
      language: (typeof tmdb.language === 'string' && tmdb.language.trim())
        ? tmdb.language.trim()
        : def.tmdb.language,
      enabled: typeof tmdb.enabled === 'boolean' ? tmdb.enabled : def.tmdb.enabled,
    },
    openlist: {
      serverUrl: asString(openlist.serverUrl, def.openlist.serverUrl),
      concurrency: clampNumber(openlist.concurrency, 1, 10, def.openlist.concurrency, true),
      requestInterval: clampNumber(openlist.requestInterval, 0.1, 5, def.openlist.requestInterval),
    },
  }
```

- [ ] **Step 4: 实现 `stores/settings.js`**

编辑 `frontend/src/stores/settings.js`。

在 `const openlist = reactive({ ...initial.openlist })` 之后加：

```javascript
  const tmdb = reactive({ ...initial.tmdb })
```

把 `apply` 替换为：

```javascript
  function apply(data) {
    const next = normalizeSettings(data)
    defaultTemplateId.value = next.defaultTemplateId
    episodePadDigits.value = next.episodePadDigits
    seasonPadDigits.value = next.seasonPadDigits
    conflictStrategy.value = next.conflictStrategy
    tmdb.apiKey = next.tmdb.apiKey
    tmdb.language = next.tmdb.language
    tmdb.enabled = next.tmdb.enabled
    openlist.serverUrl = next.openlist.serverUrl
    openlist.concurrency = next.openlist.concurrency
    openlist.requestInterval = next.openlist.requestInterval
  }
```

把 `toObject` 替换为：

```javascript
  function toObject() {
    return {
      defaultTemplateId: defaultTemplateId.value,
      episodePadDigits: episodePadDigits.value,
      seasonPadDigits: seasonPadDigits.value,
      conflictStrategy: conflictStrategy.value,
      tmdb: { ...tmdb },
      openlist: { ...openlist },
    }
  }
```

把返回对象里的 `openlist,` 改为：

```javascript
    conflictStrategy, tmdb, openlist,
```

（即把原来的 `defaultTemplateId, episodePadDigits, seasonPadDigits, conflictStrategy, openlist,` 一行替换为带 `tmdb` 的版本。）

- [ ] **Step 5: 运行断言脚本确认通过**

```bash
cd frontend && node scripts/check-settings-schema.mjs
```

预期：全部 PASS，末行输出「全部通过」，退出码 0

- [ ] **Step 6: 确认既有断言无回归**

```bash
cd frontend && node scripts/check-settings-schema.mjs && node scripts/check-sfc-compile.mjs
```

预期：两个脚本均通过

- [ ] **Step 7: 提交**

```bash
git add frontend/src/stores/settingsSchema.js frontend/src/stores/settings.js frontend/scripts/check-settings-schema.mjs
git commit -m "feat(frontend): 设置存储纳入 TMDB 分组（含类型防御与断言）"
```

---

### Task 6: 设置页 TMDB 面板

**Files:**
- Modify: `frontend/src/api/tmdb.js`（新建）
- Modify: `frontend/src/views/SettingsView.vue:41-79`

**Interfaces:**
- Consumes: `settingsStore.tmdb`（Task 5）
- Produces:
  - `frontend/src/api/tmdb.js` 导出 `testTmdb({ apiKey, language })`、`searchTmdb({ q, year, apiKey, language })`
  - 设置页新增「TMDB 设置」面板

- [ ] **Step 1: 建立 API 封装**

创建 `frontend/src/api/tmdb.js`：

```javascript
import request from './request'

// Key 走请求头而不是查询串 —— 查询串会进服务端访问日志。
export function testTmdb({ apiKey, language }) {
  return request.get('/tmdb/test', {
    headers: {
      'X-Tmdb-Key': apiKey || '',
      'X-Tmdb-Language': language || '',
    },
  })
}

export function searchTmdb({ q, year, apiKey, language }) {
  return request.get('/tmdb/search', {
    params: { q, year },
    headers: {
      'X-Tmdb-Key': apiKey || '',
      'X-Tmdb-Language': language || '',
    },
  })
}
```

- [ ] **Step 2: 设置页新增面板**

编辑 `frontend/src/views/SettingsView.vue`，在「OpenList 设置」那个 `</AppPanel>` 之后、`<AppPanel title="说明">` 之前插入：

```html
      <AppPanel title="TMDB 设置">
        <div class="flex flex-col gap-4">
          <AppInput
            v-model="draft.tmdb.apiKey"
            type="password"
            label="API Key"
            placeholder="v3 API Key 或 v4 Read Access Token"
            hint="两种都支持：32 位 Key 走查询参数，eyJ 开头的 Token 走 Bearer 头。留空则用服务端 .env 的配置。"
          />
          <AppSelect v-model="draft.tmdb.language" label="元数据语言">
            <option value="zh-CN">中文 (zh-CN)</option>
            <option value="zh-TW">繁體中文 (zh-TW)</option>
            <option value="ja-JP">日本語 (ja-JP)</option>
            <option value="en-US">English (en-US)</option>
          </AppSelect>
          <AppCheckbox
            v-model="draft.tmdb.enabled"
            label="启用 TMDB 元数据（查找每集真实标题）"
          />

          <div class="flex items-center gap-3">
            <AppButton variant="secondary" :loading="testing" @click="testConnection">
              <Plug class="h-4 w-4" aria-hidden="true" />
              测试连接
            </AppButton>
            <span v-if="testResult" class="text-[12px]" :class="testResult.ok ? 'text-ink-2' : 'text-warn'">
              {{ testResult.message }}
            </span>
          </div>
        </div>
      </AppPanel>
```

在 `<script setup>` 的 import 区把 lucide 图标补上 `Plug`：

```javascript
import { Info, Plug, RotateCcw, Save } from 'lucide-vue-next'
```

并加上：

```javascript
import { testTmdb } from '../api/tmdb'
import AppCheckbox from '../components/ui/AppCheckbox.vue'
```

（若 `AppCheckbox` 已在别处导入则不重复。）

在 `const savedFlash = ref('')` 之后加：

```javascript
const testing = ref(false)
const testResult = ref(null)
```

并在 `reset()` 之前加：

```javascript
async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    const res = await testTmdb({
      apiKey: draft.tmdb.apiKey,
      language: draft.tmdb.language,
    })
    const data = res.data || {}
    const messages = {
      ok: data.sample ? `连接正常（${data.auth_mode}，示例：${data.sample}）` : '连接正常',
      not_configured: '未配置 API Key —— 请在下方填入，或由服务端通过 .env 提供',
      invalid_key: 'API Key 无效，请检查是否复制完整',
      unreachable: '无法访问 TMDB，请检查网络',
      disabled: 'TMDB 已被服务端禁用（tmdb_enabled = false）',
    }
    testResult.value = { ok: data.status === 'ok', message: messages[data.status] || data.message || '未知状态' }
  } catch (e) {
    testResult.value = { ok: false, message: '测试失败: ' + (e.response?.data?.detail || e.message) }
  } finally {
    testing.value = false
  }
}
```

- [ ] **Step 3: 确认组件可编译**

```bash
cd frontend && node scripts/check-sfc-compile.mjs
```

预期：通过（该脚本校验所有 SFC 能编译）

- [ ] **Step 4: 构建确认无语法错误**

```bash
cd frontend && npm run build
```

预期：构建成功，无错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/tmdb.js frontend/src/views/SettingsView.vue
git commit -m "feat(frontend): 设置页新增 TMDB 面板（Key / 语言 / 启用 / 测试连接）"
```

---

### Task 7: 工作区接线、预览表与重选对话框

本任务把 TMDB 配置真正下发到后端（review focus 里「设置不生效」的防线），并把匹配结果呈现在预览表里、提供重选入口。

**Files:**
- Modify: `frontend/src/stores/workspace.js:270-305,359-402,421-434`
- Modify: `frontend/src/components/FileTable.vue:52-77,122-186`
- Create: `frontend/src/components/TmdbMatchDialog.vue`
- Modify: `frontend/src/views/HomeView.vue:54-107,109-139`

**Interfaces:**
- Consumes: `settingsStore.tmdb`（Task 5）；`searchTmdb`（Task 6）；预览响应的 `title` / `tmdb_status` / `tmdb_match`（Task 3）
- Produces:
  - `workspaceStore.tmdbOverrides`（reactive 对象，剧名 → tv_id）
  - `workspaceStore.rematchShow(row)` —— 打开重选对话框
  - `workspaceStore.tmdbDialog`（`{ open, row, query, results, loading }`）
  - `previewRows` 每行新增 `title` / `tmdb_status` / `tmdb_match`
  - `TmdbMatchDialog` 组件，props `modelValue` / `row` / `results` / `loading`，emits `search` / `pick` / `update:modelValue`

- [ ] **Step 1: 工作区新增 TMDB 状态与下发**

编辑 `frontend/src/stores/workspace.js`。

在 `const olForm = reactive({ ... })` 之后加：

```javascript
  // 剧名 -> tv_id。用户重选后写入, 随每次预览/执行下发。
  // 键用 show_name **原文**（预览行上那个），后端会做归一化后匹配 ——
  // 若这里用归一化形式，后端拿到后又归一化一次，两侧对不上就静默失效。
  const tmdbOverrides = reactive({})

  const tmdbDialog = reactive({
    open: false,
    row: null,
    query: '',
    results: [],
    loading: false,
  })
```

在 `buildPreview` 的 `previewRename({...})` 调用里，于 `season_pad_digits` 之后加三行：

```javascript
        tmdb_api_key: settingsStore.tmdb.apiKey,
        tmdb_language: settingsStore.tmdb.language,
        tmdb_overrides: { ...tmdbOverrides },
```

在 `previewRows.value = filesStore.files.map(...)` 的返回对象里，于 `override: {},` 之前加：

```javascript
          title: pv.title || '',
          tmdb_status: pv.tmdb_status || 'disabled',
          tmdb_match: pv.tmdb_match || null,
```

在 `updatePreview(row)` 里，把 `row.override = {...}` 替换为：

```javascript
  function updatePreview(row) {
    row.override = {
      show_name: row.show_name,
      season: row.season,
      episode: row.episode,
      // 空串必须传 null 而不是 ''：后端 apply_override 用 `is not None` 判断,
      // 传 '' 会把手动标题写成空串, 覆盖掉 TMDB 查到的标题。
      title: row.title ? row.title : null,
    }
  }
```

在 `executeAction` 的请求体里，同样于 `season_pad_digits` 之后加：

```javascript
        tmdb_api_key: settingsStore.tmdb.apiKey,
        tmdb_language: settingsStore.tmdb.language,
        tmdb_overrides: { ...tmdbOverrides },
```

在 `executeAction` 之后加：

```javascript
  function rematchShow(row) {
    tmdbDialog.row = row
    tmdbDialog.query = row.show_name || ''
    tmdbDialog.results = []
    tmdbDialog.open = true
    if (tmdbDialog.query) searchShow()
  }

  async function searchShow(query) {
    const q = (typeof query === 'string' ? query : tmdbDialog.query) || ''
    if (!q.trim()) return
    tmdbDialog.loading = true
    try {
      const res = await searchTmdb({
        q: q.trim(),
        apiKey: settingsStore.tmdb.apiKey,
        language: settingsStore.tmdb.language,
      })
      tmdbDialog.results = res.data?.data || []
    } catch (e) {
      showToast('搜索失败: ' + (e.response?.data?.detail || e.message), 'error')
      tmdbDialog.results = []
    } finally {
      tmdbDialog.loading = false
    }
  }

  async function pickShow(item) {
    if (!tmdbDialog.row) return
    const showName = tmdbDialog.row.show_name
    if (showName) tmdbOverrides[showName] = item.tv_id
    tmdbDialog.open = false
    await buildPreview()
    showToast(`已选用 ${item.name}${item.year ? ` (${item.year})` : ''}`, 'success')
  }
```

把 `import { previewRename, executeRename, dryRunRename } from '../api/renamer'` 之后加上：

```javascript
import { searchTmdb } from '../api/tmdb'
```

并把返回对象里的 `askConfirm, resolveConfirm, showToast,` 一行替换为：

```javascript
    askConfirm, resolveConfirm, showToast,
    tmdbOverrides, tmdbDialog, rematchShow, searchShow, pickShow,
```

- [ ] **Step 2: 预览表新增「标题」列与「TMDB」列**

编辑 `frontend/src/components/FileTable.vue`。

在表头 `</thead>` 之前，把「状态」列那一行之前插入标题列、之后插入 TMDB 列：

```html
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[180px]">标题</th>
```

放在「集」列之后；并在「状态」列之后插入：

```html
            <th class="hidden px-4 py-3 text-left font-semibold lg:table-cell">TMDB</th>
```

在数据行的「集」`<td>` 之后插入标题单元格：

```html
              <td class="px-4 py-2.5">
                <AppInput
                  v-model="row.title"
                  size="sm"
                  aria-label="集标题"
                  placeholder="TMDB 标题"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
```

在「状态」`<td>` 之后插入 TMDB 单元格：

```html
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div class="flex items-center gap-1.5">
                  <AppBadge :tone="tmdbTone(row.tmdb_status)">
                    {{ tmdbLabel(row.tmdb_status) }}
                  </AppBadge>
                  <button
                    type="button"
                    class="rounded-[6px] p-1 text-ink-3 transition-colors duration-150 hover:bg-sunken hover:text-accent focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
                    :title="row.tmdb_match ? `当前：${row.tmdb_match.name}` : '搜索剧集'"
                    :aria-label="`为 ${row.show_name} 重新选择 TMDB 剧集`"
                    @click="$emit('rematch', row)"
                  >
                    <Search class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
              </td>
```

同时把骨架行（`SKELETON_ROWS` 那段）里补上对应的两个占位 `<td>`：

在骨架行的第六个 `<td>`（集）之后插入：

```html
              <td class="px-4 py-2.5">
                <div class="h-8 w-[120px] rounded-[4px] bg-sunken" />
              </td>
```

在骨架行的「状态」占位之后插入：

```html
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div class="h-6 w-16 rounded-[4px] bg-sunken" />
              </td>
```

在 `<script setup>` 中加上：

```javascript
import { Search } from 'lucide-vue-next'

const TMDB_LABELS = {
  matched: '已匹配',
  disabled: '未启用',
  show_not_found: '未匹配',
  season_not_found: '无此季',
  episode_not_found: '无此集',
  unavailable: '不可用',
}

function tmdbLabel(status) {
  return TMDB_LABELS[status] || '未知'
}

function tmdbTone(status) {
  if (status === 'matched') return 'accent'
  if (status === 'disabled') return 'neutral'
  return 'warn'
}
```

把 `AppBadge` 的 import 补上（模板里已用到它，import 应已在文件中）。

在 `defineEmits` 数组里加入 `'rematch'`：

```javascript
defineEmits([
  'preview-all', 'clear-all', 'toggle-all', 'select-row', 'update-row', 'quick-scan', 'rematch',
])
```

- [ ] **Step 3: 建立重选对话框**

创建 `frontend/src/components/TmdbMatchDialog.vue`。

`AppModal` 只是遮罩 + 焦点陷阱的壳，**卡片样式由调用方提供** —— 这是 `frontend/src/components/BrowseDialog.vue:8-11` 确立的既有模式，照抄它的卡片结构（`max-w-[520px] rounded-[12px] bg-surface shadow-overlay` + 带关闭按钮的头 + `p-5` 体），否则对话框会是一块没有背景、直接贴在遮罩上的裸内容。

```html
<template>
  <AppModal
    :model-value="modelValue"
    title="选择 TMDB 剧集"
    z-index="50"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="w-full max-w-[520px] overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 class="text-[14px] font-semibold text-ink">选择 TMDB 剧集</h2>
        <button
          type="button"
          aria-label="关闭"
          class="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
          @click="$emit('update:modelValue', false)"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div class="p-5">
        <form class="mb-4 flex items-end gap-2" @submit.prevent="$emit('search', query)">
          <AppInput
            v-model="query"
            label="剧名"
            :placeholder="row?.show_name || '输入剧名搜索'"
          />
          <AppButton variant="secondary" type="submit" :loading="loading">搜索</AppButton>
        </form>

        <div v-if="!results.length" class="py-12 text-center text-[13px] text-ink-3">
          {{ loading ? '搜索中…' : '没有结果。换个关键词，或确认 TMDB 已启用。' }}
        </div>

        <ul v-else class="flex max-h-[320px] flex-col gap-1 overflow-y-auto">
          <li v-for="item in results" :key="item.tv_id">
            <button
              type="button"
              class="w-full rounded-[8px] border border-line px-3 py-2 text-left transition-colors duration-150 hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
              @click="$emit('pick', item)"
            >
              <div class="text-[13px] font-medium text-ink">
                {{ item.name }}<span v-if="item.year" class="text-ink-3"> ({{ item.year }})</span>
              </div>
              <div
                v-if="item.original_name && item.original_name !== item.name"
                class="text-[11px] text-ink-3"
              >
                {{ item.original_name }}
              </div>
            </button>
          </li>
        </ul>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

import AppButton from './ui/AppButton.vue'
import AppInput from './ui/AppInput.vue'
import AppModal from './ui/AppModal.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  row: { type: Object, default: null },
  results: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
defineEmits(['update:modelValue', 'search', 'pick'])

const query = ref('')

// 每次打开都把搜索框重置成该行的剧名 —— 上一次残留的关键词会让用户
// 对着一个不属于当前行的搜索结果做选择。
watch(() => props.modelValue, (open) => {
  if (open) query.value = props.row?.show_name || ''
})
</script>
```

- [ ] **Step 4: 在页面挂载对话框并接线**

编辑 `frontend/src/views/HomeView.vue`。

在 `<Toast ... />` 之前插入：

```html
  <TmdbMatchDialog
    v-model="ws.tmdbDialog.open"
    :row="ws.tmdbDialog.row"
    :results="ws.tmdbDialog.results"
    :loading="ws.tmdbDialog.loading"
    @search="ws.searchShow"
    @pick="ws.pickShow"
  />
```

在 `<script setup>` 的 import 区加入：

```javascript
import TmdbMatchDialog from '../components/TmdbMatchDialog.vue'
```

在 `<FileTable>` 的监听列表里加入：

```html
          @rematch="ws.rematchShow"
```

- [ ] **Step 5: 确认可编译并构建**

```bash
cd frontend && node scripts/check-sfc-compile.mjs && npm run build
```

预期：两者均成功

- [ ] **Step 6: 确认新代码进入构建产物**

```bash
cd frontend && grep -rl "tmdb_status" dist/assets/ | head -3
```

预期：至少命中一个文件 —— 证明新代码真的进了产物，而不是被 tree-shake 掉或构建用的是旧源码。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/stores/workspace.js frontend/src/components/FileTable.vue \
        frontend/src/components/TmdbMatchDialog.vue frontend/src/views/HomeView.vue
git commit -m "feat(frontend): 预览表 TMDB 列与剧集重选对话框, TMDB 配置随请求下发"
```

---

## 完成后

### 机械等价验证（可自动化）

```bash
cd backend && python -m pytest tests/ -v
cd frontend && node scripts/check-settings-schema.mjs && node scripts/check-sfc-compile.mjs && npm run build
```

### 端到端验证（deferred-to-human）

以下步骤需要真实 TMDB Key 与浏览器，按项目惯例标为 `deferred-to-human`：

1. 设置页填入有效的 TMDB API Key（v3 或 v4 均可），点「测试连接」→ 应显示 `连接正常（v3_api_key，示例：…）`
2. 工作区扫描一个真实剧集目录（如 `绝命毒师` 的若干集），模板含 `{title}` → 预览表「标题」列应显示每集真实标题，「TMDB」列为「已匹配」
3. 把模板改成 `{show} - S{season_padded}E{episode_padded} - {title}`，「新文件名」列应随之带上标题
4. 点任一行的 🔍，搜索并选用另一部剧 → 预览应整体刷新为那部剧的标题
5. 在「集」列手改一个不存在的集号（如 999）→ 该行「TMDB」列应变为「无此集」，`{title}` 渲染为空，**其余行不受影响**
6. 设置页把 API Key 改成无效值再保存 → 回到工作区点「预览」→ 应弹出 TMDB 配置错误提示，而不是静默无标题
7. 断开网络后预览 → 「TMDB」列应为「不可用」，**重命名仍可正常执行**

## 与下一期的衔接

本期交付后，`TmdbResolver` 的输出（`EpisodeMatch`：`show` / `season` / `episode`）即为第二期 NFO 生成的数据来源。第二期不需要重新查 TMDB —— 它复用同一份缓存与解析结果。

**第二期的第一件事**应是把 `_with_tmdb_titles` 的返回值（每文件的 `EpisodeMatch`）向上暴露给执行路径，供 NFO 构建消费。本期为了让改动最小，执行路径只取了标题、丢弃了 `EpisodeMatch` 的其余部分。

## Self-Review

**Spec 覆盖**

| Spec 节 | 落位 |
|---|---|
| §4 模块结构 | Task 1（client + models）、Task 2（resolver）、Task 4（api/tmdb.py） |
| §5.1 鉴权自动分流 | Task 1 Step 3-4，测试 `test_v4_token_goes_in_authorization_header` |
| §5.2 三个接口 | Task 1 Step 4 |
| §5.3 错误分级 | Task 1 Step 4；401 先抛后由 Task 3 Step 8 转 400 |
| §5.4 不阻断重命名 | Task 2 `test_one_bad_group_does_not_poison_the_others`；Task 3 `test_no_tmdb_key_degrades_to_disabled` |
| §6.1 按 (剧名, 季) 聚合 | Task 2 `test_ten_files_issue_three_requests` |
| §6.2 缓存 + Key 指纹 + TTL | Task 2 `test_cache_survives_across_resolver_instances` / `test_cache_key_includes_api_key_fingerprint` / `test_cache_language_is_part_of_the_key` / `test_cache_expires_after_ttl` |
| §6.3 并发合并 | Task 2 `test_concurrent_same_key_is_merged` |
| §7 六态降级 | Task 2 六个 status 测试 + Task 7 的 `TMDB_LABELS` 六项 |
| §7.1 手动补救（重选 + 手改标题） | Task 3 `test_manual_title_override_wins_over_tmdb`；Task 7 `rematchShow` / `pickShow` |
| §10.1 配置项 | Task 3 Step 1 |
| §10.2 请求字段 | Task 3 Step 2 |
| §10.3 优先级 请求体 > .env > 未配置 | Task 3 Step 8 `_tmdb_client_from_request`；Task 4 `test_header_key_overrides_env_key` / `test_env_key_is_used_when_header_absent` |
| §10.4 下发链路可测 | Task 4 的两个 header 测试 + Task 7 Step 1 的三处下发；`test_tmdb_overrides_are_accepted_by_the_request_model` 钉住字段确实被模型接受 |
| §11 两个端点 + 预览响应新字段 | Task 4；Task 3 Step 8 |
| §12.1 设置页面板 | Task 6 |
| §12.2 设置存储 | Task 5 |
| §12.3 工作区状态 | Task 7 Step 1 |
| §12.4 预览表两列（第三列归第二期） | Task 7 Step 2 |
| §13 前五组测试 | Task 1（client）、Task 2（resolver）、Task 3（template_title + routes）、Task 4（tmdb_routes）；前端断言 Task 5 |
| §15 计划 1 范围 | 全文 |

**占位符扫描**：无 TBD / TODO / 「类似 Task N」。每个代码步骤含完整可粘贴的代码。

**类型一致性**

- `TmdbClient(api_key, language, timeout, transport)` 在 Task 1 定义；Task 3 `_tmdb_client_from_request` 与 Task 4 `_client` 均按位置/关键字使用这四个参数 ✓
- `TmdbResolver(client, overrides=, cache=)` 在 Task 2 定义；Task 3 用 `TmdbResolver(client, overrides=req.tmdb_overrides)` ✓
- `ResolveRequest(show_name, season, episode)` 在 Task 2 定义；Task 3 三处调用字段名一致 ✓
- `EpisodeMatch(status, show, season, episode)` 在 Task 2 定义；Task 3 `_tmdb_summary` 读 `.show` / `.episode` ✓
- 六个状态常量在 Task 2 定义；Task 3 用 `STATUS_DISABLED` / `STATUS_MATCHED`，Task 7 的 `TMDB_LABELS` 键与六个常量逐字一致（`matched` / `disabled` / `show_not_found` / `season_not_found` / `episode_not_found` / `unavailable`）✓
- `apply_override(info, override)` 在 Task 3 Step 5 定义；Step 6 两个 renamer 与 Step 8 预览路由均按此名调用 ✓
- `_with_tmdb_titles(req, files)` 在 Task 3 Step 8 定义；Step 9 在执行与干跑路由调用 ✓
- 前端 `settingsStore.tmdb.{apiKey, language, enabled}` 在 Task 5 定义；Task 6 的 `draft.tmdb.*` 与 Task 7 的下发字段一致 ✓
- 预览响应字段 `tmdb_status` / `tmdb_match` 在 Task 3 Step 8 产生；Task 7 Step 1 消费同名字段 ✓
- `TmdbMatchDialog` 的 props / emits 契约在 Task 7 Step 3 定义，Step 4 的挂载按此接线 ✓

**Review Focus 落位**

| # | 覆盖它的测试 |
|---|---|
| 1 v4 token 抄错 | `test_v4_token_goes_in_authorization_header`、`test_v3_key_goes_in_query_param`（Task 1）；`test_header_key_overrides_env_key`（Task 4） |
| 2 Key 无效必须报错 | `test_401_raises_auth_error`（Task 1）；`test_invalid_tmdb_key_returns_400_not_silent_disabled`（Task 3） |
| 3 未配置 Key 降级 | `test_no_tmdb_key_degrades_to_disabled`（Task 3）；`test_test_endpoint_reports_not_configured`、`test_search_endpoint_requires_key_when_not_configured`（Task 4） |
| 4 归一化不误合并 / 不重复查询 | `test_normalize_keeps_different_shows_apart`、`test_case_variant_show_names_share_one_query`、`test_distinct_shows_are_resolved_separately`（Task 2） |
| 5 番剧绝对集号 | `test_episode_not_found`（Task 2）；`test_title_renders_empty_when_absent`（Task 3） |
