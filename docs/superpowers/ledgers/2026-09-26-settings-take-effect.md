# SDD ledger — plan: docs/superpowers/plans/2026-09-25-backend-pad-digits.md

MERGE_BASE: 8ef8a3f

## 背景与裁定

Ruling: 本次修复跨两份计划文档 —— 本计划全部三任务 + `docs/superpowers/plans/2026-09-25-frontend-3-features.md` 的 Task 8。理由：诊断确认「设置页设置不生效」的根因正是本计划从未执行，而前端 Task 8 的前置条件写着「本计划未合入时必须跳过」，于是两头都空。以本计划为 ledger 的 primary plan（工作区归属），前端 Task 8 作为附属任务登记 —— 代价：日后按计划文件检索时，前端那部分找不到归属，需靠本行指引。

Ruling: 用普通分支 `fix/settings-take-effect` 而非 git worktree。理由：四期重构的 ledger（`docs/superpowers/ledgers/2026-09-25-frontend-refactor-four-phases.md`）已确立该选择及其理由，且本次未获 worktree 偏好指令 —— 代价：无（隔离成立：实现不在 main 上）。

Ruling: 新增一项计划外修复 —— 设置页 `openlist.serverUrl`（「默认服务器地址」）是 spec §12 与两期计划双双漏掉的死设置：它写进 settings store，但 `workspace.initialize()` 读的是 **openlist store** 的另一个 localStorage 键。用户已批准纳入范围。无现成计划，按 TDD 自行设计 —— 代价：若语义理解有误（它本意可能不是登录表单初值），需返工一处赋值。

Ruling: 用户批准的范围是「补零位数 + 服务器地址」，**不含** openlist 的 concurrency / requestInterval —— spec §12 明确决定不修、只在 UI 标注说明，属有意的、已告知的限制，不算 bug。

## Pre-flight 冲突扫描

| 任务对 | 共享物 | 一方产出 vs 另一方消费 | 结论 |
|---|---|---|---|
| B-T1 ↔ B-T2 | `PadConfig` | T1 定义 frozen dataclass `PadConfig(episode, season)`；T2 读 `pad.episode` / `pad.season` | 干净：名称与字段逐字一致 |
| B-T2 ↔ B-T3 | `apply_template(..., pad=)` / `apply_folder_template(..., pad=)` | T2 定义签名与透传；T3 在 plan builder 调用点传 `pad=` | 干净 |
| B-T2 ↔ B-T3 | `generate_full_path` 删除 | T2 删并声明「后续任务不得引用」；T3 不引用 | 干净 |
| B-T3 ↔ B-T3(自身) | `_pad_from_request` 三路由复用 | T3 Step 5 内定义并使用 | 干净：已声明「必须显式判 None，不能用 `x or default`」（0 是合法输入） |
| B-T3 ↔ F-T8 | 请求字段名 `episode_pad_digits` / `season_pad_digits` | B-T3 加进两个 Request 模型；F-T8 在 `workspace.js` 两处请求体发送 | 干净：字段名逐字一致（ledger 已核） |
| B-T3 ↔ F-T8 | 钳制区间 | 后端 `PadConfig` 钳 [1,6]；前端 `settingsSchema.js` PAD_MIN/PAD_MAX 亦 [1,6] | 干净：两侧已对齐（前端注释亦声明以此为准） |
| F-T8 ↔ 新增 serverUrl 修复 | `workspace.js` 的 `initialize()` | T8 改 `buildPreview()` / `executeAction()`；serverUrl 修复改 `initialize()` | 干净：函数不相交 |

计划自身文本自洽性：三任务的 Files 表与正文操作对象一致；无「见 Task N」式占位。

## 任务进度

- Task 1: complete (commits 8ef8a3f..f90f440, tests: python -m pytest tests/ → 9 passed)
Task 2: Ruling: 计划的 test_folder_template_without_pad_uses_globals 断言写 "Season 02" — 但 fixture season=1 且全局补零 2 位，正确输出是 "Season 01"；同文件其余 5 条断言均与 season=1 自洽，判定为计划断言笔误，改断言而非改 fixture — 代价：若 fixture 本意是 season=2，则该用例失去对「季数=2」的覆盖（现由 test_no_pad_falls_back_to_global_settings 无覆盖，可接受）。
Task 2: Ruling: 计划的 test_pad_does_not_affect_unpadded_variables 用 `"{episode}|{episode_padded}"` 断言 `"2|002"` — 两处笔误：`|` 属 utils.ILLEGAL_FILENAME_CHARS 会被 safe_filename 换成空格；模板缺 {extension} 但 include_extension 默认 True 会补 `.mkv`（实测输出 `"2 002.mkv"`）。改为 `"{episode}_{episode_padded}{extension}"` 断言 `"2_002.mkv"`，测试意图不变且不掺入 safe_filename 改写行为 — 代价：模板字面量偏离计划文本，日后比对需读本行。
- Task 2: complete (commits f90f440..24db673, tests: python -m pytest tests/ → 16 passed)
- Task 3: complete (commits 24db673..726d4ca, tests: python -m pytest tests/ → 25 passed)
- F-T8: complete (commits 726d4ca..816a18d, 机械验证: npm run build ✓ + 产物 grep 字段各 2 处；浏览器走查 deferred-to-human)
- F-SRV: complete (commits 816a18d..HEAD, tests: node scripts/check-settings-schema.mjs → 全部通过含 5 条新断言)

Ruling: 「默认服务器地址」的优先级定为「设置页的值 > olStore 里上次实际使用的地址 > 空串」，而非「上次使用 > 设置页」。理由：用户本次的诉求就是设置要生效；若让上次使用的地址优先，用户改完设置页再回主页仍看到旧地址，会重演「设置不生效」的观感。代价：拥有多台 OpenList 服务器的用户，登录表单不再自动预填上次那台，需从设置页或手输切换。

Ruling: frontend-3-features.md Task 8 正文里的两项附带修复（①buildPreview() 载荷不含 overrides，导致预览列不反映手工编辑、与执行结果不一致；②buildPreview() 重建行时硬编码 `override: {}`，导致点一次「预览」就抹掉已编辑的 override）本次**不实施**。理由：用户批准的修复范围是「补零位数 + 服务器地址」，这两项属另一类缺陷；且前端无测试设施（spec §17 遗留 3），无法按 TDD 铁律先写出会失败的测试再修，贸然并入会让本次改动出现无测试覆盖的生产代码。代价：这两个缺陷继续存在，将在最终报告里连同证据一并交回用户决定。

## 最终评审

Final: 评审由 fresh-context 独立模型执行（非本会话模型）。结论：Critical 1 / Important 2 / Minor 10 / Declined 7，判定「With fixes」。评审独立跑了两套测试并自行探测了 API 边界（0 / -1 / 1000000 / null），与实施者的端到端结论一致。

Final: fixed 提交的构建产物不含修复（评审 Critical 1）— 判据 `git show HEAD:frontend/dist/assets/*.js | grep -c episode_pad_digits` 修复前为 **0**。后端 `app/main.py:60-73` 托管的正是 `frontend/dist`，所以 checkout HEAD 运行会完整重现原始症状。重建后已提交（a6ac74a），判据现为 2+2 次出现。此项无测试可写（是构建产物），以该判据本身为验证。

Final: fixed 保存设置后预览列不刷新（评审 Important 2；re-grade 后升为必修）— 该发现命中的正是本次修复的原始症状本身：补零位数与模板同为渲染输入，却不在重建预览的 watch 依赖里，用户保存后回工作区仍看到旧位数，必须手点「预览」。而 spec §15.3 明文要求「预览列**立即**显示」，故不修等于未满足 spec。修法：`workspace.js` 的 watch 依赖数组加入 `settingsStore.episodePadDigits` / `seasonPadDigits`。前端无测试设施可覆盖 Vue watch 语义，验证为机械等价（构建通过 + 源码调用点）＋ 走查 deferred-to-human。草稿语义不受影响：设置 store 只在点「保存设置」时写入。

Final: fixed dry-run / execute 路由缺 pad 断言（评审 Important 3）— 原测试只断言 HTTP 200，路由丢掉 `pad=pad` 也能全绿。先证明新断言确实能捕获缺陷：临时移除两处 `pad=pad` 后**恰好**这两个测试变 RED、其余 8 个仍绿，恢复后 26 passed。

Final: fixed 注释去伪（Minor 5，纳入 fix pass 的判断理由）— `settingsSchema.js` 原称「后端今天没有实现这个区间…这道 clamp 是唯一的防线」。该陈述**由本次改动本身变为虚假**（后端已落地 PAD_MIN/PAD_MAX 且区间一致），不属无关的 polish 机会；项目亦有「注释去伪」的既定实践（见 commit 95cdabf）。

Final: fixed 误提交的 `__pycache__`（Minor 7）— 核实属实：commit f90f440 因 `git add backend/tests/` 带入 2 个 .pyc。处理为连同既存的 23 个一并从索引移除（`git rm --cached`，工作区文件保留）并加 `.gitignore` 规则 —— 只清 test 目录会留下「加规则却仍脏」的自相矛盾状态。

Final: minor (deferred): `PadConfig` 未强制 `int`（评审 Minor 4）— 评审确认 API 路径不可达（Pydantic 拒绝小数）。
Final: minor (deferred): `_pad_from_request(req)` 缺类型注解（评审 Minor 8）。
Final: minor (deferred): `resolveOpenListServerUrl` 不 trim 纯空白值（评审 Minor 9）。
Final: minor (deferred): 测试 fixture 的 `cache_files` 无 teardown，跨用例泄漏（评审 Minor 10）。

Final: Ruling: 小数补零位数返回 422 而非钳制（评审 Minor 6）— 评审明确不视为缺陷（越出整数域而非越出范围，UI 无路径可达），我同意，记录为有意行为而非意外。
Final: Ruling: Task 8 两项附带修复仍不实施 — 评审接受该过程（升级为 ledger 项并附证据，而非静默丢弃），但指出我 ledger 里的理由之一「前端无测试设施」**站不住**：我确实用 node 断言测了 `resolveOpenListServerUrl`，计划也给了确切代码。理由修正为：①它们与用户报告的「设置不生效」不属同一缺陷类别，用户批准的范围是「补零位数 + 服务器地址」；②修第 ② 项需把 `buildPreview()` 重建行的逻辑抽出纯函数才可测，属重构，与系统性调试「不捆绑重构」相悖。代价：点一次「预览」仍会丢弃手工编辑的 override，且预览列不反映手工编辑 —— 评审指出这会让 Task 8 Step 4 的走查第 3 项（点「预览」验证补零）顺带抹掉编辑。
