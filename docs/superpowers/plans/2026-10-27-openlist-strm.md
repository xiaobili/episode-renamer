# OpenList STRM 生成 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法跟踪进度。

**目标：** OpenList 源在重命名执行后为每个视频写出 `.strm`，支持本地镜像 / 远端自定义目录 / 远端同目录三种落点。

**架构：** 新增纯函数模块 `core/strm.py` 负责 URL 编码、落点推导与三种写盘方式；路由在 OpenList 分支复用现有 `execute`/`dry-run`/`preview` 骨架接入；前端把配置放进设置 store，经 `renamePayload.js` 单点下发。

**技术栈：** Python 3.12 / FastAPI / httpx / pytest；Vue 3 / Pinia / Tailwind 4 / 零依赖 node 判据。

**规格：** `docs/superpowers/specs/2026-10-27-openlist-strm-design.md`

## 全局约束

- 远端路径一律 `posixpath`；本地路径一律 `os.path` / `pathlib`。
- strm 的失败只进 `strm_skipped`，绝不改变重命名的成功状态与计数。
- 字幕（`FileInfo.is_subtitle`）不进入 strm 管线。
- 目标已存在一律覆盖，不新增覆盖开关。
- 前端请求载荷只经 `renamePayload.js` 构造。
- 不自动 `git commit`；提交由用户确认后另行处理。

## 审查重点（Review Focus）

> ⚠️ 本文件记录的是**实现当时**的方案。第 3 条（逐段编码）、落点里的「相对扫描根镜像」
> 与「远端根目录在设置页」三条，已在实现后按用户反馈改掉 —— 以文末「后续修订」和
> `2026-10-27-openlist-strm-design.md`（spec）为准。

1. **落点必须来自真实落点** `result.new_path`，不是 `plan.new_path`（`moved_not_renamed` 与 `skipped_same` 都会分叉）。
2. **本地落点不得越出 `local_root`**（`..` 与绝对路径注入都要挡住）。
3. ~~**URL 必须逐段编码**~~ → 已改为**原样写入不转义**（用户要求）；编码会把中文变成 `%E6%88%91`，不可读。
4. **未落地 / 字幕不写**，且必须能区分“未落地”与“写失败”两种原因。
5. **覆盖**是刻意的：已存在的 strm 必须被重写，否则旧链接残留。
6. **指定根目录时先建剧集名目录**：落点是 `{根}/{剧名}/{文件名}.strm`，扫描根就是剧目录时也不例外。

---

## 任务 1：新增 strm 纯函数模块

**文件：**
- 创建：`backend/app/models/strm.py`
- 创建：`backend/app/core/strm.py`
- 测试：新建 `backend/tests/test_strm_url.py`、`backend/tests/test_strm_local.py`

**接口：**

```python
STRM_EXT = ".strm"
NOT_LANDED_STRM_REASON = "该文件未改名, 不生成 STRM"
MISSING_LOCAL_ROOT = "未配置 STRM 输出目录"
MISSING_REMOTE_ROOT = "未配置 STRM 远端目录"
MISSING_BASE_URL = "未配置 STRM 地址"
OUT_OF_ROOT_REASON = "输出目录越界"

def strm_filename(new_filename: str) -> str
def build_strm_url(base_url: str, remote_path: str) -> str
def rel_dir_of(landing_dir: str, scan_root: str) -> str
def strm_target(plan, result, options, scan_root) -> Optional[StrmTarget]
def strm_content(url: str) -> bytes
def write_strm_local(local_root: str, target_path: str, content: bytes) -> None
```

- [ ] **步骤 1：编写失败的测试**

`test_strm_url.py`：

```python
def test_strm_url_encodes_each_segment():
    assert build_strm_url("http://h:5244/", "/115/剧 名/S01E01 #1.mkv") == (
        "http://h:5244/d/115/%E5%89%A7%20%E5%90%8D/S01E01%20%231.mkv"
    )

def test_strm_url_keeps_slash_and_encodes_question_mark(): ...
def test_strm_url_empty_base_returns_empty(): ...
def test_strm_filename_replaces_extension(): ...
def test_rel_dir_of_strips_scan_root(): ...
def test_rel_dir_of_falls_back_when_outside_root(): ...
```

`test_strm_local.py`：落点结构、`..` 越界、覆盖已有文件、字幕跳过、未落地跳过。

- [ ] **步骤 2：运行测试验证失败**

`cd backend && .venv/bin/python -m pytest tests/test_strm_url.py tests/test_strm_local.py -v`

- [ ] **步骤 3：实现**

- `build_strm_url`：`base.rstrip("/") + "/d/" + "/".join(quote(seg, safe="") for seg in path.split("/") if seg)`；base 为空返回 `""`。
- `rel_dir_of`：`posixpath.relpath(landing_dir, scan_root)`，结果以 `..` 开头、为 `.` 或为空时回落 `posixpath.basename(landing_dir)`；`scan_root` 为空时直接回落。
- `strm_target`：字幕 / 未启用 / 未落地 / 缺根目录时返回 `None`，原因由调用方按 `strm_target_reason(...)` 取（把“为什么没写”也做成纯函数，避免路由里散落判断）。
- `write_strm_local`：`Path(target).parent.mkdir(parents=True, exist_ok=True)` 后 `write_bytes`。
- 越界守卫统一放在 `strm_target`：目标 `realpath` 不在 `realpath(root) + os.sep` 下 → 返回越界原因。

- [ ] **步骤 4：运行测试验证通过**

---

## 任务 2：远端写盘

**文件：**
- 修改：`backend/app/core/strm.py`
- 测试：新建 `backend/tests/test_strm_remote.py`

**接口：**

```python
async def ensure_remote_dir(client, dir_path: str, cache: dict[str, bool]) -> None
async def write_strm_remote(client, target_path: str, content: bytes, cache: dict[str, bool]) -> None
async def write_strm_for_plan(client, plan, result, options, scan_root) -> tuple[list[str], list[tuple[str, str]]]
async def plan_strm_for_plan(client, plan, result, options, scan_root) -> tuple[Optional[str], Optional[str]]
```

- [ ] **步骤 1：编写失败的测试**（FakeClient 记录 `mkdir` / `put_file` 调用）

覆盖：`remote_same` 不建目录、`remote_custom` 逐级建目录且同目录重复只建一次、put 的内容是 URL + `\n`、put 抛错降级为 `写入失败`、字幕不调用。

- [ ] **步骤 2：验证失败** → **步骤 3：实现** → **步骤 4：验证通过**

- `ensure_remote_dir`：从 `/` 逐段向下 `client.mkdir(parent, name)`，异常忽略（已存在），成功路径进缓存。
- `write_strm_for_plan`：`strm_target` 为 None → 返回 `([], [(path_or_expected, reason)])`；否则按模式写盘，异常转 `写入失败: {exc}`。
- `plan_strm_for_plan` 不产生任何副作用（不 mkdir、不 put）。

---

## 任务 3：模型与路由接入

**文件：**
- 修改：`backend/app/models/api.py`、`backend/app/models/file.py`、`backend/app/api/renamer.py`
- 测试：新建 `backend/tests/test_rename_strm_route.py`

- [ ] **步骤 1：编写失败的测试**

覆盖：
- 预览：`source=openlist` + `generate_strm` → 每行 `strm` 有 `mode/path/url`，路径用 `/`；
- 预览：`source=local` + `generate_strm` → 400；
- execute：假客户端，断言 `put_file` 收到 strm 路径与内容，响应 `strm_written` 含该路径；
- execute：`strm_mode=local` → 本地文件真的出现（tmp_path）；
- dry-run：返回“将写入”清单且不调用 `put_file`；
- 字幕 / 未落地：不写且原因正确。

- [ ] **步骤 2：验证失败**

- [ ] **步骤 3：实现**

- `models/api.py`：三个请求模型各加 5 个字段（`strm_mode` 用 `Literal`）。
- `models/file.py`：`BatchRenameResult` 与 `SingleRenameResult` 加 `strm_written: list[str]`、`strm_skipped: list[dict]`。
- `renamer.py`：新增 `_strm_options_from_request(req)` 与 `_reject_strm_for_local(source, req)`；preview 每行填 `strm`；execute 在 NFO 之后写 strm；dry-run 规划。

- [ ] **步骤 4：验证通过**（含现有 283 个用例）

---

## 任务 4：前端状态与载荷

**文件：**
- 修改：`frontend/src/stores/settingsSchema.js`、`frontend/src/stores/renamePayload.js`、`frontend/src/stores/workspace.js`、`frontend/src/stores/renameAggregate.js`
- 测试：`frontend/scripts/check-settings-schema.mjs`、`check-rename-payload.mjs`、`check-rename-aggregate.mjs`、`check-workspace-gating.mjs`

- [ ] **步骤 1：先改判据**
- [ ] **步骤 2：验证失败**
- [ ] **步骤 3：实现**

- `settingsSchema`：`strm: { mode, baseUrl, localRoot, remoteRoot }`，mode 白名单回落 `remote_same`。
- `renamePayload`：`strm` 参数对象 → `generate_strm` / `strm_mode` / `strm_base_url` / `strm_local_root` / `strm_remote_root`；`finalize` 不带配置项（只带 `generate_strm: false`）。
- `workspace`：`generateStrm` ref；`switchSource('local')` 关闭；`buildPreview` 行上带 `strm`；`executeAction` 载荷带 strm；`renameAggregate` 合并 `strm_written` / `strm_skipped`。
- [ ] **步骤 4：验证通过**

---

## 任务 5：前端界面

**文件：**
- 修改：`frontend/src/views/SettingsView.vue`、`frontend/src/components/TemplateConfig.vue`、`frontend/src/components/FileTable.vue`、`frontend/src/components/ResultDialog.vue`、`frontend/src/views/HomeView.vue`
- 测试：`frontend/scripts/check-sfc-compile.mjs`、`check-execute-behaviour.mjs`

- [ ] **步骤 1：设置页** — 新增「STRM 生成」面板（模式 select + 三个输入）。
- [ ] **步骤 2：模板面板** — 「同时生成 STRM」勾选 + 模式提示，本地源置灰。
- [ ] **步骤 3：预览表** — strm 落点行（`title` 全路径）。
- [ ] **步骤 4：结果对话框** — STRM 写入 / 跳过清单。
- [ ] **步骤 5：判据与构建** — `npm run check`、`npm run build`。

---

## 任务 6：文档与全量验证

- [ ] README：功能特性、接口表、OpenList 集成（strm 三种模式与 docker volume 提醒）、环境变量/设置说明。
- [ ] `cd backend && .venv/bin/python -m pytest -q` 全绿。
- [ ] `cd frontend && npm run check` 全绿、`npm run build` 成功。

---

## 执行结果（2026-10-27）

- 任务 1~5 全部完成，判据先行（先红后绿）：后端新增 45 条用例（328 passed），
  前端 11 个判据脚本全绿（工作区 79 项、执行行为 30 项）。
- **执行期与设计的唯一偏差**：镜像结构的根改用新字段 `strm_scan_root`，而不是既有
  的 `path`。原因：`path` 在前端是「首行文件所在目录」，递归扫描时不是扫描根 ——
  拿它做 relpath 会让所有剧退化成扁平落点。已同步回 spec §4 / §6。
- **`npm run build` 的异常**：本机运行环境的 fs shim 在「覆盖 `public/favicon.svg`」
  时报错并让 vite 以非零状态退出，但产物实际写全并已逐项核对 ——
  `dist/index.html` 引用的两个资源都存在、4 个新哈希 JS 已生成、bundle 内含
  “同时生成 STRM 文件 / STRM 生成 / 未生成原因”等新文案。
  在普通终端重跑一次可确认没有残留半成品。
- 构建把被替换的旧产物移进了仓库根目录的 `.Trash-0/`（环境行为，未纳入 `.gitignore`），
  确认无用后可直接删除。

---

## 后续修订（2026-10-27，按用户反馈）

1. **远端自定义目录搬进工作区左栏** — 它随任务变（扫 A 库写 A、扫 B 库写 B），
   不属于设置页的长期偏好。设置里的 `strm.remoteRoot` 字段删除，改由
   `workspace.strmRemoteRoot` 持有并持久化到独立键 `episode-renamer:strm-root`；
   左栏输入框旁加「浏览」，复用 OpenList 浏览对话框（`browse.target` 区分落点，
   选目录不会改掉扫描路径）。
2. **指定根目录时先建剧集名目录** — 落点从 `{根}/{相对扫描根}` 改为
   `{根}/{剧名}/{相对扫描根}`（`show_dir_of` + `rooted_rel_dir`）。修掉「扫描根
   就是剧目录时所有 strm 平铺进根目录」这个真实缺陷，同时也是 Emby 认库的形状。
   两种扫描起点（整库 / 单剧）靠首段去重落到同一位置。
3. **strm 内容不转义** — `build_strm_url` 去掉逐段 `quote`，原样写入远端路径。
   代价（`#` / `?` 会被播放器当语法）已写进 spec §10 与函数 docstring。

判据：后端 340 passed（strm 相关 57 条，含新增的剧名目录 / 去重 / 原样写入 / 预览剧名目录用例）；
前端 11 个脚本全绿（工作区 87 项，新增 6 条围绕「目录归属与浏览落点」的断言）；
`npm run build` 成功，产物含新文案与 `strm-root` 存储键。
