# OpenList STRM 生成 — 设计规格

- 日期：2026-10-27
- 状态：待实现
- 上游：`2026-10-26-openlist-nfo-write-design.md`（NFO 管线的落点推导、失败降级与测试分层直接复用）

## 1. 目标

为 OpenList 云盘源生成 `.strm` 文件：每个视频对应一个只含播放链接的文本文件，供 Emby / Jellyfin 直接扫描并在线播放，不需要 rclone 挂载网盘。

- 触发方式与 NFO 同构：跟随重命名执行，逐文件写自己的 strm；
- 支持三种输出位置：**本地镜像目录 / 远端自定义目录 / 远端同目录**；
- 链接形态统一为 `/d/` 直链，对外访问地址可单独配置；
- 落点与跳过原因在预览、干跑、结果对话框中如实可见。

## 2. 不在范围

- 本地源的 strm（本地文件没有可播放 URL）。
- 剧集级 / 季级 strm（strm 是每文件的派生品，没有组级事实）。
- 已存在 strm 的“跳过”语义 —— 见 §5.2。
- strm 内容模板（`{url}` 之外的变量）、多地址负载均衡、token 鉴权链接。
- 远端目录扫描、增量更新、对账（不做“库里有视频但缺 strm”的检测）。

## 3. 关键事实

| 事实 | 位置 |
| --- | --- |
| 单文件执行返回真实落点 `landed_path` | `backend/app/api/renamer.py` 的 `execute_rename` |
| `skipped_same` 算落地（名字本来就对） | `backend/app/core/local_renamer.py` 的 `landed_path_of` |
| 远端上传能力已存在 | `backend/app/core/openlist_client.py` 的 `put_file` |
| 远端 mkdir 已存在（单层） | `openlist_client.mkdir(parent, name)` |
| 请求里已有扫描根 `path` 字段 | `backend/app/models/api.py` |
| 前端载荷只有一处构造 | `frontend/src/stores/renamePayload.js` |

## 4. 落点规则

设 `stem = posixpath.splitext(result.new_filename)[0] + ".strm"`，`landing_dir = posixpath.dirname(result.new_path)`。

| `strm_mode` | 落点 | 写盘 |
| --- | --- | --- |
| `remote_same` | `posixpath.join(landing_dir, stem)` | `PUT /api/fs/put` |
| `remote_custom` | `posixpath.join(remote_root, show_dir, rel_dir, stem)` | 逐级 mkdir + `PUT /api/fs/put` |
| `local` | `os.path.join(local_root, show_dir, rel_dir, stem)` | `mkdir(parents=True)` + 覆盖写 |

**`show_dir`（剧集名目录）是所有「指定根目录」模式的必经一层**：

- 优先取 `plan.parsed.show_name`（含用户手动改过的剧名），经 `safe_filename` 清洗，
  去掉 `\ / : * ? " < > |` 与首尾空白；`.` / `..` 一律拒绝（它们是路径语义，不是名字）；
- 解析不出剧名时回落到 `basename(landing_dir)`，再回落到 `basename(scan_root)`；
- 三层全空才退化为旧行为（只按相对扫描根镜像）。

**为什么必须有这一层**：扫描根常常**就是剧目录**（用户一次扫一部剧），此时
`rel_dir` 为空，旧规则把所有 strm 平铺进输出根 —— 换一部剧再跑一次，两部的文件
混在同一个目录里。先建剧名目录后，落点与「扫的是整库还是单剧」无关，也正是
Emby / Jellyfin 认库所需的 `Show/Season/episode` 形状。

`rel_dir = posixpath.relpath(landing_dir, scan_root)`：

- `scan_root` 取请求里的 `strm_scan_root`（前端传**用户实际扫描的目录**，即 `workspace.path`）；
- 不能用请求里已有的 `path`：它由前端从首行文件路径推出（`files[0].path` 去掉文件名），
  递归扫描时只是第一集的目录 —— 拿它做根会让所有剧退化成扁平落点。该字段仅在
  `strm_scan_root` 缺省时作兜底（手工 API 调用）；
- `rooted_rel_dir(rel_dir, show_dir)` 会**去掉重复的一层**：扫描根在剧目录之上时
  `rel_dir` 首段已是剧名（`Show/Season 01`），再冠一次会得到 `Show/Show/Season 01`。
  首段与剧名同形（忽略大小写）时只保留一层，于是两种扫描起点落到同一位置；
- 结果以 `..` 开头或为空（`"."`）时回落成空串，绝不写到根外面；
- 开启季目录模板时 `landing_dir = /mount/剧名/Season 01`，于是 rel_dir 自然是 `剧名/Season 01`。

`local` 模式额外做一次落点守卫：`os.path.realpath(目标)` 必须以 `realpath(local_root) + sep` 开头，否则跳过并报 `输出目录越界`。

## 5. 行为规则

### 5.1 何时写

- `strm.enabled` 为假：什么都不做，不产生 `strm_skipped`（用户没要求）。
- 源不是 `openlist`：不写。路由在入口处拒绝（§6）。
- 字幕（`plan.file_info.is_subtitle`）：跳过，不产生记录（与 NFO 同为管线外）。
- 视频未落地（`landed_path_of(result) is None`）：不写，记 `该文件未改名, 不生成 STRM`。
- 其余一律写，包括 `skipped_same`（文件名本来就对，strm 仍需要存在）。

### 5.2 冲突与覆盖

**目标已存在一律覆盖。** strm 是派生文件：内容只由本次落点与 base URL 决定，跳过只会留下指向旧名字/旧地址的链接。不新增 `strm_overwrite` 开关。

### 5.3 URL

```
{base}/d/{原样写入的 result.new_path}
```

- `base = (strm_base_url or client.server_url).rstrip("/")`；
- **不做百分号编码**：写出来的是人能读懂的 `http://h:5244/d/115/我的剧/第 1 集.mkv`。
  Emby / VLC 取到 strm 后会自己编码再发请求，中文与空格仍能播放；
- 代价：`#` 与 `?` 在 URL 里有语法含义，文件名带这两个字符时播放器会把后面当成
  fragment / query，链接必然 404。这是「不转义」规则的边界，见 §10；
- 文件内容为 `url + "\n"`，UTF-8 编码。
- base 为空（既没配也没连上）：跳过并报 `未配置 STRM 地址`。

### 5.4 失败降级

与 NFO 同一条纪律：**strm 的任何失败都不改变重命名的成功状态与计数**，只进 `strm_skipped`。

| 情形 | 原因串 |
| --- | --- |
| 未落地 | `该文件未改名, 不生成 STRM` |
| 本地根目录未配置 | `未配置 STRM 输出目录` |
| 远端根目录未配置 | `未配置 STRM 远端目录` |
| base 为空 | `未配置 STRM 地址` |
| 本地落点越界 | `输出目录越界: ...` |
| 本地写盘失败 | `写入失败: ...` |
| 远端 mkdir / put 失败 | `写入失败: ...` |

## 6. 接口契约

三个请求模型（`RenamePreviewRequest` / `RenameBatchRequest` / `RenameExecuteRequest`）新增：

```python
generate_strm: bool = False
strm_mode: Literal["local", "remote_custom", "remote_same"] = "remote_same"
strm_base_url: str = ""
strm_local_root: str = ""
strm_remote_root: str = ""
strm_scan_root: str = ""
```

- `/rename/preview`：每行新增 `"strm": {"mode", "path", "url"} | null`。**不写盘、不出网**（不做远端存在性检查，因为总是覆盖）。
- `/rename/execute`：OpenList 分支在重命名与 NFO 之后写 strm；响应新增 `strm_written: [path]`、`strm_skipped: [{path, reason}]`。
- `/rename/dry-run`：OpenList 分支只算落点，返回同名字段表示“将写入”；不改盘。
- `/rename/finalize`：不涉及 strm（字段继承下来但不读）。
- `source=local` 且 `generate_strm=true`：`400`，`detail="STRM 仅支持 OpenList 源"`（预览 / 执行 / 干跑三处一致）。前端已置灰，这里是防手工调用。

## 7. 前端契约

- **设置页**「STRM 生成」面板只放**长期**项：
  - 输出模式（本地镜像 / 远端自定义目录 / 远端同目录）；
  - 对外访问地址（留空使用 OpenList 服务器地址）；
  - 本地根目录（仅 `local` 模式显示）。
- **远端自定义目录不在设置页**：它随任务变（扫 A 库写 A、扫 B 库写 B），住在
  **工作区左栏**「同时生成 STRM」下方的输入框 + 「浏览」按钮。
  - 值存在独立的 `localStorage` 键 `episode-renamer:strm-root`，**不进 settings** ——
    否则设置页的草稿语义会在保存时把它盖回旧值，而那个字段在设置页根本看不见；
  - 「浏览」复用 OpenList 浏览对话框，靠 `browse.target = 'scan' | 'strm'` 区分落点，
    选目录**不会**顺手改掉扫描路径；`strm` 目标允许选挂载根本身（扫描目录不允许）。
- **工作区模板面板**新增「同时生成 STRM」勾选：
  - 仅 OpenList 源可勾；本地源置灰并提示「仅 OpenList 源支持」；
  - 切到本地源时自动关闭（与早期 NFO 的处理同构）。
- **预览表**：在 NFO 落点列之后显示 strm 落点（`title` 给全路径）；字幕行与 `strm=null` 的行不显示。
- **结果对话框**：新增「STRM」清单（写入 / 跳过 + 原因），与 NFO 清单并列。
- 请求字段全部经 `renamePayload.js` 一处构造，`mode` 为 `finalize` 时不带 strm 字段（后端不读）。
  其中 `strm_remote_root` 由 workspace 的 `strmRemoteRoot` 补齐（`strmOptions` 单点组装），
  其余三项来自 `settingsStore.strm`。

## 8. 测试

后端：

| 文件 | 覆盖 |
| --- | --- |
| `test_strm_url.py` | 原样写入（不转义）、base 尾斜杠、`/d/` 后只有一个斜杠、空 base/空路径、剧集名目录与去重 |
| `test_strm_local.py` | 剧集名目录、相对扫描根镜像、扫描根=剧目录时仍建剧名目录、覆盖写、越界拒绝、字幕/未落地跳过 |
| `test_strm_remote.py` | `remote_same` / `remote_custom` 落点、逐级 mkdir 缓存、put_file 覆盖、失败降级 |
| `test_rename_strm_route.py` | 预览字段、execute 写盘（三种模式 + 扫描根=剧目录）、dry-run 不写、`source=local` 400、未配置根目录的原因串 |

前端：

- `check-settings-schema.mjs`：strm 三项归一化、非法 mode 回落、**不含 `remoteRoot`**。
- `check-rename-payload.mjs`：四个形态都带 `generate_strm`，`finalize` 不带 strm 配置字段。
- `check-execute-behaviour.mjs`：OpenList + `generateStrm` 时执行请求体带 strm 字段、结果聚合含 `strm_written`。
- `check-workspace-gating.mjs`：切到本地源自动关闭 `generateStrm`；「浏览」把目录写进
  `strmRemoteRoot` 而不动扫描路径；该值落在独立存储键上。

## 9. 验收判据

1. 云盘源勾选「同时生成 STRM」+ 本地模式，执行后本机出现 `剧名/Season 01/xxx.strm`（扫描根即剧目录时为 `剧名/xxx.strm`），内容是一行可播放的 `/d/` 直链，中文原样不转义。
2. 切到 `remote_custom`，在**左栏**填远端根目录后，同一批文件在 `根/剧名/` 下出现同名 strm；目录不存在时自动创建。
3. 切到 `remote_same`，strm 与视频同目录同名（扩展名换成 `.strm`）。
4. 预览能逐行看到 strm 落点，与实际写出的路径一致。
5. 字幕不产生 strm；未落地的视频不产生 strm 且原因可见。
6. 任一 strm 失败都不影响重命名的成功状态与计数。
7. 本地源勾选 strm 被后端拒绝（400），前端也点不到。
8. 现有后端用例与全部前端判据保持通过。

## 10. 已知限制

- 远端模式每个文件至少一次 `PUT`，限流器与并发设置照常生效；大批量会明显慢于本地模式（本地是纯 IO）。
- `remote_same` 与视频同目录：用 rclone 挂载扫描的 Emby 会同时看到视频与 strm，出现重复条目 —— 这是该模式的固有代价，界面上以提示文案说明。
- 不做“已存在但内容不同”的比对：总是重写。
- `/d/` 直链要求 OpenList 侧允许游客访问该路径；若网盘驱动限制 UA/Referer，可能需要改用 `/p/`（本期不做）。
- **strm 内容不转义**（用户要求）：文件名里的 `#` / `?` 会被播放器当成 fragment / query，
  该文件的可播放链接必然失效。要支持这类文件名只能改回逐段 `quote`，二者不可兼得。
