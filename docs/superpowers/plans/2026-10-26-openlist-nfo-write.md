# OpenList 网盘 NFO 写入 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 OpenList 云盘源与本地源一样写出每集 / 剧集级 / 季级 NFO，并跟随旧同前缀 NFO。

**架构：** 把 `nfo_writer` 的决策层参数化为本地 / 远端两套路径规则，新增 `openlist_nfo.py` 专管远端存在性、上传与跟随，路由与前端解除 OpenList 的 NFO 限制。

**技术栈：** Python 3.12 / FastAPI / httpx / pytest；Vue 3 / Pinia / Tailwind。

**规格：** `docs/superpowers/specs/2026-10-26-openlist-nfo-write-design.md`

## 全局约束

- 远端路径一律用 `posixpath`，不得用 `os.path` 或 `pathlib.Path` 推导。
- 上传用 `PUT /api/fs/put`，`File-Path` 头必须 URL 编码，不使用 `As-Task`。
- NFO 的任何失败只进 `nfo_skipped`，绝不改变重命名的成功状态与计数。
- 跳过原因串与本地逐字一致：`已存在`、`该文件未改名, 不写 NFO`、`TMDB 未匹配, 不写残缺 NFO`、`写入失败: ...`、旧 NFO 跟随失败串。
- 字幕（`FileInfo.is_subtitle`）不进入 NFO 管线；判据只看该字段，不嗅扩展名。
- 本地源现有行为不得改变；`build_nfo_decisions` 的默认 `path_mod=os.path` 必须保持向后兼容。
- 不自动执行 `git commit`；提交由用户确认后另行处理。

## 审查重点（Review Focus）

1. **远端目标已存在 + 覆盖关闭**：必须跳过并报 `已存在`，绝不能上传覆盖。
2. **列目录失败**：必须报 `写入失败`，不能当成“不存在”继续上传。
3. **视频移入季目录**：NFO 必须落在 `result.new_path` 的真实目录，而不是原目录或 `plan.new_path`。
4. **字幕与视频解析结果相同**：字幕旁不得产生 `.chs.nfo`，也不得抢占组级决策行。
5. **多剧混放目录**：不得写 `tvshow.nfo`，必须报出拒绝原因。

---

## 任务 1：NFO 决策层支持远端路径与落地筛选

**文件：**
- 修改：`backend/app/core/nfo_writer.py`
- 测试：`backend/tests/test_nfo_plan.py`、`backend/tests/test_nfo_write.py`

**接口：**
- `episode_nfo_path(video_path: str, path_mod=os.path) -> str`
- `common_parent(paths: list[str], path_mod=os.path) -> str`
- `build_nfo_decisions(entries: list[NfoEntry], options: NfoOptions, path_mod=os.path) -> list[NfoDecision]`
- 新增 `entry_from_plan(plan: RenamePlan, nfo_matches: dict[str, EpisodeMatch]) -> NfoEntry`
- 新增 `filter_landed_decisions(decisions, dead_file_ids: set[str], landed_paths: list[str], path_mod=os.path) -> tuple[list[NfoDecision], list[NfoDecision]]`，返回 `(kept, dropped)`。

- [ ] **步骤 1：编写失败的测试**

在 `test_nfo_plan.py` 增加：

```python
def test_build_nfo_decisions_uses_posix_paths_for_remote():
    import posixpath
    decisions = build_nfo_decisions(
        [entry("/media/Show/Show - S01E01.mkv")], OPTIONS, path_mod=posixpath,
    )
    paths = {d.kind: d.path for d in decisions if d.content}
    assert paths["episode"] == "/media/Show/Show - S01E01.nfo"
    assert paths["tvshow"] == "/media/Show/tvshow.nfo"
    assert paths["season"] == "/media/Show/season.nfo"
```

在 `test_nfo_write.py` 增加：

```python
def test_filter_landed_drops_dead_episode_and_group_without_landing():
    decisions = [
        NfoDecision(file_id="f1", kind="episode", path="/m/Show/a.nfo", content="<x/>"),
        NfoDecision(file_id="f2", kind="episode", path="/m/Show/b.nfo", content="<x/>"),
        NfoDecision(file_id="f1", kind="tvshow", path="/m/Show/tvshow.nfo", content="<x/>"),
    ]
    kept, dropped = filter_landed_decisions(decisions, {"f2"}, ["/m/Show/c.mkv"])
    assert [d.file_id for d in kept if d.kind == "episode"] == ["f1"]
    assert [d.kind for d in kept] == ["episode"]
    assert [d.kind for d in dropped] == ["episode", "tvshow"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest tests/test_nfo_plan.py::test_build_nfo_decisions_uses_posix_paths_for_remote tests/test_nfo_write.py::test_filter_landed_drops_dead_episode_and_group_without_landing -v`
预期：FAIL，`build_nfo_decisions` 不接受 `path_mod`、`filter_landed_decisions` 不存在。

- [ ] **步骤 3：实现参数化与筛选**

- 给 `episode_nfo_path` / `common_parent` / `_show_root` / `_folder_belongs_to_single_show` / `build_nfo_decisions` 增加 `path_mod` 参数，函数体内所有 `os.path.*` 改为 `path_mod.*`；`path_mod` 默认 `os.path`。
- `path_mod.basename` / `splitext` / `dirname` / `commonpath` 均存在，`posixpath` 与 `os.path` 接口一致。
- `entry_from_plan` 从 `local_renamer._entry_for` 原样搬迁，保持字段来源不变。
- `filter_landed_decisions` 复刻 `_keep_decision` 的判据：每集按 `file_id` 判活；组级按 `dirname(d.path)` 与 `landed_paths` 的“等于或以目录前缀开头”判活；`path_mod.dirname` 为空时丢弃。

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_nfo_plan.py tests/test_nfo_write.py tests/test_preview_nfo_fields.py -v`
预期：全部 PASS。

---

## 任务 2：本地 NFO 收尾改用共用筛选（行为不变）

**文件：**
- 修改：`backend/app/core/local_renamer.py`
- 测试：`backend/tests/test_nfo_write.py`、`backend/tests/test_rename_finalize_route.py`、`backend/tests/test_single_file_core.py`

- [ ] **步骤 1：记录重构前基线**

运行：`cd backend && python -m pytest tests/test_nfo_write.py tests/test_rename_finalize_route.py tests/test_single_file_core.py -q`
预期：全部 PASS。

- [ ] **步骤 2：替换实现**

- `_keep_decision` 删除；改为导入 `filter_landed_decisions` 与 `entry_from_plan`。
- `_entry_for` 删除，调用点换成 `entry_from_plan`。
- `finalize_show_nfo`：`kept, dropped = filter_landed_decisions(group_decisions, set(), landed_paths)`，为 `dropped` 追加 `_DROPPED_GROUP_NFO_REASON`。
- `batch_rename` 里原 `if _keep_decision(...)` 循环改为 `kept, dropped = filter_landed_decisions(nfo_decisions, dead_file_ids, landed_paths)`，仍只为 `dropped` 中 `kind != "episode"` 的决策追加丢弃原因；每集死行仍走 `dead_episode_paths` 的原有原因。

- [ ] **步骤 3：运行测试验证行为不变**

运行：`cd backend && python -m pytest tests/test_nfo_write.py tests/test_rename_finalize_route.py tests/test_single_file_core.py tests/test_rename_nfo_route.py -q`
预期：全部 PASS，无断言改动。

---

## 任务 3：OpenList 客户端增加流式上传

**文件：**
- 修改：`backend/app/core/openlist_client.py`
- 测试：新建 `backend/tests/test_openlist_client_put.py`

**接口：**
- `async def put_file(self, path: str, content: bytes) -> dict`

- [ ] **步骤 1：编写失败的测试**

```python
def test_put_file_calls_stream_endpoint_with_encoded_path(monkeypatch):
    import asyncio
    from urllib.parse import quote
    import httpx
    import app.core.openlist_client as mod

    calls = []

    class _FakeAsyncClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return False
        async def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return httpx.Response(200, json={"code": 200, "data": None},
                                  request=httpx.Request(method, url))

    client = mod.OpenListClient("http://x", "u", "p")
    client.token = "t"
    client.apply_limits(request_interval=0.0)
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeAsyncClient)

    asyncio.run(client.put_file("/媒体/Show - S01E01.nfo", b"<x/>"))

    method, url, kwargs = calls[0]
    assert method == "PUT" and url.endswith("/api/fs/put")
    assert kwargs["headers"]["File-Path"] == quote("/媒体/Show - S01E01.nfo", safe="")
    assert kwargs["headers"]["Authorization"] == "t"
    assert kwargs["headers"]["Content-Type"] == "application/xml; charset=utf-8"
    assert kwargs["content"] == b"<x/>"


def test_put_file_raises_on_non_200_code(monkeypatch):
    # 假客户端返回 {"code": 500, "message": "failed"}, 断言抛 Exception 且消息含 failed
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest tests/test_openlist_client_put.py -v`
预期：FAIL，`OpenListClient` 没有 `put_file`。

- [ ] **步骤 3：实现 `put_file`**

```python
async def put_file(self, path: str, content: bytes) -> dict:
    data = await self._request(
        "PUT", "/api/fs/put",
        content=content,
        headers={
            "File-Path": quote(path, safe=""),
            "Content-Type": "application/xml; charset=utf-8",
            "Content-Length": str(len(content)),
        },
    )
    if data.get("code") != 200:
        raise Exception(f"上传 NFO 失败: {data.get('message')}")
    return data
```

`quote` 从 `urllib.parse` 导入；`_request` 已负责鉴权、限流与 401 重连。

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_openlist_client_put.py tests/test_openlist_limiter.py -v`
预期：全部 PASS。

---

## 任务 4：新增 `openlist_nfo` 远端写盘模块

**文件：**
- 创建：`backend/app/core/openlist_nfo.py`
- 测试：新建 `backend/tests/test_openlist_nfo.py`

**接口：**
- `async def episode_nfo_for_plan(client, plan: RenamePlan, result: RenameResult, nfo_matches: dict[str, EpisodeMatch], options: NfoOptions) -> tuple[list[str], list[str], list[tuple[str, str]]]`，返回 `(written, carried, skipped)`。
- `async def plan_openlist_nfo(client, plans: list[RenamePlan], results: list[RenameResult], nfo_matches, options) -> tuple[list[str], list[str], list[tuple[str, str]]]`，干跑清单，绝不写盘。
- `async def finalize_openlist_nfo(client, plans: list[RenamePlan], landed_paths: list[str], nfo_matches, options) -> tuple[list[str], list[tuple[str, str]]]`。

**内部：**
- `async def _dir_names(client, directory: str, cache: dict[str, set[str]]) -> set[str]`：一次 `list_directory`，按目录缓存。
- `async def write_remote_nfo_files(client, decisions, overwrite, cache) -> tuple[list[str], list[tuple[str, str]]]`。
- `async def carry_same_stem_nfo(client, original_video_path, new_video_path, cache, dry_run=False) -> tuple[Optional[str], Optional[str]]`。
- `_OPENLIST_CARRY_STATUSES = {"renamed", "renamed_moved", "renamed_fallback", "moved_not_renamed", "dry_run"}`。

- [ ] **步骤 1：编写失败的测试**

`test_openlist_nfo.py` 使用一个 `FakeClient`：`list_directory(path)` 返回 `(list[OpenListFile], True)`、`put_file` / `rename` / `move` 记录调用；用例覆盖：

```python
def test_episode_nfo_uses_real_landed_path(...):
    # plan 原目录 /media/Show, 结果 renamed 到 /media/Show/Season 01/Show - S01E01.mkv
    # 断言 put_file 的 path == "/media/Show/Season 01/Show - S01E01.nfo"

def test_existing_remote_nfo_is_skipped_without_overwrite(...):
    # 目标目录含同名 .nfo → put_file 不调用, skipped == [(path, "已存在")]

def test_overwrite_replaces_existing_remote_nfo(...):
    # overwrite=True → put_file 被调用

def test_carry_moves_old_same_stem_nfo_before_write(...):
    # 旧目录含 Show.S01E01.nfo, 新目录不含 → rename/move 被调用, carried 有落点

def test_carry_refuses_when_target_exists(...):
    # 新目录已含目标 .nfo → 不 move, skipped 含 "旧前缀 NFO 未跟随"

def test_subtitle_is_excluded(...):
    # is_subtitle=True → 三个返回都为空且没有任何调用

def test_not_landed_reports_skip(...):
    # status="failed" → skipped 含 "该文件未改名, 不写 NFO"

def test_missing_metadata_reports_skip(...):
    # matches 为空 → skipped 含 "TMDB 未匹配"

def test_list_failure_is_skipped_not_raised(...):
    # list_directory 抛异常 → skipped 含 "写入失败", 不冒异常

def test_upload_failure_is_skipped_not_raised(...):
    # put_file 抛异常 → skipped 含 "写入失败", 不冒异常
```

再加两条收尾用例：

```python
def test_finalize_writes_tvshow_and_season(...):
    # landed 含真实视频 → 写入 tvshow.nfo 与 season.nfo

def test_finalize_drops_group_when_nothing_landed(...):
    # landed_paths=[] → 不写, skipped 原因为 "该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO"

def test_finalize_refuses_mixed_show_directory(...):
    # 同一远端目录下两部剧的 plan → 不写 tvshow.nfo, skipped 含 "下有多部剧混放"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest tests/test_openlist_nfo.py -v`
预期：FAIL，模块不存在。

- [ ] **步骤 3：实现模块**

关键规则：

- 决策一律 `build_nfo_decisions(..., path_mod=posixpath)`；每集落点用 `episode_nfo_path(result.new_path, path_mod=posixpath)`。
- 顺序：先 `carry_same_stem_nfo`，再 `write_remote_nfo_files`。
- 落地判据复用 `local_renamer.landed_path_of`。
- `write_remote_nfo_files`：
  - `content is None` → 追加 `(path, reason or "无内容")`；
  - 同路径去重；
  - `_dir_names` 抛错 → `(path, f"写入失败: {exc}")`；
  - 文件名已存在且未开覆盖 → `(path, "已存在")`；
  - `put_file` 抛错 → `(path, f"写入失败: {exc}")`；
  - 成功后把文件名写进目录缓存。
- `carry_same_stem_nfo`：
  - `src == dst` 或源不存在 → `(None, None)`；
  - 目标已存在 → `(None, _CARRIED_NFO_TARGET_EXISTS_REASON)`；
  - `dry_run=True` → 只返回 `(dst, None)`；
  - 同目录 `rename(src, dst_name)`；跨目录 `move` 后若名字不同再 `rename`；
  - 失败 → `(None, f"同名 NFO 跟随移动失败: {exc}")`。
- `plan_openlist_nfo`：用 `filter_landed_decisions` 过滤；`planned_carried` 中的落点在未开覆盖时按 `"已存在"` 处理；返回计划清单，不调用 `put_file` / `rename` / `move`。
- `finalize_openlist_nfo`：只取 `kind != "episode"` 的决策，`filter_landed_decisions(..., set(), landed_paths)`，`dropped` 报 `_DROPPED_GROUP_NFO_REASON`，`kept` 交给 `write_remote_nfo_files`。

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_openlist_nfo.py -v`
预期：全部 PASS。

---

## 任务 5：路由解除 OpenList 限制并接入 NFO

**文件：**
- 修改：`backend/app/api/renamer.py`
- 测试：`backend/tests/test_rename_nfo_route.py`、`backend/tests/test_rename_finalize_route.py`、`backend/tests/test_rename_routes.py`

- [ ] **步骤 1：更新失败的路由断言**

- `test_rename_nfo_route.py`：
  - 删除 `test_openlist_source_refuses_nfo` 与 `test_openlist_is_not_an_nfo_capable_source`；
  - 新增 `test_openlist_preview_plans_nfo_with_posix_paths`：`source="openlist"` + `generate_nfo=True` + 命中 TMDB，断言 `row["nfo"]` 的三个键且路径以 `/` 分隔、`nfo_scope == "full"`。
- `test_rename_finalize_route.py`：
  - 删除 `test_openlist_source_returns_empty_without_error`；
  - 新增 `test_openlist_finalize_writes_group_nfo`：monkeypatch `renamer_mod.get_default_client` 为假客户端，`landed` 给真实 OpenList 路径，断言 `nfo_written` 含 tvshow/season。
- 新增 `test_openlist_execute_writes_episode_nfo`：monkeypatch 假客户端，断言 `nfo_written` 含同名 `.nfo`，且 `put_file` 被调用。

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest tests/test_rename_nfo_route.py tests/test_rename_finalize_route.py -q`
预期：新增用例 FAIL，移除的用例不存在不参与。

- [ ] **步骤 3：修改路由**

- 删除 `_nfo_supported` 与所有调用点；`unsupported_source` 分支删除。
- `preview_rename`：OpenList 时 `build_nfo_decisions(..., path_mod=posixpath)`；本地保持默认。
- `execute_rename` OpenList 分支：
  - 取得客户端后执行重命名；
  - `outcome.nfo_written, outcome.nfo_carried, outcome.nfo_skipped = await episode_nfo_for_plan(client, plan, result, matches_by_file, nfo_options)`；
  - `outcome.executed/skipped/failed` 与 `landed_path` 维持现有逻辑。
- `dry_run_rename` OpenList 分支：批跑完后调用 `plan_openlist_nfo(client, plans, result.results, matches_by_file, nfo_options)` 并写回 `result.nfo_written / nfo_carried / nfo_skipped`。
- `finalize_rename`：OpenList 分支取客户端（未连接 401），用 `build_openlist_rename_plan` 建计划，调用 `finalize_openlist_nfo`，返回与本地同形状。

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_rename_nfo_route.py tests/test_rename_finalize_route.py tests/test_rename_routes.py tests/test_rename_single_route.py -q`
预期：全部 PASS。

---

## 任务 6：前端解除置灰与收尾限制

**文件：**
- 修改：`frontend/src/components/TemplateConfig.vue`
- 修改：`frontend/src/stores/workspace.js`
- 修改：`frontend/src/components/FileTable.vue`
- 测试：`frontend/scripts/check-workspace-gating.mjs`、`frontend/scripts/check-execute-behaviour.mjs`

- [ ] **步骤 1：更新前端判据（先失败）**

- `check-workspace-gating.mjs`：把“切到 openlist 会关闭 generateNfo”的期待改为**保持开启**：
  - 切源前 `ws.generateNfo = true`，切到 openlist 后断言仍为 `true`。
- `check-execute-behaviour.mjs`：新增场景：OpenList 源 + `generateNfo=true` 时，执行后 `/rename/finalize` 必须发一次；后端假响应照现有本地场景。

- [ ] **步骤 2：运行判据验证失败**

运行：`cd frontend && node scripts/check-all.mjs`
预期：新增/修改的断言 FAIL。

- [ ] **步骤 3：修改前端**

- `TemplateConfig.vue`：
  - 两个 NFO 勾选框删除 `:disabled="source === 'openlist'"` 与三元文案；
  - `nfoOverwrite` 只看 `!generateNfo`；
  - NFO 说明与“未刮削”提示删除 `source !== 'openlist'` 条件。
- `workspace.js`：
  - `switchSource` 删除 `generateNfo.value = false` 及其注释；
  - `executeAction` 的 finalize 条件改为 `if (generateNfo.value)`。
- `FileTable.vue`：
  - `NFO_SCOPE_HINTS` 删除 `unsupported_source`；
  - `BATCH_NFO_SCOPES` 改为 `new Set(['disabled'])`；
  - 更新上方与 `unsupported_source` 相关的注释。

- [ ] **步骤 4：运行判据验证通过**

运行：`cd frontend && node scripts/check-all.mjs`
预期：全部 PASS。

---

## 任务 7：文档与全量验证

**文件：**
- 修改：`README.md`

- [ ] **步骤 1：更新 README**

- 功能特性里“生成 NFO（仅本地源）”改为“本地与 OpenList 均可生成”；
- 执行接口说明里删掉“仅本地源且开启 NFO 生成时”的限制；
- OpenList 集成段落说明 NFO 依赖远端可写。

- [ ] **步骤 2：后端全量测试**

运行：`cd backend && python -m pytest -q`
预期：全部 PASS。

- [ ] **步骤 3：前端全量判据**

运行：`cd frontend && node scripts/check-all.mjs`
预期：全部 PASS。

- [ ] **步骤 4：构建检查**

运行：`cd frontend && npm run build`
预期：构建成功，无未使用变量报错。
