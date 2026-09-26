# TMDB 单集元数据与 NFO 生成设计

日期：2026-09-26
分支：`feat/tmdb-nfo`
状态：待用户审核
上游：无（本设计为首个元数据相关设计）

---

## 1. 目标

两件事，一件依赖另一件：

1. **让每集标题真正来自 TMDB** —— 解析出 `(剧名, 季, 集)` 后向 TMDB 查该集真实标题，填入 `ParsedInfo.title`，使模板变量 `{title}` 从死字段变成可用字段。
2. **生成剧集信息 NFO 文件** —— 输出 Emby / Jellyfin / Kodi 规范的 `tvshow.nfo` + `season.nfo` + 每集 `SxxExx.nfo`，随重命名一并落盘，让刮削不再依赖在线查询。

## 2. 范围

**在范围内**
- TMDB 客户端（搜索剧集、剧集详情、季详情）
- 按 `(剧名, 季)` 聚合查询与进程级缓存
- 匹配失败的分级降级与可见化
- 预览表新增 TMDB / 标题列 + 搜索重选对话框
- NFO 三种文件的 XML 构建与路径推导
- 剧集根目录判定与库根污染防护
- NFO 随重命名一并生成（含 dry-run 清单与覆盖开关）
- 设置页 TMDB 面板（API Key、语言、启用、测试连接）
- 配置下发链路（请求体 > `.env` > 未配置）

**不在范围内**
- OpenList 云盘的 NFO 写入（需新增 `/api/fs/put` 上传能力，本期不做）
- 海报 / 背景图下载（YAGNI）
- 番剧绝对集号到 TMDB 季内集号的自动换算（见 §14）
- 本地重命名的撤销功能（设置页文案提到但代码未实现，与本设计无关）
- 前端测试设施建设

## 3. 现状核实

本设计的全部前提均已在代码中核实，非推测。

| # | 事实 | 证据 |
|---|---|---|
| 1 | **`ParsedInfo.title` 是死字段** —— 字段存在但从未被赋值 | `backend/app/models/file.py:26` 定义；`backend/app/core/parser.py:293-361` 的 `parse_filename` 全文不写 `title` |
| 2 | `{title}` 模板变量已实现但永远渲染为空串 | `backend/app/core/template.py:49-50` → `return info.title or ""` |
| 3 | 前端 README 对此诚实标注为「部分解析时可用」 | `README.md` 变量表；`frontend/src/components/TemplateConfig.vue:74` 写「集标题（部分资源可解析）」 |
| 4 | **预览接口被高频调用** —— 模板输入框每敲一键触发一次预览 | `frontend/src/stores/workspace.js:412-419` 的 watch 依赖 `tplStore.currentTemplate`；`frontend/src/components/TemplateConfig.vue:18` 每次 input 事件都 emit `template-edit`；`workspace.js:265-268` 的 `onTemplateEdit` 直接调 `buildPreview()` |
| 5 | 项目**无 TMDB / NFO 相关代码** | 全仓 grep `tmdb`、`nfo` 仅命中无关标识符 |
| 6 | **已有「死设置」前科** —— OpenList 并发与间隔两项设置写了但未下发 | `frontend/src/views/SettingsView.vue:67-77` 的说明文字自陈：「此处保存的值会被保留，但尚未下发到后端」 |
| 7 | OpenList 客户端**无写文件能力** —— 只有 `mkdir` / `move` / `rename` | `backend/app/core/openlist_client.py:174-219` |
| 8 | OpenList 下「创建季文件夹」已采用「禁用 + 注明」处理 | `frontend/src/components/TemplateConfig.vue:24` |
| 9 | 后端 pytest 是**唯一**自动化防线 | `backend/tests/` 仅 3 个文件；`frontend/` 无测试设施（`frontend/scripts/` 为 node 断言脚本） |
| 10 | 设置项以「前端 localStorage → 随请求下发」为既定链路 | `frontend/src/stores/settingsSchema.js`；`workspace.js:284-285` 下发补零位数 |
| 11 | 测试无需新依赖即可 mock HTTP | `backend/requirements.txt` 已有 `httpx`，其 `MockTransport` 可拦截请求 |

事实 4 是本设计的技术前提，不是优化项：若预览阶段直接查 TMDB，用户打一行模板会打出十几次外部请求，功能不可用。故 §6 的缓存是**必要条件**。

事实 6 是本设计对配置链路的约束来源：新增的 TMDB 配置必须可验证地走通「设置页 → 请求体 → 后端」全程，否则会重演同一类缺陷。

## 4. 模块结构

```
backend/app/core/
  tmdb_client.py     新增  TMDB HTTP 客户端（只懂 URL 与响应，不含业务判断）
  tmdb_resolver.py   新增  分组去重 / 缓存 / 匹配 / 降级判定
  nfo_writer.py      新增  纯函数构建 XML 字符串（不触碰文件系统）
backend/app/models/
  tmdb.py            新增  TMDB 领域模型
  nfo.py             新增  NfoOptions / NfoPlan
backend/app/api/
  tmdb.py            新增  /api/tmdb/search、/api/tmdb/test
  renamer.py         改    preview / execute / dry-run 接入元数据与 NFO
backend/app/config.py  改  tmdb_* 配置项
frontend/src/
  stores/settingsSchema.js   改  新增 tmdb 分组
  stores/settings.js         改  apply / toObject 带 tmdb
  stores/workspace.js        改  NFO 选项、tmdbOverrides、预览行扩展
  views/SettingsView.vue     改  新增 TMDB 面板
  components/FileTable.vue   改  新增标题列 / TMDB 列 / NFO 列
  components/TmdbMatchDialog.vue  新增  搜索与重选
  components/TemplateConfig.vue   改  NFO 勾选
  api/tmdb.js                新增
```

**职责边界**：`nfo_writer` 只把数据变成 XML 字符串，写盘由 renamer 负责。这样 NFO 生成的全部逻辑都是纯函数，可在无文件系统、无网络的条件下穷举测试——考虑到事实 9（后端 pytest 是唯一防线），这是本设计里回报最高的一个切分。

## 5. TMDB 客户端

### 5.1 鉴权自动识别

TMDB 有两套并行的鉴权方式，用户极可能填错而不自知：

- **v3**：`?api_key=<32位十六进制>`
- **v4**：`Authorization: Bearer <JWT，以 eyJ 开头>`

客户端按前缀自动分流：以 `eyJ` 开头按 v4 Bearer 发送，否则按 v3 查询参数发送。不做这一层，用户把 v4 token 填进 Key 框会拿到 401，而 401 的成因有四种，排查成本高。

### 5.2 接口

| 方法 | 端点 | 用途 |
|---|---|---|
| `search_tv(query, language, year=None)` | `GET /search/tv` | 剧名 → 候选列表（含 `id` / `name` / `first_air_date` / `original_name`）。`year` 可选，用于消歧（如解析出的剧名自带年份） |
| `get_tv_detail(tv_id, language)` | `GET /tv/{id}` | 剧集级元数据（原名、年份、简介、评分、类型、状态、首播日） |
| `get_season(tv_id, n, language)` | `GET /tv/{id}/season/{n}` | 该季全部集的元数据（集号、标题、简介、播出日、评分、TMDB 集 id） |

`language` 默认 `zh-CN`。TMDB 在请求语言无对应数据时会回落原文，响应中如实反映，客户端不做补译。

### 5.3 错误分级

| 响应 | 处理 | 理由 |
|---|---|---|
| 401 | **抛出，前端报错** | Key 无效属配置错误，必须让用户看见 |
| 404 | 降级为 `season_not_found` | 该季在 TMDB 不存在是正常情况（如特别篇） |
| 429 | 退避重试一次，仍失败则降级 | 限流是暂时状态 |
| 超时 / 网络异常 | 降级为 `unavailable` | TMDB 不可达不应影响本地文件操作 |
| 5xx | 降级为 `unavailable` | 同上 |

### 5.4 铁律：TMDB 故障不得阻断重命名

重命名是主功能，标题与 NFO 是附加值。TMDB 不可用时，用户应得到「文件名照常改好，只是没有标题与 NFO」，而不是整个操作失败。

实现约束：`tmdb_resolver` 的任何异常都必须在**文件级**被捕获并转成降级状态，不得向上冒泡到 `/api/rename/execute` 的顶层。唯一例外是 401（配置错误）—— 它在预览阶段即报错，用户不会走到执行。

## 6. 聚合与缓存

### 6.1 按 (剧名, 季) 聚合

朴素实现会对每个文件查一次 TMDB，请求数为 O(文件数)。改为先分组：

```
10 个文件
  → 解析得 (绝命毒师, 2) × 5、(绝命毒师, 3) × 5
  → search_tv("绝命毒师")           1 次 → tv_id=1396
  → get_season(1396, 2)             1 次 → 该季 5 集数据
  → get_season(1396, 3)             1 次 → 该季 5 集数据
共 3 次请求，而非 10 次
```

请求数降为 **O(剧数 + 季数)**。

### 6.2 缓存

进程级缓存，键含 API Key 指纹：

| 缓存项 | 键 |
|---|---|
| 剧集搜索结果 | `(api_key_fingerprint, language, normalized_show_name)` |
| 季详情 | `(api_key_fingerprint, language, tv_id, season_number)` |

**Key 指纹必须进缓存键**：用户换 Key 后若命中旧缓存，会表现为「改了 Key 却不生效」，与事实 6 所记的历史缺陷同源。

TTL 默认 3600 秒。用户手动重选剧集时直接覆盖该分组对应条目，不等 TTL 过期。

剧名归一化：去首尾空白、大小写折叠、统一全角半角。归一只用于缓存键与分组，不影响展示。

### 6.3 并发

多个预览请求可能同时到达同一分组。用一个 `asyncio.Lock` 保护缓存读写与「进行中请求」去重表：同键的并发请求合并为一次外部调用。命中缓存的路径不持锁，保证正常情况无额外延迟。

## 7. 降级状态机

每个文件在解析后携带一个 `tmdb_status`，六种取值全部显式，无隐式成功：

| 状态 | 触发条件 | 预览表显示 | 该集 NFO |
|---|---|---|---|
| `matched` | 剧、季、集全部命中 | `绝命毒师 (2008)` + 集标题 | 写入，含标题与简介 |
| `disabled` | 未启用或未配置 Key | `—` | 不写入 |
| `show_not_found` | 搜索无结果 | ⚠ 未匹配 + 🔍 | 不写入 |
| `season_not_found` | 剧命中但季详情拉不到 | ⚠ 无此季 + 🔍 | 不写入 |
| `episode_not_found` | 季拿到但该集号不存在 | ⚠ 无此集 | 不写入 |
| `unavailable` | 请求失败（超时/网络/5xx） | ⚠ 不可用 | 不写入 |

**绝不猜测。** 状态非 `matched` 时不写入任何 NFO，也不回填 `title`。理由：静默写错标题的失败模式（看起来一切正常、内容全错、无从发现）远比明确报错危险——这与 §9 的库根防护同一条原则。

`tmdb_status != matched` 的文件仍**照常完成重命名**（见 §5.4），只是文件名中的 `{title}` 渲染为空串。

### 7.1 手动补救

用户在预览表点 🔍 重选剧集后，该剧名对应的 `tmdb_overrides[show_name] = tv_id` 随请求下发，分组解析时优先采用，绕开自动搜索结果。

用户还可在预览表直接编辑某行的标题（`OverrideInfo.title`，字段已存在于 `backend/app/models/file.py:43`），覆盖 TMDB 结果。这条路径同时是 `episode_not_found` 的兜底手段。

## 8. NFO 内容规范

### 8.1 三种文件

```xml
<!-- tvshow.nfo -->
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<tvshow>
  <title>绝命毒师</title>
  <originaltitle>Breaking Bad</originaltitle>
  <sorttitle>绝命毒师</sorttitle>
  <year>2008</year>
  <plot>…</plot>
  <rating>8.9</rating>
  <votes>15000</votes>
  <genre>剧情</genre>
  <genre>犯罪</genre>
  <premiered>2008-01-20</premiered>
  <status>Ended</status>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <tmdbid>1396</tmdbid>
</tvshow>

<!-- season.nfo -->
<season>
  <title>第 2 季</title>
  <seasonnumber>2</seasonnumber>
  <plot>…</plot>
  <premiered>2009-03-08</premiered>
  <uniqueid type="tmdb" default="true">3575</uniqueid>
</season>

<!-- 绝命毒师 - S02E05.nfo -->
<episodedetails>
  <title>Breakage</title>
  <showtitle>绝命毒师</showtitle>
  <season>2</season>
  <episode>5</episode>
  <plot>…</plot>
  <aired>2009-04-05</aired>
  <rating>8.7</rating>
  <uniqueid type="tmdb" default="true">62085</uniqueid>
</episodedetails>
```

### 8.2 两个关键约束

**`<uniqueid type="tmdb">` 必须存在。** Emby / Jellyfin 靠它锁定剧集身份。缺失时媒体服务器会重新走一遍在线刮削，NFO 形同白写——这是「写了 NFO 但没生效」最常见的原因。

**每集 NFO 靠文件名配对识别，不靠 XML 内容。** `绝命毒师 - S02E05.nfo` 必须与 `绝命毒师 - S02E05.mkv` 同名同目录。这直接决定了 NFO 必须与重命名在同一流程内完成（而非事后独立补写），也是本设计不接受「独立按钮」方案的技术原因。

### 8.3 生成方式

用 `xml.etree.ElementTree` 构建 + `ET.indent` 缩进（Python 3.9+ 起可用），根元素以 `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` 声明开头。

**不使用字符串拼接。** 剧名含 `&`（如「Tom & Jerry」）、`<`、`>` 时拼接必然产出非法 XML，且这种剧名在真实媒体库中并不罕见。ElementTree 自动完成实体转义。

字段缺失时**省略该标签**，不写空标签（`<plot></plot>` 会被部分刮削器当作「简介为空」而覆盖，`<plot/>` 同理）。多值字段（`genre`）重复标签。

### 8.4 内容来源

| 字段 | 来源 |
|---|---|
| `tvshow.*` | `get_tv_detail` |
| `season.*` | `get_season` 的季级字段 |
| `episodedetails.title` | `get_season` 中该集的 `name`；若用户手动覆盖则用覆盖值 |
| `episodedetails.showtitle` | 剧集 `title`（帮助 Emby 建立关联） |

## 9. NFO 路径推导与库根防护

### 9.1 三种文件的落点

| 文件 | 落点 | 风险 |
|---|---|---|
| 每集 `.nfo` | 视频**新路径**替换扩展名为 `.nfo` | 无 |
| `season.nfo` | 该季视频的**公共父目录** | 低 |
| `tvshow.nfo` | 该剧视频的**公共父目录**（剧集根） | **高——可污染整个媒体库** |

`season.nfo` 与 `tvshow.nfo` 用的是**同一条规则的两种粒度**：前者按季取公共父，后者按剧取公共父。

`season.nfo` **必须落在季目录里**，而不是剧集根 —— Emby / Jellyfin 只在季目录下查找 `season.nfo`。两种情形下它自然正确：

```
开季文件夹    /media/绝命毒师/Season 02/ 下的 Videos → 公共父 = Season 02/      ✓ 季目录
未开季文件夹  /media/绝命毒师/ 下的 Videos          → 公共父 = /media/绝命毒师/   ✓ 此处即是季目录

### 9.2 污染场景

用户扫描 `/media`，其下多部剧混放且未启用「创建季文件夹」。若把 `tvshow.nfo` 写入 `/media`，Emby 会把**整个媒体库识别为一部剧**。此操作不可逆，且执行前无任何征兆。

### 9.3 剧集根判定规则

**剧集根 = 该剧所有选中视频新路径的公共父目录**，外加一道校验：

```
✓ 开季文件夹    /media/绝命毒师/Season 02/ + Season 03/
                → 公共父 /media/绝命毒师/                    正确

✓ 未开，已分季   /media/绝命毒师/S01/ + /media/绝命毒师/S02/
                → 公共父 /media/绝命毒师/                    正确

✗ 混放          /media/未分类/ 下同时含 A 剧与 B 剧
                → 公共父 /media/未分类/
                → 校验：该目录下本批次视频的 show_name 必须同一
                → 不满足 → 不写剧集级 NFO
```

判定采用公共父目录（而非「视频所在目录」），是因为视频可能分处 `S01` / `S02` 子目录——此时剧集根应上溯一层，取视频所在目录会把 `tvshow.nfo` 写进季子目录。

**show_name 一致性校验同时把关两种剧集级文件。** 校验不通过时，`tvshow.nfo` 与 `season.nfo` 都不写：此时该目录根本不是一部剧的目录，把它当成季目录写 `season.nfo` 同样错。

### 9.4 两道保障

- **可见性**：预览表显式列出每部剧将写入的 `tvshow.nfo` / `season.nfo` **绝对路径**。落点错误时用户一眼可见，而不是执行完才发现。
- **安全性**：「覆盖已存在」开关**默认关闭**，已存在的 NFO 文件不动。

判定不成立时**宁可不写**，并在预览表标注原因（`nfo_scope: episode_only`）。

### 9.5 与季文件夹的交互

未启用季文件夹时，视频与 `season.nfo` / `tvshow.nfo` 同处一层。此时 `season.nfo` 意义有限但仍写入（不影响刮削，且启用季文件夹后可立即受益）。

## 10. 配置链路

### 10.1 后端配置（`backend/app/config.py`）

```python
tmdb_api_key: str = ""          # 空表示未配置
tmdb_language: str = "zh-CN"
tmdb_enabled: bool = True       # 关闭后完全跳过 TMDB
tmdb_timeout: float = 10.0
tmdb_cache_ttl: int = 3600
```

### 10.2 请求模型新增字段

`RenamePreviewRequest` 与 `RenameExecuteRequest` 均新增：

```python
tmdb_api_key: Optional[str] = None
tmdb_language: Optional[str] = None
generate_nfo: bool = False
nfo_overwrite: bool = False
tmdb_overrides: dict[str, int] = {}   # 剧名 -> tv_id
```

`tmdb_overrides` 以**剧名**为键，因为重选是剧集级操作，与 §6.1 的分组语义一致。

键的取值是**解析所得的 `show_name` 原文**（即 `ParsedInfo.show_name`，前端表现为预览行的 `show_name` 字段），不是 §6.2 的归一化形式——归一化仅用于内部缓存键，若前端用它作键，两侧对不上就会静默失效，重演事实 6 的缺陷。后端在查表时对传入键做一次归一化后再匹配。

### 10.3 优先级

```
请求体 > .env / 环境变量 > 未配置（功能禁用，不报错）
```

未配置 Key 时功能整体降级为 `disabled`，重命名不受影响，预览表显示 `—`，设置页给出明确提示。

### 10.4 下发链路必须可测

依事实 6 的教训，本设计要求：**存在一条自动化测试断言设置页的值确实抵达后端并被使用**。参考 `backend/tests/test_pad_config.py` 与 `test_rename_routes.py` 的既有做法，断言请求体中的 `tmdb_api_key` 进入 resolver 并被用作缓存键的一部分。

## 11. 后端 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tmdb/test` | 用给定 Key 做一次最小查询，返回有效 / 无效 / 网络不可达 |
| GET | `/api/tmdb/search?q=&year=` | 剧名搜索，供重选对话框使用 |

`/api/tmdb/search` 与 `/api/tmdb/test` 均通过请求参数或请求头接收 Key，不落盘。

`/api/rename/preview` 响应新增每行字段：

```json
{
  "title": "Breakage",
  "tmdb_status": "matched",
  "tmdb_match": { "tv_id": 1396, "name": "绝命毒师", "original_name": "Breaking Bad", "year": 2008 },
  "nfo": {
    "episode": "/media/绝命毒师/Season 02/绝命毒师 - S02E05.nfo",
    "season":  "/media/绝命毒师/Season 02/season.nfo",
    "show":    "/media/绝命毒师/tvshow.nfo"
  },
  "nfo_scope": "full"
}
```

`/api/rename/execute` 与 `/api/rename/dry-run` 的响应在既有 `BatchRenameResult` 基础上扩展：

- `RenameResult` 增加 `nfo_path: Optional[str]` —— 该文件的**每集** NFO 落点，确实与单个文件一一对应
- `BatchRenameResult` 增加 `nfo_written: list[str]` 与 `nfo_skipped: list[{path, reason}]`

剧集级文件（`tvshow.nfo` / `season.nfo`）的汇总放在**批次**上而非每条结果上：它们不隶属任何单个文件，挂到每条结果会把同一路径重复 N 遍。dry-run 时这两项描述的是「将写入 / 将跳过」的计划，不落盘。

## 12. 前端改动

### 12.1 设置页

新增「TMDB 设置」面板：

- API Key（`type=password` + 显示切换）
- 语言（下拉，默认「中文 (zh-CN)」）
- 启用开关
- 「测试连接」按钮 → `/api/tmdb/test`，就地显示结果

### 12.2 设置存储

`settingsSchema.js` 新增 `tmdb: { apiKey, language, enabled }` 分组，`normalizeSettings` 中对三项做类型防御（非字符串回落默认、布尔强转），并在 `check-settings-schema.mjs` 中补断言。`stores/settings.js` 的 `apply` / `toObject` 同步带上。

### 12.3 工作区

- 新增 `generateNfo` / `nfoOverwrite` 状态，随 preview / execute / dry-run 一并下发
- `previewRows` 增加 `title`、`tmdb_status`、`tmdb_match`、`nfo`、`nfo_scope`
- 新增 `rematchShow(row)` → 打开 `TmdbMatchDialog`
- NFO 勾选框在 OpenList 源下置灰并注明，沿用事实 8 的既有处理方式

### 12.4 预览表

新增三列：「标题」（可编辑，写入 `OverrideInfo.title`）、「TMDB」（匹配状态 + 🔍）、「NFO」（每集 NFO 路径 + 该剧剧集级 NFO 落点）。

## 13. 测试策略

后端 pytest 为唯一自动化防线（事实 9），六组测试：

| 文件 | 覆盖 |
|---|---|
| `test_nfo_writer.py` | 纯函数：三种 XML 结构、实体转义（剧名含 `&` / `<`）、字段缺失时省略标签、缩进与声明 |
| `test_tmdb_client.py` | `httpx.MockTransport`：v3 / v4 鉴权分流、401 / 404 / 429 分支 |
| `test_tmdb_resolver.py` | 分组去重（断言请求次数）、缓存命中、缓存键含 Key 指纹、六种降级状态 |
| `test_nfo_plan.py` | 公共父目录推导、混放场景拒绝写剧集级 NFO、覆盖开关 |
| `test_rename_nfo_route.py` | dry-run 只列清单不落盘、execute 真落盘、OpenList 源下不写 NFO |
| `test_template_title.py` | `{title}` 在 matched / 降级 / 手动覆盖三种情况下的渲染 |

前端沿用项目惯例（无测试设施）：扩展 `frontend/scripts/check-settings-schema.mjs` 断言、`check-sfc-compile.mjs` 校验新组件可编译、构建产物 grep 确认新代码进入 bundle。

TMDB 真实调用**不进入自动化测试**（需要网络与有效 Key，且会引入不稳定）。`httpx.MockTransport` 已随 `httpx` 提供，无需新依赖。

## 14. 已知限制

**番剧绝对集号不换算。** TMDB 常把动画按季切分，而 BDRip 习惯使用绝对集号（1–25）。二者对不上时判为 `episode_not_found`，由用户手动重选或直接编辑标题。

不做自动换算的理由：换算规则（哪些剧采用绝对编号、如何识别、跨季如何映射）无法从文件名可靠推断，猜错的代价是静默写入错误标题。明确报错 + 手动补救的成本更低。

**TMDB 语言回落不补译。** 请求 `zh-CN` 而 TMDB 无中文数据时，返回的是原文标题。这是 TMDB 的数据现状，客户端如实呈现。

**OpenList 源不写 NFO。** 见 §2。TMDB 查询与 `{title}` 变量在 OpenList 源下**照常生效**，仅 NFO 写入缺席。

**海报不下载。** 需要额外处理图片格式、体积、命名规范，本期不做。

## 15. 分期

设计量较大，拆为两个计划，均产出可独立验证的交付物：

**计划 1 —— TMDB 元数据集成**
client + resolver + 配置链路 + 设置页 TMDB 面板 + 重选对话框 + **预览表的「标题」列与「TMDB」列**（§12.4 的前两列）。
交付后可验证：某个真实目录的每集标题确实来自 TMDB，`{title}` 渲染正确。

**计划 2 —— NFO 生成**
nfo_writer + 路径推导与库根防护 + renamer 集成 + NFO 勾选 UI + **预览表的「NFO」列**（§12.4 第三列）。
依赖计划 1 的 resolver 输出。

两份计划各自交付后都能独立验收：计划 1 验「标题对不对」，计划 2 验「NFO 写得对不对、落点对不对」。§12.4 的三列按此拆开，避免计划 1 交付时出现指向未实现能力的空列。

## 16. 裁定记录

设计过程中逐项确认的决议及其理由：

| # | 决议 | 理由 |
|---|---|---|
| 1 | NFO 生成**全套**（tvshow + season + 每集） | 一次达到 Emby / Jellyfin / Kodi 完整刮削规范，避免库根缺剧集级信息 |
| 2 | 自动匹配 TMDB + 预览表可搜索重选 | 纯自动会使错配不可见；纯手动则批量场景每组都要拦截 |
| 3 | NFO **随重命名一并生成**，非独立按钮 | 每集 NFO 靠文件名与视频配对，事后补写需另一套定位逻辑 |
| 4 | API Key **设置页填写 + 随请求下发**，`.env` 作回退 | 与既有设置链路一致；同时保留服务端默认，避免 Docker 场景每人重填 |
| 5 | OpenList **本期不支持** NFO 写入 | 需新增上传能力，独立工作量与风险；已有同类先例 |
| 6 | 匹配失败**显式降级，绝不猜测** | 静默写错标题的失败模式比明确报错危险得多 |
| 7 | 聚合查询 + 进程级缓存 | 预览接口被高频调用，无缓存则功能不可用（事实 4） |
| 8 | 缓存键含 API Key 指纹 | 避免重演「改了设置却不生效」类缺陷（事实 6） |
| 9 | TMDB 故障不阻断重命名 | 重命名是主功能，元数据是附加值 |
| 10 | 剧集根取**公共父目录** + show_name 一致性校验 | 取「视频所在目录」会在已分季目录下写错位置；校验拦下混放场景 |
| 11 | 剧集级 NFO 落点**在预览表显式可见** | 库根污染风险高且不可逆，可见性优于额外猜测规则 |
| 12 | 「覆盖已存在」**默认关闭** | 降低对既有 NFO 的意外破坏 |
| 13 | XML 用 ElementTree 生成，非字符串拼接 | 剧名含 `&` / `<` 时拼接必然产出非法 XML |
| 14 | 番剧绝对集号**不换算** | 见 §14 |
