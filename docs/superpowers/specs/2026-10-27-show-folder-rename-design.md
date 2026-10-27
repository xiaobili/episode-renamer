# 剧集文件夹重命名设计（`剧名 (年份) [tmdbid-x]`）

日期：2026-10-27
状态：已实现

## 1. 需求

把剧集目录本身重命名为 Emby / Jellyfin 的标准识别形态：

```
{TMDB 剧名} ({年份}) [tmdbid-{tv_id}]
例：绝命毒师 (2008) [tmdbid-1396]
```

- 用户选择了「带空格」写法（与 Emby 官方示例一致）。
- 剧名取 **TMDB 本地化标题**（受设置页 `TMDB_LANGUAGE` 影响），与 `tvshow.nfo` 的
  `<title>` 同源；年份取 `TmdbShow.year`，`tmdbid` 取 `TmdbShow.tv_id`。
- 年份缺失（TMDB 偶有该字段为空）时省略括号段：`绝命毒师 [tmdbid-1396]`。

## 2. 关键约束

### 2.1 为什么必须是**批次级**动作

重命名的是**目录**，不是文件。若把它塞进逐文件的 `/rename/execute`：

- 前端逐文件并发，第一个文件成功改名目录之后，其余文件的 `parent_dir` **全部失效**
  （`execute_rename_plan` 的 `dst.parent.mkdir(parents=True)` 会**重建**一个旧名空目录），
  用户得到一个空壳旧目录 + 一堆散落文件；
- 目录改名的结果与「有几个文件」无关，重复执行 N 次是 N-1 次浪费加撞车。

因此新增独立接口 `POST /api/rename/folders`，一批剧一次性处理，每部剧一次。

### 2.2 为什么排在 `finalize` **之后**

| 顺序 | 后果 |
| --- | --- |
| 先改文件夹 | `finalize` 按 `plan.new_path`（旧目录）算 NFO 落点 → `write_nfo_files` 的 `mkdir(parents=True)` 会**重建旧目录**并把 `tvshow.nfo` 写进去 → 媒体库里出现一个只有 NFO 的空文件夹 |
| 先 finalize，后改文件夹 | NFO 写在旧目录里，随后整个目录被搬走，`tvshow.nfo` / `season.nfo` / 每集 `.nfo` 一并跟随 |

故前端调用顺序固定：**逐文件 execute → finalize（勾了 NFO 时）→ folders**。
该接口**不依赖** NFO 开关：没勾 NFO 时同样会在 execute 之后单独调用。

### 2.3 季文件夹（用户明确提醒的坑）

`Season 01/`、`第1季/`、`S01/` 这类子目录**不需要单独处理** —— 改的是它们的**父目录**，
整棵树跟着走。真正需要处理的是**推导剧集根**：文件躺在季目录里时，公共父目录是季目录
本身，直接改名会把 `Season 01` 变成 `绝命毒师 (2008) [tmdbid-1396]`。

判据复用 `nfo_writer._show_root`（`parser._SEASON_DIR_PATTERNS` 那套正则 + 单步上溯），
通过新增的公开别名 `nfo_writer.show_root_of` 暴露 —— **不允许**在这里写第二套季目录判定，
两份必然漂移（`tvshow.nfo` 与文件夹会落到不同层级）。

多季布局（`Season 01/` + `Season 02/`）公共父目录天然是剧目录，结果与单季一致。

### 2.4 拒绝的四种情形（`folder.reason`）

| 常量 | 含义 |
| --- | --- |
| `NO_TMDB_REASON` | 该剧没匹配到 TMDB（未启用 / 未刮削 / 未找到 / 剧集级信息缺失）。**没有 tmdbid 就没有目标名**，如实跳过 |
| `MIXED_SHOWS_REASON` | 同一目录下混有多部剧。改名会把别的剧一起搬走，属不可逆污染 |
| `ALREADY_NAMED_REASON` | 目录名**已经是**目标名（幂等；重跑不会二次改名） |
| `NO_SHOW_DIR_REASON` | 推不出剧集目录（解析失败且路径为空 / 根目录） |

执行期另有两种：`TARGET_EXISTS_REASON`（目标目录已存在，不覆盖）、`源目录不存在`。

### 2.5 混放与嵌套的判定

按解析剧名分组 → 每组用 `show_root_of(new_paths)` 求根 → 再交叉检查：

- 两个组的根**相同** → 两组都拒绝（同目录混放）；
- A 的根是 B 的根的**祖先** → 只拒绝 A（搬 A 会把 B 一起带走），B 照常。

批次之外的同级剧目录看不见（我们只有本次扫描的文件）—— 这条边界靠**预览可见性**兜住：
`/rename/preview` 每行返回 `folder.new_path`，用户在动手前就能看到「这个目录会被改成什么」，
与 NFO 落点（spec §9.4）、STRM 落点同一条治理原则。

### 2.6 尚未覆盖：`create_season_folder` 与 OpenList 的交互

OpenList 的 builder 没有本地那条「父目录已是季目录则抑制建季目录」的逻辑，前端也已禁用
OpenList 的「创建季文件夹」。因此该组合下 `new_path` 会多一层 `Season 01/Season 01`，
上溯后得到的根是 `…/Season 01` —— 已知限制，与 STRM 的同类限制一起记在这里，不做静默修正。

## 3. 接口契约

### 3.1 请求字段

`rename_folders: bool`（默认 `false`）加入 `RenamePreviewRequest` / `RenameBatchRequest` /
`RenameExecuteRequest`。**只有预览与干跑读它**（决定报不报计划）；执行接口继承了字段但
不看它（文件夹是批次级动作，逐文件接口无权代表整批做这个决定）。

### 3.2 `POST /api/rename/preview` 每行新增

```json
"folder": { "path": "/media/绝命毒师", "new_path": "/media/绝命毒师 (2008) [tmdbid-1396]" }
"folder": { "path": "/media/绝命毒师", "new_path": null, "reason": "该剧未匹配到 TMDB..." }
```

未勾选 `rename_folders` 时为 `null`（与 `nfo` / `strm` 的「没启用就没有」同构）。

### 3.3 `POST /api/rename/folders`（新）

批量、真实动盘。请求体 = `RenameFoldersRequest(RenameBatchRequest)`。

```json
{ "success": true,
  "renamed": [ { "old_path": "...", "new_path": "...", "show_name": "绝命毒师" } ],
  "skipped": [ { "path": "...", "reason": "目标目录已存在" } ] }
```

**不读** `conflict_strategy`（目录不覆盖、不自动编号 —— 重命名目录的「自动编号」会把
Emby 的库结构搞乱）；也不读 `generate_nfo` / strm 相关字段。

### 3.4 `POST /api/rename/dry-run` 新增两项

`folders_renamed`（计划改名，含 `old_path` / `new_path`）与 `folders_skipped`
（含 `path` / `reason`），与 `nfo_written` / `strm_written` 同构，供结果对话框列出。

## 4. 端到端顺序（前端 `executeAction`）

```
逐文件 execute（并发池）
  → finalize（勾了 NFO 时，只写剧集级/季级 NFO）
  → folders（勾了「重命名剧集文件夹」时）
  → buildPreview()（重扫）
```

**重扫前必须改写扫描路径**：若被改名的目录就是扫描根（用户直接扫了剧目录，最常见的用法），
`path` 会指向一个已不存在的路径，`buildPreview` 必然失败并弹「刷新失败」。故接口返回的
`renamed` 被用来做前缀替换：`path === old_path` 或 `path.startsWith(old_path + sep)` 时改写
`path`。改名前它仍是旧路径 —— 这一步不能省。

失败处置与 finalize 同一条口径：改名失败**不能**冒到外层 catch 变成「操作失败」（此时
文件改名已经完成），只降级成结果里的一条 `skipped`。

## 5. 判据

- `backend/tests/test_show_folder.py` —— 命名拼装、季目录上溯、混放/嵌套拒绝、
  无 TMDB 拒绝、幂等、本地真实改名（含 Season 子目录随迁）、目标已存在、
  OpenList 客户端调用与撞名跳过。
- `backend/tests/test_rename_folders_route.py` —— 预览字段形状、干跑清单、
  接口真实改名、路径不可用时的 400。
- `frontend/scripts/check-rename-payload.mjs` —— `rename_folders` 四种形态都在载荷里，
  且 `folders` 形态**不带** `conflict_strategy` / strm 字段。
