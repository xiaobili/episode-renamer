# 前端重构 · 第四期（打磨）— spec §15 验证记录

| | |
|---|---|
| 分支 | `feat/frontend-refactor` |
| 被验证的提交 | `aba9d96`（截图留档）及其之前的本阶段全部提交 |
| 本记录的来源 | 本阶段任务 7 的报告 `.superpowers/sdd/2026-09-25-frontend-4-polish/task-7-report.md`（该目录被 gitignore，不进仓库）+ `/tmp/er7/*-out.{json,txt}` 的原始输出 |
| 记录日期 | 2026-09-25（验证）／2026-09-26（评审后补正，见 §3） |

**为什么要落这份文档：** 计划的任务 7 步骤 10 要求把 §15 的九项
「通过 / 不通过 / 不适用」判定写进**提交信息或 PR 描述**。本仓库没有 PR，承载截图的提交
（`aba9d96`）只有一行正文，而任务报告位于被 gitignore 的目录 —— 于是分支上最强的证据
（328 行下 `scrollHeight − innerHeight = 0`、9/9 渲染对比度、10/10 键盘停靠点、4/4 断点、
「OpenList 在本环境不可用」的三重证据）无法从仓库取回。这份文档就是那个缺口。

---

## 0. 环境与方法

| | |
|---|---|
| 后端 | `cd backend && python3 run.py` → uvicorn `:8000`（reload on），`/health`、`/api/info` 均 ok |
| 前端 | `npx vite --port 5199 --strictPort`（5173 被无关进程占用，未动）。`/api` 由 vite 代理到 `:8000`，所以下面每一项测量都打在**真实后端与真实磁盘**上 |
| 浏览器 | `/usr/bin/chromium --headless=new --remote-debugging-port=9333`（Chrome 152.0.7977.82），用 CDP + Node 内置 `WebSocket` 驱动（未安装 Playwright） |
| hover 模拟 | Chromium 以 `--blink-settings=availableHoverTypes=2,primaryHoverType=2,availablePointerTypes=4,primaryPointerType=4` 启动；页内实测 `matchMedia('(hover: hover)').matches === true`、`(pointer: fine) === true` |
| 测试数据 | `/tmp/er-test`(5 文件)、`/tmp/er7-faildir`(`chmod 555`)、`/tmp/er7-browse`、`/tmp/er7-home`(15)、`/tmp/er7-long`(328)、`/tmp/er7-review`(2) |
| 驱动脚本 | `/tmp/er7/step{2,3,4,5,6,6b,6c,6d,7,8,9,9b}.mjs` + 共享 harness `/tmp/er7/lib.mjs`；原始输出 `/tmp/er7/*-out.{json,txt}` |
| 读数的性质 | 视口数字全部来自 CDP `Emulation.setDeviceMetricsOverride`；颜色全部来自 `getComputedStyle`。每次驱动都收集 `Log.entryAdded(level=error)` 与 `Runtime.exceptionThrown` —— **全为空** |

---

## 1. spec §15 九项判定

| # | 项 | 判定 |
|---|---|---|
| 1 | §15.1 构建无警告 | **通过** — `npm run build` exit 0，`✓ built in 2.16s`，1837 modules，`grep -iE 'warn\|error'` 为空；另跑 `check-sfc-compile.mjs` 22/22 OK、`check-settings-schema.mjs` 30/30 PASS |
| 2 | §15.2 功能实跑（五条路径） | **部分通过 —— 3 通过 / 2 环境不可用，未验证**。通过：路径 1 本地扫描→预览→试运行（5/5 新文件名有值；试运行前后 `readdirSync` 逐字相同）；路径 2 本地执行重命名（结果对话框 5 行 `renamed`，磁盘上的文件名与对话框逐条一致）；路径 5 制造一次失败（`chmod 555` 目录，成功 0 / 失败 3，失败徽章实测 `danger-soft` 底 `rgb(253,236,234)` + `danger` 字 `rgb(179,38,30)`，界面未崩、磁盘无半改名）。未验证：路径 3（OpenList 连接→浏览→扫描）、路径 4（OpenList 试运行），原因见 §2(b) |
| 3 | §15.3 补零位数闭环 | **不适用 —— 后端未实施**。前端半边完整（设置页可存、schema 校验通过），但 `preview` 请求 payload 的键只有 `["file_ids","source","path","template","folder_template","create_season_folder"]`，**没有** `episode_pad_digits`；后端也没有 `/api/settings` 路由。设为 3 后产物仍是 `S01E01`。见 §2(a) |
| 4 | §15.4 键盘走查 | **通过** — 10/10。完整 Tab 一圈 52 个页内停靠点（5 行真实数据），顺序与清单逐项一致；51/52 有实心 accent 环（只有 wrap 边界的 `body` 没有）；Enter 切换源、`aria-expanded` 翻转、行内输入、确认对话框 12/12 Tab 不逃逸、Esc 回焦、chip 插入模板与 caret 位置（实测 `"AA{show}A BBB"`）全部符合。第 10 项**按设计只做到无障碍名管线**（`<table aria-label>`、滚动容器 `aria-busy` 实测 `null → "true" → null`），屏幕阅读器感知留给人 |
| 5 | §15.5 对比度抽检 | **通过** — 9/9 渲染值实测，两处易错点均正确：表头文字是 `ink-2`（对 `sunken` 6.89）而不是只有 4.23 的 `ink-3`；输入框边框是 `border-control`（3.19）而不是只有 1.52 的 `line-strong`。取样是在页面内用 canvas 把颜色落到 rgb 再算 WCAG 相对亮度，`oklab()`/`color-mix()` 骗不过解析器 |
| 6 | §15.6 reduced-motion | **通过** — 9/9。`.modal/.toast/.overlay/.row` 的过渡在 `reduce` 下全部收敛到 `1e-05s`，`animate-spin` 静止，`:active` 的 `scale(0.98)` **仍然生效**（瞬时而非消失，是有意取舍），媒体还原后可逆 |
| 7 | §15.7 响应式四档 | **通过** — 4/4。1280：`aside 280` + `main 1000`，表格内部滚动，整页 `scrollHeight − innerHeight = 0`；1024：表格内部横滚（`scrollW 836 / clientW 744`），整页不滚；768：左栏折叠**默认收起**（`aria-expanded="false"`），展开后 `aside h=405 = 45.0%`；375：表格横滚，首屏可见复选框与「原文件名」，底栏 `bottomGap 0` 且不换行（`bodyScrollW 375 === innerWidth`） |
| 8 | §15.8 长表格专项 | **通过** — `/tmp/er7-long` 328 文件（320 视频 + 8 字幕）。硬判据 `documentElement.scrollHeight − innerHeight` 在初始/滚动中/滚到底三次读数**全为 0**；6 次真实 `mouseWheel` 后 `scroller.scrollTop 0 → 2400`，而 `header/aside/main/footer` 位置全部不动；`thead` sticky 贴顶（`theadTop − scrollerTop = 0`） |
| 9 | §15.9 截图留档 | **通过** — 6/6 产出，尺寸从 PNG 头（bytes 16..24）读回：`after-home.png` 1280×900、`after-home-long-table.png` 1280×900、`after-home-rail-collapsed.png` 900×900、`after-mobile.png` 375×812、`after-settings.png` 1240×906、`after-browse.png` 523×545。三张改造前的图原样未动 |

**合计：7 项通过、1 项不适用（§15.3）、1 项部分通过（§15.2）。**

---

## 2. 未交付 / 未验证（如实记录）

### (a) 补零位数闭环（spec §13）**没有打通**

不是「这次没测」，是**后端那一半从未合入**：后端只从自己的 `app/config.py:29-30` 读
`episode_pad_digits` / `season_pad_digits`（`app/core/template.py` 用它们渲染
`{episode_padded}`），既没有 `/api/settings` 路由，也不接受前端传来的位数；前端的设置页
只写 `localStorage`。交付清单收尾表把这一行标成「✅ 端到端打通」是**乐观的**，以本记录为准。
（这同时是 `settingsSchema.js` 里 `[1,6]` 钳制目前是唯一防线的原因：服务端不做任何钳制。）

### (b) OpenList 的两条功能路径在本环境**无法验证**

不是「这次漏测」，是这个环境没有能力测。三重直接证据：

1. `curl -s -m 5` 打 `http://localhost:5244 / :3000 / :8080 / :5245` → 全部 `000`（连接被拒）。
2. 走真实后端往返：`POST /api/openlist/test {"server_url":"http://localhost:5244"}` →
   `{"success":false,"connected":false,"error":"OpenList 请求失败: All connection attempts failed"}`，`127.0.0.1` 同。
3. `ss -ltn` 只有 `:8000`（本任务的后端）、`:5173`（无关 vite）、`:631`（CUPS）；
   `docker ps` → `permission denied /var/run/docker.sock`；`which podman` / `openlist` / `alist` → 均未安装。

因此记 **「环境不可用，未验证」**，不记为通过。任何「OpenList 端到端可用」的结论都缺少本机直接证据。
（`after-browse.png` 用的是**本地**浏览对话框 —— 组件是同一个 `BrowseDialog`，OpenList 与本地走同一份 UI。）

### (c) 这套验证**不可重跑**

全部证据来自 `/tmp/er7/` 下的一次性 CDP 驱动，驱动脚本**从未进仓库**。仓库里只有两个 node
断言脚本（`check-sfc-compile.mjs`、`check-settings-schema.mjs`）。下一次改动前端时，这九项要么
重写一遍驱动，要么退回人工。这是「本项目无前端测试设施」（§4 遗留 3）的直接后果。

### (d) `§15.3` 与 `§15.2` 的判定不因后续修复而改变

修复轮（§3）改的是「季/集数字框裁切」，与 (a)(b)(c) 无关。

---

## 3. 评审后补正（2026-09-26）

分支的最终评审发现：季/集数字框在**本记录所引用的截图里**就把值渲染残了 ——
`after-home.png` 第 6 行的 `10` 渲染成 `1(`，328 行的 `after-home-long-table.png` 里每一行都被
裁短，375px 的 `after-mobile.png` 里两个字段**完全空白**。这属于 §15.9 的存档证据本身在宣传一个
缺陷，故修复轮重拍了三张图，并把实测更正记在这里：

| 位置 | 修复前（`aba9d96` 存档图，像素实测） | 修复后（重拍图，像素实测） |
|---|---|---|
| `after-home.png` 第 6 行「集」= `10` | 墨迹宽 **9px**（左缘起 886，右缘 894 —— 被原生上下箭头预留的空间截断） | 墨迹宽 **13px**（882→894，完整） |
| `after-home-long-table.png` 可见行「集」= `2xx` | 墨迹宽 **10–11px**（889→898） | 墨迹宽 **21–22px**（882→902/903，三位数完整） |
| `after-mobile.png` 375px「季/集」 | 输入框盒 x=128..149 / 182..203，内部**零墨迹**（完全空白） | 输入框 x 224..288（96px 列），值正常渲染 |

机制（在本机 Chromium 152 上逐个量过，不是估算）：`input[type=number]` 的原生
`::-webkit-inner-spin-button` 会预留 **15.5px** 的布局空间（48px 宽的 number 框里，文字的
右边界实测停在 content-box 右缘往左 15.5px 处）；13px 字体下 `24` 的墨迹宽 14px、`999` 为 21.5px。
所以 80px 的「集」列（输入框 48px、内宽 26px）留给文字的空间不足，两位数的集数被截断。
修复 = 掐掉 spinner（`[appearance:textfield]` + 两个伪元素的 `appearance-none`，
在产物 CSS 里逐条核过）+ 把列宽下限提到 96px（输入框内宽 42px，三位数有余）。

**一处对评审描述的更正：** 把列宽写成 `md:w-[96px]` 只解决 1280；375px 下这张表是「超约束」的
（`min-w-[560px]` > 视口），浏览器把各列压到最小内容宽，此时 `w-*` 是提示、会被**完全忽略**
（实测把 `w` 从 72 调到 128，列宽恒为 54 = 输入框最小内容宽 22 + `td` 的 32；内宽只剩 0 →
字段空白）。故 375 那一半必须用 `min-w-[96px]` 立下限，`md:w-[96px]` 才是宽表里的宽度提示。

---

## 4. spec §17 已知遗留（不在本轮范围，一并声明）

1. **`openlist.concurrency` / `requestInterval` 仍是假设置** —— 后端读 `config.py` 的
   `openlist_max_concurrent` / `openlist_request_interval`，设置页存的值不下发。设置页已就地
   标注（`SettingsView.vue` 的提示块）。
2. **无暗色主题** —— 全站只有一套浅色 token，`style.css` 里没有 `@media (prefers-color-scheme)`。
3. **无前端自动化测试设施** —— 本轮未引入测试框架；新增的自动化只有上述两个 node 断言脚本。
   本记录 §1 的九项验证**不可在 CI 重跑**（见 §2(c)）。
