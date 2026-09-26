# SDD execution ledger — 计划 3：刮削改为用户显式触发（spec §17）

归档自执行期的工作区 ledger（原本在 `.superpowers/sdd/2026-09-26-manual-tmdb-scrape/progress.md`，
该工作区在收尾时按规程删除）。**这是本计划的裁定记录**：pre-flight 扫描表、实施期裁定、
各任务的修复轮记录、最终整分支审查与那一次修复波，以及每条裁定的理由与「判错会怎样」。

**⚠️ 命名空间**：本文件的裁定编号 **R1–R24 是「本计划内」的编号**，与
`2026-09-26-tmdb-nfo-ruling-index.md` 的 **R1–R93**（TMDB 集成 + NFO 生成两期）**不是同一个命名空间**
—— 两份文件里都有一条 R7，但它们是两件完全不同的事。本计划的裁定全部集中在**一篇 spec 小节
（§17）的落地**上，范围远小于前两期。

设计权威：`docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md` 的 §17
（执行期追加；另含 §14 的两条新限制与 §16 的裁定 #15）。计划：
`docs/superpowers/plans/2026-09-26-manual-tmdb-scrape.md`。

---
# SDD ledger — plan: docs/superpowers/plans/2026-09-26-manual-tmdb-scrape.md

分支：feat/tmdb-nfo（项目惯例：普通分支而非 worktree，见记忆 sdd-workflow）
MERGE_BASE（用于最终审查）：b940340 —— 本计划文件被提交的那个提交
起点 BASE（T1 派发前记录）：b940340
Spec：docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md 的 **§17**（可达，已读）
上一期记录：docs/superpowers/ledgers/2026-09-26-tmdb-nfo-ruling-index.md（R1–R93 索引，建议派发前参考）

## Pre-flight 冲突扫描

### 跨任务：共享文件或接口

| 任务对 | 共享物 | 一方产生 vs 一方消费 | 结论 |
|---|---|---|---|
| T1 → T2 | `scrapeGate.js` 的三个谓词 | T1 定义；T2 import（`tmdbPendingScrape` 以 `isTmdbPendingScrape` 别名引入） | 一致。**别名是必需的**：store 里有同名 computed，不别名会遮蔽成「调用 ref」，运行期报 not a function（写计划时自查抓到） |
| T1 → T2 | `buildRenamePayload` 的签名 | T1 定义 16 个入参；T2 两处调用 | 一致。preview 调用**不传** `conflictStrategy`、execute 调用传 —— 与 `mode` 语义相符（preview 模式本就不含该字段），**不要"补全"** |
| T1 → T2 | 两个 `check-*.mjs` 的断言 | 断言只依赖 T1 的函数行为；T2 只改调用方 | 一致 |
| T2 → T3 | store 导出 `tmdbPendingScrape` / `nfoNeedsScrape` / `scraping` / `scrapeTitles` | T2 导出；T3 在 HomeView 以 kebab-case 传入 FileTable | 一致（名字已在计划里逐字列出） |
| T2 → T4 | `ws.nfoNeedsScrape` | T2 导出；T4 传给 TemplateConfig | 一致 |
| T2 → T4 | `lastResult.nfo_blocked_by_scrape` | T2 写入；T4 的 ResultDialog 读 `props.result?.nfo_blocked_by_scrape` | 一致（字段名逐字一致） |
| T3 → T4 | **`HomeView.vue`** | T3 改 `<FileTable>` 属性块；T4 改 `<TemplateConfig>` 属性块 | 共享文件但**不同段落**，顺序执行无冲突 |
| T3 → T5 | `frontend/dist/**` | T3/T4 都不提交 dist；T5 统一提交 | 一致（Global Constraint） |
| T4 → T5 | 同上 | 一致 |

### 单任务：自身一致性

| 任务 | 测试 vs 实现 | 文件创建 vs 后续触碰 | 结论 |
|---|---|---|---|
| T1 | 两个脚本的断言逐条对过实现（含 `assertKey` 的存在性断言、`tmdb_enabled === false` 的严格比较） | 只创建；后续任务只 import，不改 | 自洽 |
| T2 | **无自动化测试**（store 无法被 node 加载，R44 已记录）；验证 = 两个机械判据 + 源码级 grep | 改 `workspace.js` 一个文件 | 自洽，且能力边界已在计划里写明 |
| T3 | 无自动化测试；验证 = SFC 编译 + 构建 + grep | 改 `FileTable.vue` / `HomeView.vue` | 自洽 |
| T4 | 无自动化测试；验证同上 | 改 `TemplateConfig.vue` / `ResultDialog.vue` / `HomeView.vue` | 自洽 |
| T5 | 验证本身 | 只改 `dist` | 自洽 |

### 扫描结论

无任务互相矛盾，无任务与 Global Constraints 冲突，无「计划强制要求但审查规则视为缺陷」的项（唯一候选是 T1 的 `assertKey` 与既有 `assert` 并列，但两者断言的是不同的东西——值 vs 键的存在性，不是重复）。

## Pre-flight 裁定

Ruling R1: **沿用普通分支 `feat/tmdb-nfo`，不新建 worktree。**
理由：本项目已有两次先例并记入 ledger（四期重构与设置生效那两期），且当前分支不是 main —— 隔离成立（实现不在 main 上）。代价若判错：无（与项目惯例一致）。

Ruling R2: **T2 的 import 接线没有机械判据，这是既有盲区（R48），不是本计划的缺陷。**
`check-sfc-compile.mjs` 只读 `.vue`，而 `workspace.js` 是 `.js`；rollup 对 `.js` 里漏掉的函数 import **零警告**（R48 实测过三个变异体全绿），运行期才以 `ReferenceError` 现身。**裁定：接受，以两条补偿措施兜住** —— ①T2 Step 10 的 grep 计数（能证明 import 行存在）；②在 T2 的派发里**显式交办**，要求实施者靠**阅读**核对 import，不依赖那两个检查。代价若判错：漏 import 会在点击「刮削标题」时抛 ReferenceError —— 而 Task 5 走查第 2 项（点按钮）**必然撞上**，不会流到合并。

Ruling R3: **T1 导出的 `scraped` 在 UI 层暂无消费者，保留。**
计划要求导出它（T2 Step 9），而 T3/T4 消费的是三个 derived computed。**裁定：保留导出** —— 该 store 导出了几乎全部内部状态（既有风格），且调试时能直接看到门控位。代价若判错：多一个未使用的导出（无实际风险）。

## 进度

## 任务 1

Task 1: implementer DONE (commit 56634c7；4 文件 +231)。报告要点（未独立核实，交审查者）：
        RED 为预期的 `ERR_MODULE_NOT_FOUND`；两个脚本 11 + 23 条断言全绿；
        **三个变异全部命中预测且各只红一条**（① 分支改成 `{}` → 红在「严格为布尔 false 得到 undefined」；
        ② 改成 `{tmdb_enabled: ''}` → 红在同一条得到 `""`；③ 删 `!scraped` → 红在「已刮削 → 否 得到 true」），
        三次还原后 sha256 逐字节等于基线；四份产物与 brief 代码块 diff 四次 IDENTICAL（逐字性已机械证明）；
        两模块 grep 无 import；`backend/` 与 `dist/` 未触碰。
        它自报的非阻塞顾虑：`buildRenamePayload` 在 `scraped: true` 时直接解引用 `tmdb.apiKey`
        —— 接线时必须传 `settings.tmdb`（brief 逐字代码，未加防御）。
Task 1: task review dispatched（range b940340..56634c7，1 commit，12754 bytes；model sonnet）。
        派发里带的注意力透镜：spec §17.2 的「唯一有效表达是显式 false」+ 计划要求的三种错误实现必须被打红。
Task 1: task review — **Spec ✅、Task quality Approved**，1 条 Important（plan-mandated）+ 5 条 Minor。
        审查者**从断言语义独立推出**三个变异的红/绿，而非采信报告；并做了三处具名风险的 diff 外核查：
        16 个载荷键与后端两个请求模型逐字对上（且 `conflict_strategy` 只在 execute 模型里，与
        `mode === 'execute'` 守卫相符）、spec §17.2 的 `.env` 回退前提在 `api/tmdb.py:73,76` 成立、
        `package.json` 有 `"type": "module"` 故 `.mjs` 导入 `.js` 无风险。

Ruling R4: **Important 1 —— 计划错了，修 fixture（不是修代码）。**
  审查者证明：`check-rename-payload.mjs` 里 `episode_pad_digits` / `season_pad_digits` 都断言 2、
  `generate_nfo` / `nfo_overwrite` 都断言 false，因为 fixture 把每对取成**同值** ——
  于是把实现里这两对**互换**时 23 条断言全绿，那四条断言是零鉴别力的摆设。
  我核过：成立。**裁定：改 fixture 为 2/3 与 true/false，并补第 4 条变异作为证明。**
  理由：计划是我的论证，spec 才是权威；spec §17.6 要求的正是「两处共用 + 有机械判据」，
  而同值对让那个判据失效。互换的后果是真损失（补零位数互换 → 每个文件按错的位数改名；
  NFO 两项互换 → 用户勾了却不生成），两处都静默。
  **代价若判错**：fixture 取不同值后，若有人日后「顺手统一」成同值，这条鉴别力会无声消失 ——
  已在 fixture 处写明「有意的，不要统一」。
  **形态记此**：这是本项目 ledger 反复记的同一形态的又一次命中 —— **我写的断言无法回答
  「把实现改坏它会不会红」**。而计划原定的三条变异**全部**打在 TMDB 门控上，没有一条碰透传字段，
  所以计划自己的变异清单也漏掉了它：**变异清单的覆盖面与断言的覆盖面一样会漏**。
  （fixture 修订见 b407ec8。）

Ruling R6: **Task 3 的 grep 查不出「用错谓词」，裁定不改计划、改为写进该任务的派发。**
  审查者刚抓出的 finding 属于同一族：**一条检查对错误实现也通过**。我顺着这条把其余任务的检查过了一遍，
  发现 Task 3 Step 6 的 `grep -n "'未刮削'"` 只证明那两个**字面量**存在 —— 若实现写成
  `!props.scraped` 而不是 `props.tmdbPendingScrape`（两者在「设置页关着」时结果不同），
  这条 grep **照样绿**。
  **裁定：不改计划**，理由：该区分**已被走查第 2 项覆盖**（「设置页取消勾选后再点：应弹文案，且
  TMDB 列仍应是『未启用』而不是『未刮削』」—— 那一条测的正是这个谓词），而收紧 grep 的边际收益
  很小、却要再改计划 + 重生成 brief + 再提交一次。改为把「这两个谓词的区别是 load-bearing」
  写进 Task 3 的派发提示。
  **代价若判错**：若走查第 2 项将来被跳过，用错谓词的实现只能靠最终审查发现 —— 而它是一条
  会导致错误诊断的缺陷（把「去设置页打开开关」说成「去点刮削」）。
  **同一次清扫还查出 Task 2 的一处同类盲点**：`grep -c "buildRenamePayload"` = 3 只能证明两个调用点
  都**用了**构造器，不能证明传进去的是 `scraped: scraped.value` —— 写成硬编码 `scraped: true`
  会让整个功能失效而 grep 照样绿（走查第 1、4 项覆盖它）。同样改为写进 Task 2 的派发。

Ruling R5: **Minor 2（`renamePayload.js` 注释写「17 个字段」而实际 16 个）折进本次修复轮。**
  理由：它是一个**虚假陈述**（本项目对「注释去伪」有既定实践 —— 设置生效那期的 Minor 5 因
  「该陈述由本次改动本身变为虚假」被提升进修复轮），且该文件本就在本次修复的落点上，边际成本为零。
  **代价若判错**：修复轮的 diff 里混进一行不属于该 finding 的改动 —— 已在派发里说明来由，
  审查者不会误判为范围蔓延。

Task 1: minors deferred（交最终审查分诊）：
  M3 `assert` 助手在三个脚本里逐字重复 —— 审查者核实这是仓库惯例（独立脚本、无共享模块），
     并指出第三个副本是「值得抽 `scripts/_assert.mjs`」的临界点（注意「不得 import」只约束两个
     `src/stores/` 模块，不约束脚本）。
  M4 `buildRenamePayload` 在 `scraped: true` 时直接解引用 `tmdb.apiKey` —— 契约是「调用方必须传
     settings 对象」，属 T2–T4 的接线义务；**已带进 T2 的派发**。
  M5 没有覆盖 `mode: 'execute'` + `scraped: false` 的组合 —— 审查者确认 tmdb 块与 mode 无关、
     由构造即覆盖，纯完整性注记。
  M6 两个新脚本**不会被自动运行**（`package.json` 无 `test` 脚本、无 `.github/`）——
     与既有两个脚本同惯例，非本任务回归；但它意味着本任务买到的鉴别力**只在有人记得跑时**才生效。
     **这一条值得在最终审查里重估**（是否该加一个聚合 runner）。

Task 1: fix round 1/5 dispatched（findings: 同值 fixture 零鉴别力 [R4] / 注释错数 [R5 折入]）。
Task 1: fix round 1/5 report — commit 4187175（2 文件 +10/−5；被测实现逻辑**一字未改**，只改 fixture
        与两条期望值，加 5 行「必须取不同值」的注释；`17 → 16` 那条用
        `Object.keys(buildRenamePayload(...)).length === 16` **实测**证实）。
        **变异 4 是双向证明 —— 本程目前最强的一次 finding 实证**：
          · **修复前**（56634c7 状态）同一变异 → **23/23 全绿、exit=0**，即 finding 说的「零鉴别力」当场成立；
          · **修复后** → 恰好那四条红（`episode_pad_digits 透传 得到 3 期望 2`、
            `season_pad_digits 透传 得到 2 期望 3`、`generate_nfo 透传 得到 false 期望 true`、
            `nfo_overwrite 透传 得到 true 期望 false`），其余 19 条全绿、exit=1；scrape-gate 同轮仍绿；
          · 两次还原 sha256 逐字节一致（前 `8047f00b…61818`、后 `fa5edf57…62acd`）；
          · 它另在当前提交态复验变异 1–3，仍各恰好红一条、还原哈希一致。
        **这条双向证据值得单独记**：它把 finding 从「审查者读代码推出的论断」变成了
        「同一变异在修复前后各跑一次的实测对照」—— 本项目的 ledger 里出现过多次
        「声称有鉴别力但无人实测」的情形，这次不是。
Task 1: fix round 1/5 re-review dispatched（range 56634c7..4187175，2 commits —— 其中 b407ec8 是
        **controller 的计划修订**（docs-only，即 finding 1 的裁定产物），已向再审查者说明；model sonnet）。
        给它的一条具名疑点：从改后的 fixture 与期望值**推出**互换变异确实会四条全红，而不只是采信报告。
Task 1: fix round 1/5 re-review — 2 条 findings **全部 ADDRESSED**，无新 Critical/Important。
        **再审查者没采信报告**：它在 `/tmp/mut` 的 scratch 副本上独立重跑了互换变异，复现出
        恰好 **4 FAIL / 19 PASS**（四条失败值与报告逐字一致），并从 diff 里的旧 fixture 值
        （`seasonPadDigits: 2` + 期望 `2`）确认了**修复前的方向**成立 —— 即 finding 的前提被独立复现，
        而不是只由实施者自证。它另核了：断言总数 23（与「其余 19 条」算术自洽）、
        fixture 改动的影响面（那两个值只被各自的两条断言读到，不会静默改动别的断言）、
        以及报告里被 `…` 省略的前 10 行输出（它自己跑出来补全，无出入）。
        仓库未被触碰（`git status --porcelain` 空、HEAD 仍是 4187175）。
Task 1: fix round 1/5 (2 addressed, 0 open; commits 56634c7..4187175)
Task 1: **complete** (commits b940340..4187175, review clean after 1 fix round)
        本任务净结果：2 个纯函数模块 + 2 个断言脚本；**4 条变异全部有双向实测证据**；
        一次任务审查抓到我自己写的两对零鉴别力断言（R4）—— 本项目 ledger 里同一形态的第 N 次命中。

## 任务 2

Task 2: BASE = 4187175（T1 的收尾提交）。派发里显式交办了六条**我方核出的陷阱**（全部 load-bearing）：
        ① 两个调用点必须传 `scraped: scraped.value` 而**非字面量** —— 硬编码 `true` 会让扫描照旧查 TMDB
           （本改动要消灭的正是这个症状），而 grep **抓不到**它（R6 的清扫结论）；
        ② `tmdbPendingScrape` 的 import **必须别名**（否则 computed 遮蔽，调用时拿到 ref → 运行期报错）；
        ③ preview 调用**不得**传 `conflictStrategy`（RenamePreviewRequest 无此字段）；
        ④ `file_ids` 与 `overrides` 来自不同行集合，**不要统一**（首次预览时 previewRows 为空，
           统一会让首次预览发出空 file_ids、预览整体失效）；
        ⑤ `buildPreview` 里既有的 `overrides` 收集循环**保留原地**（同一份映射还供行重建复用）；
        ⑥ **R48 盲区**：`check-sfc-compile.mjs` 只读 `.vue`，rollup 对 `.js` 里漏 import **零警告**，
           故必须靠**阅读**核对 import，不依赖那两个检查。
        另要求它在报告里**显式列出「什么没有被验证」**（store 无法被 node 加载，本任务无自动化行为判据）——
        与其让它暗示不存在的覆盖，不如把缺口写在明面上。

Task 2: implementer DONE (commit 656e06b；仅 `workspace.js`，+116/−34)。报告要点（未独立核实，交审查者）：
        两脚本 + sfc-compile + build 全绿；Step 10 计数为 **4** 而非 3 —— 第 4 处是 Step 4 代码里
        那句注释「见 buildRenamePayload」（brief 已预见并指定「以行位置为准，别去凑数字」，它照办了）。
        **它超出 brief 做到了运行时验证**：仓库外一次性探针 `/tmp/ws-probe.mjs`（`package.json` 是
        `"type": "module"`，故用 pinia + 给 `api/request.js` 的 axios 单例挂 adapter 截获载荷 +
        一个补 `.js` 的 loader 真加载了 store），**44 条断言全过**，覆盖：扫描后预览
        `tmdb_enabled===false` 且无 Key/语言/重选表、`scrapeTitles` 后三者都在、TMDB 关闭时
        `scrapeTitles` 不置位且零请求、重扫/clearAll 重置、`pickShow` 置位并下发重选表、
        干跑带 `conflict_strategy`、`nfo_blocked_by_scrape` 两种情况、**每源一份**（切 openlist → false，
        切回 local → true）。探针在 /tmp、不提交、未新建仓库测试设施。
        唯一超出 brief 字面的改动：删掉 `buildPreview` 里因内联 `fileIds` 而变成死代码的 `const ids`。
        它自报未验证：UI 层（T3/T4 范围）、真实后端契约（假 adapter）、node 版 vue/pinia 与浏览器的差异。

Ruling R7: **接受该运行时探针为本任务的证据，但不把它提升为仓库脚本（本期）。**
  理由：①它是**真实证据**（真加载 store，非重实现），且恰好把我判定为「无法自动验证」的三点
  （每源一份、pickShow 置位、扫描不出网）做成了行为级断言 —— 这是本程最实质的一次覆盖改善；
  ②但它不可重跑（探针在 `/tmp`，与四期重构那期 ledger 记过的「§15 验证不可重跑」是同一形态）；
  ③提升为常驻脚本需要 loader hack + axios adapter 桩，已越过「不新建前端测试设施」这条 Global Constraint
  的边界，属**范围决定**，不该由实施者或我在执行中单方做出。
  **裁定：记为证据 + 把「是否提升为 `scripts/check-workspace-gating.mjs`」交最终审查分诊。**
  **顺带更正一条既有认知**：ledger R44 说「断言脚本加载不了它 [vue/pinia + 无扩展名导入]」——
  实施者证明这个前提**部分可证伪**（补 `.js` 的 loader 就能加载）。R44 的结论（不新建测试设施）
  仍成立，但它的**理由**需要修正，最终审查可据此重估。
  **代价若判错**：若最终审查判「该提升」而我没提升，则本改动的核心行为长期只有一次性证据 ——
  将来有人把 `scraped.value` 改成字面量，grep 与三个既有检查全绿，只有人工走查能发现。
Task 2: task review dispatched（range 4187175..656e06b，1 commit，18947 bytes；model sonnet）。
        派发里给了四条**具名风险各一次聚焦核查**：①探针是否真加载仓库的 store（而非重实现）
        —— 它在 `/tmp/ws-probe.mjs`（7635 字节，仍在），要求判定其主张并说明「未来读者能/不能重跑什么」；
        ②被删的 `const ids` 是否留下悬空引用（那是运行期 ReferenceError）；③两个调用点是否传
        `scraped.value` 而非字面量；④import 别名是否在。
Task 2: task review — **Spec ✅、Task quality Approved、无 Critical、无 Important**，6 条 Minor。
        审查者逐条对着**已提交的文件**核了 brief 的 11 步（两个调用点 `:382`/`:530` 都传 `scraped.value`、
        别名在 `:25` 且 `:117` 的 computed 确实遮蔽模块绑定、preview 无 `conflictStrategy`（`:368-385`）、
        两个行集合仍分开（`:370` vs `:364-367`）、`overrides` 循环保留（`:354-367` 且被 `:415` 复用）、
        生命周期五处位置正确、`:715` 的导出**只增不减**）。
        **它做了两件超出要求的事**：①**重跑了那个探针**（`node --import /tmp/reg-loader.mjs /tmp/ws-probe.mjs`
        → **47 PASS，exit 0**，且 `git status` 仍干净 —— 跑它不改动任何东西）；②**对探针本身做了变异验证**
        （在 `/tmp/discrim` 的一次性副本上，仓库未触碰）：把两个调用点改成字面量 `scraped: true` → **10 条红**；
        去掉别名 → **ReferenceError / 0 PASS**；`fileIds` 改取 `previewRows` → **1 条红**（`file_ids === []`）；
        去掉 `doScan` 的重置 → **2 条红**。
        **结论：我判定为「无法自动验证」的三点（每源一份、pickShow 置位、扫描不出网）现在有经变异验证的
        行为级证据** —— 比 brief 要求的多。它另核了 `const ids` 删除无悬空引用（通读 `:347-427`，
        仅剩 `executeAction` 自己那个 `:514`/`:518`），并 grep 确认 store 里再无旧的载荷字面量
        （只剩 `:565,570` 两行注释）。

Ruling R8: **Minor 3 与 4 是「窄但可达的错误诊断」，裁定 defer 到最终审查分诊 —— 并纠正审查者的一处前提错误。**
  审查者把 Minor 3 判为「theoretical，因为 executing 遮罩挡住了刮削按钮」。**这个前提对干跑不成立**：
  `executeAction` 里是 `executing.value = !dryRun`，而 HomeView 的遮罩是
  `<ExecutingOverlay v-if="!ws.executeDryRun" ...>` —— **干跑时遮罩根本不渲染**，
  而 Task 3 要加的刮削按钮的禁用条件只有 `!files.length || scanning`，**不含 executing**。
  故「干跑在途时点刮削标题」这条路径是**可达**的：`scraped` 会在响应返回前翻成 true，
  于是 `:538-546` 在 await **之后**读 `nfoNeedsScrape.value` 会记下错的值，
  结果对话框因此**少一条**「本次未刮削」提示。
  Minor 4 同族且更直白：`scrapeTitles` 在 await **之前**就置 `scraped = true`，
  故 401 失败后 TMDB 列会从「未刮削」变成「未启用」——**把「Key 无效」说成「去设置页打开开关」**，
  正是本设计要消灭的那类错误诊断（用户能从 toast 看到真实原因，故后果有界）。
  **裁定：两条都 defer 到最终审查分诊**，理由：①规程明确「Minor findings never enter the loop」，
  而两者都不阻塞任何下游任务；②后果有界（少一条提示 / 一条列文案，均无数据风险、无错误动作）；
  ③修法各约 2 行（把表达式移到 await 前 / 失败时回退标志），而单开一轮修复 = 2 次派发，
  与收益不成比例；④最终审查之后**本就有一次**修复波，把两条折进去是零边际成本。
  **已把纠正后的可达性分析写进本行**，以免最终审查继承审查者那个错误前提而误判为不可达。
  **代价若判错**：若最终审查也判 defer，则这两条窄路径的误诊断长期留存 —— 它们的症状是
  「提示少一条」与「列文案指向错的开关」，用户仍能从 toast 得到真实原因。

Task 2: minors deferred（交最终审查分诊）：
  M1 报告里断言数写 44，实为 47（42 个 `check(` 调用点，其中一个在循环里跑 6 次）—— 报告层数字不准，
     实质不受影响。
  M2 **提交信息里写着「源码级接线检查计数为 3」，而实测是 4**（第 4 处是 `scrapeTitles` 注释里提到
     那个名字）。报告 `:56` 解释正确，但 brief 模板那行被原样抄进了**永久记录**。**裁定：不改写历史**
     （`--amend` 会作废审查锚点、且属破坏性操作），记此并在最终交付时告知用户 ——
     它正是本项目「夸大的证据描述会侵蚀信任」那条的又一例。
  M3 见 R8（可达，defer）。
  M4 见 R8（可达，defer）。
  M5 `doOpenListScan` 的重置（`:275`）**无任何运行验证**（探针只驱动 `doScan`）—— 与 `doScan` 逐字相同
     属阅读结论；报告列「未验证」时没点出这一处。**注意走查第 4 项不覆盖它**（那项测切源，不测云盘扫描）。
  M6 探针距不可复现只差一次 `/tmp` 清理（依赖 `/tmp/ext-loader.mjs` 577B 与 `/tmp/reg-loader.mjs` 88B）
     —— 即 R7 的同一件事，此处补上具体依赖文件。

Task 2: **complete** (commits 4187175..656e06b, review clean)
        本任务净结果：`scraped` 每源一份 + 五处生命周期 + 载荷改用纯函数 + `lastResult` 记标志；
        **核心行为有经变异验证的运行时证据**（探针，见 R7 的代价说明）。

## 任务 3

Task 3: BASE = 656e06b。派发里要带的交办：
        ① **R6 的注意力点**：两个谓词的区别是 load-bearing —— 必须用 `props.tmdbPendingScrape` /
           `props.nfoNeedsScrape`，**不是** `!props.scraped`；两者只在「设置页关着」时结果不同，
           而 Step 6 的 grep 区分不出来（走查第 2 项才是它的判据）。
        ② NFO 列的分支次序：字幕 → 批次级成因（未刮削 / disabled / 云盘不支持）→ 本行的「本集无 NFO」。
        ③ `disabled: '未启用'` 这条**必须保留**（设置页关着时它是正确的、且可行动的成因）。
        ④ 不要为了「整洁」把 `defineProps` 上移 —— 计划解释了为何不必（函数只在渲染期调用）。
        ⑤ `HomeView.vue` 稍后会被 Task 4 再改一次（不同段落），属计划安排，不是冲突。
        ⑥ 只提交 `FileTable.vue` 与 `HomeView.vue`；dist 不进本任务。

Task 3: implementer DONE_WITH_CONCERNS (commit 48bf0af；2 文件 +31/−0)。报告要点（未独立核实，交审查者）：
        SFC 编译两文件 OK、`npm run build` ✓；Step 6 greps：`'未刮削'` 恰好 2 行（TMDB 列 `:315`、
        NFO 列 `:384`），`disabled: '未启用'` 两处仍在（`TMDB_LABELS:305`、`NFO_SCOPE_HINTS:331`）。
        **它自报三件事**：
        ① `frontend/dist/` 因被要求的 `npm run build` 而变脏 —— brief 禁止它进提交，故它只暂存了两个源文件
           （与前三个任务的提交一致），把 dist 留给我处置。**这是预期内的**：dist 由 Task 5 统一提交（R45 的项目惯例）。
        ② **它自己补了两条 grep 做不到的只读交叉核查**（正是 R6 那个注意力点）：
           `FileTable` 与 `HomeView` 之间 prop 名与 emit 名的**三向 diff 双向为空**，
           且 `!props.scraped` / `!scraped` 在 `FileTable.vue` 里**零命中**（即谓词按 brief 原样使用）。
           它还回后端核了 `renamer.py:88-92`（未刮削时每一行都得到 `disabled`），
           确认新的「未刮削」标签**不会掩盖**真实的 `matched` / `unavailable` 状态。
        ③ 未验证：四种状态组合的实际渲染文案与色调、按钮位置/点击/loading —— 需浏览器，它没跑。

Ruling R9: **计划里四处 `npm run build 2>&1 | tail -5; echo "build=$?"` 是「永远不会失败的检查」，修正。**
  Task 3 的实施者报告它重测了 npm 的真实退出码，而不是采信 brief 那一行 —— 并指出管道让 `$?` 取的是
  **`tail`** 的状态。**我实测确认**：`false | tail -1; echo $?` → `0`；`false > /tmp/x.log 2>&1; echo $?` → `1`。
  即那四处检查在 npm 失败时**照样报 `build=0`**。
  **裁定：改计划（四处全改）+ 升格为 Global Constraints 的一条**（附理由与出处，因为照抄计划的人会重复它）。
  改成 `npm run build > /tmp/build.log 2>&1; echo "build=$?"; tail -3 /tmp/build.log`（提交 5ce413d）。
  **代价若判错**：无 —— 新写法在成功与失败两种情形下都已实测。
  **形态记此**：这与 R4 是**同一族的第二次** —— **一条不可能变红的检查**，一次在断言层、一次在 shell 层；
  而两次都是**实施者实测发现的**，不是我，也不是审查者。这说明「计划作者自查」在本项目里
  确实是最弱的一道网（与记忆 plan-test-discrimination 的记录一致）。

Task 3: task review dispatched（range 656e06b..48bf0af，1 commit，8318 bytes；model sonnet）。
        派发里给了五条具名风险各一次聚焦核查：①谓词是否按 brief 用（R6 那个区分，grep 区分不出）；
        ②NFO 列分支次序（字幕 → 批次级 → 本行的「本集无 NFO」）；③`disabled: '未启用'` 是否两条表都还在；
        ④`FileTable` 与 `HomeView` 之间 prop/emit 的一致性（实施者自称三向 diff 双向为空，要求独立复核）；
        ⑤`defineProps` 是否被上移、diff 是否外科式。
Task 3: task review — **Spec ✅、Task quality Approved、无 Critical、无 Important**，3 条 Minor。
        五条具名风险全部独立核实：`grep -n "scraped" FileTable.vue` **零命中**（R6 那个区分成立）；
        `:376-378` 字幕分支仍第一、新分支在 `:383-385`（批次级位置）；两条 `disabled: '未启用'` 都在
        （`:305`/`:331`）；**prop/emit 契约双向完整**（`:392-403` 声明 9 个 prop、`HomeView:60-68` 恰好传这 9 个；
        8 个 emit 全有处理器，且 `FileTable` 全仓只有一个实例化点 `HomeView:59`）；
        `defineProps` 在 `:392` 是未改动的上下文。它还核了**覆盖标签的爆炸半径**：
        `tmdbPendingScrape` 为真时每行必然是 `disabled`（因为载荷只发 `{tmdb_enabled: false}`），
        故新标签不会掩盖真实的 `matched` / `unavailable` —— 它用独立证据复现了实施者的论证。
        **它纠正了我 brief 里的一处类比错误**：我写「与文件里既有的 `showsWithShowLevelNfo` / `emptyState`
        同一模式」，而 `showsWithShowLevelNfo`（`:416`）其实在 `defineProps` **之后**，不是同一模式 ——
        安全结论不变（三个都是函数声明、只在渲染期调用），但**理由错了**。记此，理由见 R11。

Ruling R10: **Minor 1（刮削在途时其它动作未门控 → 可造成「预览与执行不一致」）判定比审查者的 Minor 更重，
  但仍 defer 到最终审查分诊 —— 并附我纠正后的可达性分析。**
  审查者说「`scraping` 只门控这一个按钮，刮削期间相邻的 `预览`/`清空` 与底栏的 `执行重命名` 仍可点，
  故可在预览刷新中途发起重命名」，并把它标为 plan-mandated、交跨任务审查。我核过：
  **可达**（`scraping` 不参与任何其它 disabled 条件），且后果正是本仓库的旗舰不变式 ——
  「预览显示的名字必须与执行写出的名字一致」：
  刮削期间 `scraped` **已经**是 `true`（在 await 之前置位），于是此刻点执行会用 TMDB 设置重新解析，
  写出的文件名带标题，而屏幕上的预览还是刮削前那张表（无标题）—— 用户看到与得到的不一致。
  **这是一条本改动新引入的竞态**（改动前扫描即刮削，用户在能点执行时预览已经带标题）。
  **裁定：defer，理由三条**：①规程明确「Minor findings never enter the loop」，且审查者已把它
  交跨任务审查；②最终审查是**更强模型 + 全新上下文**的整分支席位，这类跨任务竞态正是它的分诊对象；
  ③最终审查之后**本就有一次**修复波，折进去是零边际成本。修法也小（把 `scraping` 传进 `AppBottomBar`
  并并入执行/干跑的 disabled 条件，约 6 行 / 3 文件）。
  **我在本行显式标注「我认为它重于 Minor」**，以免最终审查继承审查者的等级而低估它。
  **代价若判错**：若最终审查也判 defer，则用户在一次刮削的几秒窗口内点执行，会得到与预览不一致的
  文件名 —— 可恢复（重命名本身是合理的），但属本仓库有前科的那类故障。

Ruling R11: **计划文本里一处「理由错误」的类比，记录但不改（本期）。**
  我的 brief 用「与 `showsWithShowLevelNfo` / `emptyState` 同一模式」来论证「不必把 `defineProps` 上移」，
  而审查者指出 `showsWithShowLevelNfo` 在 `defineProps` **之后** —— 类比不成立。
  安全结论仍对（三个函数都是 `function` 声明、只在渲染期被模板调用）。**裁定：记此，不改计划**：
  理由是该句只是派发里的论证，不进代码注释、也不进 spec；改它需要再动计划 + 重生成 brief，
  而收益仅是措辞精确。**代价若判错**：将来有人照该类比去推理别的 TDZ 场景时可能推错 ——
  故在此把正确理由写清：**函数声明会被提升，且调用发生在渲染期（`props` 早已初始化），
  这才是安全的原因；与 `showsWithShowLevelNfo` 的位置无关。**

Task 3: minors deferred（交最终审查分诊）：
  M1 见 R10（我判定重于 Minor）。
  M2 TMDB 单元格没有 `title`（NFO 单元格有），「未刮削」只能靠相邻按钮传达动作 —— 纯打磨。
  M3 brief 散文说按钮是「工具条的第三个动作」而 Step 1 的代码把它插在「预览」**之前**（即最左）。
     实现照的是显式代码。**裁定：最左是对的、保留** —— 手动刮削的设计下它是最需要被看见的动作；
     散文措辞含糊是我的问题，不构成实现偏差。

Task 3: **complete** (commits 656e06b..48bf0af, review clean)

## 任务 4

Task 4: BASE = 5ce413d（含我对计划的 build 检查修正）。派发里要带的交办：
        ① `ResultDialog` **读** `props.result?.nfo_blocked_by_scrape`（由 `executeAction` 在执行时算好记在结果上），
           **不得**在对话框里重算 —— 对话框打开时 `scraped` 可能已经变了。
        ② `TemplateConfig` 的新提示门控为 `nfoNeedsScrape && source !== 'openlist'`，保留云盘排除
           （与相邻那条提示一致）。
        ③ 本轮只动 `HomeView.vue` 的 `<TemplateConfig>` 区域，**不要碰** `<FileTable>` 区域（Task 3 的成果）。
        ④ 提示用 warn 色而非次要文字色（它是「你现在这样做会得到零产出」的警告，不是背景说明）。
        ⑤ brief 里 `npm run build` 的验证命令**已修**（原写法 `| tail -5; echo $?` 取的是 tail 的码、永远为 0，见 R9）——
           照新写法跑。
        ⑥ 只提交 `TemplateConfig.vue` / `ResultDialog.vue` / `HomeView.vue`；dist 不进本任务。

Task 4: implementer DONE (commit 9152f7d；3 文件 +22/−0)。报告要点（未独立核实，交审查者）：
        `check-sfc-compile` `sfc=0`；`npm run build > /tmp/build.log 2>&1` → **`build=0`（真实退出码，
        用的是 R9 修正后的写法）**、`✓ built in 2.10s`；Step 6 greps 位置正确。
        brief 五步逐字落地；`ResultDialog` 读 `props.result?.nfo_blocked_by_scrape` 而不重算
        （它另核了上游：`workspace.js:545` 写、`HomeView.vue:102` 传 `ws.lastResult`）；
        云盘排除保留；diff 外科式（`<FileTable>` 区域与 ResultDialog 既有逻辑/注释都没动）。
        一处**良性 grep 偏差**：brief 预测 `ResultDialog.vue` 里 2 行，实际 3 行 ——
        插值单独占一行（82 `v-if`、83 `{{ }}`、206 computed 读取），与 brief 自己的代码片段同形，
        也与相邻的 `hint` 块同形。属 brief 的计数不准，非实现问题。
        三条自报顾虑：①机械验证只证接线不证渲染（走查 2/3 覆盖）；
        ②**`text-warn` 是否在主题里未验证 —— 未知工具类不会让构建失败，故 `build=0` 不证明颜色**；
        ③`nfoStats` 在三个数组都空时返回 `null`（整块含提示一起隐藏）—— 既有结构、未改动，
        若走查发现提示没出现，先查 `nfo_skipped` 是否为空，而不是先怀疑接线。

Task 4: 顾虑 2 **由我当场核实并排除**（这是「不可能失败的检查」的又一形态 —— 类名拼错时构建静默通过）：
        `src/style.css:41` 有 `--color-warn: #8A5F00`，且产物 CSS 里确有
        `.text-warn{color:var(--color-warn)}`（`dist/assets/index-CjvCW2Ms.css`）。
        故该工具类真实存在、颜色会生效 —— 已把这条事实写进审查派发，免得审查者重复查。

Task 4: task review dispatched（range 5ce413d..9152f7d，1 commit，7191 bytes；model sonnet）。
        派发里给了四条具名风险各一次聚焦核查：①对话框是否**读**记录值而非重算；
        ②**提示是否真会出现** —— `nfoStats` 在三数组全空时返回 `null` 会连带隐藏提示，
        要求它从代码推出「标志为真 ⇒ `nfo_skipped` 非空」是否成立（否则提示会被静默吞掉）；
        ③`<FileTable>` 区域未动、diff 外科式；④左栏提示的云盘排除在。
        另告知它 `text-warn` 已由我核实存在，无需重复。
Task 4: task review — **Spec ✅、Task quality Approved、无 Critical、无 Important**，3 条 Minor。
        四条具名风险全部独立核实：①`:206` 是直接读 `props.result?.nfo_blocked_by_scrape`，
        且 `ResultDialog.vue` **不 import `scrapeGate`**（故不可能重算谓词），
        标志确实在执行时写入（`workspace.js:545`，与 `dry_run:540` 同一对象字面量、同一套理由注释）；
        ②它**把风险 2 推完了**：`nfo_blocked_by_scrape` 为真 ⇒ 载荷只发 `{tmdb_enabled: false}`
        ⇒ 每个非字幕条目产出 `content=None` 决策 ⇒ 两条路径（干跑 `local_renamer.py:484-485`、
        真写 `nfo_writer.py:345-347`）都变成 skip pair ⇒ **`nfo_skipped` 必非空**，
        故提示不会被 `ResultDialog.vue:183` 的早退吞掉 —— **除非批次里一个非字幕文件都没有**
        （那时整块 NFO 区本来就不显示）。它还**收窄了实施者自报的吞没条件**
        （实施者说「某些无写入无跳过的运行」，实际只可能是「批次无非字幕条目」）；
        ③diff 外科式（三个文件零删除；`HomeView` 的 `<FileTable>` 块未动 ——
        它注意到 `:68` 那个 `:nfo-needs-scrape` 是 Task 3 的既有 prop，不在本 diff 里）；
        ④云盘排除在 `:57`，与 `:51` 的相邻提示同形。
        它另核实了一条实施者自报未验证的点：提示里说的「文件列表上方」确有其物
        （`FileTable.vue:19` 的按钮在 `:3` 的工具栏里）。
        Minor 2 是**报告里的理由错误**（说两条对话框段落可能同时出现，实际互斥）—— 非代码缺陷。

Ruling R12: **Task 5 的「证明后端零改动」范围取错提交，修正（计划第三个「检查查错了东西」的缺陷）。**
  计划原文是 `git log --format=%H -1 -- <plan 文件>`，注释自称「本计划的起点」，但 `-1` 取的是
  **最后**一次改动该文件的提交（= `5ce413d`，晚于 Task 1–3）。于是 `git diff --stat $BASE..HEAD -- backend/`
  只看得到最后一个任务的范围 —— **前面几个任务若动过 backend 它报不出来**。
  **我实测对照**：错的范围与对的范围本次都输出 0 行（确实没动 backend），
  所以它是**侥幸通过**，不是通过 —— 若 Task 1–3 里真动过 backend，这条检查会给出假阴性。
  **裁定：改为 `--diff-filter=A`（首次加入该文件的提交），并在注释里写明为何不能用 `-1`**（提交见下）。
  顺带把 Step 3 的两条产物 grep 从 `dist/assets/HomeView-*.js` 放宽到 `dist/assets/*.js` ——
  `renamePayload.js` 未必并进 HomeView 那个 chunk，钉死 chunk 名会让检查因打包布局**假失败**。
  **代价若判错**：无（修正后的范围本次仍为空，且 `--diff-filter=A` 的语义就是「首次加入」）。
  **形态记此**：本计划里「不可能失败的检查 / 查错东西的检查」已出现**三次**
  （R4 同值 fixture、R9 `$?` 取 tail 的码、本条取错提交），**三次都是我写的**，
  两次由实施者发现、本条由我在准备派发时发现。这与记忆 plan-test-discrimination 的记录一致。

Ruling R13: **Task 4 的 Minor 3（两条提示文案不一致）裁定为「有意的差异」，保留。**
  审查者注意到左栏提示结尾是「点…『刮削标题』后才会写出」，而对话框那条多一句「后重新执行即可」，
  并说「两条是一起写的，差异看起来像无意的」。**裁定：差异是对的，不改。** 理由：
  两条出现的**时机不同** —— 左栏那条在**执行前**（它就在 NFO 勾选框下方，用户还没执行），
  那时说「刮削后才会写出」已经完整；对话框那条在**执行后**，用户已经执行过一次，
  所以必须补「重新执行」这一步，否则用户刮削完不知道还要再点一次执行。
  **代价若判错**：若最终审查认为该统一措辞，改动是一行文案 —— 但统一反而会让其中一条在它的语境里说不全。

Task 4: minors deferred（交最终审查分诊）：
  M1 对话框提示可被 `ResultDialog.vue:183` 的既有早退吞掉 —— 审查者已证明**只在批次无非字幕条目时**
     可达，而那时整块 NFO 区本来就不显示；属既有结构、非本轮引入。
  M2 报告里的理由错误（见上，非代码缺陷）。
  M3 见 R13（裁定保留）。

Task 4: **complete** (commits 5ce413d..9152f7d, review clean)

## 任务 5

Task 5: BASE = a29fc3f（含 R9/R12 两次计划修正）。这是收尾任务：证明后端零改动、跑齐四个前端判据、
        构建 + 产物 grep、提交 dist、交付 deferred-to-human 走查清单、与 spec 对表、写报告。
        派发里要带的交办：①**走查清单必须原样交付**（它是 deferred-to-human，实施者**不能**声称跑过）；
        ②只 `git add frontend/dist`（**不要** `-A`）；③用 R9 修正后的 build 写法；
        ④它**不得修改任何源文件** —— 若发现源码有问题，报告而不是改。

Task 5: implementer DONE_WITH_CONCERNS (commit 996729c；**只**改 `frontend/dist/**`，7 个路径，
        源码零改动)。报告要点（未独立核实，交审查者）：
        **BASE 取对了** —— 它打印出 `b940340` 并**核实了那是「加入该文件」的提交、且是 HEAD 的祖先**；
        更进一步，它**验证了这条命令在别的路径上是非空心的**（即证明了该检查能失败）——
        这正是在补 R12 那个「侥幸通过」的洞。
        结果：backend diff 为空、后端 **214 passed**；四个前端判据全 exit=0；真实 `build=0`；
        产物 grep **两个分支都在**（`tmdb_enabled:!1` 与 `tmdb_enabled:f.enabled`）；
        spec §17.2–§17.9 与 §14 **逐条对到 file:line，未发现不符**；
        它还**在 `/tmp` 副本上重做了 §17.7 要求的三条变异**（反转 / 省略 / 空串）全部打红
        （exit=1，8/1/3 条 FAIL），仓库源码未被触碰、临时文件已清理。
        **它的自查记录值得单独记**：它承认最初有两处 PASS 计数是**目测**写的（48 / 17），
        用 `grep -c` 实测后是 **49 / 23**，并在报告的自查节里更正 —— 这正是本项目反复在修的
        「数字不准」形态，而它自己抓住了。
        四条自报顾虑见下（两条属实/一条不成立，见 R14/R15）。

Ruling R14: **顾虑 2 属实（§17.5 的表漏写云盘排除），修 spec（docs-only）。**
  实施者指出左栏提示多了一个 §17.5 表里没提的 `source !== 'openlist'` 条件。
  我核过：实现是对的（云盘本就不写 NFO，那条提示在那里是噪音，且与相邻那条 NFO 说明同形），
  **是 spec 表漏写**。**裁定：补进 §17.5 的表**（一行，附理由）。它**没有**自行改 spec，是对的。
  **代价若判错**：无（纯文档补全，与实现一致）。

Ruling R15: **顾虑 4 不成立 —— 它误读了 spec。**
  它说「`clearAll` 也重置 `scraped`，而 spec 只列了两个扫描动作」。**实测**：§17.3 第二行原文是
  「初始 `false`；`doScan` / `doOpenListScan` / `clearAll` **重置当前源那一份**」——
  `clearAll` **在**清单里。它大概看的是 §14 那条「每次扫描重置刮削状态」（那条只谈扫描，因为它的
  主题是「为什么重扫要重刮」）。
  **裁定：不改 spec、不改代码。** 记此以免最终审查把这条当成真缺口去「补」。
  **代价若判错**：若 §14 那条措辞确实容易让人误以为只有两个重置点，可在 §14 加一句指引 ——
  但 §17.3 是权威且已完整，故本期不动。

Task 5: 顾虑 1（六项走查**全部未执行**、按指示原样交付，未声称跑过）与顾虑 3（NFO 列的「未刮削」
        只在 `row.nfo === null` 时渲染 —— 依赖后端「未刮削时每行 nfo 必为 null」这条跨端隐式前提，
        实施者已核到 `renamer.py`，但**前端没有任何判据能在该前提变化时报警**）→ 均记入最终审查分诊。

Task 5: task review dispatched（range a29fc3f..996729c；model sonnet）。
Task 5: task review — **Spec ✅、Task quality Approved，五条声明全部 CONFIRMED**，1 条 Important + 4 条 Minor。
        **审查者独立重跑了每一条机械声明**（它没采信报告）：后端 `214 passed` 逐字吻合；
        四个前端脚本 exit=0 且 49/11/23/23 与报告一致（含实施者自我更正后的数字）；
        产物里 **`tmdb_enabled:!1` 与 `tmdb_enabled:f.enabled` 两个分支都在**（同一 chunk）；
        dist 提交 7 个路径**全是** `frontend/dist/**`（无源文件、无 backend、无计划/spec）；
        三条变异在 `/tmp` 副本上复现为 **8/1/3 条 FAIL**；它逐条核了 **约 25 处 file:line 引用，全部准确**；
        走查六项**确认是「交付而非执行」**（有「全部未执行」前言、每条预期都写成「应/不得」、
        附加证据都标了「不替代走查」）。
        **它另加了一条我没要求的硬核检查**：在 `/tmp` 用当前源码**重新构建**（符号链接 `node_modules`），
        与已提交的 dist **逐字节比对 —— 四个 JS chunk 的 sha256 全部相同**，Vite 报告的体积也一致。
        即**产物可证是 HEAD 源码的新鲜构建，不是陈旧的**。它还顺手纠正了自己的一个怀疑
        （Vite 报告的 kB 不是磁盘字节数，它先疑后证伪）。
        **Important #1 = 报告里那条「§17.3 没提 clearAll」的假声明**（且与它自己 Step 6 的表自相矛盾）
        —— 这正是我 R15 已经裁掉的同一条，审查者独立得出同一结论，**R15 得到确认**。
        Minor 2/3/4/5 全是**报告文本**层面的（±1 的计数、被截断的引文、走查项附加了机械证据、
        §17.4 的 apiKey 枚举不穷尽）—— 不进循环，记此。

Ruling R17: **Task 5 的 Important #1 与 R15 是同一件事，裁定：无需动作（报告本身会随工作区删除）。**
  审查者要求「把那条假声明划掉，免得有人凭它的权威去『修』spec 或代码」。
  但那份报告位于 `.superpowers/sdd/<plan>/`，**收尾时按规程整个删除**；而 R15 已经把纠正
  写进了归档的 ledger（那是长期记录）。故本条的处置 = **R15 已覆盖**，不另开修复轮。
  **代价若判错**：若有人在删除前读到那份报告并据其「修」spec，会引入一个不必要的改动 ——
  故我在最终审查的派发里**显式说明 §17.3 已含 `clearAll`**，把这条错误声明的传播路径掐断。

Task 5: **complete** (commits a29fc3f..996729c, review clean)

## 全部任务完成 —— 进入最终整分支审查

Task 1–5 全部 complete（无一条需要第二轮修复；仅 Task 1 有一轮，且那轮修的是**我的计划**）。
累计：**1 轮修复**（T1）、**0 条未解决的 Critical/Important**、**18 条 Minor 已记入分诊清单**。
最终审查：MERGE_BASE = `a3f9bdf`（见 R16），range a3f9bdf..aca5168，15 commits，633949 bytes
（体量大是因为含两笔 dist 提交的压缩产物 diff）。model：opus（最强档）。
派发里点名了两条我判断最重的待分诊项：**R7**（探针是否提升为常驻脚本）与
**R10**（刮削在途时可发起执行 → 预览与执行不一致的新竞态）；并说明 §17.3 已含 `clearAll`（掐断 R17 那条错误声明）。

## 最终整分支审查（opus，range a3f9bdf..aca5168，15 commits）

判 **With fixes**：**3 条 Important + 5 条 Minor + 5 条建议**，并给出了完整的 deferred-minor 分诊。
它独立重跑了：四个前端判据、后端 214 passed、`a3f9bdf..HEAD -- backend/` 为空、
**ledger 里的运行时探针（47 PASS，且跑它不脏工作树）**、自己又写了三个 /tmp 探针，
并**自行复现了 §17.7 的三条变异**（均能鉴别）。

Ruling R18: **最终审查的 3 条 Important 全部判为必修，合成一次修复波（规程：整轮审查后只派一次）。**
  **I1（= R10 确认）**：审查者**运行时复现**了那条竞态 —— 刮削在途时 `scraped` 已为 true 而
  `previewRows[0].new_filename` 仍是刮削前的名字，执行载荷却带 `tmdb_enabled: true` + Key，
  结果不同（「用户看到 Show.S01E01.mkv / 实际写出 Some Show - S01E01 - A Title.mkv」）。
  它确认**这是本改动新引入的**（改动前扫描的 `scanning` 标志 + 空 `previewRows` 关掉了这个窗口）。
  它判 I1 为 Important 而非 Critical 并给了理由（需在数秒窗口内刻意交错、可恢复、用户意图被满足）——
  我同意该分级。**我 R10 里写的「我认为它重于 Minor」得到确认，且它比我说得更硬：有了运行时证据。**
  **I2（乐观置位）**：`workspace.js:590` 在 await **之前**置位，于是**每次刮削期间**两个谓词都变 false
  → TMDB 列显示「未启用」（把用户推去翻一个本来就开着的开关）、左栏的零产出警告消失 ——
  **正是 §17.5 存在的理由被违反**。且持久变体 = R8-M4：401 失败后标志不复位，
  列**一直**说「未启用」，且后续每次自动回刷都继续带着被拒的 Key（审查者实测确认）。
  **I3（第三对零鉴别力断言）**：`check-rename-payload.mjs` 的 fixture 里
  `createSeasonFolder` / `tmdb.enabled` / `generateNfo` **三个布尔全为 true**，
  故 `create_season_folder` / `tmdb_enabled` / `generate_nfo` 三者可互换而 23 条断言全绿
  （审查者实测：把 `create_season_folder: generateNfo` 与 `generate_nfo: createSeasonFolder` 互换
  → **23/23 PASS, exit 0**）。
  **形态记此（本计划第三次）**：R4 的修复只处理了**被点名的那两对**，而 fixture 的注释里
  我自己写着「必须取不同的值」这条规则 —— **规则写下了，却没有穷尽地施加**。
  且更深一层：**布尔只有两个值，三个字段必有重复，故「取不同值」对三个以上布尔根本不成立** ——
  正解是**逐项变动 + 交叉钉住**（审查者给的配方）。这条比 R4 更值得记：
  **一条我写下的规则，可能因为它在数学上不适用于该情形而形同虚设。**

Ruling R19: **接受 R7 的裁决 —— 把运行时探针提升为仓库脚本 `frontend/scripts/check-workspace-gating.mjs`。**
  审查者的论证我核过并同意：①Global Constraint 里被认可的机械判据形式**字面上就是**
  `scripts/check-*.mjs`（约束的括号里枚举的是 vitest / vite test 这类**框架**，不是这个）；②探针是
  **零依赖、约 60 行**的单个文件，形态与既有四个脚本同类；③**没有它，本分支的核心结构性声明就没有
  任何机械判据** —— 「`workspace.js` 传的是 `scraped.value` 而非字面量」「标志每源一份」
  「五个生命周期点在 §17.3 说的位置」「扫描路径不发任何 TMDB 字段」，今天只在**构造器层**
  被 `check-rename-payload.mjs` 覆盖；把 `scraped` 改成全局、或漏掉一处重置，
  **四个既有判据全绿**；④而本该替代它的六项走查**从未执行**。
  它另给出一条**必须带进实现**的陷阱：自定义 axios adapter 对非 2xx 必须**显式 reject** ——
  `validateStatus` 不作用于 adapter 的返回值，直接 resolve `{status: 401}` 会被当成成功
  （它自己为此损失了一轮），**在仓库版里写成那样就会是又一条「永远不会失败的检查」**。
  **代价若判错**：多一个约 60 行的脚本要维护，且 loader hack 可能随 Node 版本漂移 ——
  若它开始假失败，最坏是删掉它并回退到走查。

Ruling R20: **接受建议 2 —— 加聚合 runner（`scripts/check-all.mjs` + `npm run check`）。**
  理由：本计划里我自己写的三个缺陷**全是「检查查错了东西 / 不可能失败 / 根本不会跑」**，
  而 runner 至少保证它们**执行**（审查者原话：两次自查发现的缺陷都是「不可能失败的检查」）。
  代价若判错：一个 15 行的脚本 + 一行 npm script，可随时删。

Ruling R21: **I3 的修法采用审查者给的配方（逐项变动 + 交叉钉住），而非「把三个布尔取成不同值」。**
  理由：**布尔只有两个值，三个字段必有重复**，「取不同值」在该情形下数学上不可能 ——
  必须靠「只动一个输入、断言另两个不受影响」来钉住每个字段的来源。
  **代价若判错**：断言条数增加约 6 条，换来三个布尔各自的来源都被独立钉住。

Ruling R22: **走查六项仍然交用户执行，不因 R19 而取消。**
  理由：探针（R19）覆盖的是 store 层的结构性声明，**渲染层**（按钮位置与 loading、四种状态组合的
  文案与色调、提示是否出现）它一概覆盖不到 —— 那仍是 §17.7 声明的前端既知缺口。
  故最终交付时**照旧附上六项走查清单**，并标明哪些已被探针机械覆盖、哪些仍需人眼。

### 修复波的文档留痕（先于代码）

最终审查后我先改了文档再动代码 —— 否则代码与文档会立刻漂移（本项目反复记的坑）：
- **spec §17.3** 补两条：刮削失败回退置位；在途刮削视为「尚未刮削」（两个谓词把 `scraping` 作为输入）。
- **spec §17.4** 补一条：刮削在途时门控 `预览` / `清空` / `试运行` / `执行重命名`。
- **计划** 追加「修复波修订」节：明确取代了 Task 1 Step 1 的透传断言与 Task 3/4 的按钮禁用条件，
  并附新代码；其中记下 R21 那条关键认识（**「取不同值」对三个以上布尔在数学上不可能**）。
提交 `fc475e6`。

Task: **fix wave dispatched**（BASE = fc475e6；一次性派发 7 项，model sonnet）：
  I1 按钮门控（FileTable 预览/清空、AppBottomBar 试运行/执行、SourceConfigPanel 扫描按钮、
     HomeView 两处传参）· I2(a) 失败回退置位 · I2(b) 两个谓词加 `scraping` + 更新 scrape-gate 断言
  · I3 fixture 与交叉钉住断言 · M1 把 `nfoNeedsScrape.value` 提到 await 之前 · M4 在 `nfoNullHint`
  里写明跨端前提及其后端位置 · R19 提升探针为 `scripts/check-workspace-gating.mjs`（自包含 +
  **adapter 对非 2xx 必须显式 reject** 的陷阱）· R20 `scripts/check-all.mjs` + `npm run check`
  · 重建并提交 dist（源码改了，产物会陈旧 —— 本项目有过的 Critical 1）。
  要求的证明：五个脚本 + aggregator 全 exit=0；真实 build 退出码；**三条变异各打红且逐字节还原**
  （I2a 去掉回退、I2b 去掉 `|| scraping`、I3 互换那三个布尔 —— 并要求它先验证**修复前同一变异是全绿**，
  那是 finding 的证据）；后端 214 passed；backend diff 为空。
  并明确要求它**诚实列出什么没被验证** —— 尤其是 `.vue` 里的禁用条件，本仓库没有任何判据能执行模板。

Task: fix wave report — commit `453318f`（12 个源/脚本/package.json + 重建的 dist）。
        五个 check 全 exit=0（**15 / 26 / 49 / SFC ok / 75 条断言**）+ `check-all` exit=0；
        `npm run build` → **build=0**（用重定向写法取真实退出码）；后端 **214 passed**；
        `-- backend/` diff 为空；重建后 `git status` 为空（**dist 与源码逐字节一致**）。
        **三条变异全部打红、逐字节还原（hash 与基线一致）**：
          ① 删掉失败回退 → 4 红（含静态与运行期 401 用例）；
          ② 删掉 `|| scraping` → scrape-gate 与 workspace-gating 各 1 红；
          ③ 互换 `renamePayload` 那两对字段 → 4 红，**而修复前同一互换是 23/23 PASS exit 0**
             （finding 的原始证据被原样复现 —— 这是本波最有说服力的一条）。
        两处它主动做对的事：`registerHooks` 在缺 API 时 **exit 2 而非静默跳过**；
        `check-all` 名单硬编码、**缺脚本也算失败** —— 两者都在防「检查不执行却报成功」。
        它自报两条顾虑：①**I1 的五个 `:disabled` 与「谓词值 → 屏幕上的字」没有任何自动化证据**
        （模板无常驻判据；且 prop 默认 `false`，漏传会**静默退化成改动前行为**）；
        ② M1 的触发路径（干跑在途时重选）**没有写成断言**，只有代码审阅级证据。

Task: fix wave scoped re-review dispatched（range aca5168..453318f，2 commits —— 其中 `fc475e6`
        是 controller 的 docs-only 提交，已向再审查者说明；model sonnet）。
        五条具名风险各一次聚焦核查，其中三条专治「新写的检查本身不可能失败」：
        ①新脚本的 axios adapter 是否**真的 reject** 非 2xx（否则 401 用例是假绿）；
        ②`check-all` 是否**真的传播失败**、缺成员是否算失败；③`registerHooks` 缺 API 时是否响亮退出；
        另两条：④I3 的交叉钉住是否**真的能红**（而不是又添了一组非鉴别性断言）；
        ⑤I2(b) 的谓词在两个调用点是否一致、设置页关着时是否仍返回 false。
Task: fix wave scoped re-review — **8/8 全部 ADDRESSED，无新 Critical/Important**。2 条新 Minor + 2 条 out-of-scope。
        八项逐条给了 file:line 证据，且它**自己加跑了**：`node scripts/check-all.mjs`（exit 0、165 PASS）
        —— 它跑的理由值得记：报告里的 sha256 表与 HEAD 对不上（见下），所以报告里那些「通过」的跑
        未必覆盖已提交的字节；实测覆盖了。它另核了两处 I1 的边界：`AppButton` 的
        `:disabled="disabled || loading"` 让 loading 中的刮削按钮无法双击（否则会重开 I2(a) 的失败模式）；
        `ConfirmDialog` 是全屏模态，故「刮削前打开的确认框」不可能在刮削开始后被确认。
        I3 那项它**穷举了三种两两互换**，并逐一给出会红的断言 —— 即新断言真的能鉴别，而不是又添了一组摆设。

Ruling R23: **两条新 Minor 裁定：park（无第二次修复波），并在交付时显式告知用户。**
  **M-a（新的破坏面，Minor）**：`workspace.js:607` 的 `scraped.value = previous` 写的是
  **请求落定时处于活动状态的那个源**（`scraped` 是可写 computed，setter 指向 `activeSource`）。
  故「在 local 上刮削 → 途中切到从未刮削的 openlist → 请求失败」会让 **openlist 被标成已刮削**，
  之后在 openlist 执行会带 `tmdb_enabled: true` + Key —— 与 I1 同一伤害类，走的是新路径。
  审查者判 Minor 的理由我接受：触发需「切源 + 刮削失败」同时发生，**且同一个在途窗口本来就会**
  通过既有的、未加门控的 `buildPreview`（`workspace.js:372-421`）把 `previewRows` 写错源 ——
  即那是既有的异步/切源交互形态，本波只是给它添了一条新路径。
  **裁定：park。** 修法是 2 行（在 `scrapeTitles` 里捕获 `activeSource` 并写回 `sourceStates[src].scraped`）。
  **代价若判错**：该窄路径下执行会写出用户没见过的文件名 —— 用户可从本条与交付清单得知并索要那 2 行修复。
  **M-b（证据链，Minor）**：修复波报告的变异 1 基线 `workspace.js` sha256（`9f75b797…`）
  **不匹配任何已提交版本**（审查者把 20 个触及该文件的提交全哈希了一遍），故「逐字节还原」这一步
  **对已提交文件不可核**。审查者同时确认：该变异**结构上仍被抓**（静态断言 grep `scraped.value = previous`），
  `git status` 干净、diff 的三个 hunk 与磁盘逐行一致。**裁定：park（代码无问题，属报告的证据链瑕疵）。**
  **代价若判错**：无（变异 2 与 3 的基线都对得上，只有这一条的还原声明不可核）。
  **形态记此**：这是本计划里**第四次**「报告/提交里的一句话强于它实际证明的」（前三次：T1 的 44 vs 47、
  T2 的「计数为 3」、T5 的 ±1 计数）—— 四次都出在**证据描述**上，而非代码上。
  这正是本项目 ledger 反复记的「零鉴别力」在**元层**的镜像：代码是对的，但关于代码的声明不可核。

Ruling R24: **两条 out-of-scope 观察同样 park，其中一条是 I1 修复的一个已知缺口。**
  **O-a**：空态那个「开始扫描」按钮（`FileTable.vue:446` → `quick-scan` → `ws.doScan`）是
  **第二个未加门控的扫描入口点** —— 正是 I1 的修复给面板扫描按钮加门控时引用的那条镜像竞态。
  仅在「`previewRows` 为空而文件存在」（如首次预览失败）时可达。**park**：
  它是本波理由的自然后续，但不在八项范围内；**已记入交付清单**。
  **O-b**：`check-workspace-gating.mjs:165` 断言 `scraped: false` 字面量出现次数 `=== 2`，
  将来加第三个源会**因错误的理由**失败。纯观赏性。**park**。

## 计划完成

Task 1–5 全部 complete；最终整分支审查判 With fixes；**唯一一次修复波已应用并再审查通过**
（8/8 ADDRESSED，无新 Critical/Important）。
累计：**2 轮修复**（T1 一轮、修复波一轮）· **0 条未解决的 Critical/Important** ·
**23 条 Minor / 观察已 park 或记入分诊清单**（见上，逐条带裁定与代价）。


Ruling R16: **最终审查的 MERGE_BASE 定为 `a3f9bdf`（本会话开始时的 HEAD），而非 `git merge-base main HEAD`。**
  skill 给的形式是 `MERGE_BASE = git merge-base main HEAD`（例），但 `feat/tmdb-nfo` 这条分支已承载
  **三个阶段**：TMDB 集成（计划 1）、NFO 生成（计划 2）、以及本次的手动刮削。前两个阶段
  **各自做过整分支最终审查**（见 `2026-09-26-tmdb-metadata.md` 的 R57 与
  `2026-09-26-nfo-generation.md` 的 R86，均判 With fixes 并已修复）。照字面取 `merge-base main HEAD`
  会把 95+ 个提交全拉进来，**重复审查两个已审过的阶段**，既浪费又会产出关于既有代码的 finding。
  **本项目自己的惯例是「MERGE_BASE = 上一阶段的收尾提交」**（计划 2 的 ledger 明写
  「MERGE_BASE（用于最终审查）：b442b22 —— 即计划 1 的收尾提交」）。本阶段的「上一阶段收尾提交」
  就是 `a3f9bdf`（上个会话的最后一笔，也是我会话开始时的 HEAD）。
  **取 `a3f9bdf..HEAD`（14 个提交）还有一层好处**：它把**我本会话里未经独立审查的那一处改动**
  （R89 的 `df0ecdb` + 产物 `a40267e`）也纳入了最终审查 —— 那是我自己做的、只过了产物 grep 的一处
  文案单位改动，本该有独立眼睛看一遍。
  **代价若判错**：若最终审查者认为范围该更宽，它会说出「这不在我的 diff 里」——
  那时我再补一次限定范围的审查。反过来若我把 95 个提交全塞进去，审查者的注意力会被两个
  已审阶段摊薄，本阶段的缺陷更可能被漏掉。




