# SDD execution ledger — 计划 1：TMDB 单集元数据集成

归档自执行期的工作区 ledger（原本在 `.superpowers/sdd/2026-09-26-tmdb-metadata/progress.md`，
该工作区在计划收尾时按规程删除）。**这是本计划的裁定记录**：pre-flight 扫描表、实施期裁定、
修复轮记录、以及每条裁定的理由与「判错会怎样」。计划文档本身在
`docs/superpowers/plans/2026-09-26-tmdb-metadata.md`；设计权威在
`docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md`。

裁定编号 R1–R59。要查「为什么代码是这样」时，从这里找。
**索引**：`docs/superpowers/ledgers/2026-09-26-tmdb-nfo-ruling-index.md` —— 跨两份 ledger 的
「会改变行为/范围」的裁定清单（附判错代价与锚点），合并审查从这里进。

---

# SDD ledger — plan: docs/superpowers/plans/2026-09-26-tmdb-metadata.md

分支：feat/tmdb-nfo（项目惯例：普通分支而非 worktree，见记忆 sdd-workflow）
MERGE_BASE：01b752d917138536df71bb5446d2058d40e39e65
Spec：docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md（可达，已读）
第二个计划：docs/superpowers/plans/2026-09-26-nfo-generation.md —— 完成本计划后执行，**不得并行**

## Pre-flight 冲突扫描

### 跨任务：共享文件或接口

| 任务对 | 一方产生 | 一方消费 | 结论 |
|---|---|---|---|
| P1T1 → P1T2 | `TmdbClient(api_key, language, timeout, transport)`、`cache_fingerprint()`、三个异常类、`TmdbShow/Season/Episode` | resolver 的 `self._client.cache_fingerprint()` / `.language` / `search_tv` / `get_tv_detail` / `get_season` | 一致。假客户端契约已在 P1T2 的 Interfaces 中列明 |
| P1T2 → P1T3 | `TmdbResolver(client, overrides=, cache=)`、`ResolveRequest(show_name, season, episode)`、`EpisodeMatch(status, show, season, episode)`、六个状态常量 | 路由 `_tmdb_summary` 读 `.show` / `.episode`；`_with_tmdb_titles` 构造 `ResolveRequest` | 一致 |
| **P1T2 文件被 P1T3 改** | P1T2 建 `tmdb_resolver.py`，`_DEFAULT_CACHE` 用字面量 `3600` | P1T3 Step 1 改为 `settings.tmdb_cache_ttl` 并补回 `settings` import | **有意为之，已双向写明**。见 Ruling R1 |
| P1T1 → P1T4 | `TmdbClient`、`TmdbAuthError`、`TmdbUnavailableError` | `api/tmdb.py` 的 `_client` / `test_tmdb` / `search_tv` | 一致 |
| P1T3 文件被 P2T4 改 | P1T3 定义 `_with_tmdb_titles` 返回**二元组** | P2T4 Step 3 改为**三元组**，三处调用点同步解包 | **有意为之，已写明**。见 Ruling R2 |
| P1T3 → P1T7 | 预览响应 `title` / `tmdb_status` / `tmdb_match` | workspace.js 的 previewRows 消费同名字段 | 一致 |
| P1T5 → P1T6 | `settingsStore.tmdb.{apiKey, language, enabled}` | SettingsView 的 `draft.tmdb.*` | 一致 |
| P1T5 → P1T7 | `settingsStore.tmdb` | workspace.js 三处下发 | 一致 |
| P1T4 → P1T6 | `GET /api/tmdb/test`，请求头 `X-Tmdb-Key` / `X-Tmdb-Language` | `api/tmdb.js` 的 `testTmdb` 发同名字段 | 一致 |
| P1T4 → P1T7 | `GET /api/tmdb/search` | `api/tmdb.js` 的 `searchTmdb` → `workspace.searchShow` | 一致 |
| P1（全部）→ P2T1 | `TmdbShow/Season/Episode` | `nfo_writer` 三个构建函数 | 一致 |
| **P2T1 文件被 P2T2、P2T3 追加** | P2T1 建 `nfo_writer.py`（只含 XML 构建） | P2T2 追加路径与决策；P2T3 追加写盘 | **有意为之**，每个追加步骤都写明要补的 import。见 Ruling R3 |
| P2T2 → P2T3 | `build_nfo_decisions(entries, options)`、`NfoDecision` | `batch_rename` 与 `write_nfo_files` 消费 | 一致 |
| P1T3 文件被 P2T3 改 | P1T3 改过 `models/api.py`、`local_renamer.py` | P2T3 再改两个文件（加 NFO 字段与参数） | 顺序执行，无冲突 |
| P2T3 → P2T4 | `batch_rename(..., nfo_options=, nfo_matches=)`、`RenameResult.nfo_path`、`BatchRenameResult.nfo_written/nfo_skipped` | 路由按此调用并断言同名响应字段 | 一致 |
| P1T7 文件被 P2T5 改 | P1T7 改 `workspace.js` / `FileTable.vue` / `HomeView.vue` | P2T5 再改同三个文件（加 NFO 选项与列） | 顺序执行，无冲突。两者追加的位置已分别写明（P1T7 在「集」后与「状态」后，P2T5 在「新文件名」前） |
| P2T4 → P2T5 | `nfo_scope` 四值 `disabled` / `unsupported_source` / `episode_only` / `full` | `NFO_SCOPE_HINTS` 的键 | 逐字一致 |

### 单任务：自身一致性

| 任务 | 测试 vs 实现 | 文件创建 vs 后续触碰 | 结论 |
|---|---|---|---|
| P1T1 | 14 个测试全部对应 `TmdbClient` 的既有方法 | 只建，不被后续改 | 自洽 |
| P1T2 | 23 个测试（计划原写 24，已更正，见 R4） | `tmdb_resolver.py` 被 P1T3 改，已双向写明 | 自洽 |
| P1T3 | `test_title_renders_when_present` 在 Step 4 应 FAIL、Step 7 后 PASS —— 时序正确 | 改 6 个文件，均为既有文件 | 自洽。Step 6 的行号引用有误，已更正（见 R4） |
| P1T4 | 5 个测试 | 只建 + `main.py` 注册 | 自洽 |
| P1T5 | 断言脚本 12 条新增断言 vs `normalizeSettings` 的 tmdb 分支 | 只改既有 3 个文件 | 自洽 |
| P1T6 | 无自动化测试，靠 `check-sfc-compile.mjs` + `npm run build` | 只建 `api/tmdb.js` + 改 SettingsView | 自洽（前端无测试设施是项目既知事实） |
| P1T7 | 无自动化测试，靠编译 + 构建产物 grep | 建 `TmdbMatchDialog.vue`；改 3 个既有文件 | 自洽。`AppModal` 用法已按 `BrowseDialog.vue` 的实际模式核对 |
| P2T1 | 15 个测试（计划原写 17，已更正，见 R4） | `nfo_writer.py` 被 P2T2/P2T3 追加 | 自洽 |
| P2T2 | 20 个测试，含顺序契约测试 | 追加 `nfo_writer.py` | 自洽。排序断言已按中文字符码位逐个核对（绝命律师 < 绝命毒师） |
| P2T3 | 8 个测试 | 追加 `nfo_writer.py`；改 4 个既有文件 | 自洽。`Path` 已在 local_renamer 顶部导入，无需局部 import |
| P2T4 | 6 个测试（5 + 1） | 改 `api/renamer.py` | 自洽。`nfo_scope` 的 disabled 分支已修正（见 R5） |
| P2T5 | 无自动化测试，靠编译 + grep | 改 3 个既有文件 | 自洽 |

## Pre-flight 裁定

Ruling R1: P1T2 先用字面量 `3600`、P1T3 再接到 `settings.tmdb_cache_ttl` —— 保留这个两步，不改成一,
因为 config 字段属于 P1T3 的边界（客户端与解析器的任务不该顺手改全局配置）；两步各有明确的 before/after
文本，不会漏。代价若判错：一个 `3600` 字面量若漏改，TTL 会无视 `.env` 配置 —— 影响仅为缓存时长，不致命，
且 P1T3 的 diff 里那行改动显眼。

Ruling R2: P2T4 把 `_with_tmdb_titles` 从二元组改为三元组 —— 接受这个跨计划签名破坏,
因为 NFO 的内容来源必须是同一份 `EpisodeMatch`（重新查 TMDB 会引入第二次外部调用与不一致风险）。
代价若判错：若 P2T4 遗漏某个调用点，Python 解包会立刻抛 ValueError，不会静默 —— 失败是响亮的。

Ruling R3: `nfo_writer.py` 被三个任务依次追加 —— 不拆成三个文件,
因为「XML 构建」「路径推导」「写盘」共用 `NfoDecision` 这一组类型，拆开会产生循环 import；
且 append-only 的改动模式冲突面最小。代价若判错：文件会到约 350 行，与 `parser.py`(372 行) 同量级，仍在可读范围。

Ruling R4: 计划四处笔误（P1T2 预期 24→23、P1T3 预期 11→10 与行号 10→13、P2T1 预期 17→15）就地更正,
因为它们是计数与行号疏漏，不影响任何设计决策。代价若判错：无 —— 更正后的数字已按测试函数逐个重数。

Ruling R5: P2T4 预览路由的 `nfo_scope` 在「启用了 NFO 但未配 TMDB」时必须报 `disabled` 而非 `episode_only`
—— 已修正计划文本。原写法会让 `all(...)` 在空字典上返回 False 从而落到 `episode_only`,
而那会误导用户以为「只是没写剧集级文件」。代价若判错：用户看到一个含糊的状态标签，不致命。

Ruling R6: P1T2 的 `test_concurrent_same_key_is_merged` 声明了未使用的 `monkeypatch` fixture —— 保持原样,
它是无害的（pytest 允许未使用的 fixture 参数），改它只会让转录与计划文本产生无谓差异。代价若判错：一条 lint 噪音。

Ruling R7: P1T3 Step 11 的 `test_invalid_tmdb_key_returns_400_not_silent_disabled` 会真的向 TMDB 发请求。
若执行环境无外网，该用例会得到超时/502 而非 400。实施者应如实报告该情况，由我裁定，**不得**为了让它变绿而
把断言放宽成「400 或 502」。

## 实施期裁定

Ruling R8: P1T1 实施者报告 brief 里两个 429 用例的 monkeypatch 会无限递归
（`lambda _s: asyncio.sleep(0)` 的 lambda 体在调用时按模块属性查找 `asyncio.sleep`，
而它已被换成 lambda 自身），并做了最小修正（先捕获 `real_sleep` 再 patch）—— **接受该修正**，
因为 brief 原文在本环境下按字面不可能通过，且实施者的改法保留了原意（仍走被 patch 的
asyncio.sleep、仍 await 一个真实的 0 秒协程），断言与结构一字未动。计划文本已同步更正并提交（6c26e24）。
代价若判错：429 退避路径的测试覆盖失真 —— 但该用例仍断言「重试一次后抛 TmdbUnavailableError」
与「第一次 429、第二次 200 时返回结果」，核心行为仍被钉住。

Ruling R9: 实施者遗留观察 —— `get_tv_detail` 在 Task 1 的 Interfaces 中列出，却无任何直接测试覆盖
（brief 未给，实施者按「只做 brief 要求」未自行补测）。**判定为真实缺口**，责任在计划而非实施者：
它是三个客户端方法里唯一没有被直接测试响应映射的一个，而 Task 2 的 resolver 与 Task 3 的 NFO
都依赖它的返回值。**将在本次任务审查后的修复轮中补一个映射测试**（不在审查前抢跑，
以免与审查者的独立判定冲突）。代价若判错：`get_tv_detail` 的字段映射若有误，
会一直到 Task 3 写 NFO 时才以「剧集元数据不对」的形式暴露，定位成本更高。

Ruling R10: 审查者把「畸形 2xx 响应逃出错误分类体系」评为 Minor 并明确要求 controller 确认任务 2 的调用点 ——
我查了：任务 2 的 resolver 只捕获 `TmdbNotFoundError` / `TmdbUnavailableError`，不捕获 `json.JSONDecodeError`(⊂ValueError)
与 `KeyError`。因此「代理 / captive portal 返回 HTML 而状态码是 200」会让一个本应降级为「TMDB 不可用」的故障
以未分类异常穿过 resolver、`_with_tmdb_titles`，最终 500 掉整个预览请求，**直接违反全局约束「TMDB 故障绝不阻断重命名」**。
**裁定：升级进修复轮**（非润色，是约束违反）。代价若判错：多改约 6 行生产代码与 2 个测试，
换来的是铁律在「非 JSON 200」这一路径上也成立。

Ruling R11: 延后处理的 Minor（交最终整分支审查分诊，不占修复轮）：
  - Minor A: 14 处断言均未检查 `request.url.path` 与 `request.method` —— 本任务只**新建**路径、
    不改既有路径，因此不存在回归风险，属面向未来的加固。延后。
  - Minor B: 重试耗尽后仍多付 1 秒 sleep；`raise last_error or ...` 的 `or` 分支不可达。属噪音，
    不影响正确性（最坏是每次限流耗尽多等 1 秒）。延后。
  - Minor C: `test_cache_fingerprint_differs_per_key` 偏弱（返回原始 Key 的前 12 位也能通过）；
    `_year_of` 的 `len < 4` 与 `isdigit` 假分支未测。实现本身用的是 sha256，已正确，
    只是测试没钉住「原始 Key 不得进入缓存键」这一属性。延后。

Ruling R12: 审查者提出的 4 条 ⚠️（无法从本 diff 验证项）逐条裁定 ——
  - 「401 不可降级」：任务 3 的 `_with_tmdb_titles` 捕获 `TmdbAuthError` 并转 HTTP 400，计划已写。非缺口。
  - 「cache_fingerprint 是否真被组合进缓存键」：任务 2 的 `_scope()` 返回
    `(client.cache_fingerprint(), client.language)`，计划已写。非缺口。
  - 「状态非 matched 时不回填」：任务 2/3 的职责，计划已写。非缺口。
  - 「Python 3.9+ 未经执行验证，实际解释器为 3.14.7」：审查者确认本任务所用构造在 3.9 合法
    （PEP 585 下标泛型；`from __future__ import annotations` 使 `-> tuple[...]` 不求值）。
    另注：仓库既有 `backend/app/models/api.py:69` 使用 `Optional[dict | list]`，该语法需 3.10+，
    故 README 声称的 3.9+ 在本仓库**本就已不成立** —— 既有问题，不属本计划范围，延后不处理。代价若判错：无。

Task 1: implementer DONE_WITH_CONCERNS (commit 954c093; 14/14 passed, 全量 40 passed / 3 warnings 均为既有 openlist.py 的 Pydantic 弃用与本任务无关)
Task 1: review package review-f63c219..954c093.diff（1 commit, 15560 bytes）
Task 1: review — Spec ✅（4 条 ⚠️ 已由 R12 逐条裁定为非缺口）、Task quality **Approved**、
        1 条 Important（`get_tv_detail`/`TmdbShow` 零覆盖）+ 5 条 Minor。
        审查者独立复现了 429 递归并确认 R8 的修复忠实无削弱；独立验证了 3 条 warning 的归因
        （对新测试文件跑 `-W error::DeprecationWarning` 得 14 passed，新文件零 warning）。
Task 1: fix round 1/5 dispatched（findings: get_tv_detail 覆盖 [Important] / 畸形响应分类 [R10 升级] /
        文件头注释与事实不符 [Minor，计划原文之误]）
Task 1: fix round 1/5 re-review — 全部 3 条 findings **ADDRESSED**，修复 diff 无新破坏。
        再审查者未轻信变异验证的说法：逐字段核对 payload（vote_average=8.9 与 vote_count=12345 确为
        不同值、各断言到正确字段），并独立推出「交换后 votes=8.9 会被 pydantic 的 int_from_float 拒绝、
        且 rating 断言同时失败」，确认该测试在互换下不可能通过。
Task 1: fix round 1/5 (3 addressed, 0 open; commits 954c093..09c2df9)
Task 1: **complete** (commits f63c219..09c2df9, review clean)

Ruling R14: 再审查者独立提出 R13 同一逃逸类的两个变体，**扩大 R13 的 park 范围并一并指向最终审查**：
  (a) 2xx body 是合法 JSON 但非对象（数组/标量）→ `data.get(...)` 抛 `AttributeError`；
  (b) `tmdb_client.py` 的 `genres=[g.get("name","") for g in ...]` 在 genres 数组含 `null` 元素时抛 `AttributeError`。
  两个独立审查者各自命名同一类，是值得记录的信号；但我**维持 park 而非再开一轮**，理由是：
  (a) 仍无现实主体会产出；(b) 需要 TMDB 自身的数据缺陷，而 TMDB 的 genres 恒为对象数组。
  关键信息留给最终审查：**若判定该类值得关闭，修复是在 `_get` 的 return 处加一处 `isinstance(data, dict)`
  守卫即可覆盖整个类**（单点、约 3 行），无需逐调用点加固。代价若判错：若真有中间设备或 TMDB 数据异常，
  预览会以 500 崩掉而非降级到「TMDB 不可用」—— 该路径下铁律不成立。这是本计划里我最不确定的一条裁定，
  故在此显式标注，供最终审查优先分诊。
        实施者对 findings 1 做了**变异验证**：把 rating/votes 对调后新测试 FAILED、恢复后通过，
        证明断言真的钉住了互换。另声明所有结论取自清 __pycache__ 后的重跑（踩到 stale .pyc：
        变异版与恢复版大小相同且同一秒写回，CPython 按 mtime 整秒+大小判失效）。

Ruling R13: 实施者在 DONE 报告里上报了一处同类逃逸 —— 200 的 JSON 解析成功但不是对象（如数组）时
`data.get(...)` 抛未分类的 `AttributeError`，爆炸半径与 findings 2 相同。**裁定：park（延后），不进修复轮。**
理由：区别在「谁会产出这种输入」。HTTP 代理与 captive portal **确实**会把 200 响应的 body 换成 HTML
——那是它们的正常行为，所以 R10 是真实世界输入；而没有任何现实主体会对 TMDB 的端点返回一个裸 JSON 数组
——TMDB 自身的契约恒为对象，代理不会把对象改写成数组。为一种对抗性构造的输入加防御性检查，
正是 YAGNI 要挡的。代价若判错：若真有中间设备这么做，预览会以 500 崩掉而非降级 —— 但该场景
目前只能构造、不能举例。指向最终整分支审查分诊（与 R11 的 Minor 一并）。

---

## 任务 2

Task 2: implementer DONE_WITH_CONCERNS (commit 32fb2b2; 23/23 resolver, 全量 67 passed, 输出干净;
        生产文件与 brief 逐字节一致，仅省略 markdown 围栏)

Ruling R15: 实施者报告 brief 的测试文件**不可能达到 23 passed**：6 个用例省略 `cache=`，于是共用模块级
`_DEFAULT_CACHE`，而 `FakeClient` 的 `cache_fingerprint()` 与 `language` 是常量 → 键必然碰撞 → 先前用例的
命中让后来的假客户端根本不被调用 → 请求计数与注入失败的断言落在陈旧值上（GREEN 阶段实测 6 failed / 17 passed，
每个用例单独跑均通过）。实施者用 autouse fixture 每用例清 `_DEFAULT_CACHE` 修复，未改任何断言、未动生产代码。
**裁定：接受该修复，不 revert。** 这是我计划里的**测试隔离缺陷**（我写了共享进程级缓存的测试函数），
责任在计划。代价若判错：每用例清缓存会重置生产缓存 —— 但生产环境没有测试边界，且「缓存跨 resolver 实例存活」
这一属性仍由专用用例（均用显式 `cache=`）守护，无损失。计划文本由 controller 回填。

Ruling R16: 实施者报告 `test_concurrent_same_key_is_merged` **零鉴别力** —— 假客户端的 `search_tv` 从不
让出控制权，`gather` 的两个任务无法交错，**删掉 `TmdbCache` 的锁该测试依然通过**。实施者另用临时
suspending fake 实验证明「有锁=1 次、无锁=2 次」，即锁本身正确、测试无效。**裁定：升级进修复轮**
（审查准则明列「断言等于没断言的测试」为 Important；且该测试是 spec §6.3「同键并发合并为一次外部调用」
这一设计承诺的唯一守护者）。要求修复后**用变异验证证明有效**（临时去锁 → 测试必须 FAILED）。
代价若判错：多一次 dispatch 与再审查，换来的是一条真正能捕获锁被移除的测试。

Ruling R17: 三处未使用 import（resolver 的 `field` 与 `TmdbAuthError`、测试的 `EpisodeMatch`）——
虽属 Minor，**顺手在本次修复轮一并清掉**：它们是新建文件里的无用 import，代价约 0，
不值得占用最终审查的注意力。代价若判错：无。

Task 2: fix round 1/5 dispatched（findings: 并发测试零鉴别力 [R16 升级] / 三处无用 import [R17 顺手清]）
Task 2: fix round 1/5 report — commits 914b4ce + ee26a58；23 passed（正序+倒序）、全量 67 passed。
        **变异验证扎实**：清 __pycache__/.pytest_cache 后复做 —— 变异前 sha1 3aa1a9db → 23 passed；
        把 `get_or_create` 的 `async with self._lock` 换成 `if True` → sha1 51abc39e →
        该用例 **FAILED**（`assert 2 == 1`，观察到 `['绝命毒师','绝命毒师']` 两次调用）；
        恢复后 sha1 3aa1a9db（与变异前一致）→ 23 passed。sha1 往返证明恢复到位，
        观测到的 2 次调用证明鉴别力真实存在。实施者另主动核查了时序影响（其余用例均为单次
        resolve_many、无 gather，不受让出点影响）。

Ruling R18: 实施者指出我的派发消息说让出点加在 **2** 个方法（search_tv / get_season），
而我随后提交的计划修订（28caa55）说 **3** 个（含 get_tv_detail）。**裁定：以落盘的计划文本为准（3 处）。**
该分歧的成因是我那条消息写得不精确 —— 真实网络调用三者都会挂起，3 处更忠实；
保留 ee26a58 那一行。代价若判错：无（并发用例只断言 search 次数，第三处让出点对其断言无影响）。

Ruling R19: 实施者的 fixture 写法（`tmdb_resolver._DEFAULT_CACHE.clear()` 模块属性访问 +
`yield` 前后各清一次）比我的计划原文（import 私有名 `_DEFAULT_CACHE` + 仅前置 clear）更干净 ——
不 import 私有名，且用后即清不留残余。**裁定：采纳实施者的写法，改计划文本对齐代码**（提交 5a97cc0）。
理由：本项目有过「计划文档与代码不一致」的历史教训（见记忆 sdd-workflow），
计划是接手者的对照物，代码更优时应对齐计划而非反过来。代价若判错：无。

Ruling R20: **流程裁定** —— Task 2 尚未做过完整任务审查（DONE_WITH_CONCERNS 报告中的正确性顾虑
按规程可在审查前先行处理，我的修复轮即基于此）。因此本任务的完整审查在修复轮之后进行，
其范围为 `09c2df9..HEAD` 全量（含修复提交），**不再另做一次范围限定的再审查** ——
那会是同一 diff 上的重复审查席位，而规程明确警告重复席位。代价若判错：
若审查者只看修复提交而忽略主提交，本任务的规格合规性会失去把关 —— 故已在派发中显式告知
「这是本任务首个也是唯一一个完整门禁，须评估整个范围」。

Task 2: task review dispatched (range 09c2df9..5a97cc0, 5 commits, 30004 bytes)
Task 2: task review — Spec ✅、**无 Critical、无 Important**、9 条 Minor，Task quality **Approved**。
        审查者未污染检出（守只读），改在 /tmp 写脚本、用无锁子类驱动真实 TmdbResolver 复现变异：
        有锁 1 次 search / 无锁 2 次，独立证实 T:228 的断言真有鉴别力。
        另独立核实：六态中 5 态被互斥断言钉住（**`disabled` 本任务无生产者，属 Task 3 职责**），
        `unavailable` 的断言不可能被 `show_not_found` 满足，R:159-167 的 try 只包住季拉取故单季失败不拖垮整批。

Ruling R21: **推翻 R13/R14 的 park 决定。** 审查者提出（并明确说属 Task 1 代码、本任务范围外）：
`tmdb_client.py` 的 `int(number)` 在畸形 payload 上抛 `ValueError`，逃出三个已分类异常，
`resolve_many` 不捕获 → 500 掉整个预览请求。这是**第三个独立审查者**指出同一件事
（HTML 响应 [R10 已修] / 非对象 JSON 与 genres 含 null [R13-R14 parked] / 字段类型不符 [本条]）。
关键在于：我原先提议的单点守卫在 `_get` 的 return 处，**根本覆盖不了 `int(number)`** ——
它在映射层而非请求层，所以那个「单点关闭整类」的方案是错的，我 park 的依据也随之失效。
**裁定：在 resolver 的外部数据边界加守卫**，把客户端调用包起来，除 `TmdbAuthError`（必须继续冒泡，
它是配置错误）外，任何异常转 `TmdbUnavailableError` 降级。理由：铁律的措辞是「**绝不**阻断」，
是分类性的而非枚举性的；要让它分类成立，只能在外来数据进入的那一层做宽捕获 —— 而外部数据边界
正是宽捕获惯用且正确的地方（不同于在内部逻辑里吞异常）。该守卫同时关闭 R13/R14 两个 parked 项。
代价若判错：一个我们自己的编程错误（如 TypeError）会被降级成「TMDB 不可用」而非暴露为 500 ——
这是有意的权衡（预览是只读操作，降级比崩溃对用户更友好），且守卫的 docstring 会写明缘由以防被「清理」。

Ruling R22: 审查者的 Minor 中有一条**跨任务交办**，记入 Task 3 的派发：没有任何测试断言状态的
**字面字符串**（`tmdb_resolver.py` 里六个常量），因此把 `STATUS_MATCHED = "unavailable"` 之类
的值互换可以全绿 —— 而这些字符串是 Task 3 与前端据以分支的**线上契约**。Task 3 应在自己的测试里
钉住字面值（含本任务无生产者的 `disabled`）。

Task 2: minors deferred（指向最终整分支审查分诊）：
  M1 TmdbAuthError 传播与「失败不缓存」两条 spec 保证无测试钉住 → **已并入本次修复轮**（见下）
  M2 状态字面串无断言 → 交办 Task 3（R22）
  M3 归一化碰撞会进缓存键而非仅分组（plan-mandated；审查者无法举出现实中会被合并的两部不同剧）
  M4 `resolve_many` 末尾 `EpisodeMatch(STATUS_UNAVAILABLE)` 兜底不可达（死代码，会把未来的分组 bug 变合理状态）
  M5 `T:56` docstring 说两处让出点、实际三处 → **已并入本次修复轮**（一行，且该歧义是我造成的）
  M6 `T:123` 注释说 3 次请求、实际 4 次（多了每个剧一次 get_tv_detail）
  M7 `T:215` 未使用的 monkeypatch 参数（plan-mandated，R6 已接受）
  M8 `_DEFAULT_CACHE` 从不清理未被再次访问的键（plan-mandated；Task 3 接 TTL 时值得留意）
  M9 `resolve()` 辅助函数静默丢弃未知 kwargs

Task 2: fix round 2/5 dispatched（findings: 外部数据边界守卫 [R21] + 其契约两端的测试 +
        FakeClient docstring 让出点数 [M5]）

Task 3: 派发时须带的两条交办 —— (a) R22 钉住状态字面串；(b) 计划 Task 3 Step 11 的
        `test_invalid_tmdb_key_returns_400_not_silent_disabled` 会真的打 TMDB，离线环境须如实报告，不得放宽断言（R7）。

Ruling R23: 实施者报告它**不得不偏离 R21 要求 1 的字面表述**：我的原文是「除 `TmdbAuthError` 外
**任何**异常都转成 `TmdbUnavailableError`」，按字面实现会把**已分类**的 `TmdbNotFoundError` 一并压成
`unavailable`，而六态降级正是靠它区分 `season_not_found`（TMDB 说没这一季）与 `unavailable`（TMDB 挂了）。
变异 B 实测：按字面收窄后 `test_season_not_found` FAILED（`assert 'unavailable' == 'season_not_found'`）。
**裁定：接受该偏离 —— 我的措辞不准。** 本意是「**未分类**的异常」，字面漏了限定词。
保留 `TmdbNotFoundError` / `TmdbUnavailableError` 两者的 re-raise，只归并未分类异常 ——
这未削弱 R21 的目的（未分类异常照样被兜住），且保住了六态的语义区分。
代价若判错：若真该把 NotFound 也压平，则「没这一季」会被显示成「TMDB 挂了」，
用户会去查网络而不是去核对季号 —— 明显更差，故该偏离方向正确。

Task 2: fix round 2/5 report — commit b532e18；`test_tmdb_resolver.py` **26 passed**（23 原有 + 3 新增，
        正序+倒序）、全量 **70 passed**。新增 `TmdbResolver._guarded`（staticmethod）包住
        fetch_search / fetch_detail / fetch_season 三条路径；未改 `tmdb_client.py`。
        **变异验证 A/B/C 三组**（清 __pycache__/.pytest_cache、sha1 确认恢复、pristine 769ff950）：
          A 去掉宽捕获兜底 → `test_unclassified_error_is_degraded_not_raised` FAILED（ValueError 逃逸）
          B 按字面收窄（连 NotFound 一起压） → `test_season_not_found` FAILED（见 R23）
          C 守卫吞掉 401 → `test_auth_error_propagates` FAILED（DID NOT RAISE）——
            **独立复现了审查者「吞 401 时旧用例全绿」的发现**
          恢复后 sha1 与 pristine 一致 → 26 passed

Task 2: fix round 2/5 re-review dispatched (FIX_BASE 5a97cc0, HEAD b532e18)

Task 2: fix round 2/5 re-review — 3 条 findings **全部 ADDRESSED**，修复 diff 无新破坏。
        再审查者逐句核对了守卫的子句顺序（`except TmdbAuthError: raise` 在宽捕获之前，而
        三个异常都直接继承 `Exception`，故子句顺序是唯一判据）、确认 :154 行先 re-raise NotFound
        因此 `season_not_found` 与 `unavailable` 的区分未被压平、确认 `tmdb_client.py` 未被改动。
        另主动核实：守卫不吞 `BaseException`（`CancelledError`/`KeyboardInterrupt` 不继承 Exception，
        取消语义未破）、factory 抛异常时 `async with` 退出即释放锁。
Task 2: fix round 2/5 (3 addressed, 0 open; commits 5a97cc0..b532e18)
Task 2: **complete** (commits 09c2df9..b532e18, review clean after 2 fix rounds)

计划文本已回填并提交（527bd74）—— 守卫与三条契约用例逐字对齐实际实现。回填时发现我的初稿有
三处与代码不符（测试名、虚构的 `fail_once` 参数、第三条实际用 flaky 闭包），已改正。
这正是本项目记忆里那条教训的形态：计划的产物必须核对代码是否存在，而不是照着计划想当然。

## 任务 3

Task 3: implementer DONE_WITH_CONCERNS (commit 220e621; 9 files, +313/-34; 全量 80 passed 正序倒序各一次)

Ruling R25: **单元测试不得依赖外网。** 实施者如实报告 brief 的
`test_invalid_tmdb_key_returns_400_not_silent_disabled` 真的打到了 TMDB（本机有外网，真实 401 → 400，
1.42s），并按 R7 的要求**没有**放宽断言、没有跳过。**裁定：必须密闭化** —— 需要出网的用例在单元套件里
是构造性地不稳定（换机器 / CI / 断网即红或超时）。**不加 `@pytest.mark.network`**（那等于承认套件里
有一条不确定的用例），**也不给生产代码塞测试注入口**（为测试改生产代码是更大的毛病）。改为
monkeypatch `TmdbClient.search_tv` 抛 `TmdbAuthError`，断言路由 400 且 detail 含 "TMDB"。
理由：链路已由两端完整覆盖 —— Task 1 的 `test_401_raises_auth_error` 用 `MockTransport` 证明了
「真实 401 → `TmdbAuthError`」，本用例只需证明「`TmdbAuthError` → 400」；真实 Key 的端到端验证
保留在计划的 `deferred-to-human` 一节。代价若判错：失去了「真 Key 打真 TMDB」这一条自动断言 ——
但那条本就只能在有网机器上跑，且其价值（401 被识别）已由 Task 1 的 MockTransport 用例承担。

Ruling R26: 实施者指出 brief 那 4 条测试在「退回单遍解析」与「无条件覆盖（忽略手动标题）」两种坏实现下
**全绿**，即零鉴别力；它自行补了 2 条离线用例并用变异验证证明有效（A 去掉合并 → FAILED `None == 'Breakage'`；
B 无条件覆盖 → FAILED 保留 Breakage 而非手工标题），改动已逐字还原。**裁定：保留这 2 条。**
这是**我第二次写出零鉴别力的测试**（第一次是 R16），同一缺陷形态、同一根因：我写测试时只验证了
「正常路径产出正确」，没有问「把实现改坏它会不会红」。这是本计划里我犯得最多的一类错误，记此备查。
代价若判错：多 2 条用例；换来的是「title 真的来自 TMDB」与「手动标题真的优先」这两条核心承诺
有东西守着。

Ruling R27: 计划三处笔误，**均在计划层修正**（实施者发现的，责任在我）：
  (a) `test_title_renders_empty_when_absent` 的期望值 `绝命毒师 - S02E05 -.mkv` 少一个空格，
      与计划自己 Step 10 的 `"Test Show - S01E02 - .mkv"` 自相矛盾 —— 照抄会永久红。
  (b) 计划预测 `test_template_title.py` 会 RED 是错的：`{title}` 自 d6f01a7 就已在
      `template.py:49-50` 实现，它是**刻画测试**而非 TDD 红。我把「解析器从不填 `title`」
      误当成「模板不认 `title`」。
  (c) `_tmdb_summary` 的 `episode_title` 是死字段（预览响应用不到它，`title` 取自
      `plan.parsed.title`；Task 4 直接消费 `EpisodeMatch` 不经 summary）→ 顺手删。
  另修：路由 400 的 detail 写成 `f"TMDB API Key 无效: {exc}"`，而 `TmdbAuthError` 的消息本身就是
  「TMDB API Key 无效」，产出重复文案 → 改为 `detail=str(exc)`（仍含 "TMDB"，断言不受影响）。
代价若判错：无。

Task 3: fix round 1/5 dispatched（findings: 用例密闭化 [R25 裁定] / 400 文案重复 [R27] / 死字段 [R27]）
Task 3: fix round 1/5 report — commit f00d2e4；全量 80 passed，**有网 0.56s / 无网 0.59s**。
        密闭化证据扎实：用 `unshare -rn` + `curl --max-time 6` 得 `http_code=000` / exit 7 **确证无网**，
        再在同一命名空间内跑整套得 80 passed；变异后（`except TmdbAuthError` 改静默降级）在同一无网
        命名空间下仍 FAILED `assert 200 == 400`，证明密闭化未削掉鉴别力。
        **实施者主动更正了自己上一份报告里一处未经实测的推测**：断网时旧写法不是「超时/502」，
        实测是 `200 + tmdb_status="unavailable"`（连接失败被归类为可降级的 TmdbUnavailableError）。
        findings 2 已 grep 确认文案唯一来源，并加精确等值断言钉住；findings 3 已删，全域 grep 零命中。

Ruling R28: 实施者的残留顾虑（「`401 → TmdbAuthError` 这一半现在只由 Task 1 的 MockTransport 用例保证，
两条用例之间是约定而非编译期约束，将来客户端改了异常类型本用例仍会绿而链路已断」）——
**裁定：不是缺口，无需处理。** 因为若客户端的 401 分支改成别的异常类型，**Task 1 的
`test_401_raises_auth_error`（`pytest.raises(TmdbAuthError)`）会红**。链路的两端各由一个测试钉住：
Task 1 钉「401 → TmdbAuthError」，Task 3 钉「TmdbAuthError → 400」。缺一即红，已是完整覆盖，
不必为此引入跨套件约束。代价若判错：若有人把 401 与 403 都映射成 TmdbAuthError 之类**语义**改动，
两端测试都不会红 —— 但那是无人会做的改动，且不在本设计范围内。

Ruling R29: 实施者 §6 第二条观察（execute / dry-run 路径的标题合并**仅有一次性脚本验证、未落盘**）——
**裁定：升级进修复轮（Important）。** 这不是覆盖率锦上添花，而是**本仓库有前科的缺陷形态**：
`plans/2026-09-25-backend-pad-digits.md` 的注释里写着同一件事 ——「只加 buildPreview 一处…
写出的文件名与预览不一致」。Step 9 给 execute/dry-run 加的两行（`merged` 与 `overrides=effective_overrides`）
**若被删掉或漏传，没有任何测试会红**，用户会看到预览里有标题、执行后文件名里没有，且全程无报错。
这与 R16 / R26 是同一类缺陷（改坏实现而测试仍绿），既已判定为 Important 两次，此处保持一致。
要求：用 tmp_path 造真实源文件 + 复用 `fake_tmdb` fixture，断言 execute 的 `new_filename` 真的含标题；
dry-run 同理各一条；并做变异验证（把 `overrides=effective_overrides` 改回 `overrides=req.overrides`
→ 新用例必须 FAILED）。代价若判错：多 2 条用例与一轮 dispatch，
换来的是「预览与执行一致」这条承诺有东西守着。

Task 3: fix round 2/5 dispatched（findings: execute/dry-run 标题合并无覆盖 [R29 升级]）

Ruling R30: **流程改进，适用于 Task 4 起的所有后续派发（含计划 2）。**
「零鉴别力的测试」已出现三次（R16 / R26 两条），**三次都是计划写的**，且每次都由实施者或审查者发现。
依赖事后审查去抓是碰运气 —— 实施者才是最早能发现它的人（它正在把测试跑绿，最清楚哪条在坏实现下也绿）。
故从 Task 4 起，每个派发提示里显式加入一段要求：
  1. 若我为该任务指定的某条测试，在**把对应实现改坏后仍然通过**，必须直接报告，不要默默照抄；
  2. 尽可能用变异验证证明（改坏 → 必须 FAILED → 恢复 → 通过，附 sha1 往返与失败输出）；
  3. 若判断某条测试本就无法具有鉴别力（如纯刻画既有行为的用例），说明理由而非硬造变异。
理由：这是本计划里复发率最高的缺陷形态，而它有一个客观判据（「改坏实现它会不会红」），
不依赖审查者的直觉。代价若判错：每次派发多几行字，实施者偶尔会多花一轮做变异验证。
Task 3: fix round 2/5 report — commit 82f83e6（仅改测试，生产代码未动，sha1 与上一提交一致）；
        全量 82 passed，有网 0.59s / 无网命名空间 0.58s。**变异验证三组**：
          A execute 退回 `overrides=req.overrides` → 全量 1 failed/81 passed，唯一红的就是新用例
            （`'Test Show - S01E02 - .mkv' != '… Breakage.mkv'`）—— 把 R29 那条缺口量化了
          B **dry-run 单独退回 → 只有 dry-run 那条红，execute 那条仍绿**（实施者主动多做的检查，
            证明两条用例各钉自己的路径、不互相掩护）
          C 两行整体删掉 → `NameError: effective_overrides`，且既有 pad 用例因悬空引用连带红
Task 3: task review dispatched (range 527bd74..82f83e6, 4 commits)
Task 3: task review — **规格合规 ✅（生产代码每一条约束都满足）**，但 **Task quality: Needs fixes**
        （1 条 Important + 6 条 Minor）。审查者自行核实了「`resolve_many` 只抛 `TmdbAuthError`」
        这条约定（逐层读守卫与三个转换点），确认路由的单个 except 足够。

Ruling R31: 审查者的 Important 1 —— `tests/test_rename_routes.py` 的三条用例
（`test_no_tmdb_key_degrades_to_disabled` / `test_manual_title_override_wins_over_tmdb` /
`test_tmdb_overrides_are_accepted_by_the_request_model`）**从环境继承「未配置 Key」这个前提**
而非自己建立它：`config.py` 的 `Settings` 带 `env_file=".env"`，而 `.env` 是**本设计明确支持的**
配置来源之一，故任何配了 key 的机器上这三条都会真的去打 TMDB，且第一条会直接红。
审查者核实当前检出干净（无 `.env`、无 `TMDB*` 环境变量），属**潜在违规而非现存故障**。
**裁定：进修复轮。** 这与 R25 是同一类（单元套件不得依赖外网，也不得依赖运行环境的偶然状态），
且同样**源自我的计划**。修法是新建 `backend/tests/conftest.py` 用 autouse fixture 钉死配置 ——
比逐条改 payload 可靠，因为它对**将来新增的**用例也生效。代价若判错：无。

Ruling R32: 审查者的 Minor 2 我**升级进修复轮**，理由与 R29 一致 —— `tmdb_overrides` 的接线
无验证：唯一的发送用例跑在 disabled 路径上（`TmdbResolver` 根本不被构造），故**删掉
`overrides=req.tmdb_overrides` 这一处传递，82 条测试全绿**。而 `tmdb_overrides` 正是用户在产品里
选的「自动匹配 + 预览表可重选」能力的**唯一承载**，它若静默失效，用户的「重选」毫无反应 ——
spec 对这种失灵有明确措辞：「不做归一化就会静默失效 —— 用户点了重选却没有任何变化」。
要求：新用例断言 override 的 tv_id 真的抵达 resolver、且自动搜索**从未被调用**；并做变异验证
（`overrides=req.tmdb_overrides` → `overrides={}` 必须 FAILED）。代价若判错：多 1 条用例与一轮 dispatch。

Ruling R33: 审查者的 Minor 5（我的文档漂移）—— 上一轮回填时我把改后的用例记成
`test_tmdb_auth_error_becomes_400` / `"tmdb_api_key": "whatever"`，而落盘的是原名
`test_invalid_tmdb_key_returns_400_not_silent_disabled` / `"definitely-invalid"` 且多一条等值断言。
**裁定：我自己修**（提交 623c3f6），按落盘代码改写计划并补上 import 说明。
这正是本项目记忆里「计划的产物必须核对代码是否存在」的形态 —— 我上一轮**又**犯了它。

Task 3: minors deferred（交最终审查分诊）：
  M4 `_with_tmdb_titles` 在 source 校验之前执行 → 非法 source / 未连 OpenList 会先空跑一次 TMDB
     查询，且错误优先级可议（可能报出「TMDB API Key 无效」而非更对症的错误）。无正确性影响。
  M6 3 条 warning 是从既有代码继承的（`models/api.py` 的 `Field(..., example=...)` 等），非本任务引入。
  M7 `renamer.py` 早已使用 3.10+ 语法（`PadConfig | None`，本次 diff 的 context 行），
     故 README 声称的 3.9+ 在本次改动**之前**就已不成立；项目实际跑 python:3.12-slim。与 R12 同源。

Task 3: fix round 3/5 dispatched（findings: conftest 钉死环境配置 [R31] / tmdb_overrides 接线覆盖 [R32 升级]）
Task 3: fix round 3/5 report — commit 30907d5（3 files, +86/−18；新建 `tests/conftest.py`；
        生产代码一行未改，`renamer.py` sha1 与上一提交一致）。
        全量 83 passed × **三场景**：有网 0.44s / 无网命名空间 0.44s / **`TMDB_API_KEY=whatever` + 无网 0.44s**。
        findings 1 的变异证据：把夹具改成 `pass` 后**同一个场景**即红 ——
        `FAILED test_no_tmdb_key_degrades_to_disabled: assert 'unavailable' == 'disabled'`，
        正是 R31 预测的形态。**实施者另发现泄漏面比报告更大**：同一变异在**有网**下是
        13 failed / 69 passed（连 pad 用例都连带红，13.00s 就是真实往返耗时）——
        即这个洞在有网机器上不只是「三条用例会红」，而是会污染整个套件。
        缓存隔离的实效用一次性探针文件单独验证过（A 写缓存、B 断言起手干净：有夹具 2 passed，
        夹具改成只 yield 后 B `assert 'v' is None` FAILED），探针已删，两处 sha1 均逐字节还原。
        findings 2：新增 `test_tmdb_override_selects_that_tv_id_and_skips_search`（`_OverrideOnlyTmdbClient`
        继承 `_FakeTmdbClient` 并加 `search_tv` 计数，自动搜索返 1396）；变异
        （`overrides=req.tmdb_overrides` → `{}`）→ 全量 1 failed / 82 passed，唯一红的就是它
        （`assert 1396 == 9999`），还原后 sha1 一致。
        **实施者的一处判断值得记**：替身做成**计数**而非「让 `search_tv` 抛 AssertionError」，
        因为后者会被 `_guarded` 归类成 `unavailable`，失败信息会退化成 `'unavailable' != 'matched'`，
        诊断力更差 —— 它在按本设计的语义推理，而不是机械照做。

Task 3: fix round 3/5 re-review — 2 条 findings 全部 **ADDRESSED**，修复 diff 无新破坏。
        审查者核实：`backend/tests/conftest.py` 是仓库内唯一 conftest 且 `pytest.ini` 的
        `testpaths = tests` 使其覆盖整个 `tests/`；`settings` 是同一个单例、`Settings` 非 frozen
        故 `monkeypatch.setattr` 确实落地；全文件 grep 确认无测试重新打开该洞（`test_rename_routes.py:180`
        的 `tmdb_api_key` 是请求体字段而非 settings，且那用例在 :172 patch 了 `TmdbClient.search_tv`）；
        搬移后无重复 fixture 残留，原中文 docstring 未丢失（conftest 里保留并补了一段说明搬移缘由）。
        override 测试的鉴别力经独立推出：假客户端 search 返 1396、override 给 9999，
        故 `overrides={}` 时 `assert 9999 == 1396` 与 `assert 0 == 1` **两条**都会红。
        工作树干净（`git status --porcelain` 为空），磁盘状态 = 被审查提交。
Task 3: fix round 3/5 (2 addressed, 0 open; commits 82f83e6..30907d5)
Task 3: **complete** (commits 527bd74..30907d5, review clean after 3 fix rounds)

Task 3: 残留观察（非缺陷，交最终审查）：
  - conftest 的夹具只钉住 5 项 TMDB 配置中的 2 项（`tmdb_language` / `tmdb_timeout` / `tmdb_cache_ttl`
    仍取环境值）。当前无用例断言它们，且它们不可能造成网络出口，故未重开 R31 的洞；
    但对将来断言语言/超时的用例是潜在耦合。
  - Minor 4（非法 source 先空跑一次 TMDB 查询）已在前述 park 清单里，本轮未动。
Task 3: 3 轮修复的代价评估：三处 findings（R29/R31/R32）**全部源自我的计划**，
  且都不是实施者引入的缺陷。这印证了 R30 的必要性 —— 缺陷集中在计划层，
  而实施者与审查者是最早能发现它们的两道网。

## 任务 4

Task 4: implementer DONE_WITH_CONCERNS (commit 7614e67; 88 passed / 0.46s，baseline 83 → +5)
Task 4: **R30 首次生效且有效** —— 实施者答「无一条指定测试缺乏鉴别力」，并附 6 个变异杀死了全部 5 条
        测试、每个变异恰好只红目标那条，原始与恢复后文件哈希均为 `c3f0f5df…`。
        它还证明了两个 key 用例**互补而非重复**（M1-vs-M3）。即本次计划写的测试是健全的。
Task 4: 实施者验证了 conftest 与用例自身 monkeypatch 的交互（三条独立证据：顺序探针 / 运行时证据 /
        变异 M3），确认夹具不会盖掉用例自己的 setattr —— 我要求它「去验证而不是假定」，它照做了。

Ruling R34: concern 1（brief 的 Interfaces 列了四个 status，代码返回第五个 `disabled`）——
**代码是对的，是我的清单不全。** `disabled` 是真实状态（服务端 `tmdb_enabled=false`），
且 Task 6 的设置页文案表已为它单列一条。不改代码，只修计划清单（提交 c86f1d9）。

Ruling R35: concern 2（committed 测试从不触碰 `/test` 的 ok / invalid_key / unreachable / disabled
四分支与 `auth_mode` / `sample`，也不触碰 `/search` 的 payload 映射 / `year` 透传 / 400-vs-502；
实施者已逐条临时验证且全部正确，但无回归保护）—— **裁定：进修复轮（审查前）。**
理由两层：(a) 按我在 R32 立的标尺（一个参数透传没覆盖即升级为必修），这里更该修 ——
`/api/tmdb/test` 存在的**全部意义**就是告诉用户「Key 能不能用」，四个 status 分支就是这个端点的
产品价值本身，分支写错会让用户拿着错误的诊断去改一个没问题的配置；(b) 规程允许
`DONE_WITH_CONCERNS` 的 scope 类顾虑在审查前处理，且这样**更省**（现在修 = 修复 + 审查两次派发；
留给审查发现 = 审查 + 修复 + 再审查三次）。代价若判错：多一轮 dispatch 与约 15 条用例。

Ruling R36: concern 3（计划的 RED 预测写「404」是错的）—— 确认。`main.py` 在
`frontend_dist.exists()` 时注册了 SPA catch-all `@app.get("/{full_path:path}")`，
它把**任何未注册的 GET 路径**用 `200 + index.html` 兜住。故在已构建过前端的检出上，
未注册的 `/api/tmdb/*` 返回 200 + HTML 而非 404 —— 实施者的 RED 仍然成立（断言 JSON 字段的用例
会炸在解析上），但形态不同。已修计划（c86f1d9）。
**另记一条既有观察交最终审查**：这条 catch-all 意味着**任何**拼错的 GET API 路径都会得到
200 + HTML 而不是 404，前端 axios 会以「JSON 解析失败」的形式报错而非干净的 404。
这是既有的应用装配问题（`main.py`），不是本任务引入，也不在本计划范围内 —— 但它会让
「API 路径拼错」这类错误极难诊断。是否值得在合并前处理，交最终审查判断。

Task 4: fix round 1/5 dispatched（findings: `/test` 四分支与 `/search` 行为无覆盖 [R35]）
Task 4: fix round 1/5 report — commit e729e1c（纯追加 +150 行，brief 原 5 条未动）；98 passed / 0.49s，
        无网命名空间下同样 98 passed。**11 个变异 M7–M17，每个恰好只红目标那条**；
        实现哈希 `c3f0f5df…` 变异前后一致。实施者主动声明：这 10 条是**刻画测试**，
        **不声称有 RED**，其鉴别力完全建立在变异之上 —— 这个声明比含糊地宣称 TDD 更诚实。
        四处主动设计的鉴别力防御：`year` 一请求内两路独立防御（记录收到的 year + 按其分支返回）；
        `disabled` 喂**有效 Key** 使 `not_configured` 分支无法满足它；`ok` 用两条不同名字的命中
        使 `sample` 钉住**第一条**；400 断言 detail **精确等值**以钉住「不重复前缀」。
Task 4: task review — **规格合规 ✅**，Task quality **Needs fixes**（1 Important + 4 Minor）。
        审查者确认 10 条补测是真覆盖：每条都断言 body 字段或捕获参数，**没有一条能被 SPA catch-all
        的 `200 text/html` 满足**；并核实了 header > `.env` 双向、五 status 互斥、
        `main.py` 净 +1 行、无全局 exception_handler。

Ruling R37: **重开 R24(a) —— 我推翻自己的 park。** 审查者的 Important 1 指出 `api/tmdb.py`
只捕获三个异常里的两个，`TmdbNotFoundError`（`tmdb_client.py` 在任何 404 上抛出，含 `/search/tv`）
无人接，仓库又无全局 handler，故 TMDB 边缘回 404 会让 `/api/tmdb/test` 吐 500 ——
而该端点存在的**全部意义**就是给设置页一个可读状态。
**这条同时证伪了我在 R24 的 park 依据。** R24 我 park 的是「`tmdb_resolver.py` 的 search 路径
同样漏捕 `TmdbNotFoundError`」，理由是「TMDB 不会对它自身存在的端点回 404、**没有可举出的现实制造者**」。
审查者给出的制造者是：**拦截式代理 / DNS 屏蔽网络对被封主机回 404**。
这正是我在 **R10** 已经接受过的那一类制造者（当时是「代理回 HTML」）——
我接受了那一类却拒绝了这一类，**不一致**。
**裁定：两处都修**（端点 + resolver 的 search 路径，后者补一条与 detail 路径对称的
`except TmdbNotFoundError: return STATUS_SHOW_NOT_FOUND`）。代价若判错：各多 1 行生产代码与 1 条测试；
换来的是「`Tmdb*` 失败不得逃过分级」这条仓库自身约定在两个层次上都不再有余口。
**教训记此**：我在 R13/R14/R24 三次以「不现实」为由 park 同一类缺口，其中 R24 的前提被这一轮证伪。
判「不现实」时只想到「上游服务自身的行为」，漏了「中间设备的行为」——而中间设备恰恰是本工具
（自建媒体库、常在家用网络与反代之后）最可能遇到的。此后再判「不可达」时，必须把中间设备算进去。

Ruling R38: 审查者的 Minor 5（`test_search_endpoint_rejects_empty_query` 用真实 Key header 且无打桩，
其密闭性依赖「路由在构造客户端之前就 400」这个守卫还在）**一并进修复轮**。理由与 R31 同类：
这是**有条件的密闭性**，而 R31 我判为 Important 的理由正是「单元套件不得依赖运行环境的偶然状态」。
接上既有的单一打桩缝即可让密闭性无条件。代价若判错：无。

Task 4: minors deferred（交最终审查分诊）：
  M2 `_client` 与 `/test` 各算一次 header/`.env` 优先级（两处正是本仓库「设置不生效」那类缺陷会重现的位置；
     今天两者一致且都有测试，但将来只改 `_client` 会让 `/test` 的 `not_configured` 判断变陈旧）
  M3 纯空白的 header key 被当真 key（`"   "` 为真值 → 短路 `.env` 回退 → 报 invalid_key 而非 not_configured）
  M4 `PROBE_QUERY`（改成 `"x"` 也能过）与 `settings.tmdb_timeout`（硬编码也能过）未被断言
  ⚠️ 审查者未能从 diff 验证的三项已由我自己裁定：全量密闭性（实施者的 `unshare -rn` 是唯一证据，
     我在最终审查前会自己跑一次复核）；`auth_mode` 的线上行为归 Task 1 的 seat；3 条 warning 归因既有代码。

Task 4: fix round 2/5 dispatched（findings: 端点补 NotFound 分级 [R37] / resolver search 路径对称补捕 [R37] /
        空查询用例无条件密闭 [R38]）
Task 4: fix round 2/5 report — commit 5b37718（4 files, +59/−3）；101 passed / 0.51s，
        无网命名空间下 101 passed。三条新测试**先写先红**，失败原因是
        `E app.core.tmdb_client.TmdbNotFoundError: TMDB 无此资源: /search/tv` ——
        即它们钉的是**分级**而非某个值。变异 N1/N2/N3 各恰好只红对应的那条，
        且 N1/N2 同处一个文件仍可区分。`_guarded` 未被触碰（其内无 hunk），
        补捕在**调用点**，守卫的 re-raise 原样保留。
        **finding 3 的证明方式值得单独记**：去掉空查询守卫后，该用例现在以 **400 断言**变红
        （即使在 `unshare -rn` 下，打桩吸收了调用）。修复前同样的变异会真的出网，而**在联网机器上
        真 TMDB 会回 401 → TmdbAuthError → 400，测试会因为错误的原因而通过** ——
        即那条用例在联网环境下本是零鉴别力的，只在无网时偶然暴露。现在密闭性由打桩保证、不依赖守卫存在。
        实施者另给出一条前瞻提醒：`/test` 新增的 NotFound 分支位于**第二处**优先级计算点，
        若将来统一 Minor 2，该分支必须随解析逻辑一起搬，否则 `/test` 会静默丢掉本轮的分级。
Task 4: fix round 2/5 re-review — 3 条 findings 全部 **ADDRESSED**，无新破坏。审查者独立核实
        `_guarded` 内无 hunk、新子句的 try 只跨 `get_or_create` 一行（不可能截走 detail 路径或
        别处的 re-raise）、`fail="search_not_found"` 复用既有 FakeClient 模式列表而非另起替身、
        N1/N2 同处一个文件仍可区分。两条 out-of-scope 观察我认为该修（见 R39/R41）。

Ruling R39: 审查者的 out-of-scope 观察 2 让我**再纠正自己一次** —— R37 里我要求 search 路径
「与 detail 路径**对称**」地捕 `TmdbNotFoundError` → `show_not_found`，**那个要求在语义上是错的**。
两条路径的 404 含义不同：`get_tv_detail(tv_id)` 的 404 确实意味着「那个 tv_id 不存在」；
而 `/search/tv` 对不存在的剧是**回 200 + 空结果**，所以它上面的 404 只可能来自**基础设施**
（代理 / DNS 屏蔽）→ 应归 `unavailable`。
后果是真实误导：代理屏蔽 TMDB 时预览显示「剧集未找到」，把用户推去核对文件名，而问题在网络 ——
正是我这一程一直在修的那类「让用户去改一个没问题的东西」的诊断错误。
**裁定：search 分支改为返回 `STATUS_UNAVAILABLE`，并在注释里写明为何此后**不再对称**，
以免后来者又把它「修」回 symmetry。** 代价若判错：两条路径的措辞不一致（detail 说「未找到」、
search 说「不可达」）—— 但那恰恰反映了两种 404 的不同含义，是对的。
**教训**：我提「与 X 对称」这类要求时，只看了**形状**（同一类异常）而没校验**语义**（同一个
异常码在两条路径上是否同义）。形状对称不等于语义对称。

Ruling R40: 审查者指出计划文档里没有 R37 标签，`progress.md` 才有 —— 而本项目的收尾惯例
（见记忆 sdd-workflow）是把 ledger 归档到 `docs/superpowers/ledgers/`，所以裁定**本来就会**进仓库。
**裁定：收尾时按项目惯例归档本 ledger**，届时计划里引用的裁定标签才有落点。
（这条也决定了我最终消息里那份「Rulings I made」清单不只是说给人听，而是有仓库内的对应物。）

Ruling R41: 审查者的 out-of-scope 观察 1（`test_search_endpoint_requires_key_when_not_configured`
与已修的 finding 3 同类，密闭性「有条件」）**进修复轮**，理由同 R38。其失效模式更糟：删掉「缺 Key 就 400」
守卫后它会**真的出网**，而真 TMDB 回 401 → detail 含 "TMDB" → 断言**照样满足**，即「删掉守卫也抓不到」。
另要求实施者按 **AST 审计整个文件**，不要只修我点名的那条 —— 我不想再出现「隔壁还有一条」。
代价若判错：无。

Task 4: fix round 3/5 report — commit 0a97a6e（3 files, +22/−10）；101 passed / 0.52s，
        无网命名空间下同样 101 passed（用例数不变 —— 一条断言被改正、打桩属加固，无新用例）。
        **实施者按 AST 审计了整个文件，发现第三处同类**（`test_test_endpoint_reports_not_configured`），
        并如实说明它**更弱**（需同时移除两个守卫才能触网，而非一个），不夸大。修后审计：**零未打桩用例**。
        **变异证据（本轮最强的一点）**：
          MA 去掉新增的打桩、守卫完好 → 101 passed（对照：打桩是行为中性的）
          MB 去守卫 + 留打桩 → 仅目标用例红在 **400 断言**上，`{"success":true,"data":[]}` 可见，
             在 `unshare -rn` 下同样红（假客户端吸收了调用）
          MC 去守卫 + **去打桩**（即修复前的反事实），仅在无网命名空间下跑 →
             `{"detail":"TMDB 请求失败: All connection attempts failed"}`、`assert 502 == 400`。
             detail 是**连接错误**，证明代码真的走到了 httpx —— 即在联网机器上它会打到 TMDB、
             拿 401、变 400、**在发起外部调用的同时通过**。危害被演示而非论证。
          N5 回退 search 的 404 分级 → 仅 resolver 那条红。四个哈希均逐字节还原，工作树干净。
        findings 2 的一处判断值得记：实施者**拒绝**把两个 `except` 合并成一个元组（都返回 UNAVAILABLE，
        合并等价且更短），理由是合并会把 `TmdbNotFoundError` 埋进元组里，而未来读者会**假定它在元组里
        正是为了对称** —— 那恰恰是那条注释存在的目的。
        实施者另主动承认：它自己的 Addendum B 已经点出了措辞不一致，但**没有得出结论**，
        「你抓到了就摆在我眼前的东西」。
        Adjacent note for Minor 3（未处理）：纯空白 header key 会作为 v3 `api_key` **查询参数**发给 TMDB；
        仍不进**我们的**访问日志，故头条要求成立。

Task 4: fix round 3/5 re-review — 2 条 findings 全部 **ADDRESSED**，无新破坏。审查者独立 AST 审计
        确认 17/17 全打桩、核实打桩不可掩蔽回归（不碰 `_client` 优先级 / 守卫 / 状态映射 /
        `is_v4_token()`，且 `auth_mode` 由真实 `is_v4_token()` 钉住）。三条 out-of-scope 观察中，
        第 1 条（`_guarded` docstring 与 search 调用点矛盾）我判为本轮引入、进修复轮 4（见 R42）。

Ruling R42: 观察 1（`_guarded` 的 docstring 写着「`TmdbNotFoundError` 不能被压成 unavailable」，
而 search 调用点已刻意把它降级 → 同文件两处注释给出相反指引，且陈旧那处更有权威感）——
**裁定：进修复轮 4（仅 docstring）。** 判据是**它由本轮改动自己引入** —— 该 docstring 在此前是准确的，
修复轮 3 改变行为后才变成误导；修掉自己刚弄不一致的东西属完成该改动，不是扩大范围。
加重情节：那条陈旧注释位于守卫内，其末尾还写着「不要删掉这个宽捕获或那两个 re-raise」，
未来维护者可**引用守卫自身的权威文档**把 search 分支「修」回对称 —— 正是本轮注释要挡的动作。
代价若判错：多一轮 dispatch（9 行注释）。
**并预先声明**：若第 4 轮再发现新东西，只要不 load-bearing，我**直接裁定收口、不开第 5 轮** ——
剩下的都属 Minor，而最终整分支审查本就是它们的分诊场；对自己声明的判据反复比留下措辞 Minor 更糟。

Task 4: fix round 4/5 report — commit b5b8d95（1 file, **+9/−0**，全部在 `_guarded` 的 docstring 内；
        宽捕获与两个 re-raise 逐字节未动）；101 passed / 0.40s，无网命名空间同样 101 passed。
        实施者按调用**方式**（`get_tv_detail` / `get_or_create`）而非行号指认两个调用点 —— 行号会腐烂。
Task 4: fix round 4/5 re-review — finding **ADDRESSED**，无新 Critical/Important。
        审查者逐项核实：docstring 已把「不能被压成 unavailable」限定为只约束守卫自己、
        点明分级属各调用点、点名两个调用点的不同归属、并写明所禁的回退动作；
        所述理由与代码下的注释逐字同旨；`+9/−0` 无 `-` 行、宽捕获与两个 re-raise 逐字节一致。
Task 4: fix round 4/5 (1 addressed, 0 open; commits 0a97a6e..b5b8d95)
Task 4: **complete** (commits 30907d5..b5b8d95, review clean after 4 fix rounds)

Task 4: minors deferred（交最终审查分诊）：
  M2 `_client` 与 `/test` 各算一次 header/`.env` 优先级（两处正是「设置不生效」那类缺陷会重现的位置；
     实施者的前瞻提醒：`/test` 新增的 NotFound 分支位于第二处计算点，统一 M2 时必须随解析逻辑搬走）
  M3 纯空白的 header key 被当真 key → 短路 `.env` 回退；adjacent note：它仍会作为 v3 `api_key`
     **查询参数**发给 TMDB（但不进**我们的**访问日志，故头条要求成立）
  M4 `PROBE_QUERY`（改成 `"x"` 也能过）与 `settings.tmdb_timeout`（硬编码也能过）未被断言
  M5（本轮新增）修复轮 4 的 docstring 里「两个调用点」未加限定词，实际有第三处（`_resolve_season`
     也捕 `TmdbNotFoundError` → `None` → `season_not_found`）。不致矛盾、不削弱反回退指令；
     收紧为「show 级的两个调用点」即可。
  M6（本轮新增）search 那处的描述符（「`_resolve_show` 里 get_or_create 那个 except」）单独看有歧义
     —— `get_or_create` 也是 detail 捕获所在的调用。整段读可解，无需动作。
  **M5/M6 按 R42 预先声明收口，不开修复轮 5。**
  ⚠️ 剩余未能从 diff 验证的项：全量密闭性我将在最终审查前自己跑一次 `unshare -rn` 复核。

Task 5: brief 已预生成 (task-5-brief.md, 193 lines)

## 任务 5（前端设置存储）

Task 5: implementer DONE_WITH_CONCERNS (commit 8070ca2; 3 files, +49/−1)
        RED 先于实现（3 FAIL + TypeError，exit 1）→ GREEN（断言脚本 47 PASS/0 FAIL exit 0；
        `check-sfc-compile.mjs` exit 0；`npm run build` ✓）。提交后 blob 哈希与工作树一致，
        断言块与 brief 逐字节相同，`settingsSchema.js` 仍零导入。

Ruling R43: concern 1+2 —— **R30 第五次抓到零鉴别力断言，这次在本任务、也是我写的。**
`apiKey 为空串时保持空串` 的期望值**就是**回退默认值 `''`，故「空串保持空串」与「空串回落默认」
在观测上不可区分；实施者的变异 D/E 证明它恒绿。
实施者顺带发现一件我该管的事：**`apiKey` 不做 trim 而 `language` 做**，且无断言钉住该差异。
从 TMDB 网页复制 Key **经常带尾部空白或换行**，后果是 401 →「API Key 无效」→ 用户查不出原因 ——
与本项目历史上那些误导性诊断同类，也正是本程一直在修的东西（后端为此做了 `first_air_date_year`
参数名核实、401 文案去重、404 分级等）。
**裁定：(a) 给 `apiKey` 加 `.trim()`**（Key 本身不含空白，trim 无损；与 `language` 一致）；
**(b) 把那条无用断言换成两条有鉴别力的**（`'  key  '` → `'key'` 钉 trim；`'   '` → `''` 钉全空白
回落 —— 去掉 `.trim()` 后第一条会红）；**(c) 修 `language 为空串回落 zh-CN` 的标签**（实际传 `'   '`，
断言有效但标签说谎）；(d) 按 R30 做变异验证并记哈希往返。
代价若判错：若某类真实 Key 含空白（我不知道有），trim 会破坏它 —— 已要求实施者若有此知识先说。

Ruling R44: concern 3（`stores/settings.js` 的接线**零自动化覆盖** —— 断言脚本加载不了它
[vue/pinia + 无扩展名导入]，`check-sfc-compile.mjs` 只读 `.vue`，`npm run build` 在 `tmdb` 从
store 返回对象里消失时不会失败；而这正是本仓库「死设置」缺陷的所在地）——
**裁定：按项目惯例标为 deferred-to-human，不新建前端测试设施。**
理由：`settingsSchema.js` 开头的注释就写着「本项目没有前端测试设施」，那是**刻意**的架构选择；
为一个计划的单个任务引入 vite/vitest 级设施属范围外。实施者已用一次性 esbuild bundle 验证过接线
（store 上暴露 tmdb、apply/toObject 往返、`apply(null)` 重置、openlist 完好），但那次验证不可重跑。
**补偿措施**：(a) 在计划的「完成后」一节写入一条精确的人工步骤（打开设置页 → 改 TMDB 三项 →
保存 → 刷新 → 确认留住 → 再回工作区确认预览随之变化）；(b) Task 6 与 Task 7 都会消费
`settingsStore.tmdb`，它们的实施者处于发现接线缺失的位置，故在这两个任务的派发里显式要求
核对 store 的字段暴露。代价若判错：接线若写错，只有人工验证能发现 —— 这是本项目既有的、
被明确接受的验证缺口，不是我新引入的。

Ruling R45: concern 4 —— `frontend/dist/` 是被跟踪的构建产物（19 文件），`npm run build` 使它变脏。
实施者按仓库惯例（`a6ac74a` / `0b812b4` 都是独立的 `build: 更新前端构建产物` 提交）把它排除在本次提交外。
**裁定：T5–T7 全部不提交 dist；前端三个任务做完后在收尾处打一个 `build:` 提交。**
并已在 Task 5 的修复指令里显式要求实施者**只 `git add` 实际改动的文件、不要 `git add -A`** ——
否则 dist 会被顺手扫进任务提交，污染后续审查包。代价若判错：若我忘了收尾那个提交，
工作树会留一份未提交的构建产物（可 `git checkout -- frontend/dist` 复原）。

Task 5: fix round 1/5 dispatched（findings: apiKey trim + 换掉无用断言 + 修标签 [R43]）
Task 5: fix round 1/5 report — commit 97504b4（2 files, +8/−3）；脚本 47 PASS/0 FAIL exit 0、
        SFC 编译 exit 0、`npm run build` ✓；`settingsSchema.js` 仍零 import。
        **变异证据干净且对比鲜明**：去掉 `.trim()` → 两条新断言全红（`得到 "  key  "` / `得到 "   "`，exit 1）；
        **而原那条断言在同一个变异下是绿的** —— 这就是它有无鉴别力的直接差别。恢复后哈希三点一致
        （变异前 = 备份 = 恢复后）。另用一次性 esbuild bundle 复核 trim 穿透 store
        （`'  pasted-key\n'` → `'pasted-key'`），临时入口已删。

Task 5: task review — **规格合规 ✅、Task quality Approved、无 Critical、无 Important**，3 条 Minor。
        审查者逐项核实了五个 watch-item，并做了两处命名风险的 diff 外检查（`asString` 被 hunk 边界截断、
        `readSettings` 在 hunk 之下）。点名表扬的一幕：实施者**刻意没有**为
        `!Array.isArray(raw.tmdb)` 那条守卫加断言 —— 因为数组没有 `apiKey`/`language`/`enabled`，
        `{tmdb:[1,2]}` 与 `{tmdb:{}}` 归一化结果相同、该守卫**不可观测**，加断言会重现它要修的缺陷类。
Task 5: **complete** (commits b5b8d95..97504b4, review clean after 1 fix round)

Ruling R46: 审查者的 ⚠️(a)（目前**没有任何东西消费 `settingsStore.tmdb`**，请求体也不带它；
「死设置」正是本任务存在的意义所在，故请 controller 确认后续任务会接线）——
**裁定：已规划、非缺口。** 核对计划：Task 7 Step 1 会在 `buildPreview` 与 `executeAction` 两处
下发 `tmdb_api_key: settingsStore.tmdb.apiKey` / `tmdb_language` / `tmdb_overrides`，
并在 `watch` 依赖数组之外按需刷新。**派发 Task 7 时必须把这条作为显式验收点**，
因为它是本计划的头号风险（设置写进 localStorage 却没人读、全程零报错）。

Task 5: minors deferred（交最终审查分诊）：
  M1 `language` 的**返回侧 trim 无断言** —— 保留守卫但去掉返回侧 `.trim()` 的变异能通过全部 13 条断言；
     是本轮刚给 `apiKey` 补的那条断言的**对称孪生**。实施正确、纯覆盖洞、1 行断言。
     **裁定：不开修复轮，折进 Task 6 的派发**（规程明确许可「批量小的同形工作」，
     折进下一个前端任务比单开一轮便宜）。见 R47。
  M2 `check-settings-schema.mjs` 里 `apiKey 全空白回落空串` 的标签写「回落」而机制是「trim 后为空」；
     值正确且有鉴别力（no-trim 变异下得 `'   '` → 红），纯措辞。
  M3 字段级断言直接解引用 `normalizeSettings(...).tmdb.apiKey`，故 `tmdb` 整组缺失时脚本以 TypeError
     崩掉而非逐条打印 FAIL；退出码仍为 1，门禁成立。属既有脚本形状、本任务未改。
⚠️ 审查者未从 diff 验证的另两项：(b) store 接线无机械断言 —— 已由 R44 裁定并写入计划的人工步骤；
  (c) 未重跑三个前端命令 —— 它静态核对了退出码路径（:15/:141），无阅读疑点需要新跑。

## 任务 6

Task 6: implementer DONE_WITH_CONCERNS (commits 259f806 + 88720e5；3 files，dist 计数 0)
        实施者**把折叠进来的断言拆成独立提交**（88720e5），理由是 brief Step 5 的提交信息只描述面板、
        塞一起会信息与内容不符，且本仓库对复审补偿已有独立提交的惯例（如 97504b4）。判断得当，接受。
        验证：断言脚本 49 PASS exit=0 / SFC 编译 exit=0 / `npm run build` exit=0，均提交后重跑。
        折叠断言实测能红：去掉 return-side `.trim()` → **仅** `language 被 trim` 一项 FAIL
        （其余 13 条 TMDB 断言全绿，证实了 R47 的判断），哈希三点往返一致。

Ruling R48: **实施者发现一条项目级基础设施盲区，值得单独记。**
brief 指定的两条前端检查（`check-sfc-compile.mjs` 与 `npm run build`）**都无法鉴别「漏 import」**：
实测两个变异体均为绿 —— (a) 模板用了 `Plug` 但 import 里没有（`compileTemplate` 未传 `bindingMetadata`，
`Plug` 被编成 `_resolveComponent`）；(b) `testTmdb` 的 import 整行删掉（未声明的标识符被 Rollup 当全局量）。
仓库也没有 lint 脚本。**这是既有盲区，非本任务引入。**
**裁定：不改 `check-sfc-compile.mjs`、不引入 lint —— 记入 ledger 并交最终整分支审查。**
理由：该脚本目前工作正常，为一处不在本计划范围内的基础设施改进去动它，破坏一个working check 的风险
大于收益；而可观测后果有界 —— `Plug` 漏 import 只少一个图标（静默但无害），`testTmdb` 漏 import 会在
点击时抛 `ReferenceError`（人工步骤必然撞上）。**补偿措施**：把该盲区作为显式警告带进 Task 7 的派发
（要求实施者靠阅读核对 import，不依赖那两个检查）。代价若判错：若 Task 7 漏了某个 import 且其后果是
静默的（如少一个图标），只有人工走查能发现。

Task 6: 顾虑逐条裁定（均不构成修复轮）：
  C1 未保存的草稿 Key 不 trim（trim 只在保存时发生）—— **实测无影响**：Key 走 `X-Tmdb-Key` **请求头**，
  而 HTTP 头值在传输层会被剥掉首尾空白（Node 的 HTTP 解析器如此），故后端收到的已是 trim 过的值。
  实施者的自评正确。
  C2 `testResult` 在改动 Key 后不清空 → 上一把 key 的「连接正常」会留在界面上，是同类「误导性状态」的小号版本。
  **交审查判定**（若审查者判为 Important 则进修复轮；否则 ledger 分诊）。
  C3 `searchTmdb` 是死代码（brief 要求导出，Task 7 才接线）—— **非缺陷，已规划**（同 R46）。

Task 6: 未验证、deferred-to-human（实施者主动列明，未假装覆盖）：面板从未在浏览器渲染；
        「测试连接」五种状态从未真跑（含需 `tmdb_enabled=false` 的 `disabled`）；
        未用 devtools 确认 Key 只走 header；草稿/重置/保存路径未实机走查。

Task 6: task review — **规格合规 ✅、Task quality Approved、无 Critical、无 Important**，5 条 Minor。
        审查者**自己在检出上跑了**两个检查（49 PASS exit 0 / 18 SFC OK exit 0），并**刻意没跑
        `npm run build`**「因为它会重写 `frontend/dist`」—— 守住只读约束同时把能做的都做了。
        它在**机制层**核实了 R48 的盲区说法（读 `check-sfc-compile.mjs:37,40-44` 确认
        `compileScript` 独立调用、`compileTemplate` 未传 `compilerOptions.bindingMetadata`），
        而非照单全收；并确认该盲区对本 diff **无实际影响**（三个 import 齐全且都被消费）。
        它另指出本 diff 特有的教训：漏 import 会以 `测试失败: testTmdb is not defined` 现身 ——
        **一个编程错误穿着连接失败的外衣**。这正是 import 块必须留给人眼的原因。
Task 6: **complete** (commits eeaf895..88720e5, review clean, no fix rounds)

Task 6: minors deferred（交最终审查分诊，全部 plan-mandated 且无错误行为）：
  M1（=C1）trim 契约在「测试」与「保存」间不一致 —— 审查者**认同实施者的评估：影响实为零**
     （HTTP 会剥掉头值首尾空白，且含内部空白的 key 本就无效、会落进可读的 catch）
  M2（=C2）陈旧判定不会被编辑作废：`testResult` 只在请求开始时清（:206），故用 key A 挣来的
     「连接正常」在用户输入 key B 时仍留在屏幕上，且 `reset()` 也不清它
  M3（=C3）`searchTmdb` 无调用方 —— 非缺陷（brief 的 Produces 要求导出），
     **但对 Task 7 有交办**：因为无人行使它，「搜索时 key 不进查询串」目前只是**代码阅读结论**，
     Task 7 接线时必须确认 `params` 不会加上 key
  M4 成功提示用 `text-ink-2`（普通次要文字）而失败用 `text-warn`，故「测试通过」读起来像提示语
  M5 `disabled` 的文案把 `tmdb_enabled = false` 这个内部配置名泄漏给了终端用户

## 任务 7

Task 7: implementer DONE_WITH_CONCERNS (commit 6baadea；4 files, +210/−2；`frontend/dist` 未提交)
        验证全绿：断言脚本通过 / SFC 23 OK / `npm run build` ✓ 1839 modules / Step 6 grep 命中 /
        后端 101 passed。并把「检查是否有鉴别力」这件事做成了方法：**M2–M6 测的不是代码写得对不对，
        而是「给定的检查能不能发现它没写对」**。
        (a) 两处调用点均已接线（`workspace.js:300-302` 与 `:409-411`），而且 **M6** —— 只从
            `executeAction` 移除 `tmdb_*`（即 brief 引用的那个历史故障）—— 让断言脚本 / SFC 检查 /
            `npm run build` / Step 6 grep **四个检查全绿**。「预览与执行不一致」这个本仓库有前科的
            具体故障，在前端这一侧零机械覆盖（与 Task 3 我判为 Important 的是同一故障）。
        (b) **R48 的盲区比原先报告的更宽**：M2/M3/M4 证明删掉 `TmdbMatchDialog` 的 import、
            `Search` 图标 import、**甚至纯 `.js` 文件（`workspace.js`）里 `searchTmdb` 的 import**，
            两个检查都绿、rollup 零警告 —— 静默的运行时 `ReferenceError`。
        (c) 确认 `searchTmdb` 的 params 只有 `{q, year}`，key 只走 `X-Tmdb-Key`（连压缩产物里也核了）。
        (d) **M5 揭穿 Step 6 的 grep 比它看起来弱**：删掉 `FileTable.vue` 整个 TMDB `<td>`，
            `grep -rl tmdb_status dist/assets/` 仍命中（字符串也来自 `workspace.js`）。
            它证明产物不陈旧，但**不能证明新列进了产物**。

Ruling R49: Task 7 的三条 concern **全部判为必修**，进修复轮 1。逐条理由：
  **findings 1（真 bug，且是我延后裁定导致的）**：`api/tmdb.py` 的 `_client` 用真值判断而
  `renamer.py` 的 `_tmdb_client_from_request` 用 `is not None`，故前端空白字段发的 `''` 被当成
  「已提供」→ 短路掉 `.env` 回退 → TMDB 被禁用，而设置页提示恰写着「留空则用服务端 .env 的配置」。
  **Docker 部署（配 `.env` 一次）这个主用例被破坏，且界面在说谎。**
  **这正是 Task 4 审查者的 Minor 2 所预言的重现** —— 它当时说这两处优先级计算「正是本仓库
  『设置不生效』那类缺陷会重现的位置」，我把那条记为 Minor 延后。**它重现了。**
  代价若判错：无（无论哪种语义，两处必须一致，而当前是不一致）。
  **教训**：审查者指出「这两处是同 defect 类的重现位置」时，那不只是 DRY 洁癖，而是一个
  风险定位；我当时按「今天两者一致且都有测试」把它降级为 Minor，漏掉了「它们服务的是同一个
  用户可见承诺」这一层。
  **findings 2（死设置，本项目头号风险实现）**：`settingsStore.tmdb.enabled` 无人读，取消勾选
  不停止 TMDB 查询。后端根本没有 `enabled` 请求字段 —— 而 spec 的问题 5 明确承诺了「启用开关」。
  故这是**补完 spec**，不是范围蔓延。
  **findings 3**：TMDB 设置变更不刷新预览；而计划自己的 §15.3 要求「预览列立即显示」，
  且补零位数那条注释已写明漏掉输入项会「与修复前那种『设置不生效』的观感一模一样」。
  代价若判错：无。

Ruling R50: Task 7 的 M5 结论（Step 6 的 grep 只能证明产物不陈旧、不能证明新列已进产物）——
**裁定：改计划文本**，把该步骤的描述改成它真正证明的东西，免得后来者高估它。
并**在计划的 deferred-to-human 清单里补一条**：「执行后的文件名必须与预览显示的一致」——
因为 M6 证明了这条具体承诺在前端零机械覆盖，而它正是本仓库有前科的故障。代价若判错：无。

Task 7: fix round 1/5 dispatched（findings: 空白 Key 短路 `.env` + 两处优先级收敛 [R49-1] /
        `enabled` 死设置 [R49-2] / 预览不随 TMDB 设置刷新 [R49-3] / Step 6 描述改准 [R50]）
Task 7: fix round 1/5 report — commit 39e825d（6 files, +225/−21）；后端 **101 → 109 passed**；
        断言脚本 / SFC 23 OK / `npm run build` 全绿；`dist` 未提交、未用 `git add -A`。
        **收敛成一个决策点**：新增 `api/tmdb.py::build_tmdb_client(header_key, header_language, enabled)
        -> Optional[TmdbClient]`，`_client`（抛 400）与 `renamer._tmdb_client_from_request`（降级 disabled）
        都只是它的薄包装；判定改用**真值**，docstring 写明与 `_pad_from_request` 的 `is not None` 语义不同
        （0 是合法补零位数 / Key 的 `''` 就是「未提供」）。未新建模块或基类 —— 函数落在**已经是**决策者的
        `api/tmdb.py`，`renamer.py` 跨路由导入与既有 `from .scanner import get_default_client` 同 pattern。
        **变异证据锐利**：决策点改回 `is not None` → **2 红，而原有 101 条全绿** ——
        这就是该缺陷此前不可见的原因（`test_env_key_is_used_when_header_absent` 传的是 `None` 而非 `''`）。
        去掉 `enabled is False or` → 2 红；去掉 `or not settings.tmdb_enabled` → 4 红。
        **密闭性做了反向验证**（非仅断言）：三个 proxy 环境变量指向死端口后跑两个 TMDB 测试文件 →
        45 passed（httpx `trust_env=True`，真出网必红）。

Ruling R51: 实施者报告收敛**顺带修掉一个真缺陷**：`/api/tmdb/search` 原先从不看 `settings.tmdb_enabled`
（服务端总开关对搜索端点形同虚设 —— 填了 Key 就照查不误），而 `/test` 早就报 `disabled`；
它判断这是「两处优先级两个判断点」的产物，问我是否属预期范围。
**裁定：属预期范围，确认保留。** 理由：这是我所下令的收敛的直接后果，而「总开关在一个端点上有效、
在另一个上失效」本身不自洽 —— 服务端关掉 TMDB 却仍允许搜索，是同一个 defect 类的残留。
两种成因给两种文案（服务端禁用 vs Key 无效），已有测试钉住两者。代价若判错：
`/search` 的行为比改动前更严格（服务端禁用时返回 400 而非照查）—— 但那个「照查」正是缺陷。
实施者也明确提出另一种做法（把 enabled 判定挪回 `/test` 与 rename 两处）并**自陈不推荐**，
因为那会重新长出两个判断点 —— 我同意，不采纳。

Task 7: task review — **规格合规基本 ✅、Task quality 批准**，**2 条 Important** + 5 条 Minor。
        审查者独立核实：两处调用点字段完整且一致、决策点确实唯一（`grep` 显示读取只在
        `api/tmdb.py` 与两个模型声明处，`api/renamer.py` 已是一行委派）、变异证据结构上成立
        （新测试经 `payload.update(extra)` 把 `''` 真的放进请求体，而旧测试走的是「请求头缺失」→ `None`）、
        `/search` 的总开关改动与 R51 一致、无循环 import 且依赖方向合既有 house pattern。
        **它还做了一件我没要求的事**：去构建产物里核对一个时序假设 —— 手动标题的 override 依赖
        `v-model` 先于 `@update:model-value` 赋值，它用 `dist/assets/HomeView-*.js` 里的
        `"onUpdate:modelValue":[k=>c.title=k,k=>o.$emit("update-row",c)]` 确认顺序正确。
        这类「只有运行时才暴露、但产物里恰好读得出」的检查很聪明。

Ruling R52: Important 1 —— **我的计划里有一条验收标准不可能达成。**
`buildPreview` 的请求体从不发 `overrides`（只有 `executeAction` 发），故逐行手动编辑**永远不会反映到
预览**：改标题后「新文件名」列仍是服务端的值；改集号为 999 后「TMDB」列永远不会变「无此集」。
**而计划 `完成后` 第 5 条验收步骤写的正是后者。** 它是**既有的**缺陷（brief 规定的 preview 请求体本来
就没有 `overrides`），不是实施失误；但本计划新加的「标题」列让它刺眼 —— 本计划的核心就是让用户看见并改
标题，改完毫无反应，功能等于没有。
**裁定：(a) `buildPreview` 补发 `overrides`**（一行，照 `executeAction` 的构造）；
**(b) 不改「编辑即重建」** —— 那会给四个输入框每次按键都带来一次整列表的服务端往返，属行为与性能改动、
不在本范围；**(c) 把计划的验收步骤改成「点『预览』按钮后生效」**，那是可达且诚实的表述。
代价若判错：用户改完标题需点一下「预览」才看到新文件名 —— 比默认自动重建少一点顺滑，
但比「改了毫无反应」好，且不引入每次按键的往返。

Ruling R53: Important 2 —— **违反我在派发里立的全局约束「取消勾选后不得再查 TMDB」。**
`searchShow` 不带 `enabled`（`/api/tmdb/*` 也没有该字段），故用户关掉开关后对话框仍查 TMDB；
更糟的是 `pickShow` **无条件**弹「已选用 …」成功提示，而开关关着时 `buildPreview` 全返回 `disabled`
—— **选择被静默丢弃，用户却被告知成功了**。这是本程一直在修的那类「让用户相信一件没发生的事」。
**裁定：进修复轮** —— 前端侧门控（开关关时不发请求、不弹成功提示），不新增请求字段
（辅端点保持只受服务端开关约束，与 R51 一致）。代价若判错：无。

Task 7: minors deferred（交最终审查分诊）：M3 成因归属重复推导（加第三种成因要改两处）、
        M4 后端不 trim（`"   "` 被当成已提供 Key；前端已 trim，只有手写客户端会撞上）、
        M5 标题无法清空（plan-mandated，注释已写取舍）、M6 搜索词两个真相源、
        M7 `dist` 脏（下一个任务不得扫进去）。

Task 7: fix round 2/5 dispatched（findings: preview 补发 overrides [R52] / 对话框受用户开关门控 [R53]）
Task 7: fix round 2/5 report — commit cb7fd0f（仅 `workspace.js`，+45；`dist` 未提交）；
        后端 109 passed（另把三个 proxy 指向死端口重跑，仍 109 —— 密闭性未变）；
        断言脚本/SFC 23 OK/`npm run build` 全绿。
        findings 1：`buildPreview` 补发 `overrides`（构造与 `executeAction` 逐字相同）；
        **产物级证据**：压缩后的预览请求体已是 `…create_season_folder:…,overrides:E,episode_pad_digits:…`
        而 `const E={};F.value.forEach(B=>{B.override&&(E[B.id]=B.override)})`（`F` = `previewRows`）。
        findings 2：三个入口共用 `tmdbOff()` + 一句 warning；`searchShow` 早退在 `loading` 与
        `searchTmdb` **之前**；**产物级复核**：`async function O(_){…if(x()){N.results=[],I(T,"warning");return}N.loading=!0;try{const q=await Wg({…})`
        —— 守卫确实在 axios 调用之前。
        **过程留痕（值得记）**：它写的顺序检查第一版报了两条**假 FAIL**，因为它自己的注释里就写着
        `searchTmdb(` 与「已选用」；剥掉行注释后才对。**一个检查工具自身的假阳性与它断言的东西同等重要**，
        它把这件事写进了报告。

Ruling R54: **实施者发现了它自己修复所「解锁」的新缺陷，并拒绝擅自修。**
`buildPreview` 重建行时硬编码 `override: {}`（brief 原文），于是「编辑 → 预览 → 执行」会丢掉手动编辑：
预览按 override 渲染（显示「我的标题」），执行读到空 override → 写出 TMDB 标题。
**修复前这个序列不可能出现**（预览不发 overrides，编辑会被肉眼可见地还原）——
即**我下令的修复制造了这条路径**，而方向正是本仓库有前科的「写出的文件名与预览不一致」。
**裁定：必修为回归。** 不留它不动就等于是发布一个我开启的回归。
修法：重建行时按 file id 沿用上一份 `override`（4 行），不改请求体、不改服务端、不引入自动重建。
代价若判错：手动编辑在重建后保留，而用户若期望「重建即放弃编辑」，需自己把字段改回去 ——
已要求实施者把该语义写进注释，并在报告里说明产物级证据。
**实施者拒绝擅自修是对的**：brief 明写 `override: {},`，且这会为「编辑→预览→编辑」的往返语义
定新规矩 —— 那是设计决策，不是实施细节。

Ruling R55: **我的计划第 5 条措辞第二次出错，这次是实测推翻的。**
`updatePreview` 在每次编辑时把四个字段（含 `title`，取自标题框）整体写入 `row.override`，
所以「原本有 `Breakage`、只改集号」时 `{title}` 渲染 `Breakage`，而非我 `762aa66` 改后写的「渲染为空」。
实施者用一次性探针实测（跑完即删、未提交）：
  CASE A（updatePreview 实际发的）：episode_not_found | 'Breakage' | Test Show - S01E999 - Breakage.mkv
  CASE B（标题为 null）：        episode_not_found | None       | Test Show - S01E999 - .mkv
**裁定：改计划（第二次），补一张两行表说明两种情形都正确。** 代价若判错：无。
**教训**：我在 R52 里说「写验收步骤时是照着『用户会怎么用』写的，而不是照着『代码会怎么跑』写的」——
这条第二次出错说明我改的时候**仍然只改了我被指出的那半句**，没有把整条步骤按代码重推一遍。

Task 7: fix round 3/5 dispatched（findings: 重建保留 override [R54]）
Task 7: fix round 3/5 report — commit 1331e0e（`workspace.js`，+18/−1）；后端 109 passed、
        三 proxy 死端口下仍 109、断言脚本/SFC 23 OK/`npm run build` ✓。
        修法一行：`override: {}` → `override: overrides[f.id] || {}` —— **复用请求体那一份映射**，
        故「预览里显示的」与「随后执行写出的」**同源**（单点真相，不是两处各算）。
        它**纠正了我一处不必要的含糊**：我写「新扫描若同名文件 id 相同则保留编辑，可接受」，
        而实测 `file_id` = `uuid.uuid4().hex[:12]`、**每次扫描全新随机**，故那个 hedge 根本不成立；
        它按实测事实写注释，而非顺着我的说法写。
        验证两条：可变异复现的数据流检查（改回 `override: {}` → 2 红；只删请求体的 `overrides,` → 1 红，
        回滚 md5 校验）＋产物级证据（行构造 `override:E[B.id]||{}`，而 `E` 正是下发的那一份）。
        我方对 `updatePreview` 的理解被确认为**正确无偏差**，并得到两条补充：(a) 冻结前提是标题框那一刻
        **非空**（`''` 走 `title: null`，TMDB 标题仍能进来），故「原本无标题、只改集号」不冻结；
        (b) 对称地，改标题也会把当时显示的 `show_name/season/episode` 一起冻结 —— 四字段共用同一处理器，无主次。
        后两条已回填计划（避免后来者把正常行为当故障查）。

Ruling R56: **流程裁定 —— 把修复轮 2 与轮 3 合并为一次再审查。**
轮 2（cb7fd0f）之后我**直接**进入了轮 3，跳过了轮 2 的范围限定再审查，原因是实施者自己发现
轮 2 的修复解锁了新缺陷、说明轮 2 的工作尚未完成。若再补一次轮 2 的再审查，就是在同一份文件上
多开一个重叠的审查席位（规程明确警告重复席位）。**裁定：用一次覆盖 `39e825d..1331e0e` 的再审查
同时核验三轮的全部 findings。** 代价若判错：若轮 2 的某条 finding 被轮 3 的改动掩盖，
它与轮 3 的改动在同一份 diff 里，审查者仍看得到 —— 风险可控。

Task 7: fix rounds 2+3 merged re-review — 3 条 findings 全部 **ADDRESSED**，无新 Critical/Important。
        审查者独立核实：override 的恢复与下发**用的是同一个对象字面量**（构造于 `:301-304`、下发于 `:312`），
        即单一真相而非两处各算；三个入口的守卫均在网络调用**之前**返回；守卫条件与后端
        `enabled is False` 精确对齐（`None`/`undefined` 两边都当「未指定」）；
        并**对着代码而非注释**核实了 `uuid4().hex[:12]` 的推理。
        它还排查了一个我没点名的风险：新持久化是否会让重建触发 `updatePreview`、把服务端解析永久冻结
        —— `AppInput` 只在 `@input` 时 emit、对 prop 无 watcher，故重建无法伪造编辑；`clearAll` 与
        `updatePreview` 也都不受影响。它另主动声明 diff 文件在一处 hunk 被截断、并从源码读了余下部分。
Task 7: fix rounds 2+3 (3 addressed, 0 open; commits 39e825d..1331e0e)
Task 7: **complete** (commits 88720e5..1331e0e, review clean after 3 fix rounds)

## 计划 1 全部完成

Task 1–7 全部 complete。汇总：
  T1 修复 1 轮 / T2 修复 2 轮 / T3 修复 3 轮 / T4 修复 4 轮 / T5 修复 1 轮 / T6 修复 0 轮 / T7 修复 3 轮
后端：109 passed，全程密闭（无网命名空间 + proxy 死端口两种方式验证）。
前端：5 个机械检查（断言脚本 / SFC 编译 / build / 产物 grep），外加两处**已明确记录**的验证缺口。

Task 7 遗留（交最终审查）：pickShow 在**服务端**开关关闭而浏览器开关开着时仍会弹成功提示
（需在对话框打开期间重启服务端才可达，因此非阻塞）。

计划 1: final whole-branch review — **With fixes**（5 条 Important + 一批 Minor）。
        model: opus；审查者**分三遍**读（代码 → 5500 行设计/计划散文 → 验证运行），
        并**独立复现了密闭性**：在 `unshare -rn` 内确认 `api.themoviedb.org:443` 是
        `Network is unreachable`，后端 109 passed —— **这替我关掉了 ledger 里最后一个 ⚠️ 项**
        （我在 R44 承诺过自己复核，它替我做且做得更硬）。它也刻意**没跑** `npm run build`（会重写 dist）。
        **它自己点名表扬的**：`_guarded` 把宽捕获放在外部数据边界且 docstring 写出理由与禁止改动；
        404 分级的不对称正确且有注释与测试钉住（R39 的逆转是可读的）；
        六态各有互斥断言且字面值被 `test_tmdb_status_literals_are_the_wire_contract` 钉住（R22 落实了）；
        单点优先级 + `test_build_tmdb_client_is_the_single_decision_point` 防复辟；
        Key 卫生干净（头的 key 不进访问日志、错误信息不回显 key、缓存键只存截断 sha256）；
        **`safe_filename` 在 `apply_template` 末尾意味着 TMDB 文本无法把 `/` 注入文件名**（它专门找过路径注入，已关闭）；
        R54 的单一真相修法形状正确；conftest 让套件与环境无关。

Ruling R57: 最终审查的 5 条 Important **全部判为必修**，连同审查者点名的「fix-before-merge」Minor 与
几条 1 行加固，合成**一次**修复波派发（规程：整分支审查只派一次修复、之后一次范围限定再审查，
所以没有「下一波」可推）。其中三条 Important 是**我的问题**：
  #1 前端吞掉 spec 要求必须显示的认证错误 —— `buildPreview` 只 `console.error(e)`，
     `previewAll` 无条件弹「预览已刷新」成功；Key 无效时用户看不到任何提示，且旧行留在屏幕上使他
     以为新 Key 可用。**计划自己的验收步骤 6 因此不可能达成**（同 R52 的形态：我写了做不到的验收）。
  #4 计划在 Task 7 的修复轮之后**从未回填**，现在描述的是修复前的实现（`override: {},`、无 `overrides,`、
     无 `tmdb_enabled`、无 `tmdbOff()`、通篇无 `build_tmdb_client`）。审查者点中要害：
     「按计划 Task 7 Step 1 逐字重跑的实现者会**重新引入本程修好的两个回归**」。
     我给 Tasks 3/4/5 都做了回填（R19/R33/R50），**唯独漏了 7** —— 而 Task 7 恰好是修复轮最多（3 轮）的那个。
  #5 分支的旗舰约束「TMDB 故障绝不阻断重命名」**无路由级测试** —— 只有解析器级；
     路由级只经 `disabled` 路径（那里 `TmdbResolver` 根本不被构造）。将来 `_with_tmdb_titles` 里出现一个宽
     `except` 会让 109 条测试全绿而阻断每一次重命名。**这与我在 Task 3 判为 Important 的 R29 是同一类，
     而这次是分支的旗舰承诺。**
另两条 #2（`pickShow` 在 `show_name` 为空时静默丢弃选择却报成功 —— 正是 R53 修过的同一缺陷的另一分支）、
#3（spec §12.1 的「Key 显示切换」被计划悄悄丢掉，而它正是本程头号 Review Focus「v3/v4 抄错却无从判断」的直接成因）。

Ruling R58: 审查者指出**我的计划 Self-Review 里有一条假证据** ——
`test_tmdb_overrides_are_accepted_by_the_request_model` 因 pydantic 忽略未知字段而**无法因它声称的原因失败**，
而我的 Self-Review 把它写成了 §10.4「字段确实被模型接受」的证据。pydantic 忽略未知字段，故删掉该字段模型仍返回 200。
**这是第六次「零鉴别力检查」，而这次它出现在我自己的自查里** —— 前五次被实施者/审查者抓出，
这一次是一个更上游的读者（最终审查者）纠正了我的**元层**声明。
**裁定：进修复波**（改为断言 `"tmdb_overrides" in RenamePreviewRequest.model_fields`）。代价若判错：无。

Ruling R59: 审查者的 Phase 2 交接警告 —— 「合并进来的 `title` 在下游与用户手打的标题**不可区分**
（`_with_tmdb_titles` 把 TMDB 标题折进 `overrides` 通道）」，故 Phase 2 应当**向上暴露 `EpisodeMatch`**
而不是重新推导，否则 NFO 生成会继承同一种混淆。
**裁定：记入计划 2 的派发交办。** 这正是计划 1 的「与下一期的衔接」一节已经写过的方向，
但审查者给出了**理由**（下游不可区分），比原计划写的更硬。代价若判错：NFO 会用错标题来源，
表现为「NFO 里的标题与文件名不一致」——静默且难查。

计划 1: final-review fix wave dispatched（11 项：5 Important + fix-before-merge Minor + 1 行加固；
        model: sonnet；明确要求每项给覆盖测试或变异证明，并要求跑 `unshare -rn` 复核密闭性）

Task 7: deferred（交最终审查）：Concern 4（对话框搜索框缺 `flex-1`，需浏览器判断）；
        R48 的扩展结论（盲区覆盖到 `.js` 文件里漏掉函数 import → 静默 ReferenceError，rollup 零警告）；
        以及是否值得为前端引入 lint 或让 `check-sfc-compile.mjs` 传 `bindingMetadata`
        —— 我先前裁定为「不在本计划范围内」，但 R48+M2/M3/M4 让这条基础设施缺口的证据强了很多，
        最终审查可据此重估。

Task 7: task review 交办汇总（派发时必须带）：
  (a) **R46 的显式验收点**：`buildPreview` 与 `executeAction` **两处**都要下发
      `tmdb_api_key` / `tmdb_language` / `tmdb_overrides` —— 这是「设置写进 localStorage 却没人读」
      那条头号风险的唯一接线处
  (b) **R48 的盲区警告**：`check-sfc-compile.mjs` 与 `npm run build` **都无法发现漏 import**，
      实施者必须靠阅读核对 import，不依赖那两个检查
  (c) **M3 的交办**：确认 `searchTmdb` 的 params 不会加上 key

Ruling R47: Task 5 的 M1 折进 Task 6 的派发（1 行断言：`normalizeSettings({ tmdb: { language: ' ja-JP ' } })`
→ `'ja-JP'`）。理由：它属「小的同形工作」，规程明确许可批量；且 Task 6/7 本就要跑
`check-settings-schema.mjs` 作为验证的一部分，顺手关闭比单开修复轮省一轮 dispatch 与一轮再审查。
代价若判错：Task 6 的 diff 里混进一条不属于它主题的断言 —— 已在派发中显式说明来由，审查者不会误判为范围蔓延。

Ruling R24: 再审查者提出 3 条 out-of-scope 观察，**全部 park 并指向最终整分支审查**，不再开第三轮修复：
  **[已被 R37 + R39 推翻，本条保留仅供追溯]** —— 下述判断的前提（「没有可举出的现实制造者」）
  已被 R37 证伪（拦截式代理 / DNS 屏蔽回 404），且 R39 进一步纠正了分级目标（应为 `unavailable`
  而非本段设想的 `show_not_found`）。本条不再代表现行裁定。
  (a) `tmdb_resolver.py:241-244` 的 search 路径只捕 `TmdbUnavailableError`；若 `search_tv` 抛
      `TmdbNotFoundError`（`_get` 的 404 分支可达）会逃出 → 500。修复是 1 行（补一条与 detail 路径
      :257-258 对称的 `except TmdbNotFoundError: return STATUS_SHOW_NOT_FOUND`）。
  (b) detail 路径的 `except TmdbNotFoundError → show_not_found`（:253-260）是 `show_not_found` 的
      一个来源，而 26 条用例无一让 `get_tv_detail` 抛 NotFound（只经 `hits=[]` 覆盖）。既有覆盖缺口。
  (c) `:248` 的 `tv_id = hits[0].tv_id` 在守卫之外 —— 若客户端映射层将来返回畸形条目，
      AttributeError 会绕过守卫。
  **park 理由**：(a)(c) 在**当前客户端契约下不可达** —— (a) 需要 TMDB 对一个它自身存在的端点回 404，
  (c) 需要 `search_tv` 返回畸形条目而它已跳过缺 id 的项、且 `TmdbSearchItem` 是 pydantic 模型故
  `tv_id` 恒存在；没有可举出的现实制造者。(b) 是覆盖缺口而非缺陷。
  **我把 (a) 摆在最终审查的第一优先**：它虽然现实性最低，却是三者中唯一一条 1 行、且能让 search 与
  detail 两条对称路径真正对称的修复，且与 R21「分类性而非枚举性」的理由一脉相承。**但我不再自己开轮** ——
  已为 Task 2 花掉两轮修复，每多开一轮都有真实成本，而「Minors 不进循环、交最终审查分诊」正是规程
  为此设的闸门；继续为每个新观察开轮会让循环永不收敛。代价若判错：一个只可能由 TMDB 自身异常行为
  触发的 500 路径留存到合并，最终审查会看到并决断。
