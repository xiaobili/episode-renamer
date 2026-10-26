# OpenList 网盘 NFO 写入 — 设计规格

- 日期：2026-10-26
- 状态：待实现
- 上游：`2026-09-26-tmdb-metadata-and-nfo-design.md`（§2 曾明确“OpenList 本期不写 NFO”）
- 范围决策：与本地源**完整对齐**（每集 + 剧集级 + 季级 + 旧同前缀 NFO 跟随）

## 1. 目标

让 OpenList 云盘源与本地源拥有同一套 NFO 生成能力：

- 每集 `.nfo` 随 `POST /api/rename/execute` 一起写出；
- `tvshow.nfo` / `season.nfo` 由 `POST /api/rename/finalize` 在批次结束后写出；
- 已存在的**同前缀**旧 `.nfo` 跟随视频改名，避免孤儿；
- 预览、干跑、结果对话框的 NFO 落点与跳过原因与本地一致。

## 2. 不在范围

- OpenList 视频本身的冲突策略（`skip` / `abort` / `rename_dup` / `overwrite`）—— 现状未实现，本次不改。
- NFO 之外的远端文件上传（字幕、图片等）。
- OpenList 上传失败后的自动重试或回滚。
- 本地源 NFO 行为变更。

## 3. 现状与关键事实

| 事实 | 位置 |
| --- | --- |
| NFO 决策是纯函数，已与落盘分离 | `backend/app/core/nfo_writer.py` 的 `build_nfo_decisions` |
| 本地收尾把“筛选未落地”与“写盘”混在一个函数 | `backend/app/core/local_renamer.py` 的 `finalize_show_nfo` / `_keep_decision` |
| OpenList 客户端无上传能力 | `backend/app/core/openlist_client.py` 只有 list/get/mkdir/rename/move/batch_rename |
| 路由用 `_nfo_supported` 挡掉云盘 | `backend/app/api/renamer.py` |
| 前端在云盘源置灰 NFO、切源时强制关闭 | `frontend/src/components/TemplateConfig.vue`、`frontend/src/stores/workspace.js` |
| 前端只为本地源调用 finalize | `frontend/src/stores/workspace.js` |

## 4. 模块设计

### 4.1 `nfo_writer.py` — 共用决策层

- `build_nfo_decisions(entries, options, path_mod=os.path)`：
  - 默认 `os.path` 保持本地行为不变；
  - OpenList 传 `posixpath`，确保远端落点始终用 `/`。
  - `episode_nfo_path` / `common_parent` / 剧集根推导 / 混放校验都接受同一 `path_mod`。
- 新增 `filter_landed_decisions(decisions, dead_file_ids, landed_paths, path_mod=os.path)`：
  - 从 `local_renamer._keep_decision` 抽出；
  - 每集决策按 `file_id` 判活，组级决策按“该目录（含子树）有无真实落地”判活；
  - 本地与云盘共用。

### 4.2 新增 `core/openlist_nfo.py`

云盘 NFO 的唯一副作用入口，全部 `async`：

| 函数 | 职责 |
| --- | --- |
| `async episode_nfo_for_plan(client, plan, result, matches, options)` | 单文件：旧 NFO 跟随 + 每集 NFO 写入，返回 `(written, carried, skipped)` |
| `async batch_nfo_plan(client, plans, matches, options, dry_run)` | 批量干跑：返回将写入 / 将跳过清单，绝不写盘 |
| `async finalize_nfo(client, plans, landed_paths, matches, options)` | 收尾：只写 `tvshow.nfo` / `season.nfo` |

内部约束：

- 目标目录的存在性统一走 `list_directory` 精确匹配文件名，并按目录缓存（`dict[str, set[str]]`）。
- 所有远端路径拼接与父目录推导用 `posixpath`。
- 字幕过滤复用 `FileInfo.is_subtitle`，不在 NFO 层嗅扩展名。
- 跳过原因串与本地逐字一致，前端 `ResultDialog` 的“已存在”提示依赖该字面值。

### 4.3 `openlist_client.py`

新增：

```python
async def put_file(self, path: str, content: bytes) -> dict
```

- 方法：`PUT /api/fs/put`
- 请求头：
  - `File-Path`：`urllib.parse.quote(path, safe="")`；
  - `Content-Type`：`application/xml; charset=utf-8`；
  - `Content-Length`：内容字节数；
  - Authorization 由 `_request` 统一注入。
- 不加 `As-Task`，等待上传完成。
- 返回 `code != 200` 时抛错，由调用方转为 NFO 跳过原因。

### 4.4 路由

- 删除 `_nfo_supported` 及其所有调用点；OpenList 与本地同权。
- `/rename/preview`：
  - OpenList 分支用 `posixpath` 构造决策；
  - `nfo_scope` 只保留 `disabled / episode_only / full`；
  - 预览不访问 OpenList。
- `/rename/execute`：
  - OpenList 分支在执行重命名后调用 `episode_nfo_for_plan`；
  - 响应字段与本地一致：`nfo_written` / `nfo_carried` / `nfo_skipped`。
- `/rename/dry-run`：
  - OpenList 分支构造计划后调用 `batch_nfo_plan(dry_run=True)`；
  - 只做只读目录列举，不写盘。
- `/rename/finalize`：
  - 接受 `source=openlist`；
  - 用 `build_openlist_rename_plan` 重建计划；
  - `landed` 仍只取前端回传的真实落点；
  - 客户端未连接返回 401；
  - 返回形状不变。

## 5. 行为规则

### 5.1 单文件执行顺序

1. 重命名（现有 `execute_openlist_one`）。
2. 若为视频且已落地：**先**搬旧同前缀 `.nfo`，**再**生成每集 NFO。
3. 每集 NFO 落点 = `episode_nfo_path(result.new_path)`，而不是 `plan.new_path`。
4. 未落地：不写，但把落点与原因`该文件未改名, 不写 NFO`放进 `nfo_skipped`。

### 5.2 旧 NFO 跟随

- 只处理与原视频**同前缀**的那一个 `.nfo`。
- 旧文件不存在：什么都不做。
- 新目标已存在：不覆盖，报 `旧前缀 NFO 未跟随: 新名字处已有文件, 覆盖开关不影响跟随`。
- 跨目录：先 `move` 再 `rename`；同目录：直接 `rename`。
- 失败只记跳过，不阻断重命名。

### 5.3 上传与覆盖

- `nfo_overwrite=false` 且远端目标已存在：不写，报 `已存在`。
- `nfo_overwrite=true`：直接上传覆盖。
- 上传失败：报 `写入失败: ...`，重命名结果保持成功。

### 5.4 组级 NFO

- 规则与本地一致：剧集根取公共父目录并按季目录上溯；混放目录拒绝写 `tvshow.nfo`。
- 该剧/该季没有任何文件真实落地时，组级决策丢弃并报
  `该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO`。
- 多剧混放时为组内每个条目发决策、按 `(路径, 原因)` 去重，复用 `dedupe_skipped_pairs`。

## 6. 前端契约

- `TemplateConfig.vue`：NFO 两个勾选框在 OpenList 下不再置灰，删除“OpenList 暂不支持”文案；NFO 说明与“未刮削”提示在云盘源下照常显示。
- `workspace.switchSource`：切到 OpenList 时不再重置 `generateNfo`。
- `workspace.executeAction`：`generateNfo` 为真时，无论源都执行 finalize；`landed` 仍只收后端 `landed_path`。
- `FileTable.vue`：
  - 删除 `unsupported_source` 的文案与批次级成员；
  - `NFO_SCOPE_HINTS` 只保留 `disabled / episode_only / full`。
- 请求与响应字段不新增、不改名。

## 7. 错误处理

- **NFO 永不阻断重命名**：所有远端失败都降级为 `nfo_skipped`。
- 目录列举失败与上传失败分别给出可区分的原因串。
- OpenList 未连接：执行/收尾返回 401；预览不要求连接。
- 上传存在性检查与上传之间存在竞态：单用户工具，接受该窗口；`nfo_overwrite=true` 是用户显式承担覆盖。

## 8. 测试

后端：

| 文件 | 覆盖 |
| --- | --- |
| `test_openlist_client_put.py` | `PUT /api/fs/put`、`File-Path` URL 编码、Authorization、Content-Type/Length、非 200 code |
| `test_openlist_nfo.py` | 存在性缓存、已存在跳过、覆盖、跟随成功/目标已存在、字幕排除、无 TMDB 不写、上传失败降级、未落地不写 |
| `test_rename_nfo_route.py` | OpenList 预览落点与 `nfo_scope`；删除 `unsupported_source` 断言 |
| `test_rename_routes.py` / 新路由用例 | OpenList 执行写每集 NFO、finalize 写 tvshow/season、客户端未连接 401 |
| `test_nfo_plan.py` / `test_nfo_write.py` | 确认 `path_mod` 默认值不改变本地行为；新增 posixpath 用例 |

前端：

- `check-workspace-gating.mjs`：切源不再关闭 `generateNfo`。
- `check-execute-behaviour.mjs`：OpenList 源勾 NFO 时也发 finalize。
- 其余 `check-*.mjs` 保持通过。

## 9. 验收判据

1. 云盘源预览能看到每集、tvshow、season 三类落点。
2. 云盘执行后，远端出现与视频同名的 `.nfo`；`nfo_written` 如实列出。
3. 已存在的同前缀旧 `.nfo` 随视频改名，`nfo_carried` 如实列出。
4. 云盘批次结束后写出 `tvshow.nfo` 与 `season.nfo`；混放目录拒绝写组级 NFO 并报原因。
5. 关覆盖时目标已存在报 `已存在`，不修改远端文件。
6. 任一步 NFO 失败都不影响重命名的成功状态与计数。
7. 本地源现有测试与前端判据全部通过。

## 10. 已知限制

- 远端存在性依赖目录列举，若挂载点目录极大，单次列举成本高于本地 `exists()`。
- 上传接口在部分存储驱动上可能是“任务式”实现；本设计不使用 `As-Task`，超时行为由客户端现有 60 秒超时约束。
- 不支持视频冲突策略，与现状一致。
