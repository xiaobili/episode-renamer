# SDD execution ledger — 计划 2：NFO 生成

归档自执行期的工作区 ledger（原本在 `.superpowers/sdd/2026-09-26-nfo-generation/progress.md`，
该工作区在收尾时按规程删除）。**这是本计划的裁定记录**：pre-flight 扫描表（含 R60 —— 本计划最大的
风险：它是照着「计划 1 的计划文本」写的，而计划 1 实际经历了 11 轮修复）、实施期裁定、各任务的
修复轮记录、残留项与已知限制，以及每条裁定的理由与「判错会怎样」。

裁定编号 **R60–R88**（R1–R59 属于计划 1，见 `2026-09-26-tmdb-metadata.md`）。
要查「为什么代码是这样」时，从这里找。设计权威在
`docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md`（执行期补入 §9.1.1 与 §9.3 的两处修正）。

---

# SDD ledger — plan: docs/superpowers/plans/2026-09-26-nfo-generation.md

分支：feat/tmdb-nfo（项目惯例：普通分支而非 worktree，见记忆 sdd-workflow）
本计划的 MERGE_BASE（用于最终审查）：b442b22 —— 即计划 1 的收尾提交
Spec：docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md（可达，已读）
计划 1 的执行记录：docs/superpowers/ledgers/2026-09-26-tmdb-metadata.md（R1–R59，**建议派发前必读**）

## Pre-flight 冲突扫描

### 跨任务：共享文件或接口

| 任务对 | 一方产生 | 一方消费 | 结论 |
|---|---|---|---|
| P2T1 → P2T2 | `NfoOptions` / `NfoEntry` / `NfoDecision` 与三个 XML 构建函数 | 路径推导与 `build_nfo_decisions` | 一致 |
| **P2T1 文件被 P2T2、P2T3 依次追加** | T1 建 `nfo_writer.py`（只含 XML 构建） | T2 追加路径与决策；T3 追加写盘 | **有意为之**，每个追加步骤都写明要补的 import。代价：文件最终约 350 行，与 `parser.py`(372) 同量级 —— 可接受 |
| P2T2 → P2T3 | `build_nfo_decisions(entries, options)`、`NfoDecision` | `batch_rename` 与 `write_nfo_files` 消费 | 一致 |
| P2T3 → P2T4 | `batch_rename(..., nfo_options=, nfo_matches=)`、`RenameResult.nfo_path`、`BatchRenameResult.nfo_written/nfo_skipped` | 路由按此调用并断言同名响应字段 | 一致 |
| P2T4 → P2T5 | `nfo_scope` 四值 `disabled`/`unsupported_source`/`episode_only`/`full` | `NFO_SCOPE_HINTS` 的键 | 需逐字一致 |
| P2T4 → P2T5 | 预览响应行新增 `nfo` 字段 | `previewRows` 的 `nfo` / `nfo_scope` | 一致 |
| P2T3 改 `models/api.py` | 计划 1 已加 `tmdb_api_key`/`tmdb_language`/`tmdb_overrides`/`tmdb_enabled`（**4 个**） | P2T3 再加 `generate_nfo`/`nfo_overwrite` | 顺序执行，无冲突。注意计划 2 的 Self-Review 写的是「两个 Request 各加 2 个字段」—— 那是**增量**，不是总数 |
| P2T3 改 `local_renamer.py` | 计划 1 已把内联覆盖逻辑抽成 `apply_override` | P2T3 改 `batch_rename` 签名与函数体 | 顺序执行 |
| P2T4 改 `api/renamer.py` | 计划 1 已把 preview 改成两遍解析、加了 `_tmdb_client_from_request` 薄包装、`_tmdb_summary` 去掉了 `episode_title` | P2T4 改 `_with_tmdb_titles` 返回值与 preview/execute 路由 | **见 R60 —— 这是本计划最大的风险** |
| P2T5 改 `workspace.js` / `FileTable.vue` / `HomeView.vue` | 计划 1 T7 已改过同三个文件 | P2T5 再加 NFO 选项与列 | 顺序执行。两者追加位置已分别写明（T7 在「集」后与「状态」后；P2T5 在「新文件名」前） |

### 单任务：自身一致性

| 任务 | 测试 vs 实现 | 结论 |
|---|---|---|
| P2T1 | 15 个测试（计划已更正） | 自洽 |
| P2T2 | 20 个测试，含顺序契约测试；排序断言已按中文码位核对 | 自洽 |
| P2T3 | 8 个测试；`Path` 已在 `local_renamer` 顶部导入 | 自洽 |
| P2T4 | 6 个测试（5 + 1）；`nfo_scope` 的 `disabled` 分支已修正（R5 of 计划 1） | 自洽 |
| P2T5 | 无自动化测试，靠编译 + 构建 grep | 自洽（前端既知限制） |

## Pre-flight 裁定

Ruling R60: **本计划的最大风险，必须在每个派发里显式交办。**
计划 2 是**照着「计划 1 的计划文本」写的**，而不是照着**计划 1 实际落盘的代码**。而计划 1 经历了
11 轮修复 + 一波整分支修复波（11 项），其计划文本自身都曾被回填三次（R19/R33/R50/6ade6eb）。
计划 2 有**至少三处**是「把某函数体**整体替换**为下面这版」：T3 的 `batch_rename`、T4 的
`preview_rename` 路由、T5 的三个前端文件。若那些代码块与 shop 的代码有任何差异，**整体替换会静默回退
修好的东西** —— 这正是本程反复出现的同一形态（R52/R55/计划 1 Important #4）。
**裁定：在 Task 3/4/5 的每个派发里加一条硬要求** ——
  1. **先读 HEAD 上的实际函数体**，再决定改哪里；
  2. 把计划的代码块当作**意向说明**，把改动**施加到实际代码上**，不要整段粘贴覆盖；
  3. 若发现计划的代码块与 HEAD 的实现有差异（哪怕看似无关），**在报告里逐条列出**，
     由我裁定哪个是权威 —— 不要自行选择。
已核对的一项：`_with_tmdb_titles` 在 HEAD 上仍返回**二元组**（`app/api/renamer.py:69-71`），
故 T4 改成三元组的前提成立。代价若判错：若实施者整段粘贴而计划块陈旧，会静默回退计划 1 修好的东西，
且**没有任何测试会红**（前端尤其：四个检查都发现不了）—— 这是本计划最可能造成真实损失的一条。

Ruling R61: 计划 1 的残留项**折进本计划的派发**（规程明确许可「批量小的同形工作」），不另开修复波：
  交 P2T4（它改 `api/renamer.py`，是最近的落点）：
    (a) `app/api/renamer.py:51-52` 与 `app/models/api.py:47,66` 的注释仍写着 `build_tmdb_client`，
        而真正的单点是 `app/api/tmdb.py:40` 的 `resolve_tmdb_client` —— 三处注释改成对的名字。
    (b) `app/api/tmdb.py:29` 的消息表键 `"rename"` 其实只被 `/search` 的 400 用（`/api/rename/*`
        从不发这些串，它降级）—— 改名 `"search"`。
    (c) `tests/test_rename_routes.py:409` 的注释说「只有本条用例红」，实测去宽捕获红 3 条、
        调用点 re-raise 红 6 条 —— 把描述改成实际情况（**夸大的证据描述会侵蚀信任**，
        这与本程一直在修的「零鉴别力」是同一族问题的镜像）。
    (d) 路由级铁律用例只在 `search_tv` 注入失败 → 给 `_FakeTmdbClient.fail` 与参数化列表
        补 `"detail"`/`"season"`，让 detail/season 步骤也被路由级覆盖。
  交 P2T5（它改 `workspace.js`）：
    (e) `workspace.js` 的 `doScan` 与 `doOpenListScan` 里的 `await buildPreview()` **丢弃了返回值**，
        故扫描后的 TMDB 失败仍静默（计划 1 的 Important #1 是同一缺陷的隔壁调用路径）——
        两处各改成 `refreshPreviewReportingFailure()`（一处一行）。
    (f) `workspace.js` 里那处指向 `build_tmdb_client` 的注释同上改对（与 (a) 同类）。
  理由：这些都是 ≤1 行的改动，落在本就要改的文件里；单开一轮 dispatch + 再审查不划算。
  代价若判错：任务 diff 里混进不属于它主题的小改 —— 已在派发里逐条说明来由，审查者不会误判为范围蔓延。

Ruling R62: 前端四条修复（计划 1 的 1/2/3/6）**无常驻自动化覆盖**，其中 Key 显示切换只有编译级证据、
**渲染行为从未被行使**。本计划 T5 又要改前端，故：
**裁定：把这三条人工步骤列进计划 2 的 deferred-to-human 清单**（设置页显示切换的渲染、预览失败的提示、
扫描后失败的提示），并**不**尝试为前端新建测试设施（本仓库刻意没有，且本计划范围不含）。
代价若判错：前端的这几条分支若被将来的重构弄坏，只有人工走查能发现 —— 这是本项目已知且被接受的缺口。

## 进度

## 任务 1

Task 1: implementer DONE_WITH_CONCERNS (commit 1e10a0e；3 个新文件，297 插入 / 0 删除)
        聚焦 15 passed / 0 warnings；全量 **127 passed**（3 条 warning 仍来自未触碰的既有文件）。
        RED 为预测的 `ModuleNotFoundError: No module named 'app.core.nfo_writer'`。
        **忠实度可检验**：逐字节比对三个文件与 brief 的代码块 —— `nfo.py` 与测试文件**完全相同**，
        `nfo_writer.py` 仅差 brief 明说要延后的三个 import。
        **16 个变异的行动：15 条测试全部至少被一个变异打红 —— 没有孤儿测试。**
        每条变异以 `sha256sum -c` 验证还原、`git diff --exit-code HEAD -- backend` 确认工作树干净。
        **这在计划 1 里从未一次性做到**（我在那边六次写出无鉴别力的检查）。
        注意：本条是**本计划第一个任务就达标**，而计划 1 的第一个任务就需要一轮修复 ——
        与 R30 在派发里预先声明这条要求有直接关系。

Ruling R63: C1（去掉 `_text` 的 `.strip()` 后**全套仍绿**，即「仅含空白的值也省略标签」分支无覆盖）
—— **裁定：现在补测，不走审查轮。** 理由：它不是覆盖面锦上添花，而是**本计划核心设计所依赖的那条
风险的另一半** —— 那条理由是「空标签会被部分刮削器当成『该字段为空』的真值而覆盖已有数据」，
而纯空白只是中间隔了一层空白，机制相同。实施者按 brief 的逐字要求未自行补测是**对的**
（决定权在 controller），故这不是它的失误。代价若判错：无（一条测试）。

Ruling R64: C2（两条 `assert "&amp;" in raw` 与上方 `parse()` 冗余）、C3（`field` 未使用，brief 原文）、
C4（`sorttitle` 有产出无断言）—— 逐条裁定：
  **C2 保持原样**：它们确实无独立鉴别力，但**不制造虚假的覆盖信心**（旁边就是一条真检查 ——
  `parse()` 会在未转义时直接抛），删掉反而丢了「转义是刻意为之」的显式说明。
  这与 R43 那类「无鉴别力且制造虚假信心」的情形不同，故不再一并清理。
  **C3 交最终审查分诊**：仓库无 lint 配置，且是 brief 原文（与计划 1 的 R6 同类）。
  **C4 现在补**：一行，成本为零。
代价若判错：C2 那两行继续占位；无实际风险。

Task 1: fix round 1/5 dispatched（findings: whitespace 分支补测 [R63] / sorttitle 断言 [R64]）
Task 1: fix round 1/5 report — commit 5b25b83（仅测试文件，+18）；**129 passed**（127 + 2）。
        生产代码零改动（哈希 `8be5d796…de4f107` 与 Task 1 提交一致，`git diff --stat HEAD~1 -- backend/app` 为空）。
        两条新测试各被一个变异唯一打红（N1 = 此前让全套 15/15 全绿的那个变异，现被唯一一条断言钉住）。
        它另用 `cat -A` 确认 `status="\t\n"` 落盘为**字面转义序列**而非真实制表/换行 ——
        否则那条测试断言的就不是它以为的东西。这是「让测试真的测它声称的东西」的一个好例子。

Task 1: task review — **规格合规 ✅、Task quality Approved、无 Critical、无 Important**，5 条 Minor。
        审查者用 `difflib` **机械地**核对了忠实度（不信报告）：`models/nfo.py` 与 brief 代码块零差异；
        `nfo_writer.py` 恰好少三行（brief 明说要延后的三个 import）且无其他偏离。
        逐项直执行验证：`_text` 对 `0`/`"0"`/`0.0` 都写出、对 `None`/`""`/`"   "`/`"\t\n"` 都省略。
Task 1: **complete** (commits b442b22..5b25b83, review clean after 1 pre-review fix round)

Ruling R65: 审查者**纠正了实施者的自我评估，且方向是「比实施者自己说的更好」**：
实施者称那两条 `assert "&amp;" in raw` / `"&lt;" in raw` 与上方 `parse()` 冗余、无鉴别力。
审查者复现字符串拼接的破坏后发现，在拼接产物上这两条断言**独立地为 False** —— 它们确实可失败，
只是在第 98 行的 `parse()` 先抛之后不可达。**故 R64 的「保持原样」结论不变，但理由更正**：
它们不是「废话」，而是「真但被前一条遮住」。代价若判错：无。
**教训**：实施者对自己代码的自我评估也可能是错的，且**可能低估自己的产物** ——
审查者不该只找「报告说了什么缺陷」，也该找「报告自称有缺陷但其实没有」的地方。

Ruling R66: 审查者提的跨任务交接 —— `nfo_writer` 的产物声明 `UTF-8` 但返回 `str`，故 Task 2/3 必须以
`encoding="utf-8"` 写盘，否则声明的编码与实际字节不符（中文标题会 mojibake 或抛错）。
**已核对：计划 2 的 T3 写的正是 `target.write_text(decision.content, encoding="utf-8")`，
且其测试 `test_written_content_is_utf8_with_chinese` 已断言中文可读回。故这是 pre-flight 已核实项，
不是新 finding。** 它提的 newline 风险（text 模式把 `\n` 译成 `os.linesep`）对本项目无实际影响 ——
部署是 Linux（Dockerfile 钉 `python:3.12-slim`），且 XML 解析器会规范化行尾。代价若判错：无。

## 任务 2

Task 2: implementer DONE_WITH_CONCERNS (commit 5daa1de；`nfo_writer.py` +140，新建 `test_nfo_plan.py` +283)
        RED 逐字如预期（`ImportError: cannot import name 'build_nfo_decisions'`）→ 简报 20 条 20 passed
        → 补 2 条后 **22 passed**；全量 **151 passed**。变异 23 条，全部按预期打红、逐条还原并 hash 校验
        （`problems: 0`，实现 hash `450b6018…` 恒定）。它另踩到并识别了 stale `.pyc` 陷阱
        （同尺寸 + 同 mtime 秒）—— 与计划 1 的某个实施者踩到的是同一个坑。

Ruling R67: **本程发现密度最高的一次：我的计划里有三处自相矛盾。** 实施者按「顺序契约 + 测试优先」
修正，**全部裁定为正确**：
  (a) `entry()` helper 缺 `show=` 形参，而两条混放用例以 `show=show(...)` 调用 → **`TypeError`**：
      照抄根本跑不起来。加参数、**不改调用点**。代价若判错：无。
  (b) `build_nfo_decisions` 的代码块产出 `tvshow_A, season_A, tvshow_B, season_B`，与计划**自己的顺序契约**
      （「其后是剧集级（tvshow）、再是季级（season）」）及 `test_decisions_are_deterministic`
      （`["episode","episode","tvshow","tvshow","season","season"]`）矛盾。**单剧时两种顺序重合，
      只有多剧才暴露** —— 与计划 1 的 R55 同一形态：我写验收/契约时没按代码推一遍。改为三桶拼接。
  (c) 拒绝文案 `下有多个剧目` **不含**断言要求的子串「多部剧」—— 改为 `下有多部剧混放`，
      与 docstring 及前端文案一致。
**教训**：计划 1 与计划 2 各有一处「照抄跑不起来」（R55 的测不了、R67a 的 TypeError）。
两处都不是笔误级的手滑，而是**我写代码块时没有把它们当代码运行过一遍**。

Ruling R68: 实施者另报告**简报的 20 条测试有 3 个真盲区**（打断实现仍全绿）：
  混放分支改成「每剧一条」或「完全不发 season 决策」原本全绿（`all()` 建立在**可能为空的列表**上）；
  季级决策「真的带了 XML」原本无任何断言。它补了 2 条关闭并做变异复验。
  **裁定：接受这两条补测**（与 R63 同类 —— 那条也是我漏掉的空/空白等价情形）。
  另有 6 处非判别性用例/未覆盖分支在报告 §8 逐条列出，**交任务审查评级后我再裁定**，
  不抢在审查前处理（审查者可能给出与我不同的评级，且这是它的职责）。
  代价若判错：若那 6 处里有真盲区而审查漏判，会流到最终审查 —— 有兜底。

Task 2: task review — **Needs fixes**（1 Important + 3 Minor + §8 六项逐条评级）。
        审查者独立执行验证了：`episode_nfo_path`（含名字带点的情形）、`common_parent`（分季/兄弟/单元素/空）、
        **无前缀兄弟 bug**（`os.path.commonpath(['/media/Show','/media/Show2'])` = `/media`，逐组件而非逐字符）、
        一致性检查确实遍历**全部** entries 而非仅本组、三桶顺序、模块**零文件系统访问**（grep + 读 posixpath 源码）。
        三处偏离它逐条判为**正确**，且第 2 条专门论证「该改代码而非改测试」——
        顺序契约在计划里出现两次措辞相同，加上 brief 自带的测试在断言它，三件产物里那段循环是孤例；
        它另核实了下游不需要交错序（Task 3 按 file_id 建字典、按路径去重）。
        它还把 §8 的第 6 项**锐化**了：区分场景是「部分匹配」（一条有 show/season_data、一条没有），
        现有实现取非 None 者并写出内容（正确），而 `group[0]` 式实现会拒绝，套件无人反应。

Ruling R69: Important 1 —— `test_show_level_files_skipped_without_show_metadata` 的三条 `all(...)`
建立在**可能为空的列表**上，故「`show_data is None` 时不发决策、直接 continue」这个变异让**22 条全绿**。
审查者指出：**这正是实施者已经关过两次的同一类洞**（混放分支、季级内容），第三处活了下来；
而它守的是计划在每集情形明确要求的性质（「也要给出一条带原因的『不写』决策」）的剧集级对应物。
**裁定：补两行基数断言**（`len(...) == 1`），并做变异验证。代价若判错：无。
**形态记此**：`all()` 建立在可能为空的集合上，是**本程最高产的一个假绿灯** —— 它已出现三次，
且每次都由实施者或审查者用变异发现。此后我写断言时会优先写基数/形状断言。

Ruling R70: Minor 2（决策的 `file_id` 归属随输入顺序变化；而 `test_decisions_are_deterministic`
的注释写「逐项一致」却只比较 `.path` —— **注释比断言强**）—— **裁定：两件都做**
（归属改用已排序的 `ordered`；断言加强到同时比较 `file_id` 与 `kind`）。
理由：那条测试的价值就在于「换个顺序结果逐项一致」，只比路径就少了一半；
而「注释比断言强」是本程反复在修的「声明强于事实」的镜像，不该留。代价若判错：无。

Ruling R71: Minor 3（混放守卫只查**同目录**，故 `/m/未分类/A.mkv` + `/m/未分类/B/S01/B.mkv`
这种非对称布局不被拒，仍会把 `tvshow.nfo` 写进混放的树）—— **裁定：扩展守卫到「root 之下任意层级
存在别剧的文件就拒绝」。** 理由三条：(a) **拒绝是安全方向** —— 最坏是古怪布局下少写剧集级 NFO，
且预览的 NFO 列会显示「仅每集 NFO」（**可见，非静默**），另一边是不可逆的媒体库污染；
(b) 推演过不误伤合法布局（多剧各自在 `/media/ShowA/`、`/media/ShowB/` 时互不嵌套；
同剧文件分处 `root/` 与 `root/S01/` 时 show_name 相同，不触发）；
(c) spec 把混放定义为「同目录」是我的措辞不够严，而 harms 相同。
代价若判错：某个我没想到的布局会少写剧集级 NFO —— 但它是可见的（预览列），可纠正。

Task 2: fix round 1/5 dispatched（findings: 空列表真空断言 [R69] / 归属顺序 + 加强断言 [R70] /
        守卫扩到嵌套 [R71] / `season is None` 分支补测 / 部分匹配补测）

Task 2: fix round 1/5 report — commit 2ac74f1（`nfo_writer.py` +25/−9，`test_nfo_plan.py` +130/−9）；
        聚焦 26 passed；全量 **155 passed**。**两轮合并 31 条变异 M1–M31 全部符合预期、problems: 0**，
        每次还原后 hash 与基线一致。
        **它自己发现的两个设计层细节值得记**：
        (a) finding 2 —— **只加强断言而不扩入参仍是空转**：原入参每剧只有 1 个文件，`group[0]` 本就无歧义。
            故它把入参扩到 3 条（给剧A 加同季不同集，使组与季组都不止一条目），断言才真正有鉴别力。
            这是「让测试真的测它声称的东西」的又一层，比单纯加断言难得多。
        (b) 它的守卫用 `root.rstrip(os.sep) + os.sep` 保证**目录分隔符边界**，
            避免「逐字符前缀」陷阱（`/m/未分类/剧` 与 `/m/未分类/剧B`）。

Ruling R72: 实施者在 finding 3 之外**多加了一条反向保险测试**
（`test_sibling_show_directories_are_not_mistaken_for_nesting`），作为「扩守卫不误伤合法布局」的对重；
并**主动报告它自己的第一版是空转的**（写成 `.../剧/S01/` 时 root 就是 S01 目录，前缀陷阱未触发），
改成同级目录后才真正判别（M27 能打红）。它问我是否超范围。
**裁定：保留。** 理由：我刚把守卫**扩成更保守**（R71），而「它不会误伤合法布局」正是那次改动所需的
对重 —— 一次收紧若没有被「不该拒的没被拒」钉住，就只是单边的。且它已被 M27 证明有鉴别力。
**它主动报告自己测试的空转，是这一程最有价值的自省之一** —— 空转的测试比没有测试更危险，
因为它制造的是虚假的信心。代价若判错：多一条测试。

Task 2: fix round 1/5 re-review — 5 条 findings **全部 ADDRESSED**，无新 Critical/Important。
        审查者在 `/tmp` 副本里跑（仓库未被触碰，两文件 `git status` 干净、HEAD 确认），
        基线 hash 与报告一致。**独立验证了两条自我披露的说法**：
        (A) 它重跑了那条 sibling 测试的**第一版**（`.../剧/S01/` + `.../剧B/S01/`）配裸 `startswith` 变异
            → 26 passed 无红，与实施者所述完全一致；理由是各组 show 的 root 是其自己的 `S01` 目录，
            比较从未涉及相撞的 `剧` 与 `剧B`；**且它在基线下也是绿的，所以看起来像覆盖** ——
            这正是「空转的测试制造虚假信心」的实例。终版是真判别的：裸 `startswith` 变异打红它，
            且它是**唯一**能抓该变异的测试（1 failed / 25 passed）。
        (B) finding 2 的「只加强断言仍会空转」：用原 2 条入参 + 强化后的三元组断言跑 `ordered→entries`
            变异 → 26 passed 无红（每组只有一条目，`group[0]` 本就与顺序无关）；换成新 3 条入参后
            同一变异打红 `test_decisions_are_deterministic`。**实施者的说法成立。**
        它另跑了**守卫矩阵**（8 种布局、新旧对比）：同目录混放仍被拒；`未分类/A/a.mkv`+`未分类/B/b.mkv`、
        `未分类/剧`+`未分类/剧B`、同一剧分处 S01/S02、剧目录含自己的 S01/S02 + 兄弟剧 —— **全部仍写出**，
        无误伤；新被拒的只有真正的嵌套（3 种）。**这正是我扩守卫时所需的对重。**
Task 2: fix round 1/5 (5 addressed, 0 open; commits 5daa1de..2ac74f1)
Task 2: **complete** (commits 5b25b83..2ac74f1, review clean after 1 fix round)

Task 2: 残留（无第二波修复，交最终审查）：
  (1) 两处裸 `all()`（`test_nfo_plan.py:208`、`:375`）原则上可能为空，但审查者确认**不可利用**
      （完全不发 season 决策会打红 8 条测试、完全不发 tvshow 决策打红 13 条 —— 基数由兄弟测试钉住）。
      这是一条**关于 R69 那个形态的边界观察**：真空断言是否可利用，取决于是否有兄弟测试钉住基数。
  (2) 混放分支的排序确定性（本轮顺带修好）**无测试**。
  (3) season 拒绝决策复用了剧集级文案（`nfo_writer.py:197`）—— 已按裁定 defer。
  (4) 同名不同剧的混放不会被拒（守卫按 show_name 跳过同名项）—— 既有设计限制，非本轮引入。
Task 2: 顺带确认（非破坏）：混放分支改为按排序序遍历后，每文件的拒绝决策也变成确定序 ——
        与 finding 2 同类，属严格改进，但未触碰 docstring 的跨剧顺序契约，也无测试钉两边。

## 任务 3

Task 3: implementer DONE_WITH_CONCERNS (commit b4cbc4d；brief 的 5 个文件，**+493/−0** —— 零删除，
        故计划 1 的 `apply_override` 抽取可证未被回退）。新建测试文件 20 passed
        （brief 的 8 条 + 它自己补的 12 条集成测试 —— brief 对 Step 5–7 **没给任何测试**）；
        全量 **175 passed**。23 条变异里 22 条打红、逐条 sha256 还原。

Ruling R73: **本程最重要的一条发现，结论是「实施者对、Task 2 错、根因在 spec」。**
**单季布局下剧集根推导错误。** `common_parent` 的规则是「该剧所有视频的公共父目录」：多季时给出剧集根 ✓；
但**只有一个季文件夹时，公共父目录就是那个季文件夹本身**，于是 `tvshow.nfo` 落进 `Season 02/` ——
而 Emby/Jellyfin **只在剧集根**找 `tvshow.nfo`，放季目录里找不到，**等于白写**。
**根因是我的 spec §9.3 不完备**：它只举了多季的例子（`Season 02`+`Season 03`、`S01`+`S02`），
单季布局从未被考虑；而计划的每处测试也都只用多季布局（Task 2 的
`test_tvshow_goes_to_show_root_and_season_to_season_folder` 正是 `Season 02`+`Season 03`），
**所以这个洞一路穿过了 Task 2 的实现、它的 20 条测试、以及它的完整审查**。
T4 的计划测试期望与我 T3 的测试一致（后者才是对的），**故它会同样挡住 Task 4** —— 必须现在解决。
**裁定：剧集根 = 公共父目录，但若该目录名字本身是季目录则再上溯一层**；判据**复用**
`parser.py` 的 `_SEASON_DIR_PATTERNS`（`local_renamer.py` 已在用），不另立一套正则；
只在 basename 匹配时上溯且上溯后不得为空/根；`season.nfo` 落点不变；混放校验用上溯后的 root。
**折进 Task 3 的修复轮**（它已改过 `nfo_writer.py`，且 T3 的测试要求这个语义），不另开任务。
**已同步修正 spec §9.3**（那是设计权威，缺口在那里）。
代价若判错：若「上溯」在某布局下过头，`tvshow.nfo` 会写到剧集根之上 —— 测试覆盖了三种季目录写法
与「未启用季文件夹」两种边界，且预览的 NFO 列会把落点显示出来（可见）。
**形态记此**：这是**第一次由「实现与测试互相矛盾」暴露出的设计缺口** ——
不是实施者做错，也不是审查者漏看，而是 spec 的**举例不覆盖它的规则**。
我写 spec 时用例子代替了穷举，而规则的真实边界比例子宽。

Ruling R74: concern 2（`nfo_matches` 注解 `dict | None` 比 Interfaces 的 `Optional[dict[str, EpisodeMatch]]` 松）
—— **裁定：用严格注解**。`local_renamer.py` 有 `from __future__ import annotations`（注解是字符串、无运行时成本），
且 `local_renamer → tmdb_resolver` 不构成循环。退化的注解会削弱 Interfaces 作为契约的价值。
代价若判错：无。

Ruling R75: 实施者实测「去掉 `encoding="utf-8"` 在本机 UTF-8 locale 下**不红**，但在 `LC_ALL=C` 下打红 16 条」。
**裁定：这不是缺陷，但必须写进注释。** 两种写法在 UTF-8 locale 下产出**相同字节** ——
没有任何字节级断言能区分它们，所以「本机不红」是必然的。但测试的注释必须写明
**它只在非 UTF-8 locale 下有鉴别力**，真正的证据是冻结 locale 的那次运行（CI 与 Docker 常用 `LANG=C`）。
**不要让测试看起来比它实际证明的更强** —— 与本程反复在修的「声明强于事实」是同一族，只是换了个方向。
代价若判错：一位后来者可能误以为这条测试在本机能抓回退 —— 而它的注释会纠正他。

Task 3: fix round 1/5 dispatched（findings: 单季剧集根上溯 [R73] / 严格注解 [R74] /
        encoding 测试注释诚实化 [R75]）

Task 3: fix round 1/5 report — commit 9f9588a（4 files，+93/−9）；**177 passed × 2**
        （默认 locale 与 `LC_ALL=C`）。新增 `nfo_writer._show_root`：仅当公共父目录的 basename 匹配
        `parser._SEASON_DIR_PATTERNS`（复用，不另立正则）时上溯一层；父目录为空/根则保持原样；
        `season.nfo` 落点不变；混放校验改用上溯后的 root。测试覆盖**三种季目录写法**
        （这样私有正则不能通过）+ 未启用季文件夹 + 两个 root 守卫。变异 MU1/MU2/MU3 分别打红 3/1/10 条。
        它**把被裁定作废的两处期望改了并说明**（一处是守卫改用上溯后 root 的直接后果），并把
        `test_writes_all_three_kinds` 恢复成 brief 原文。另：它**更正了自己上一轮的过度声称**
        （「C locale 下 16 条红」多数是夹具 `os.mkdir` 建不出来，不是 `encoding` 的证据），
        重做隔离探针得到真证据。

Task 3: task review — **规格合规 ✅，Needs fixes**（2 Important + 5 Minor）。
        审查者独立读取盘代码核实每一项（含 `b4cbc4d` 的 numstat `54/0` 证明零删除、
        整个范围内 `local_renamer.py` 只有 **1** 行删除且那是本轮的注解改动，非计划 1 回退）；
        并核对了本次所有测试**无真空断言**（`test_mixed...` 的 `all()` 有 `len(...) == 4` 守卫、
        路径断言用精确列表相等、`test_failures_are_reported_not_raised` 真会红）。
        它对我交办的**具名风险**（`except OSError` 是否接得住 `UnicodeEncodeError`）给出了清晰结论：
        层级说法**成立**（`UnicodeEncodeError → UnicodeError → ValueError → Exception`，
        `issubclass(..., OSError)` 为 False），但**有 `encoding="utf-8"` 在就根本不会抛**，
        故约束对现实中所有写失败都成立；它另逐一枚举了本项目可达的其他非 OSError 逃逸（均不可达）。
        **裁定：不加宽 handler**（它的理由：加宽会掩盖编码 bug 而非暴露它）—— 与 R21 的宽捕获不同，
        那里的边界是外部数据，这里的 try 只包着 `mkdir`/`write_text`。

Ruling R76: Important 1（`_show_root` 在**剧目录本身叫季名**时上溯过头，把 `tvshow.nfo` 写到库根）——
**裁定：只做文档补救，不改代码逻辑。** 审查者证明了**不存在纯路径的修法**：
`show_name == basename(上溯后 root)` 在两种布局下**相等**（它探针验证过），故用剧名当判据会误伤
合法目录名（如 `[NC-Raws] 葬送的芙莉莲 (2023)`）；而若要求探测文件系统，就破坏了
`build_nfo_decisions` 的「纯函数、不碰 FS」契约。补救：docstring 点名该类别 + 写明为何可接受
（dry-run 清单在执行前显示落点 = §9.4 的可见性即安全阀；组合罕见）+ 注明上溯是单步非循环。
**我已同步补进 spec §9.3。** 代价若判错：该组合下会污染库根 —— 但**执行前可见**，可纠正。

Ruling R77: Important 2（`rename_dup` 下 NFO 与视频配不上）—— **裁定：修。**
每集决策用 `plan.new_path`，而 `execute_rename_plan` 在 `rename_dup` 策略下会把真实目标解析成
`name_1.mkv` → 视频拿不到 `..._1.nfo`，且 `overwrite=True` 时冲突那个文件的 NFO 会被改写。
可达（界面有「自动编号」），会落进 `nfo_skipped`（非静默）但仍是错的配对。
修法：重命名循环后、`write_nfo_files` 前，对 `result.new_path != plan.new_path` 的 file_id
把每集决策改指向 `episode_nfo_path(result.new_path)`（`NfoDecision` 可变）。
代价若判错：无。

Task 3: fix round 2/5 report — commit d1a53b6（3 files，+69/−1）；**178 passed × 2**（默认 locale 与 LC_ALL=C）；
        变异累计 29 条。**MV3 证明一条我没意识到的性质**：去掉 `kind == "episode"` 守卫会红 2 条 ——
        因为 tvshow/season 决策**与 episode 决策共享 file_id**，故那个守卫是必要的。
        dry-run 也受益（`execute_rename_plan` 在 dry-run 返回前已解析出 `_1` 目标）→ 预览与执行一致。
        **它又更正了自己一次**：第一版探针用手工传入的 `show_name`，得出「等式判据能区分」；
        走真实管线后，解析器推导剧名时会跳过季目录，于是坏布局给出 `show_name='lib'` == basename(root)，
        与合法布局完全一样 —— 并多指出一点：`show_name` 可被用户覆盖，所以它本来就不是路径的函数。
        它**有意没给上溯过头加刻画测试**，理由是「那会让将来的修复看起来像回归」。**我认同** ——
        对「已知且接受、且明确不是契约」的行为，持久记录该在 docstring 与 spec 里，而非测试里。
Task 3: fix round 2/5 re-review — 2 条 findings **ADDRESSED**，无新 Critical/Important。
        审查者在 /tmp 副本里独立复现 MV1/MV2/MV3；对着**活的解析器**核实了 `_show_root` 的各项说法；
        确认 docstring-only（`+24/-0`，无 `-` 行）；确认新测试在 MV1/MV2 下都会红，
        且 `overwrite=True` 时 sentinel 断言（:345）正是该 finding 描述的破坏。
        它另独立同意那个有意省略，**理由比我的更好**：「没有独立的机制需要保护 ——
        过度上溯与合法布局走的是同一条单步路径，合法布局已被 `test_single_season_folder_...` 钉住」。
Task 3: fix round 2/5 (2 addressed, 0 open; commits 9f9588a..d1a53b6)
Task 3: **complete** (commits 2ac74f1..d1a53b6, review clean after 2 fix rounds)

Task 3: 新残留（Minor，既有，交最终审查）：
  (a) dry-run 与执行在「**两个 plan 共享同一 new_path**」时仍会不一致：dry-run 把两者都解析成 `X_1.mkv`
      （那时还没东西被创建），执行给出 `X_1`/`X_2` → 第二个文件的**预览 NFO 落点会错**。
      源于 `execute_rename_plan` 按实时 FS 解析冲突；对视频路径同样成立。
      这**软化了本轮报告里「dry-run 与执行总是一致」的笼统说法**。
      最小修法：给 dry-run 分支传入一个「本批次已保留目标」的集合。
  (b) `abort` 分支在赋 `nfo_path` **之前**就 `continue`，故被中止的文件 `nfo_path` 为 `None`，
      而它的每集决策仍存在、NFO 仍会按设计被写。最小修法：该分支 `results.append` 前补一行
      `result.nfo_path = nfo_path_by_file.get(plan.file_id)`（安全 —— `abort` 从不改 `new_path`）。

## 任务 4

Task 4: implementer DONE (commit f02abc7；**192 passed**；新增 11 + 1 条测试与 2 个铁律参数；
        `frontend/dist` 未触碰)。**未粘贴简报代码块** —— 按意图改造 HEAD，并保留了 HEAD 的 401 分支
        （简报版会产出「TMDB API Key 无效: …」双前缀并打红既有用例）。
        12 条变异 + 4 处分类点变异全部实测，改后源文件 sha256 与改前逐字节一致。

Ruling R78: 实施者发现**我的计划里又一处 `all(...)` 假绿灯，而且是严重的一个**：
`nfo_scope` 的逐文件 `all("tvshow" in nfo_paths_by_file.get(f.id, {}) for f in files)` ——
而剧集级决策只挂在组内**首个** file_id 上，所以**同一部剧选两集（正常情形！）时 `full` 会被误报成
`episode_only`**，用户会看到「仅每集 NFO」而实际写了全套。
**裁定：接受它改为按剧判定**（变异 M5：粘回字面版只有那条用例红）。
而我的计划里**没有任何测试覆盖 `full`**（`test_preview_reports_disabled_scope_without_tmdb` 只查
disabled 路径）—— 故这是「`all()` + 不完整集合」的第 4 次，且这次最严重（它误报的是**正常情形**）。
代价若判错：无。

Ruling R79: 键名分歧 —— 计划的**代码**与 T5 前端都用 `"tvshow"`，而计划的 **Interfaces 行**与
spec §11 写 `"show"`（又一次计划内部不一致）。**裁定：保留 `"tvshow"`**
（代码与消费方一致，且与产物名 `tvshow.nfo` 对应），**改 spec**（已改）。
代价若判错：无。

Task 4: 实施者的零鉴别力披露（值得记）：`test_generate_nfo_off_writes_nothing` **在未实现的 HEAD 上也通过**
（简报 Step 2 称「全部 FAIL」不成立），它加严了断言并说明该测试只覆盖「无视 generate_nfo」一种变异；
另 OpenList 执行侧的 `NfoOptions()` vs `None` 在行为上不可区分（报告 §9.5）。
它还发现：补 `fail="season"` 时 `tmdb_match` 断言原本是**步相关的**，已按步分支并写明理由。

Task 4: 四处 carry-in 均落地（注释改名、消息表键 `rename`→`search`、
铁律用例的变异描述改为实测值、补 `detail`/`season` 两个 fail 取值）。
        顾虑：预览构造两次 TMDB 客户端（纯判定、无 I/O，受简报三元组签名所限）→ Minor，交最终审查。

Task 4: fix round 1/5 report — commit 39135ab；**193 passed**。补了 `full` 判据「每部剧」那一半的钉子
        （三条文件/三部剧：剧甲干净命中、剧乙剧丙同处未分类被拒 → 全行 `episode_only`，而剧甲行仍带 `nfo.tvshow`）。
        测试注释里解释了**为什么需要三部剧**：守卫判的是「该剧根目录**及其子树**里有没有别的剧」，
        只有一部剧的目录永远干净。变异：判据换成「任一剧有就 full」→ 1 failed（正是新用例）；
        deselect 该用例 → 192 passed（独立复现审查者的测量）。
Task 4: task review — **Approved**（1 Important 覆盖缺口 + 4 Minor）。实施者未粘贴简报代码块、
        按意图改造 HEAD，并保留 HEAD 的 401 分支（简报版会产出双前缀并打红既有用例）。
        四处 carry-in 均落地且审查者独立复现了变异记录；证明 `[detail]`/`[season]` 各是**不同调用点**的
        唯一点子、故清理 4 不是冗余。**12 条变异 + 4 处分类点变异全部实测**。
Task 4: fix round 1/5 (1 addressed, 0 open; commits f02abc7..39135ab)
Task 4: **complete**（review clean after 1 fix round）

Ruling R81: 再审查者**抓到了我的一个事实错误** —— 我在修复指令里说「spec §11 写的是 `tvshow`」，
而在那个 fix base 上 spec §11 **确实写的是 `"show"`**：实施者**原本的报告是对的**，是我的指令前提错了。
它没有去「更正」报告，而是**把我说的变成真的**（先改 spec 再改计划行），最终状态更好
（spec == 计划 Interfaces == `decision.kind` == T5 消费端），但报告的历史叙述被掩盖了。
**教训：引用文档状态时必须分清「我改之前」还是「我改之后」** —— 这次我在派发前改了 spec，
然后把改动后的状态当作实施者的错误来陈述。

Task 4: 残留（交最终审查）：(a) 报告 §6 D3/§10.3 的历史叙述仍掩盖了那次 spec 编辑（一行文档修正）；
(b) `_nfo_supported` 的不可达 `else` 分支只有报告里写了「有意保留」，**调用点注释没写「运行期不可达」**
（两处，各半句）；(c) Minor 2（`nfo_scope` 是批次级值被复制到每行）、Minor 4（预览构造两次 TMDB 客户端）。

## 任务 5（最后一个）

Task 5: 四轮修复，最终 **197 passed**。要点：
  - implementer e9a2f42 → 修复轮 1（C1 watch 依赖缺 `generateNfo`/`nfoOverwrite`；C4 加第五个文件
    `ResultDialog.vue` 显示 `nfo_written`/`nfo_skipped`，因为「覆盖已存在」默认关闭使**跳过是重跑常态**，
    只报「成功 N 个」等于用省略告知用户一件没发生的事；C3 `episode_not_found` 行在 NFO 列上是空白的）
    → ccb221e
  - task review → Needs fixes（Important：`FileTable.vue` 用**行级**信号断言**批次级**事实 ——
    任何 ≥2 集的剧目录会给除代表行外每一行打橙色假警告，10 集 → 9 条假警告；
    审查者用**仓库里真实的 `build_nfo_decisions`** 实跑证明，不是读出来的）
    → 修复轮 2（128a0f4）+ 修复轮 3（64c6ed2，R3-4 字幕过滤）
  - re-review（2+3 合并）→ 全部 ADDRESSED，但残留里有两条属本程反复在修的那类
    → 修复轮 4（a1e2db4）
  - 再审查 → **全部 ADDRESSED，无新破坏**

Ruling R82: **实施者发现的 R3-4（我 spec 的缺口）：NFO 管线没有「只处理视频」的过滤。**
解析器对字幕与视频给出**完全相同**的结果（实测 `Show.S01E01.chs.srt` 与同名 `.mkv` 一字不差），
故每个字幕旁会多写一个无意义的 `.nfo`（**纯库污染**），且决策按路径排序时会挂到字幕行上
（`'….chs.srt' < '….mkv'`）—— 后者是实施者提供的具体证据，没有它我不会意识到。
**裁定：必修**，判据用扫描器已设好的 `FileInfo.is_subtitle`（比嗅探扩展名精确，不会与
`settings.subtitle_extensions` 漂移），两处 `NfoEntry` 构造点都过滤，且**不影响字幕重命名**。
已同步补进 spec §9.1。代价若判错：若某目录只有字幕，`nfo_scope` 仍报 `episode_only`（见 R4-5）。

Ruling R83: **R4-5（只有字幕的目录会报 `episode_only` 而实际零落点）—— 裁定 defer。**
实施者的分析比我最初的直觉好：把 `all(...)` 换成过滤后的视频列表会**踩到空列表恒 True 的老坑**
（变成 `full`，比现在更假）；修对需要第五个 scope 取值或回落规则 —— 那是 Task 4 的线上契约变更，
而现有测试逐个钉着四个取值。UI 后果轻（每行 `nfo=null`），且 R5 的字幕早退让这些行变成中性的
「字幕不写 NFO」而非橙色警告。交最终审查判断。

Ruling R84: 实施者**自行补了一条测试**（它发现「去掉 `rename_dup` 那条字幕过滤，整套一条都不红」，
即那道修复当时零覆盖），断言字幕 `nfo_path is None`。**裁定：保留** ——「修了但零覆盖」正是本程
反复在修的类别，且它断言的是我实际观察到的症状（字幕报出与视频**同一个** `_1.nfo`）。

Ruling R85: 实施者在修复轮 1 的**过程诚实记录**值得单独记：首次插入时它的锚点少看了最后一行，
把 `test_mixed_shows_in_one_directory_are_refused` 的**最后一句断言**挤进了新用例 ——
而它**只因为自己的用例变红才发现**。**若无那次红，「既有断言被静默搬走」是完全无声的**
（少一条断言不会让任何东西变红）。它修回并核对了原用例仍有全部断言。
**这与本程的「零鉴别力」是同一族问题的另一面：不仅新写的检查可能不检查任何东西，
既有的检查也可能被静默搬走而无人察觉。**

Task 5: 残留（交最终审查）：R1（`is_subtitle` 分支在批次分支**之前**，故 NFO 关闭时字幕行读「字幕不写 NFO」
        而非「未启用」—— 纯重排，1 行）、R2/R3（信息性，非回归）、以及前几轮的 Minor 4/5/6。

计划 2: 全部 5 个任务 **complete**。最终整分支审查（opus，range b442b22..a1e2db4，20 commits）
        判 **With fixes**：3 Important + 一批 Minor。

Ruling R86: 最终审查的 3 条 Important **全部判为必修**，合成**一次**修复波（规程：整分支审查后只派一次）：
  #1 **「静默写错元数据」真的发生了** —— NFO 会为**重命名没有发生**的文件写出，于是元数据落在
     **另一个视频**旁边（审查者复现了 `skip` 与 `abort` 两例；`abort` 那例更糟：用户选了最保守策略、
     被告知该行**没有落点**，然后在库里发现新文件躺在别人的视频旁）。而计划自己要求写盘阶段必须薄到
     「不产生重命名失败却写了 NFO 的半成品状态」—— 实现产出的正是那个半成品。
  #2 **§9.4 的「可见性安全阀」根本没交付** —— 预览只渲染基名字面量、绝对路径只在会截断的 tooltip 里、
     `season.nfo` 从不渲染；结果对话框只给计数与原因、**从不给路径列表**。
     **这条要紧在：我在 R76/R77 接受「上溯过头会把 tvshow.nfo 写进库根」这个已知类别，
     理由正是「dry-run 的清单会在执行前把落点显示出来」—— 那个前提在实现上是假的。**
  #3 spec 未闭合围栏（**我的错**，已由我修于 cd1c80a）。

Ruling R87: 修复波报告「**没有任何东西落地 → 剧集级文件也不写**」的规则，使单文件批次在未落地时
也会失去 `tvshow.nfo`。**裁定：接受。** 安全方向（不写元数据比写错元数据好），且已文档化。
代价若判错：某个古怪场景下少写一个剧集级 NFO —— 可见（预览/结果都列落点），可纠正。

计划 2: 修复波应用的 3 个提交（a006baa / 4d1b73e / 68ff2f2），**202 passed**（含无网命名空间）。
计划 2: 修复波的再审查 —— **全部项 ADDRESSED，无新 Critical/Important**。
        它做了我要求的**误抑制排查**并找到三类：
        (a) `failed` + 目标已存在 ⇒ 本该正确配对的 NFO 现在被抑制 —— **保守方向，低危**，
            审查者明确建议**不放宽**（那会把元数据写在身份未验证的视频旁）。**裁定：接受，保持原样。**
        (b) `dead_episode_paths` **未去重** → 两个同集源都缺失时 `nfo_skipped` 会出现**同一路径两次**
            —— 正是 minor 2 修过的「数字本身在说谎」那一类，漏了一处。
        (c) 「`skipped_same` 仍要写」这条**我显式要求的语义无测试** —— 行为正确（实测过），
            但将来改 `_NO_LANDING_STATUSES` 或那个 `elif` 分支会让「给已整理好的库补 NFO」这个
            主用例静默回归。
        另：掉落的**组级**决策不产生 `nfo_skipped` 条目（结果里看不到它们被丢掉了）；
        §9.4 的字面「预览表显式列出绝对路径」只在对话框满足，预览单元格给的是末两段。
计划 2: (b)(c) 与组级不报告三项**遗留**（均 Minor、非阻塞），按 R86 的「无第二波」规则交你裁决 ——
        我建议在实现 §9.1.1 时**一并补上**（同一文件、同一类问题，比单开一轮划算）。

## 追加期：§9.1.1 既有的同名 NFO 跟随视频改名

用户报告：改名后旧文件名的 `.nfo` 会留下。
根因：`.nfo` **既不在** `video_extensions` 也不在 `subtitle_extensions`，故从不进入扫描、不在批次里，
重命名路径上没有任何东西碰它。**这是我设计的真空** —— 我只写了「生成 NFO」，没写「已有的怎么办」。
字幕没这问题（字幕在扫描里、会被当独立文件重命名），NFO 有。

Ruling R88: 设计经用户确认：**旧 NFO 跟随改名**（移动到新前缀）。四条边界：只对视频、
只跟同前缀那一个（绝不碰 tvshow/season.nfo）、**与是否生成 NFO 无关**（主用例恰是「不生成 NFO 但
已有 NFO 是别的工具写的」）、**先移动后生成**（这个顺序使「生成开 + 覆盖关」保留用户原有内容 ——
反过来会让生成先写、移动再覆盖它）。失败处理沿用既有铁律：目标已存在**不覆盖**（报跳过，
宁可留下可见的孤儿也不静默改写别人的元数据）、移动失败不阻断批量。dry-run 不移动但列出。
OpenList 不在本期（已知限制）。
**已写入 spec §9.1.1**（提交 f221a51）。实现待做。

Task 3: deferred（交最终审查）：Minor 3（dry-run 与执行在「重复 + 已存在」时报告数不一致；
dry-run 内联重写了跳过规则，两处可能漂移）、Minor 4（`nfo_path` 是落点非已写）、
Minor 5（重命名被跳过/中止的文件仍会被写 NFO —— brief 注释认可，无测试）、
Minor 6（`Specials`/`特别篇` 不在 `_SEASON_DIR_PATTERNS` —— 与 R76 同一类别，但那是 parser 的
共享模式表、影响面更大，不在此处动）、Minor 7（三处措辞/平台细节）。
        以及：`RenameResult.nfo_path` 即使在没写 NFO 时也被填充
        （计划行为 —— 它是「落点」不是「已写」；**下游必须用 `nfo_written`/`nfo_scope` 判断**，
        这条会在 T4 的派发里明确要求）。

Task 2: deferred（交最终审查）：§8(1) `test_empty_entries_produce_nothing` 非判别性（那条 `or not entries`
        守卫本就冗余）、§8(2) `common_parent` 的空守卫与单元素短路等价且防御性、
        §8(3) `test_two_shows_get_two_tvshow_files` 只查路径、Minor 4（拒绝文案把「剧集级」一词
        复用到 season 决策上；前端自己渲染文案）、⚠️ `common_parent` 的 `ValueError`
        （绝对/相对混用会抛，Task 3 必须保证路径同构 —— 计划里已是如此，会在其派发里明说）。

Task 1: minors deferred（交最终审查分诊）：`field` 未使用（plan-mandated，仓库无 lint）、
        两条冗余但可失败的转义断言（保留）、`_uniqueid` 在 id 为 None 时省略与「必写」措辞的分歧
        （可达性有界，brief 自己的测试表明该省略是有意的）、`value` 无类型标注（brief 原文）。
