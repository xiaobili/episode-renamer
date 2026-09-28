# 重命名执行单文件化与前端进度条设计

日期：2026-09-28
分支：`main`
状态：待用户审核
上游：[`2026-09-26-tmdb-metadata-and-nfo-design.md`](./2026-09-26-tmdb-metadata-and-nfo-design.md)（NFO 管线；本设计改动其**执行阶段**的调用形态，不改其内容规范与路径推导）

---

## 1. 目标

两件事，一件是另一件的手段：

1. **把执行接口由批量改为单文件** —— `POST /api/rename/execute` 一次只重命名一个文件，批次的编排搬到前端。
2. **在前端显示进度条** —— 逐文件执行让「已完成 n / 共 m」成为可能；这正是本次改动的动机。

批量执行期间界面只有一个旋转图标（`ExecutingOverlay.vue:15`），用户无从知道进行到哪一步、还要多久。拆成单文件请求后，每完成一个文件就有一个进度事件。

## 2. 范围

**在范围内**
- `/api/rename/execute` 契约改为单文件
- 新增 `/api/rename/finalize` 批次收尾接口（写剧集级 / 季级 NFO）
- `core/local_renamer.py` 的拆分：`plan_files` / `execute_one` / `finalize_show_nfo`
- `core/openlist_renamer.py` 的拆分：`execute_openlist_one`
- 前端并发池（`renameRunner.js`）与进度状态
- `ExecutingOverlay.vue` 进度条
- 设置页：`openlist.concurrency` 默认 3 → 2 并**真正下发**；`openlist.requestInterval` 一并下发；新增 `localConcurrency`
- `OpenListClient` 的限流参数改为可运行时调整
- 后端与前端判据脚本的相应改写

**不在范围内**
- `/api/rename/preview` 与 `/api/rename/dry-run` 的形态（**保持批量** —— 它们是纯计划操作，不写盘，不需要进度）
- OpenList 云盘的 NFO 写入（仍是 `_nfo_supported` 的 local-only，见上游 spec §2）
- NFO 内容规范、路径推导、库根防护（全部沿用上游 spec §8/§9，本设计一行不改）
- 重命名的撤销 / 回滚
- 前端测试设施建设（仍用 `scripts/check-*.mjs` 的 node 断言）
- `openlist_scanner.py` 自身的并发（`max_concurrent=8`，与本次设置无关）

## 3. 现状核实

本设计的全部前提均已在代码中核实，非推测。

| # | 事实 | 证据 |
|---|---|---|
| 1 | **执行接口是批量的** —— 一次请求处理整个选中集合 | `backend/app/models/api.py:54-55`（`file_ids: list[str]`）；`backend/app/api/renamer.py:304` 的 `@router.post("/rename/execute")` |
| 2 | **剧集级 / 季级 NFO 决策是批次级的** —— 每部剧只出一条，挂在排序后的 `group[0]` 上 | `backend/app/core/nfo_writer.py:191` `build_nfo_decisions`；其 docstring 的顺序契约 |
| 3 | **组级决策的落地判据是「该目录下有没有真的落地过视频」** —— 不是「组代表那一行有没有落地」 | `backend/app/core/local_renamer.py:112` `_keep_decision` 的 docstring；调用点在 `:451`，入参 `landed_paths` |
| 4 | **`abort` 是整批语义** —— 冲突行不执行 | `backend/app/core/local_renamer.py:363` `aborted = bool(plan.conflicts and conflict_strategy == "abort")` |
| 5 | 每集 NFO 的落点在 `rename_dup` 下会被改指向真实落点 | `backend/app/core/local_renamer.py:390`；`nfo_path_by_file` |
| 6 | 既有同前缀 NFO 的跟随是**每文件**的，与批次无关 | `backend/app/core/local_renamer.py:403` `carry_same_stem_nfo` |
| 7 | **前端载荷只有一处构造**，且被 node 断言钉住 | `frontend/src/stores/renamePayload.js:11` `buildRenamePayload`；`frontend/scripts/check-rename-payload.mjs` |
| 8 | **执行是单次批量请求，期间无任何进度状态** | `frontend/src/stores/workspace.js:504` `executeAction`；`:526` 单次 `await fn(...)` |
| 9 | **执行遮罩只有一个旋转图标** | `frontend/src/components/ExecutingOverlay.vue:15`；`:36` 的注释自陈「唯一的进度指示」 |
| 10 | **`openlist.concurrency` / `requestInterval` 是死设置** —— 存进 localStorage、有输入框、无消费点 | `frontend/src/stores/settingsSchema.js:30-31`；`frontend/src/views/SettingsView.vue:51,58`；全仓 grep 这两个字段只命中设置自身 |
| 11 | **但 OpenList 限流本身是实现了的** —— 只是由服务端 `.env` 决定 | `backend/app/core/openlist_client.py:24` `asyncio.Semaphore(settings.openlist_max_concurrent)`；`:30` 的间隔 sleep；`backend/app/config.py:32-33` 默认 3 / 0.5 |
| 12 | **设置页文案自己承认了这一点** | `frontend/src/views/SettingsView.vue:71-76`：「这两项当前由服务端的 `openlist_max_concurrent` 与 `openlist_request_interval` 决定。此处保存的值会被保留，但尚未下发到后端。」 |
| 13 | **TMDB 有模块级共享缓存** —— 拆成 N 次请求不会造成 N 倍出网 | `backend/app/core/tmdb_resolver.py:107` `_DEFAULT_CACHE = TmdbCache(ttl=...)` |
| 14 | **文件缓存是模块级内存字典**，且部署为单 worker | `backend/app/api/renamer.py:149` `_cached_files`；`Dockerfile:40` `uvicorn ... --port 6969`（无 `--workers`） |
| 15 | `nfo_scope` 是**预览行**的概念，由文件表消费，不在执行结果里 | `frontend/src/stores/workspace.js:406`；`frontend/src/components/FileTable.vue:260,331` |
| 16 | 结果对话框消费 `nfo_written` / `nfo_carried` / `nfo_skipped` 三个字段 | `frontend/src/components/ResultDialog.vue:178,182`；`:201` 以 `reason === '已存在'` 为判据串 |
| 17 | 前端无测试设施，判据是 `scripts/check-*.mjs` + 一个硬编码名单的 runner | `frontend/scripts/check-all.mjs` |

事实 2、3 是本设计的**约束来源**：剧集级 NFO 天生需要「整批」这个视野，所以单文件化必须为它保留一个批次收尾的落点，且该落点必须拿到**真实落地情况**而非「假定都成功」。

事实 11、12 是本设计对配置链路的约束来源：并发/间隔**不是**从零新建，而是把已有的服务端实现接到设置页上。若只做前端在途上限而不下发，用户把并发调到 5 时实际仍是 3 —— 那正是本设计要消灭的那一类「能改不生效」。

## 4. 接口契约

### 4.1 `POST /api/rename/execute` —— 改为单文件

请求模型 `RenameExecuteRequest`（`backend/app/models/api.py`）：

| 字段 | 变化 |
|---|---|
| `file_ids: list[str]` | **移除**，改为 `file_id: str` |
| `overrides: dict[str, dict]` | **移除**，改为 `override: dict \| None = None` |
| `template` / `folder_template` / `create_season_folder` / `source` / `path` / `conflict_strategy` / `episode_pad_digits` / `season_pad_digits` / `tmdb_*` / `generate_nfo` / `nfo_overwrite` | 不变 |
| `openlist_max_concurrent: int \| None` | **新增**（见 §7） |
| `openlist_request_interval: float \| None` | **新增**（见 §7） |

`override` 用单数而非「只有一个键的字典」：单文件接口收字典-of-1 是无意义的形状。路由内做一次适配（`{file_id: override}`）喂给既有的 `_with_tmdb_titles`，该函数不动。

响应模型 `SingleRenameResult`（新）：

```
success: bool
source: str
file_id: str
result: RenameResult      # 原模型，含 status / new_path / error / nfo_path
executed: int             # 0 或 1
skipped: int              # 0 或 1
failed: int               # 0 或 1
nfo_written: list[str]    # 本文件的每集 NFO（生成）
nfo_carried: list[str]    # 跟着视频搬走的既有 NFO
nfo_skipped: list[dict]   # {path, reason}
```

`result` 嵌套而不摊平：前端把它 `push` 进批次形状的 `results` 数组即可，`ResultDialog.vue` 无需改动。

**计数由后端给出，前端只做求和。** `executed / skipped / failed` 三个字段的值由后端按 `local_renamer.py:424-431` 那套既有规则算出（就是现在 `batch_rename` 里用的那一套），每条响应必为 0 或 1，前端把它们各自累加即得批次的三个计数。

这样安排是刻意的：若让前端按 `result.status` 自己判「这算 executed 还是 skipped」，那套规则就有了**第二份副本**，而两份副本必然漂移（`renamePayload.js:1-9` 已经写明这条，且新增状态时漏改一处没有任何机械判据能发现）。计数规则只留在后端一处。

**落地判定不新增判据**：`RenameResult.status` 已能区分（`local_renamer.py:48` 的 `_NO_LANDING_STATUSES` = `{skipped_conflict, conflict, failed}`；`:70` 的 `_CARRY_STATUSES` = `{renamed, moved, dry_run}`）。前端据此算 `landed` 表，**不引入第二套状态语义**。

### 4.2 `POST /api/rename/finalize` —— 批次收尾（新）

请求模型 `RenameFinalizeRequest`：

```
file_ids: list[str]              # 本批次全部文件（用于重建 plan）
landed: dict[str, str]           # file_id → 真实落点；只有落地的文件在表里
overrides: dict[str, dict]
template / folder_template / create_season_folder / source / path
episode_pad_digits / season_pad_digits / tmdb_* / generate_nfo / nfo_overwrite
```

不含 `conflict_strategy`（finalize 不做任何文件操作）。仅在 `source == "local"` 且 `generate_nfo` 为真时被调用。

**`landed` 必须由前端回传实际结果，不能靠后端重算「假定都成功」。** 这是本接口唯一的设计要害：整批失败时（如用户选了 `abort` 而每一行都冲突），后端若自行重建 plan 并假定全部落地，就会推出一个没有任何剧集文件的目录，写出一份 `tvshow.nfo` —— 正是上游 spec §9.4 要防的库根污染，且比原来更隐蔽（原来的批次里至少 `landed_paths` 是真实算出来的）。

响应模型 `FinalizeResult`（新）：

```
success: bool
nfo_written: list[str]   # 只含 tvshow / season
nfo_skipped: list[dict]
```

不返回 `nfo_scope`：它是**预览行**的概念（事实 15），由 `FileTable.vue` 消费，与执行结果无关。

### 4.3 `POST /api/rename/dry-run` —— 形态不变，换模型

dry-run 继续批量（它是纯计划操作，不写盘，不需要进度），但它此前复用 `RenameExecuteRequest`，而后者已改单数。故：

- 抽出 `RenameBatchRequest`（批量的字段集合：`file_ids` / `overrides` / 模板与 pad / `tmdb_*` / `generate_nfo` / `nfo_overwrite` / `conflict_strategy` / 两个 OpenList 限流字段），`RenameDryRunRequest` 继承它。
- `RenameFinalizeRequest` 同样继承它，但**去掉 `conflict_strategy`**，再加 `landed`。

`/api/rename/preview` 用独立的 `RenamePreviewRequest`，**完全不动**。

### 4.4 载荷构造（前端）

`frontend/src/stores/renamePayload.js` 的 `buildRenamePayload` 仍是**唯一**的载荷构造处（事实 7）。新增：

- `mode: 'finalize'` → 出 `file_ids` + `landed`（+ 其余同 execute）
- `mode: 'execute'` → 出 `file_id`（单数）+ `override`（单数）
- `mode: 'preview'` → 维持 `file_ids` + `overrides`（不变）

函数内加**互斥断言**：`mode === 'execute'` 时 `fileId` 必须非空且 `fileIds` 必须为空；`mode === 'preview'` 时反之。这是机械判据，防止调用点把两种形状混着传。

## 5. 后端实现拆分

### 5.1 `core/local_renamer.py`

`batch_rename`（`:285`）目前一个函数里串了四件事：建 plan、执行、每集 NFO、剧集级/季级 NFO。拆成三段，**每段只有一份实现**：

| 函数 | 职责 | 来源 |
|---|---|---|
| `plan_files(files, template, folder_template, create_season_folder, overrides, pad) -> list[RenamePlan]` | 建 plan + `check_conflict` | 抽取现有 `:297-309` |
| `execute_one(plan, *, dry_run, conflict_strategy, nfo_options, nfo_matches) -> OneOutcome` | 执行单个 plan + 每集 NFO 决策 + 跟随既有 NFO | 抽取现有 `:359-417` |
| `finalize_show_nfo(plans, landed_paths, nfo_matches, options) -> (written, skipped)` | 只取 `kind in ("tvshow","season")` 的决策并落盘 | 抽取现有 `:448-520` 的组级部分 |

`batch_rename` **保留为批量的参考实现**（干跑仍走它，且 `dry_run=False` 分支不删）。它改为调用上述叶子助手，但**不**改成「逐文件调 `execute_one`」的组合。

不组合的理由是硬的：干跑的跳过清单依赖**批次级**的 `planned_carried` —— 那个集合要在整批的 carry 全部算完之后才成立（`local_renamer.py:500` 附近的 `planned_carried = set(nfo_carried)` 在循环**之后**），逐文件调用时第一个文件根本不知道后面哪些路径会被占。强行组合要么改变干跑的报数（对话框把 N 个读成 1 个），要么给 `execute_one` 塞一个它自己算不出来的入参。

代价是每文件的编排循环存在两份（`batch_rename` 的循环与 `execute_one`）。**叶子助手是共用的，漂移风险集中在编排层**，故补一条交叉判据钉住它：

> 同一批输入分别走 `batch_rename`（批量）与 `execute_one` × N + `finalize_show_nfo`（单文件），聚合后的 `executed / skipped / failed / nfo_written / nfo_skipped / nfo_carried` 必须逐项相等。

这条判据在两条路径的任何一处漂移时都会红 —— 它才是「两份副本」这个顾虑的答案，而不是靠「不写第二份」的愿望。

**每集 NFO 的决策逻辑只允许有一份**（抽成 `_episode_decision_for(plan, nfo_matches, options)`，被 `execute_one` 与 `batch_rename` 共用）。理由是 `renamePayload.js:1-9` 已经写明的那条：同一逻辑的两份副本必然漂移，且新增字段时漏改一处**没有任何机械判据能发现**。

`batch_rename` 的 `dry_run=False` 分支在生产路径上不再被调用（`/rename/execute` 走 `execute_one`），但**不删**：`tests/test_nfo_write.py` 有 37 处直接调它，那些用例是 NFO 全部语义（carry / 去重 / `_keep_decision` / rename_dup 改指向）的既有防线，删掉分支等于删掉防线。

`finalize_show_nfo` 复用既有的 `_keep_decision`（`:112`）与 `dedupe_skipped_pairs`（`nfo_writer.py:301`），**不改判据**：`landed_paths` 由前端回传的 `landed` 表推导（取 `os.path.dirname` 去重），语义与批次内自算的完全一致。

**组级决策的 NfoEntry 直接用 `plan.new_path`，不用 `landed` 里的真实路径。** 这是刻意的，且已核实过：

- 组级落点的推导链 —— `common_parent`（`nfo_writer.py:97`）、`_show_root`（`:111`）、`_folder_belongs_to_single_show`（`:166`）—— **全部只消费 `os.path.dirname(p)`**，文件名不参与任何判断。
- 而 `rename_dup` 只改文件名的词干（`local_renamer.py:249-254`），**目录不变**。

两条合起来：真实路径与预测路径的目录必然相同，组级结论必然相同。所以这里**不加**「用 landed 覆盖 new_path」的分支 —— 它买不到任何东西，却会让「每集 NFO 用真实路径、组级 NFO 用预测路径」这个差异看起来像是疏忽。

（每集 NFO 那边**必须**用真实路径，理由完全不同：`episode_nfo_path` 靠**文件名**与视频配对，见 `nfo_writer.py:87`。两者判据不同，不是不一致。）

### 5.2 `core/openlist_renamer.py`

`execute_openlist_batch(client, plans, dry_run)` → `execute_openlist_one(client, plan, dry_run)`。OpenList 不写 NFO，故无 finalize 对应物。

### 5.3 `api/renamer.py`

- `/rename/execute` 改为：取单个 `FileInfo` → `_with_tmdb_titles`（单元素）→ `plan_files`（单元素）→ `execute_one` → 组装 `SingleRenameResult`。
- 新增 `/rename/finalize`：取 `file_ids` 全部 `FileInfo` → `_with_tmdb_titles` → `plan_files` → 用 `landed` 算 `landed_paths` → `finalize_show_nfo`。
- `/rename/dry-run` 不变，仅换请求模型。

## 6. 前端并发池与进度

### 6.1 `frontend/src/stores/renameRunner.js`（新）

零依赖纯函数（与 `settingsSchema.js` 同规格：不 import 任何东西，node 能直接加载跑断言）：

```js
export async function runWithConcurrency(items, limit, worker, { onProgress, intervalMs } = {})
```

契约：
- `limit` 由调用方传入，**函数内不得有默认值兜底** —— 兜底会让「调用点忘了传设置」静默退化成某个魔数，正是本设计要防的那类 bug。
- 返回 `{ results, failures }`，`results` 按 `items` 原序（并发完成顺序不确定，排序必须在函数内做，不能推给调用方）。
- **单个 worker 抛错只记入该条**，不影响其余任务继续（对应 §8「一律跑完」）。
- `onProgress(done, total)` 每完成一个调用一次（成功与失败都算完成）。
- `intervalMs > 0` 时，每次发请求前 `await sleep(intervalMs)`。

### 6.2 `frontend/src/stores/renameAggregate.js`（新）

同样零依赖纯函数：`aggregateBatch({ items, finalize, nfoBlockedByScrape, source })` → `BatchRenameResult` 同形状的对象。

抽成独立模块的理由与 `settingsSchema.js` 相同 —— 本项目没有前端测试设施，纯函数是唯一能被 node 直接加载并断言的东西。聚合逻辑里最容易出错的一处（计数是「用后端给的字段」还是「自己按 status 重判」）必须可被机械检验，见 §9.4。

### 6.3 `stores/workspace.js`

- 新增 `progress = reactive({ done: 0, total: 0, current: '' })`。
- `executeAction`（`:504`）改写：

```
1. 收集选中行 → 逐文件构造载荷（buildRenamePayload, mode:'execute'）
2. limit = 批次内 new_path 有重复 ? 1 : 源相关并发设置   ← 见 §10.1
3. await runWithConcurrency(items, limit, worker, { onProgress, intervalMs })
4. 若 local && generateNfo：await finalizeRename(buildRenamePayload(mode:'finalize', ...))
5. 聚合 → lastResult（**保持 BatchRenameResult 同形状**，ResultDialog.vue 不动）：
   - executed / skipped / failed / total = 各条响应的计数**直接求和**（不按 status 重判，见 §4.1）
   - results = 各条的 result 原序拼接；errors = 各条 result.error 中的非空项
   - nfo_written / nfo_skipped / nfo_carried = 各条拼接，再并上 finalize 响应里的同名两项
   - success = (failed === 0)；dry_run = false；nfo_blocked_by_scrape = await 前捕获的局部变量
6. await buildPreview()
```

- **顺序约束（必须写进代码注释）**：finalize 必须在 `buildPreview()` **之前**调用。`buildPreview` 会重扫并刷新后端的 `_cached_files`，之后 finalize 就重建不出同一批 plan 了。
- `executeDryRun` / `executing` 的既有语义与 HomeView 的 `v-if` 交互**不动**（`ExecutingOverlay.vue:44-56` 那段关于挂载时机的注释仍然有效）。

### 6.4 `components/ExecutingOverlay.vue`

- 真执行：进度条 + 「已完成 n / 共 m」+ 当前文件名。
- 干跑（`dryRun === true`）：保持现有的旋转图标，**不显示进度条** —— 干跑仍是单次批量请求，没有进度可言，给一个永远 0% 的进度条就是撒谎。
- 仍然阻断、不可 Esc 关闭（`:44` 的既有理由不变）。
- 进度条需带 `role="progressbar"` 与 `aria-valuenow/min/max`（遮罩已有 `role="status" aria-live="polite"`）。

### 6.5 `stores/renamePayload.js`

见 §4.4。

## 7. 设置链路

### 7.1 前端

| 设置项 | 位置 | 默认 | 区间 | 变化 |
|---|---|---|---|---|
| `openlist.concurrency` | 原处 | 3 → **2** | [1,10] | 接上 |
| `openlist.requestInterval` | 原处 | 0.5 | [0.1,5] | 接上 |
| `localConcurrency` | 新增（顶层） | 4 | [1,10] | 新增 |

- **不做迁移**：`normalizeSettings`（`settingsSchema.js:56`）只在字段缺失时回落默认，所以老用户已存的 `concurrency: 3` 会保留，只有新装/未设置者拿到 2。用户显式设过的值不该被静默改掉。
- `SettingsView.vue`：新增「本地并发」输入项；**改掉** OpenList 分组那段「尚未下发到后端」的提示（`:71-76`）—— 它在下发之后就是一句假话。
- 载荷：`openlist_max_concurrent` 与 `openlist_request_interval` 随 `/rename/execute` 与 `/rename/dry-run` 下发；`localConcurrency` **不下发**（纯前端在途上限）。
- `openlist.requestInterval` 只作用于 OpenList 请求（本意是别把 OpenList 的 API 打爆）；本地请求不设间隔。

### 7.2 后端

- `OpenListClient`（`openlist_client.py:24`）的 `_semaphore` 换成**可运行时调整的限流器**：

```python
class _AdaptiveLimiter:
    """上限可变的并发限流器。"""
    def __init__(self, limit): ...
    async def __aenter__(self): ...   # 计数 < limit 才通过，否则 await cond.wait()
    async def __aexit__(self, *a): ...  # 计数 -1，cond.notify(1)
    def set_limit(self, n): ...       # 变大时 notify_all
```

  不用「替换整个 `asyncio.Semaphore` 对象」的做法：每个请求都替换会**摧毁限流本身**（在途持有者释放到旧对象，新对象满额放行），而「值没变就不替换」的补丁仍会在批次首个请求处留下瞬时抖动。计数器 + `Condition` 是十几行代码，且语义完全正确。

- `_wait_interval` 改为读**实例**的间隔值而非全局 `settings.openlist_request_interval`。
- 路由在进入执行前调用 `client.apply_limits(max_concurrent, request_interval)`；两个参数为 `None` 时保持当前值（回落 `.env`）。
- `.env` 的 `OPENLIST_MAX_CONCURRENT` / `OPENLIST_REQUEST_INTERVAL` 降级为「请求未提供时的初值」。

**已知副作用（需写进代码注释）**：限流参数设在**进程级单例**客户端上，所以一次执行设下的值会**持续生效**到下次被覆盖 —— 之后的预览、扫描、列目录同样受它约束。单用户场景下可接受（设置页的值本就是用户想要的稳态），但它是隐性状态，不写明就会在将来被当成 bug 排查。

**作用域说明（诚实交代）**：该限流器位于 `OpenListClient._request`，对**所有**客户端调用生效 —— 扫描、列目录、登录同样受它约束。设置页的标签「最大并发请求」是名副其实的，但用户应知道它不只管重命名。

## 8. 失败与冲突语义

- **一律跑完**：单个文件失败或冲突，不中断后续。进度条能走到 100%。
- **`abort` 降级**：由「整批中止」变为「该文件不执行」。冲突行的 `status` 仍是 `conflict`、`error` 仍是 `冲突: ...`，只是不再影响别的文件。
- **失败不阻断 finalize**：finalize 只为 `landed` 里的文件写剧集级 NFO。全批失败时 `landed` 为空 → 一个组级 NFO 都不写（这是判据，见 §9）。
- **批次级 `abort` 语义消失**是本次的**已知行为变更**，需在 README 的冲突策略说明里同步。

## 9. 测试策略

后端 pytest（现有 214 条）。**每条新判据都要能回答「把实现改坏它会不会红」**。

### 9.1 改写既有测试

- `tests/test_rename_routes.py`（3 处）与 `tests/test_rename_nfo_route.py`（6 处）里的 `/api/rename/execute` 调用改为单文件契约。
- 干跑路径的既有测试**必须全绿且不改语义** —— 它们是「拆分没有改变行为」的唯一证据。

### 9.2 新增 `tests/test_rename_single_route.py`

| 判据 | 改坏后必须红的方式 |
|---|---|
| 单文件成功：`result.new_path` 正确、`nfo_written` 含该集 NFO | — |
| 冲突 + `skip`：`status == skipped_conflict`，且 `nfo_written` 为空 | 去掉 `_NO_LANDING_STATUSES` 过滤 |
| 冲突 + `skip`：响应里 `skipped == 1` 且 `failed == 0`（与批量时的计数规则一致） | 把 `skipped_conflict` 归进 failed 分支 |
| 冲突 + `abort`：该文件 `failed == 1`（沿用 `:424` 的既有归法），且不报错中止 | — |
| 同一 `file_id` 请求两次不写两遍 NFO | 去掉 `nfo_overwrite` 判断 |
| `rename_dup` 下真实落点 X_1.mkv → 每集 NFO 落 X_1.nfo | 去掉 `:390` 的改指向 |

### 9.3 新增 `tests/test_rename_finalize_route.py`

| 判据 | 改坏后必须红的方式 |
|---|---|
| `landed` 为空 → `nfo_written` 里一个 `tvshow.nfo` 都没有 | 删掉 `landed` 过滤，改为「假定全部落地」 |
| finalize **不得**再写每集 NFO（`nfo_written` 里无 `SxxExx.nfo`） | 去掉 `kind in ("tvshow","season")` 过滤 |
| `landed` 只含第二集 → `tvshow.nfo` 照写（组级判据是「目录里有视频落地」，不是「组代表落地」） | 把 `_keep_decision` 的组级分支改成按代表行判 |
| `landed` 指向季子目录 → `season.nfo` 落在该季目录 | — |

### 9.4 前端判据脚本

新增 `frontend/scripts/check-rename-runner.mjs`：

| 判据 | 改坏后必须红的方式 |
|---|---|
| 在途数从不超过 `limit`（用计数器 + 可让出的 worker 测） | 把 `limit` 当摆设、一次全发 |
| `results` 顺序 == `items` 顺序（让先发的慢于后发的） | 直接返回完成顺序 |
| 单个 worker 抛错不影响其余，且记入 `failures` | 让 `Promise.all` 直接 reject 掉整批 |
| `onProgress` 调用次数 == `items.length` | 只在成功时调 |
| `limit` 未传时**抛错**而不是兜底 | 加一个默认值 |

新增 `frontend/scripts/check-rename-aggregate.mjs`：

| 判据 | 改坏后必须红的方式 |
|---|---|
| **计数用后端给的字段、不按 `status` 重判**：喂一条自相矛盾的响应（`status: 'skipped_conflict'` 但 `executed: 0, skipped: 0, failed: 1`），断言 `lastResult.failed === 1` 且 `skipped === 0` | 改成按 `result.status` 归类 → 得到 `skipped: 1`，断言红 |
| finalize 的 `nfo_written` 并入批次结果（且不与每集的重复） | 丢掉 finalize 响应 |
| `success === (failed === 0)` | 恒返回 true |
| 空批次（`items: []`）不崩，`total === 0` | — |

更新 `check-rename-payload.mjs`：单数 `file_id`/`override`、finalize 载荷形状、未刮削时仍只发 `tmdb_enabled: false`（这条既有断言不能丢）。

更新 `check-settings-schema.mjs`：`openlist.concurrency` 新默认 2、`localConcurrency` 的钳制区间。

**针对「死设置」回归的专项断言**（写在 `check-rename-runner.mjs` 或 `check-workspace-gating.mjs`）：

> 若 `executeAction` 把字面量传给 `runWithConcurrency` 而不是从 `settingsStore` 读，断言必须红。

否则「设置项在页面上可改、实际不生效」这个 bug 可以原样复发 —— 它正是事实 10 记录的那一个。

`check-all.mjs` 的硬编码名单加入新脚本。

## 10. 已知限制与风险

### 10.1 并发下的同目标冲突（真风险）

串行时 `rename_dup` 保证 `X` / `X_1`；3–4 并发时若同一批次内两个文件目标同名，可能双双通过存在性检查 → 双写 `X`（`overwrite` 策略下是**数据丢失**）。

**缓解**：前端在发起前用预览已有的 `new_path` 检测批次内重名，**有重名就把该批次的 `limit` 降为 1**。纯前端可判，后端不参与。代价是这种情况退回串行，但它是病态输入，且预览里本来就会显示两个相同的目标名。

### 10.2 `_cached_files` 是单进程内存（事实 14）

已确认 `Dockerfile:40` 是**单 worker** uvicorn，安全。但这是隐性约束：一旦将来加 `--workers`，`/rename/execute` 与 `/rename/finalize` 可能落在不同进程上，后者拿不到前者的文件缓存。**必须在 `/rename/finalize` 的路由注释里钉住这条依赖。**

### 10.3 破坏性接口变更

`/api/rename/execute` 的契约变了。README 未承诺公开 API，外部调用方风险低，但这是**不兼容变更**，需在 README 注明。

### 10.4 请求数从 1 变 N

一次执行产生的后端日志由 1 组变为 N 组，`[RENAME]` 前缀的日志会变得密集。不引入正确性问题，但排查时的阅读方式会变。

### 10.5 `abort` 语义变更

见 §8。用户若依赖「一个冲突就整批不动」，行为会变。设置页的冲突策略说明需同步。

## 11. 分期

单个实施计划交付，任务顺序：

1. 后端：`local_renamer` 拆分（纯重构，既有测试必须全绿）
2. 后端：`/rename/execute` 单文件化 + 模型拆分
3. 后端：`/rename/finalize`
4. 后端：`OpenListClient` 可调限流器
5. 前端：`renameRunner.js` + `check-rename-runner.mjs`
6. 前端：`renameAggregate.js` + `check-rename-aggregate.mjs`
7. 前端：`workspace.js` 执行循环接线
8. 前端：`ExecutingOverlay` 进度条
9. 前端：设置链路（schema / 设置页 / 载荷）
10. 文档：README 的冲突策略与接口说明

第 1 步单独成步的理由：它是纯重构，不改变任何对外行为，既有 214 条测试是它的完整防线。把它与接口变更混在一起，一旦测试红了就分不清是重构错了还是接口改错了。

## 12. 裁定记录

| # | 裁定 | 理由 |
|---|---|---|
| R1 | 剧集级/季级 NFO 走**批次收尾接口**，而非降级为「只写每集 NFO」 | 降级会让 NFO 功能退化，且 Emby/Jellyfin 的剧集识别依赖 `tvshow.nfo` |
| R2 | 失败**一律跑完**，最后汇总 | 用户可见的进度条必须能走到 100%；半途停下的进度条与现在的转圈一样无从判断 |
| R3 | 小并发 3–4（本地 4 / OpenList 2） | 总耗时接近现状，同时保留进度粒度 |
| R4 | **彻底替换**批量执行接口，不并存 | 两套执行路径长期并存 = 死代码，且必然漂移 |
| R5 | 并发/间隔的权威放**设置页**，下发到后端 | 只做前端上限会让「设 5 实际 3」，正是本设计要消灭的那类缺陷 |
| R6 | 本地并发也做成可配 | 与 OpenList 对称；设置页已有的分组结构可直接容纳 |
| R7 | `openlist.requestInterval` 一并接上 | 否则设置页上会留着一个相邻的、仍是死的输入框 |
| R8 | **不做迁移**，老用户已存的 `concurrency: 3` 保留 | 用户显式设过的值不该被静默改掉；新默认只影响新装与未设置者 |
| R9 | `preview` 与 `dry-run` 保持批量 | 它们是纯计划操作，不写盘，没有进度可言 |
| R10 | `nfo_scope` 不由 finalize 返回 | 它是预览行的概念（事实 15），与执行结果无关 |
| R11 | `executed / skipped / failed` 由**后端**在单文件响应里给出，前端只求和 | 让前端按 `status` 重判会把计数规则复制成第二份，两份必然漂移 |
| R12 | 聚合抽成 `renameAggregate.js` 纯函数 | 本项目无前端测试设施，纯函数是唯一能被 node 直接断言的东西；R11 的约束需要机械判据 |
| R13 | OpenList 限流器用计数器 + `Condition` 实现，不替换 `Semaphore` 对象 | 每请求替换会摧毁限流本身；「值没变就不替换」的补丁仍有瞬时抖动 |
| R14 | 组级决策的 NfoEntry 用 `plan.new_path`，不加「用真实落点覆盖」的分支 | 推导链只消费 `dirname`、`rename_dup` 只改词干 —— 覆盖买不到任何东西（已核实，见 §5.1） |
| R15 | `batch_rename` 保留为批量参考实现，**不**改为逐文件组合；改以交叉判据钉住两条路径 | 干跑的 `planned_carried` 是批次级事实，循环内算不出来；而删掉它的 `dry_run=False` 分支会摧毁 `test_nfo_write.py` 的 37 条既有防线 |
