# 前端重构 · 第一期：设计地基 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把设计地基铺好 —— 新 token 体系（含过渡别名层）、Geist 字体自托管、SVG 品牌标记、可访问的 `AppModal`、六个 UI 原语。本期结束时应用必须仍然可构建、可运行、旧界面在新配色下完全可读。

**Architecture:** `style.css` 一次性重写为新 token；同时保留一层**过渡别名**，把旧 token 名（`primary` / `text-text` / `border-border` …）映射到新值，让尚未改造的 11 个旧组件继续正常渲染。别名层在第四期（polish）全部组件迁移完成后删除。UI 原语是纯展示组件，本期**不接任何调用方**，只保证自身正确。

**Tech Stack:** Vue 3.5.43（`useId` 可用）/ Vite 5 / Tailwind CSS v4 / Pinia 2 / lucide-vue-next / @fontsource-variable

**Spec:** `docs/superpowers/specs/2026-09-25-frontend-refactor-design.md`（§5 token、§6 排版、§8.1–8.2 组件契约、§9 品牌标记、§16 阶段 1–2）

**上游计划:** `docs/superpowers/plans/2026-09-25-backend-pad-digits.md`（后端补零位数，已在第三期接线）

**本系列四期**

| 期 | 文件 | 覆盖 spec §16 阶段 |
|---|---|---|
| 1 | `2026-09-25-frontend-1-foundation.md`（本文） | 1–2 地基 + UI 原语 |
| 2 | `2026-09-25-frontend-2-shell.md` | 3 App Shell |
| 3 | `2026-09-25-frontend-3-features.md` | 4–6 业务组件 + 设置 store + 补零位数接线 |
| 4 | `2026-09-25-frontend-4-polish.md` | 7–8 收尾 + 全量验证 |

本文档内 `Task N` 均指本期任务；跨期引用一律写作「第二期 Task 3」。

---

## Global Constraints

以下约束来自 spec，四期全部适用，每个任务的验收都隐含包含本节。

- **字体族名必须是 `'Geist Variable'` 与 `'Geist Mono Variable'`**，不是 `Geist` / `Geist Mono`（spec §6.1 原文写的是后者，见下方「对 spec 的两处修正」）
- 字号只允许出现在阶梯上：`11px / 12px / 13px / 14px / 20px / 24px`（spec §6.3）。正文基准 `14px`
- 圆角只允许两种：控件（Button / Input / Select / Checkbox / Badge）`rounded-[8px]`；面板 / 模态 / 下拉 `rounded-[12px]`（spec §5.3）。**禁止** `rounded-md` / `rounded-lg` / `rounded-xl` / `rounded-2xl` / `rounded-full`
- **默认无阴影。** 唯一例外是浮层用的 `shadow-overlay`（spec §5.4）。禁止 `shadow-sm` / `shadow-lg` / `shadow-2xl`
- 全站唯一强调色 `--color-accent`（`#0F766E`）。**不使用绿色表达「成功」**（spec §5.2）
- 交互控件边框必须用 `border-border-control`（`#8A9199`）。`line` / `line-strong` **禁止**用于交互控件（spec §5.1）
- 禁用态统一 `opacity-45`，不新增更浅的文字 token（spec §5.1）
- 表格表头文字用 `text-ink-2`，**不得**用 `text-ink-3`（对 `sunken` 底仅 4.23:1，低于 AA）
- 路径与文件名**不用** `font-mono`（含中文，等宽下中文回退导致列对不齐，spec §6.2）。等宽只用于纯技术值：季数、集数、模板变量名、并发数、补零位数
- 不做暗色主题（spec §5.4）
- 每个任务结束时 `cd frontend && npm run build` 必须通过。任一阶段结束时应用都必须可构建可运行

### 对 spec 的两处修正

1. **§6.1 字体引入方式（按你的指示改）**：`geist@1.7.2` 是 Next.js 专用包（其 `next/font` 导出依赖 Next 构建链），**Vite 下不可用**。改用 `@fontsource-variable/geist` 与 `@fontsource-variable/geist-mono`（均为 5.3.0，OFL-1.1）。
   连带修正：fontsource 的 `@font-face` 声明的 `font-family` 是 **`Geist Variable`** / **`Geist Mono Variable`**（已解包核实，见下方「前期实测结论」）。若照抄 spec 的 `Geist`，浏览器匹配不到任何 `@font-face`，**静默**回退到 `PingFang SC`，整轮排版工作白做且零报错。字体栈按实际族名书写。

2. **§14「`index.html` → Geist 预加载」不实现**：Vite 会给 woff2 资源加内容哈希，`<link rel="preload">` 无法在 `index.html` 里写死路径。fontsource 的 CSS 已带 `font-display: swap`，且 `unicode-range` 保证浏览器只下载实际用到的子集（中文界面只需 latin + latin-ext，约 46 KB）。**不做**预加载，理由是收益为零、代价是一套构建期注入逻辑。

## Review Focus

以下是 spec 隐含、但没有任何现有检查会覆盖、且最可能咬到真实用户的输入与状态。每条的验证已挂到拥有该代码的任务里。

1. **字体族名不匹配**（本期最高风险）—— 若字体栈写成 `Geist`，浏览器静默回退，无任何报错，只有肉眼看排版才能发现。期望：构建产物 CSS 里出现 `Geist Variable`，`dist/assets/` 里有 `geist-latin-wght-normal-*.woff2`。→ Task 1
2. **模态打开态被卸载 / 三条关闭路径** —— Esc、点遮罩、点按钮都必须解锁 `body` 滚动并还原 `padding-right`；若只处理其中一条，页面会永久失去滚动或侧栏横向跳动。→ Task 5
3. **模态内没有可聚焦元素** —— 例如只放一行文字的提示框。Tab 必须仍被钉在模态内（焦点落在 `tabindex="-1"` 的面板上），不能漏到背后的页面。→ Task 5
4. **焦点归位到已卸载的触发元素** —— 触发按钮在模态打开期间被 `v-if` 移除（FileTable「清空」正是这种），关闭时 `focus()` 必须不抛错。→ Task 5
5. **`opacity-45` 已不在默认刻度记忆里** —— 禁用态若混入 `opacity-50`，全站禁用强度不一致；且 `disabled:opacity-45` 必须真的生成（v4 才有 45 这一档）。→ Task 6、Task 7

---

## 前期实测结论

以下均已在本机实测（Tailwind v4.3.3 + Vite 5.4.21 + Vue 3.5.43），**实现时直接采用，不必重新验证**；但如果你的改动让其中任何一条不再成立，说明改动方向错了。

| 结论 | 实测方式 |
|---|---|
| `--color-*` 新 token 全部生成对应工具类（`bg-canvas` / `text-ink-2` / `border-border-control` / `ring-offset-canvas` / `divide-line` …） | 构建后 grep 产物 CSS，全部命中 |
| `--shadow-overlay` 在 `@theme` 里可用，生成 `.shadow-overlay` | 同上，展开为 `box-shadow: var(--tw-inset-shadow), …` |
| **过渡别名层可行**：`--color-primary: var(--color-accent)` 写在 `@theme` 里会被原样输出为 CSS 变量，运行时解析正常；旧类名 `bg-primary` / `text-text` / `border-border` / `bg-success-light` 全部照常生成 | 同上 |
| `@fontsource-variable/geist` 的族名是 `Geist Variable`，mono 是 `Geist Mono Variable`；入口 `.` → `index.css`（含全部子集，各带 `unicode-range`） | 解包 5.3.0 tarball 读 `index.css` |
| Vite 会把 11 个 woff2 全部落盘到 `dist/assets/` 并改写 CSS 里的 `url()`（总计 176 KB，浏览器按 `unicode-range` 只取 latin 29 KB + latin-ext 17 KB） | 起一个最小 Vite 工程实测构建 |
| `opacity-45` 与 `disabled:opacity-45` 在 v4 存在并生成 | 构建后 grep |
| `peer` / `peer-checked:opacity-100` / `peer-focus-visible:ring-2` / `checked:bg-accent` / `appearance-none` / `accent-accent` / `bg-ink/40` / `ring-accent/35` / `placeholder:text-ink-3` / `sr-only` / `-translate-y-1/2` / `grid-cols-[280px_1fr]` 全部生成 | 构建后 grep |
| 当前基线：18 处手写输入框样式（5 个文件）、`focus-visible` 0 处、`aria-` 0 处、`prefers-reduced-motion` 0 处、`shadow-sm` 6 处、emoji 4 处、`font-mono` 8 处 | `grep -rn` 实测 |
| `frontend/src/` 下除 `style.css` 外**没有任何**硬编码十六进制色、也没有直接 `var(--color-*)` 引用 | `grep -rnE "#[0-9A-Fa-f]{3,8}"` 实测 |
| `frontend/public/` **不存在**，需本期创建 | `ls` 实测 |

---

## File Structure

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `frontend/package.json` | 前端依赖清单 | 新增两个 fontsource 包 |
| `frontend/src/main.js` | 应用入口 | 引入两组字体 CSS |
| `frontend/src/style.css` | 设计 token + 全局基线 | **重写**：新 token、字体栈、过渡别名层 |
| `frontend/index.html` | HTML 外壳 | favicon 由 emoji data-URI 换成 `/favicon.svg` |
| `frontend/public/favicon.svg` | 站点图标 | 新建 |
| `frontend/src/components/BrandMark.vue` | 品牌标记（方框 + 重命名箭头） | 新建 |
| `frontend/src/components/ui/AppModal.vue` | 模态基座：焦点陷阱 / Esc / 滚动锁 / 焦点归位 / aria | **重写** |
| `frontend/src/components/ui/AppButton.vue` | 按钮原语，4 变体 × 2 尺寸 | 新建 |
| `frontend/src/components/ui/AppInput.vue` | 输入框原语，label / hint / error / mono | 新建 |
| `frontend/src/components/ui/AppSelect.vue` | 下拉原语 | 新建 |
| `frontend/src/components/ui/AppCheckbox.vue` | 复选框原语 | 新建 |
| `frontend/src/components/ui/AppBadge.vue` | 状态徽章统一入口，4 tone | 新建 |
| `frontend/src/components/ui/AppPanel.vue` | 发丝线容器，替代「卡片」 | 新建 |
| `frontend/src/App.vue` | 应用外壳 | 仅替换侧栏 emoji（整体重写在第二期） |

---

### Task 1: Geist 字体自托管接入

装字体、引入 CSS、把字体栈切成 Geist + 中文回退。**只动字体相关行**，`style.css` 的 token 重写在 Task 2，两个任务各有一个独立提交点。

**Files:**
- Modify: `frontend/package.json`（用 `npm i` 写入）
- Modify: `frontend/src/main.js:1-13`
- Modify: `frontend/src/style.css:26-27`（`--font-sans` / `--font-mono` 两行）

**Interfaces:**
- Consumes: 无
- Produces: 全站可用的 `Geist Variable` / `Geist Mono Variable` 字体族；`--font-sans` / `--font-mono` 两个 token（Task 2 重写 `style.css` 时**必须原样保留**这两行）

- [ ] **Step 1: 安装字体包**

```bash
cd frontend && npm i @fontsource-variable/geist @fontsource-variable/geist-mono
```

预期：`package.json` 的 `dependencies` 新增两行（均为 `^5.3.0`）。

**不要装 `geist`** —— 那是 Next.js 专用包，其 `next/font` 入口在 Vite 下无法解析。

- [ ] **Step 2: 在入口引入字体 CSS**

把 `frontend/src/main.js` 改为（`import './style.css'` 必须留在最后，见 Step 4 的说明）：

```js
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'

import './style.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.mount('#app')
```

- [ ] **Step 3: 切字体栈**

编辑 `frontend/src/style.css`，把 `--font-sans` 与 `--font-mono` 两行（第 26–27 行）改为：

```css
  /* fontsource 声明的族名是 "Geist Variable" / "Geist Mono Variable"，不是 "Geist"。
     照抄 "Geist" 会静默回退到中文字体，且没有任何报错。 */
  --font-sans: "Geist Variable", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
               "Noto Sans SC", system-ui, -apple-system, sans-serif;
  --font-mono: "Geist Mono Variable", "JetBrains Mono", ui-monospace,
               "SFMono-Regular", Menlo, monospace;
```

`Geist` **无中文字形**，所以中文回退链不能省 —— 拉丁字符走 Geist，中文回退系统无衬线。

- [ ] **Step 4: 构建并校验字体真的进了产物**

```bash
cd frontend && npm run build && \
  ls dist/assets/geist-latin-wght-normal-*.woff2 && \
  grep -o "Geist Variable" dist/assets/*.css | sort -u && \
  grep -o "Geist Mono Variable" dist/assets/*.css | sort -u
```

预期：
- `ls` 打印出形如 `dist/assets/geist-latin-wght-normal-XXXXXXXX.woff2`（**必须存在**，不存在说明字体包没被引入）
- 两条 grep 各打印出 `Geist Variable` 与 `Geist Mono Variable`

若 `ls` 报「没有那个文件或目录」：检查 Step 1 是否真的装了两个包、Step 2 的两条 import 是否写在 `./style.css` **之前**。

- [ ] **Step 5: 视觉确认字体已生效**

```bash
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173/`，DevTools → Network → 过滤 `woff2`，刷新页面。

预期：加载了 `geist-latin-wght-normal-*.woff2` 与 `geist-mono-latin-wght-normal-*.woff2`（各约 29 KB / 23 KB）。**不会**加载 cyrillic / vietnamese 子集 —— `unicode-range` 会挡掉。

再在 Console 里执行 `getComputedStyle(document.body).fontFamily`，预期以 `"Geist Variable"` 开头。

- [ ] **Step 6: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/main.js frontend/src/style.css
git commit -m "feat(frontend): 自托管 Geist 字体并切换字体栈"
```

---

### Task 2: 设计 token 全量重写 + 过渡别名层

把 `style.css` 换成本设计的新 token 体系，并加一层**临时**别名把旧 token 名映射到新值 —— 这样第二、三期逐个改造组件时，未改造的组件仍然正常渲染，应用全程可构建可运行。

**Files:**
- Modify: `frontend/src/style.css`（整文件重写，但保留 Task 1 写好的两行字体 token）

**Interfaces:**
- Consumes: `--font-sans` / `--font-mono`（Task 1）
- Produces: 新 token，供第二、三、四期使用 ——
  - 背景：`canvas` `surface` `sunken`
  - 边界：`line` `line-strong` `border-control`
  - 文字：`ink` `ink-2` `ink-3`
  - 强调：`accent` `accent-hover` `accent-soft`
  - 语义：`warn` `warn-soft` `danger` `danger-hover` `danger-soft`
  - 阴影：`shadow-overlay`
  - 过渡别名：`primary` `primary-hover` `primary-light` `bg` `surface-muted` `border` `border-strong` `text` `text-secondary` `text-muted` `text-faint` `success` `success-light` `warning` `warning-light` `error` `error-light`（**第四期删除**）

- [ ] **Step 1: 重写 `frontend/src/style.css`**

整文件替换为（`--font-sans` / `--font-mono` 沿用 Task 1 的内容）：

```css
@import "tailwindcss";

/* 已跟踪的 frontend/dist 会被 Tailwind 自动扫描（它不在 .gitignore 里），
   把上一版构建出的类名当成候选，产出 .hidden/.static/.table/.filter 这类
   幽灵工具类，并且让产物大小随 dist 是否存在而变 —— 构建因此不确定。
   显式排除掉它。src/ 与 index.html 仍在自动扫描范围内。 */
@source not "../dist";

/* static 修饰符：无条件发射下面这些变量，即使没有任何源码引用它们。
   默认（非 static）下 Tailwind v4 会 tree-shake 掉未被引用的主题变量 ——
   实测 4.3.3 下 --color-danger-hover 与 --shadow-overlay 会因此缺席 :root。
   这两个 token 迟早会被用到（前者是 danger 按钮的 hover，后者是模态/浮层的
   阴影），而设计 token 作为「系统的公开接口」不该取决于谁碰巧用了它 ——
   组件 <style> 块里的 var(--shadow-overlay) 引用一旦遇上 tree-shaking 就是
   静默失效。代价实测为 2 个变量、百字节级（本仓库 +98 字节）。 */
@theme static {
  /* ---------- 背景三级：用明度差做层级，不用阴影 ---------- */
  --color-canvas:  #F6F7F8;  /* 页面底，比纯白低一档 */
  --color-surface: #FFFFFF;  /* 面板 / 表格底 */
  --color-sunken:  #EDEFF1;  /* 凹陷：表头、代码块、骨架 */

  /* ---------- 边界三级：角色不同，不可互换 ----------
     line / line-strong 只做装饰性分隔，对白底 1.52:1，做 input 边框不合格。
     border-control 对白底 3.19:1，满足 WCAG 1.4.11 非文本对比度 3:1。 */
  --color-line:           #E2E5E8;
  --color-line-strong:    #CDD2D7;
  --color-border-control: #8A9199;

  /* ---------- 文字三级：无第四级；禁用态用 opacity-45 ---------- */
  --color-ink:   #15181B;
  --color-ink-2: #4B5257;
  --color-ink-3: #6B7278;

  /* ---------- 强调：全站唯一 ---------- */
  --color-accent:       #0F766E;
  --color-accent-hover: #0B5F59;
  --color-accent-soft:  #E6F4F2;

  /* ---------- 语义：只留告警与危险 ----------
     强调色占用了绿系，「成功」不再用绿色表达，见 spec §5.2。 */
  --color-warn:         #8A5F00;
  --color-warn-soft:    #FDF6E3;
  --color-danger:       #B3261E;
  --color-danger-hover: #8E1D17;
  --color-danger-soft:  #FDECEA;

  /* ---------- 字体 ----------
     fontsource 声明的族名是 "Geist Variable" / "Geist Mono Variable"，不是 "Geist"。
     照抄 "Geist" 会静默回退到中文字体，且没有任何报错。 */
  --font-sans: "Geist Variable", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
               "Noto Sans SC", system-ui, -apple-system, sans-serif;
  --font-mono: "Geist Mono Variable", "JetBrains Mono", ui-monospace,
               "SFMono-Regular", Menlo, monospace;

  /* ---------- 阴影：只有真正浮起于内容之上的元素才用 ---------- */
  --shadow-overlay: 0 8px 28px -6px rgb(21 24 27 / 0.14), 0 2px 6px -2px rgb(21 24 27 / 0.08);
}

/* ==========================================================================
   过渡别名层 —— 第四期删除
   --------------------------------------------------------------------------
   第二、三期会逐个组件改用上面的新 token 名。在那之前，这一层让仍未改造的
   11 个旧组件继续正常工作，使「每一期结束应用都可构建可运行」成立。

   映射中两处是有意的降级，不是随手对应：
     success / success-light → ink-2 / sunken   让出绿系给强调色（spec §5.2）
     text-faint              → ink-3            文字只有三级，禁用态靠 opacity-45

   删除前提：第四期 Task 8 的 grep 校验必须零命中。
   ========================================================================== */
/* 注意：这一块**不加** static —— 它是第四期要删除的过渡脚手架，
   按需发射正好：旧组件用到哪个别名就发射哪个，删掉之后不留残留。 */
@theme {
  --color-primary:        var(--color-accent);
  --color-primary-hover:  var(--color-accent-hover);
  --color-primary-light:  var(--color-accent-soft);
  --color-bg:             var(--color-canvas);
  --color-surface-muted:  var(--color-sunken);
  --color-border:         var(--color-line);
  --color-border-strong:  var(--color-line-strong);
  --color-text:           var(--color-ink);
  --color-text-secondary: var(--color-ink-2);
  --color-text-muted:     var(--color-ink-3);
  --color-text-faint:     var(--color-ink-3);
  --color-success:        var(--color-ink-2);
  --color-success-light:  var(--color-sunken);
  --color-warning:        var(--color-warn);
  --color-warning-light:  var(--color-warn-soft);
  --color-error:          var(--color-danger);
  --color-error-light:    var(--color-danger-soft);
}

html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-ink);
  background: var(--color-canvas);
  -webkit-font-smoothing: antialiased;
}

* {
  box-sizing: border-box;
}

button {
  font-family: inherit;
}

input, select, textarea {
  font-family: inherit;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--color-line-strong);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--color-border-control);
}
```

注意：**不要**保留 `--color-secondary: #7C3AED` —— 它是零引用的死 token（spec §3.2 第 9 条）。

- [ ] **Step 2: 构建并校验**变量**都落到 `:root`**

```bash
cd frontend && rm -rf dist && npm run build && \
  grep -oE -- "--color-(canvas|surface|sunken|line|line-strong|border-control|ink|ink-2|ink-3|accent|accent-hover|accent-soft|warn|warn-soft|danger|danger-hover|danger-soft):[^;}]*" dist/assets/*.css | sort -u && \
  echo "--- 阴影与字体 ---" && \
  grep -oE -- "--(shadow-overlay|font-sans|font-mono):[^;}]*" dist/assets/*.css | sort -u
```

预期：**17 条** `--color-*` 变量 + **3 条**阴影/字体变量，一条不少，全部非空。例如应看到 `--color-accent:#0f766e`、`--color-sunken:#edeff1`、`--color-border-control:#8a9199`、`--color-danger-hover:#8e1d17`、`--shadow-overlay:0 8px 28px -6px …`。

**为什么查的是「变量」而不是「工具类」** —— Tailwind v4 只为在源码里出现过的候选类名生成工具类。本期只改 `style.css`，还没有任何组件使用新 token，所以下面这些工具类此时**必然是 `0`**，这是正常的：

```bash
# 全为 0 是正确的 —— 新 token 要到 Task 3 起的组件改造才会被用到
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
  for c in "bg-canvas" "text-ink-2" "border-border-control" "bg-sunken" "bg-accent"; do
  printf "%-34s %s\n" "$c" "$(sed 's/\\//g' dist/assets/*.css | grep -oF -- "$c" | wc -l)"
  done
```

**不要去「修」这些 0** —— 它们不是错误。若你去改 `@theme` 里的 token 名来「让它们出现」，会破坏后面所有任务。

**为什么要 `rm -rf dist` 再构建** —— `frontend/dist` 被 git 跟踪、不在 `.gitignore` 里，Tailwind 会自动扫描它，把上一版构建产出的类名当候选，多出 `.hidden` / `.static` / `.table` / `.filter` 这类幽灵工具类，并让产物大小依赖于「dist 是否存在」。快照里的 `@source not "../dist";` 已经从根上排除它，这条 `rm -rf dist` 是双保险，也让本步的产物计数可复现。

**为什么 token 块用 `@theme static`** —— 实测 Tailwind 4.3.3 默认会 tree-shake 掉没有任何源码引用的主题变量：不写 `static` 时 `--color-danger-hover` 与 `--shadow-overlay` **不会**出现在 `:root`（这两个此时恰好无人引用，其余变量都因别名块的 `var()` 引用而幸存）。设计 token 是系统的公开接口，不该取决于谁碰巧用了它 —— 组件 `<style>` 块里的 `var(--shadow-overlay)` 一旦遇上 tree-shaking 就是静默失效。`static` 的代价实测为 2 个变量、72 字节，而**工具类仍然按需生成**，不会因此膨胀。

- [ ] **Step 3: 确认过渡别名既生成工具类、又能在运行时可解析**

```bash
cd frontend && echo "--- 别名的工具类必须存在（旧组件还在用）---" && \
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
  for c in "bg-accent" "hover:bg-accent-hover" "bg-danger" "hover:bg-danger-hover" \
           "border-line-strong" "bg-sunken" "rounded-[8px]" "whitespace-nowrap" \
           "active:scale-[.98]" "disabled:opacity-45" "ring-offset-canvas"; do
    n=$(sed 's/\\//g' dist/assets/*.css | grep -oF -- "$c" | wc -l)
    printf "%-34s %s\n" "$c" "$n"
  done
```

预期：全部 ≥ `1`。

**这是本期唯一能自动发现的失败模式**：类名拼错时 Tailwind 不会报错，只是不生成这条规则，按钮会静默少一个变体样式。任何一个为 `0` 就必须修正拼写。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ui/AppButton.vue
git commit -m "feat(frontend): 新增 AppButton 按钮原语"
```

---

### Task 5: AppModal 重写（焦点陷阱 / Esc / 滚动锁 / 焦点归位 / aria）

当前 `AppModal.vue` 只有遮罩和过渡，`role="dialog"`、Esc、焦点陷阱、滚动锁、焦点归位**全部缺失**（spec §3.4）。三个对话框（`ConfirmDialog` / `ResultDialog` / `BrowseDialog`）都建立在它之上，所以必须先修基座。

**Files:**
- Modify: `frontend/src/components/ui/AppModal.vue`（整文件重写）

**Interfaces:**
- Consumes: 新 token `ink`（遮罩色 `bg-ink/40`）
- Produces:
  ```js
  props: {
    modelValue: Boolean      // v-model
    title: String            // 无障碍名；有值时渲染 sr-only <h2> 并作为 aria-labelledby
    zIndex: Number | String  // default 50
    closeOnOverlay: Boolean  // default true
  }
  emits: ['update:modelValue']
  ```
  默认插槽放对话框卡片本体，样式（尺寸 / `rounded-[12px]` / `shadow-overlay`）由调用方负责 —— 三个对话框的宽度各不相同（420 / 700 / 520px），宽度不能由基座决定
- **破坏性变更**：删掉了旧的 `backdrop` 与 `backdropBlur` 两个 prop（当前三个调用方都没传）。旧代码里也 emit 的 `close` 事件一并删除，只保留 `update:modelValue`
- 第三期三个对话框改造、第四期 aria 补全都依赖它

- [ ] **Step 1: 重写 `frontend/src/components/ui/AppModal.vue`**

```vue
<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="modelValue"
        class="fixed inset-0 flex items-center justify-center bg-ink/40 p-4"
        :style="{ zIndex }"
        @click="onOverlayClick"
      >
        <div
          ref="panelRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="title ? titleId : undefined"
          tabindex="-1"
          class="flex w-full justify-center outline-none"
        >
          <h2 v-if="title" :id="titleId" class="sr-only">{{ title }}</h2>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  zIndex: { type: [Number, String], default: 50 },
  closeOnOverlay: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const panelRef = ref(null)
const titleId = `modal-title-${useId()}`

let triggerEl = null
let prevOverflow = ''
let prevPaddingRight = ''

function focusableNodes() {
  if (!panelRef.value) return []
  // getClientRects().length === 0 的元素（display:none / 未布局）不可聚焦，
  // 必须排除，否则陷阱会把焦点扔到一个收不到的节点上，Tab 看起来「卡死」。
  return Array.from(panelRef.value.querySelectorAll(FOCUSABLE)).filter(
    (el) => el.getClientRects().length > 0,
  )
}

function lockScroll() {
  const gap = window.innerWidth - document.documentElement.clientWidth
  prevOverflow = document.body.style.overflow
  prevPaddingRight = document.body.style.paddingRight
  document.body.style.overflow = 'hidden'
  // 补上滚动条宽度，否则锁定瞬间整页会横向跳一下
  if (gap > 0) document.body.style.paddingRight = `${gap}px`
}

function unlockScroll() {
  document.body.style.overflow = prevOverflow
  document.body.style.paddingRight = prevPaddingRight
}

function close() {
  emit('update:modelValue', false)
}

function onOverlayClick(event) {
  if (!props.closeOnOverlay) return
  // 面板外层是 w-full 的居中容器，点卡片左右两侧的空白命中的是「面板本身」
  // 而不是遮罩。这两种位置都应当视为「点了外部」，所以不能简单用 @click.self。
  if (panelRef.value && event.target !== panelRef.value && panelRef.value.contains(event.target)) {
    return
  }
  close()
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab' || !panelRef.value) return

  const nodes = focusableNodes()
  if (nodes.length === 0) {
    // 模态内一个可聚焦元素都没有（例如纯提示框）时，把焦点钉在面板上，
    // 不让它漏到背后的页面。
    event.preventDefault()
    panelRef.value.focus()
    return
  }

  const first = nodes[0]
  const last = nodes[nodes.length - 1]
  const active = document.activeElement
  const inside = panelRef.value.contains(active)

  if (event.shiftKey && (active === first || !inside)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !inside)) {
    event.preventDefault()
    first.focus()
  }
}

function onOpen() {
  triggerEl = document.activeElement instanceof HTMLElement ? document.activeElement : null
  lockScroll()
  document.addEventListener('keydown', onKeydown, true)
  nextTick(() => {
    const nodes = focusableNodes()
    if (nodes.length) nodes[0].focus()
    else panelRef.value?.focus()
  })
}

function onClose() {
  document.removeEventListener('keydown', onKeydown, true)
  unlockScroll()
  // 触发元素可能在模态打开期间被 v-if 卸载（FileTable 的「清空」就是这种情况），
  // 所以必须先确认它还在文档里。
  if (triggerEl && document.contains(triggerEl)) triggerEl.focus()
  triggerEl = null
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) onOpen()
    else onClose()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown, true)
  if (props.modelValue) unlockScroll()
})
</script>

<style>
/* 模态进出 200ms —— spec §11 的动效表。只做透明度与极小的位移，
   意图是「让用户看清层级来自哪里」，不做弹跳。 */
.modal-enter-active {
  transition: opacity 0.2s ease-out;
}
.modal-enter-active > * {
  transition: opacity 0.2s ease-out, transform 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.modal-leave-active {
  transition: opacity 0.15s ease-in;
}
.modal-leave-active > * {
  transition: opacity 0.13s ease-in, transform 0.13s ease-in;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from > * {
  opacity: 0;
  transform: scale(0.96) translateY(6px);
}
.modal-leave-to > * {
  opacity: 0;
  transform: scale(0.98) translateY(-3px);
}
</style>
```

几处不是随手写的：

- `keydown` 监听挂在 `document` 上并用**捕获阶段**（第三个参数 `true`）—— 因为模态内的输入框可能 `stopPropagation`，挂在自己节点上的监听会漏掉 Esc。
- `useId()` 生成 `aria-labelledby` 的目标 id —— 页面上可能有多个模态实例，硬编码 id 会互相覆盖。
- **没有** `Teleport` 之外的重排 —— `Teleport to="body"` 是为了避免模态被祖先元素的 `transform`（过渡动画会产生）劫持 `position: fixed` 的包含块。
- 过渡曲线从原来的 `scale(0.94) translateY(8px)` 收紧到 `scale(0.96) translateY(6px)` —— spec §11 把 modal 动效定为「状态转换：层级来源」，幅度过大会变成装饰。

- [ ] **Step 2: 构建并确认三个调用方未受影响**

```bash
cd frontend && npm run build && \
  grep -rn "backdrop\|backdropBlur\|@close" src/components/ConfirmDialog.vue src/components/ResultDialog.vue src/components/BrowseDialog.vue
```

预期：`npm run build` 通过；`grep` **无输出**（退出码 1）—— 证明删掉的 `backdrop` / `backdropBlur` 两个 prop 和 `close` 事件确实没有调用方。

若有输出，说明还有文件依赖被删的 API，先修正调用方再继续。

- [ ] **Step 3: 逐条走查第 2–4 号 Review Focus**

```bash
cd frontend && npm run dev
```

打开 `http://localhost:5173/`，先扫描一个目录（左栏有「点击浏览选择目录」，或直接填一个含视频的路径）让表格出现，然后点表格右上角的「清空」触发 `ConfirmDialog`。

| # | 操作 | 预期 |
|---|---|---|
| 1 | 打开模态后滚轮上下滚 | 背后页面**不动**（滚动锁生效） |
| 2 | 按 `Tab` 循环 | 焦点在「取消」与「确定」之间循环，**不会**跑到背后的侧栏导航上 |
| 3 | 按 `Esc` | 模态关闭 |
| 4 | 关闭后看焦点 | 焦点回到「清空」按钮上（按一次 `Enter` 会重新打开模态即为正确） |
| 5 | 重新打开，点卡片**左侧空白处**（不是卡片上） | 模态关闭（这是 `contains` 判断那条分支） |
| 6 | 重新打开，点卡片**内部**输入区 | 模态**不**关闭 |
| 7 | 关闭后滚动页面 | 页面可正常滚动（滚动锁已解除） |
| 8 | 打开模态前后对比侧栏位置 | 侧栏**不横向跳动**（`padding-right` 已补） |

**第 4 条（焦点归位到已卸载的触发元素）单独构造一次：**

先在 Console 里执行下面这段，把「清空」按钮在模态打开期间移除，再关闭模态，确认控制台无报错：

```js
const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('清空'))
btn.click()                                // 打开模态
const card = document.querySelector('[role="dialog"]')
setTimeout(() => btn.remove(), 200)        // 模拟触发元素被卸载
setTimeout(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })), 500)
```

预期：模态关闭，Console **无** `TypeError` / `Failed to execute 'focus'` 报错。

**第 3 条（模态内无可聚焦元素）单独构造一次：**

```js
// 在模态打开状态下，把内部所有可聚焦元素禁用，再按 Tab
document.querySelectorAll('[role="dialog"] button').forEach(b => b.disabled = true)
```

然后按 `Tab`。

预期：焦点停在 `[role="dialog"]` 面板上（`document.activeElement.getAttribute('role') === 'dialog'`），不会漏到背景。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/ui/AppModal.vue
git commit -m "fix(frontend): AppModal 补齐焦点陷阱 / Esc / 滚动锁 / 焦点归位 / aria"
```

---

### Task 6: AppInput + AppSelect 表单控件原语

当前输入框样式手写 **18 处**（实测：SettingsView 7 / ScanPanel 4 / TemplateConfig 3 / FileTable 3 / ActionBar 1），是本项目最大的一块复制粘贴债务。这两个原语是第三期清零该债务的工具。

**Files:**
- Create: `frontend/src/components/ui/AppInput.vue`
- Create: `frontend/src/components/ui/AppSelect.vue`

**Interfaces:**
- Consumes: 新 token `surface` `border-control` `ink` `ink-2` `ink-3` `accent` `danger` `canvas`（Task 2）
- Produces:
  ```js
  // AppInput
  props: {
    modelValue: String | Number | null   // v-model
    label: String        // 渲染在控件上方
    hint: String         // 控件下方辅助说明
    error: String        // 控件下方错误说明，优先于 hint
    type: String         // 'text' | 'number' | 'password'，default 'text'
    mono: Boolean        // 仅纯技术值设为 true
    disabled: Boolean
    placeholder: String
    min: String | Number
    max: String | Number
    step: String | Number
    id: String           // 可选，覆盖自动生成的 id
  }
  emits: ['update:modelValue']

  // AppSelect —— 同构但**不做** hint / error / placeholder / ariaLabel：
  // spec §8.2 只给了 AppInput 的契约；这三期的 AppSelect 调用点（顶栏挂载点、
  // 底栏冲突策略、设置页默认模板 / 冲突策略）一个都用不到它们。
  // ariaLabel 由第二期 Task 3 Step 2 在第一个真正需要它的调用点引入。
  props: { modelValue, label, disabled, id }
  emits: ['update:modelValue']
  ```
- **`AppInput` 在 `type="number"` 下清空输入框会 emit `null`，不是 `0`，也不是空字符串。** 第三期补零位数接线依赖这一点：`null` 一路传到后端 `Optional[int]`，语义是「用服务端默认值」；若传 `0`，后端会把它钳到 `1`，界面显示与实际生效值不一致
- 第三期所有表单改造、第四期表单错误态都依赖它

- [ ] **Step 1: 创建 `frontend/src/components/ui/AppInput.vue`**

```vue
<template>
  <div class="flex flex-col gap-2">
    <label v-if="label" :for="inputId" class="text-[13px] font-medium text-ink-2">{{ label }}</label>
    <input
      :id="inputId"
      :type="type"
      :value="modelValue ?? ''"
      :placeholder="placeholder"
      :disabled="disabled"
      :min="min"
      :max="max"
      :step="step"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedById"
      class="h-9 w-full rounded-[8px] border border-border-control bg-surface px-3 text-[13px] text-ink transition-colors duration-150 outline-none placeholder:text-ink-3 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35 disabled:opacity-45 disabled:cursor-not-allowed"
      :class="[mono ? 'font-mono' : '', error ? 'border-danger' : '']"
      @input="onInput"
    />
    <p v-if="error" :id="`${inputId}-error`" class="text-[12px] text-danger">{{ error }}</p>
    <p v-else-if="hint" :id="`${inputId}-hint`" class="text-[12px] text-ink-3">{{ hint }}</p>
  </div>
</template>

<script setup>
import { computed, useId } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  type: { type: String, default: 'text' },
  mono: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
  min: { type: [String, Number], default: undefined },
  max: { type: [String, Number], default: undefined },
  step: { type: [String, Number], default: undefined },
  id: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const generatedId = useId()
const inputId = computed(() => props.id || `input-${generatedId}`)

const describedById = computed(() => {
  if (props.error) return `${inputId.value}-error`
  if (props.hint) return `${inputId.value}-hint`
  return undefined
})

function onInput(event) {
  const raw = event.target.value
  if (props.type !== 'number') {
    emit('update:modelValue', raw)
    return
  }
  // 清空数字框必须得到 null（= 用服务端默认值），不能是 0。
  // 若给 0，后端 PadConfig 会把它钳到 1，界面显示 0 而实际补零 1 位，两侧不一致。
  emit('update:modelValue', raw === '' ? null : Number(raw))
}
</script>
```

几处不是随手写的：

- **label 在控件上方**，禁用 placeholder 充当 label（spec §8.2，来自技能 4.6 的硬规则）。
- `gap-2` 的控制块间距 —— spec §8.2 明确要求。
- `border-border-control` 而非 `border-line-strong` —— 后者对白底仅 1.52:1，做控件边框不满足 WCAG 1.4.11 的 3:1（spec §5.1）。
- `focus-visible:border-accent` + `ring-accent/35` —— 输入框的聚焦环不用 `ring-offset-2` 的「双环」样式（那是按钮的），否则 13px 高的控件会被 2px 间隙的环包得过于笨重。
- `error` 与 `hint` 互斥且顺序固定 —— 用 `v-if` / `v-else-if` 保证同时只渲染一条，避免 `aria-describedby` 指向两个 id 而屏幕阅读器读两遍。
- `:value="modelValue ?? ''"` —— 让 `null` 显示为空，而不是字符串 `"null"`。

- [ ] **Step 2: 创建 `frontend/src/components/ui/AppSelect.vue`**

```vue
<template>
  <div class="flex flex-col gap-2">
    <label v-if="label" :for="selectId" class="text-[13px] font-medium text-ink-2">{{ label }}</label>
    <div class="relative">
      <select
        :id="selectId"
        :value="modelValue"
        :disabled="disabled"
        class="h-9 w-full appearance-none rounded-[8px] border border-border-control bg-surface pl-3 pr-8 text-[13px] text-ink transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35 disabled:opacity-45 disabled:cursor-not-allowed"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <slot />
      </select>
      <ChevronDown
        class="pointer-events-none absolute top-1/2 right-2.5 h-4 w-4 -translate-y-1/2 text-ink-3"
        aria-hidden="true"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, useId } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  id: { type: String, default: '' },
})
defineEmits(['update:modelValue'])

const generatedId = useId()
const selectId = computed(() => props.id || `select-${generatedId}`)
</script>
```

`appearance-none` + 自绘 `ChevronDown` 是必要的：原生 select 的下拉箭头由浏览器绘制，各平台大小与颜色都不同，在 8px 圆角体系里会显得格格不入。`pointer-events-none` 让点击穿透到 select 上。

**注意：`AppSelect` 本任务先不写 `ariaLabel`。** 它由第二期 Task 3 Step 2 引入 —— 那是第一个需要它（无可见 label 的底栏冲突策略下拉）的调用点。第一期在这里预先写一个没人用的 prop 没有意义。

- [ ] **Step 3: 构建并校验类名与结构**

```bash
cd frontend && npm run build && \
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
  for c in "border-border-control" "placeholder:text-ink-3" "ring-accent/35" "focus-visible:border-accent" \
           "appearance-none" "pr-8" "-translate-y-1/2" "text-ink-2" \
           "text-ink-3" "text-danger"; do
    n=$(sed 's/\\//g' dist/assets/*.css | grep -oF -- "$c" | wc -l)
    printf "%-34s %s\n" "$c" "$n"
  done
```

预期：全部 ≥ `1`。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/ui/AppInput.vue frontend/src/components/ui/AppSelect.vue
git commit -m "feat(frontend): 新增 AppInput 与 AppSelect 原语"
```

---

### Task 7: AppCheckbox + AppBadge + AppPanel 原语

收尾剩下的三个原语。三者都小，合成一个任务、一道评审门。

**Files:**
- Create: `frontend/src/components/ui/AppCheckbox.vue`
- Create: `frontend/src/components/ui/AppBadge.vue`
- Create: `frontend/src/components/ui/AppPanel.vue`

**Interfaces:**
- Consumes: 新 token `surface` `sunken` `line` `border-control` `ink` `ink-2` `ink-3` `accent` `warn` `warn-soft` `danger` `danger-soft` `accent-soft` `canvas`（Task 2）
- Produces:
  ```js
  // AppCheckbox
  props: { modelValue: Boolean, label: String, disabled: Boolean }
  emits: ['update:modelValue']

  // AppBadge
  props: { tone: 'neutral' | 'accent' | 'warn' | 'danger' }   // default 'neutral'
  // 默认插槽放文字；具名插槽 #icon 放前置图标

  // AppPanel
  props: { title: String }
  // 默认插槽放内容。刻意没有 actions 插槽 —— 见 Task 7 Step 3 的说明
  ```
- 第三期 FileTable 的状态徽章、左栏面板、各复选框改造都依赖它

- [ ] **Step 1: 创建 `frontend/src/components/ui/AppCheckbox.vue`**

```vue
<template>
  <label
    class="inline-flex items-center gap-2 select-none"
    :class="disabled ? 'cursor-not-allowed' : 'cursor-pointer'"
  >
    <span class="relative inline-flex h-4 w-4 shrink-0 items-center justify-center">
      <input
        type="checkbox"
        :checked="modelValue"
        :disabled="disabled"
        class="peer h-4 w-4 appearance-none rounded-[4px] border border-border-control bg-surface transition-colors duration-150 outline-none checked:border-accent checked:bg-accent focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-45 disabled:cursor-not-allowed"
        @change="$emit('update:modelValue', $event.target.checked)"
      />
      <Check
        class="pointer-events-none absolute h-3 w-3 text-white opacity-0 peer-checked:opacity-100"
        aria-hidden="true"
      />
    </span>
    <span v-if="label || $slots.default" class="text-[13px] text-ink-2" :class="disabled ? 'opacity-45' : ''">
      <slot>{{ label }}</slot>
    </span>
  </label>
</template>

<script setup>
import { Check } from 'lucide-vue-next'

defineProps({
  modelValue: { type: Boolean, default: false },
  label: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>
```

**一处对 spec §5.3 的有意偏离，需要评审时知情：** spec 的圆角表把 Checkbox 归入「控件 = 8px」，但复选框是 **16px 见方**的控件 —— 8px 圆角正好是边长的一半，渲染出来是一个**正圆**，与 spec §5.3「取消 `rounded-full`」的意图直接冲突。这里取 `rounded-[4px]`。

**这不是随意放宽，而是把 spec 那条规则换算成了它真正想表达的东西。** 人眼读到的「圆角的圆」是**圆角与元素尺寸的比值**，不是一个绝对像素值：

| 元素 | 圆角 | 圆角 / 高度 | 观感 |
|---|---|---|---|
| `AppButton` `md`（36px 高） | 8px（spec §5.3） | 22% | 方角矩形 |
| `AppInput`（36px 高） | 8px（spec §5.3） | 22% | 方角矩形 |
| `AppBadge`（约 24px 高） | 8px（spec §5.3） | 33% | 明显圆角，但仍非胶囊 |
| **Checkbox（16px 见方）** | **4px（本计划）** | **25%** | **方角矩形，与按钮同族** |
| Checkbox（若照抄 8px） | 8px | **50%** | **正圆 —— 与「取消 rounded-full」冲突** |

4px / 16px ≈ 8px / 36px，所以复选框的**感知圆度**与按钮、输入框一致 —— 这恰好是 spec §5.3「形状读得出角色」要的结果。主要设计系统的取值也落在这个区间：Material 3 的 18px 复选框用 2px，USWDS 用 2px，Apple HIG 的复选框约 4px。8px 在任何一套体系里都不用于 16px 见方的复选框。

`appearance-none` + 自绘 `Check` 图标是必要的：原生复选框的边框粗细、圆角、对勾形状都由浏览器绘制，`rounded-[4px]` 和 `border-border-control` 在原生渲染下**完全无效**。

- [ ] **Step 2: 创建 `frontend/src/components/ui/AppBadge.vue`**

```vue
<template>
  <span
    class="inline-flex items-center gap-1 whitespace-nowrap rounded-[8px] px-2 py-0.5 text-[12px] font-medium"
    :class="TONE_CLASSES[tone]"
  >
    <slot name="icon" />
    <slot />
  </span>
</template>

<script setup>
// 状态表达的统一入口。全站只有这四种 tone，不允许在调用处临时拼颜色。
//
// 「成功」故意没有自己的 tone：强调色占用了绿系，绿色不再表达成功
// （spec §5.2）。「已解析」用 neutral + 对勾图标，「待确认」用 warn。
const TONE_CLASSES = {
  neutral: 'bg-sunken text-ink-2',
  accent: 'bg-accent-soft text-accent',
  warn: 'bg-warn-soft text-warn',
  danger: 'bg-danger-soft text-danger',
}

defineProps({
  tone: {
    type: String,
    default: 'neutral',
    validator: (v) => ['neutral', 'accent', 'warn', 'danger'].includes(v),
  },
})
</script>
```

徽章文字 `12px`（spec §6.3 的阶梯里徽章属 12px 一档），不是当前的 11px。

- [ ] **Step 3: 创建 `frontend/src/components/ui/AppPanel.vue`**

```vue
<template>
  <section class="rounded-[12px] border border-line bg-surface">
    <header v-if="title" class="border-b border-line px-4 py-3">
      <h2 class="text-[14px] font-semibold text-ink">{{ title }}</h2>
    </header>
    <div class="p-4">
      <slot />
    </div>
  </section>
</template>

<script setup>
// 发丝线容器，替代旧的「白卡片 + shadow-sm」。层级靠 12px 圆角 + 1px 发丝线
// + 与 canvas 背景的明度差表达，不用阴影（spec §5.4）。
//
// 刻意只做「标题 + 内容」两件事：spec §8.1 对它的定义就是「发丝线容器」。
// 不做 actions 插槽 —— 唯一需要「标题 + 右侧操作」的地方是 FileTable 的
// 表格头，而它是撑满工作区的主区域、不是卡片，用不上 AppPanel。
// 等真有调用点再加。
defineProps({
  title: { type: String, default: '' },
})
</script>
```

- [ ] **Step 4: 构建并校验类名全部生成**

```bash
cd frontend && npm run build && \
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
# 为什么用 `sed 's/\\//g' | grep -oF`，而不是直接 `grep -o "\.$c{"`：
# Tailwind 产出的选择器把 `:` `[` `]` `.` 都做了反斜杠转义
# （`.hover\:bg-accent-hover:hover`、`.rounded-\[8px\]`），于是两件事同时失效 ——
# ① 带前缀的变体（hover: / focus-visible: / active: / disabled:）与任意值
#    （[8px] / [.98]）永远匹配不到，闸门给出**假的 0**；
# ② 类名后面紧跟 `{` 的要求也匹配不到带伪类后缀的选择器。
# 先去掉反斜杠再做固定串匹配，既不漏也不误报（实测：原先假 0 的类全部转为 ≥1，
# 而搜一个不存在的类名仍为 0）。
  for c in "appearance-none" "peer" "peer-checked:opacity-100" "checked:bg-accent" \
           "checked:border-accent" "rounded-[4px]" "bg-accent-soft" "bg-warn-soft" \
           "bg-danger-soft" "text-warn" "text-danger" "border-line" \
           "rounded-[12px]" "py-0.5" "whitespace-nowrap"; do
    n=$(sed 's/\\//g' dist/assets/*.css | grep -oF -- "$c" | wc -l)
    printf "%-34s %s\n" "$c" "$n"
  done
```

预期：全部 ≥ `1`。任何 `0` 都说明类名拼错或该工具类不存在，必须修正。

- [ ] **Step 5: 确认原语尚无调用方（本期的预期状态）**

```bash
cd frontend && grep -rn "AppButton\|AppInput\|AppSelect\|AppCheckbox\|AppBadge\|AppPanel\|BrandMark" src --include=*.vue | grep -v "src/components/ui/"
```

预期：**只有一行** —— `src/App.vue` 引用 `BrandMark`。六个 UI 原语本期不接调用方（spec §16 阶段 2 的完成判据就是「六个组件就位，尚无调用方」），第三期才落地使用。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/ui/AppCheckbox.vue frontend/src/components/ui/AppBadge.vue frontend/src/components/ui/AppPanel.vue
git commit -m "feat(frontend): 新增 AppCheckbox / AppBadge / AppPanel 原语"
```

---

## 本期完成后的状态

- `npm run build` 通过，无警告
- 应用可运行，旧界面在新配色与 Geist 字体下**布局不变、完全可读**
- 六个 UI 原语 + `BrandMark` + 重写后的 `AppModal` 就位，尚未接入业务组件
- 过渡别名层在场，支撑第二、三期的渐进式改造
- 技术债清偿进度（spec §3 的 15 条）：#12 emoji 从 4 处降到 3 处（App.vue 已清）；`focus-visible` 从 0 处变为原语内置；`aria-*` 从 0 处变为 `AppModal` / `AppInput` / `AppSelect` / `AppCheckbox` 内置

下一步：`docs/superpowers/plans/2026-09-25-frontend-2-shell.md`

---

## 阶段收尾：提交构建产物

阶段结束时，在**最后**追加一个只含构建产物的提交：

```bash
cd frontend && npm run build
cd .. && git add frontend/dist && \
  git commit -m "build: 更新前端构建产物"
```

**为什么 dist 需要跟踪**：`backend/app/main.py:60-73` 会把 `frontend/dist` 挂成 `/assets` 并对未知路径回退到 `dist/index.html` —— 也就是 `python run.py` 的单端口模式（Dockerfile 里反而是 node 阶段现构建，不用仓库里的 dist）。所以 dist 必须保持与源码一致，否则从检出直接起后端会serve 一个过期的前端。

**为什么按阶段而不是按任务提交**：本系列 29 个任务几乎每个都会重建 dist（约 400 KB/new commit，含字体二进制），逐任务提交会给仓库历史增加约 12 MB 且无法在不改写历史的前提下回收。阶段边界是一个「可构建、可运行、可部署」的完整状态，足够。

**任务内的纪律**：计划里每个任务给出的 `git add <具体文件>` 列表都**不含** dist，照做即可。构建后 dist 会在工作区里显示为已修改但未暂存 —— 这**不影响**任务评审，因为评审包用的是 BASE..HEAD 的**提交**区间，不是工作区。不要去 `git checkout` 还原 dist（Task 1 的实现者那样做是多余的），也不要顺手 `git add` 它。

## Self-Review

**Spec 覆盖**

| spec 条目 | 落位 |
|---|---|
| §5.1 色彩三级 token + 对比度约束 | Task 2 Step 1（token 值逐字抄自 §5.1 验证表） |
| §5.2 「成功」语义降级 | Task 2 别名层（`success` → `ink-2`）+ Task 7 `AppBadge` 无 success tone |
| §5.3 形状一致性锁 | Global Constraints 圆角约束 + Task 4/5/6/7 逐组件落实 |
| §5.4 层级与阴影 | Task 2 `--shadow-overlay`；全站禁 `shadow-*` 写入 Global Constraints |
| §6.1 字体栈 | Task 1（含族名修正） |
| §6.1 引入方式 | 改为 fontsource，理由见「对 spec 的两处修正」第 1 条 |
| §6.2 等宽使用纪律 | Global Constraints；具体清理落第三期（`ScanPanel:13` / `BrowseDialog:32` 路径去 mono） |
| §6.3 字号阶梯 | Global Constraints 白名单，第四期 grep 收口 |
| §8.1 新增组件清单（前 9 个） | Task 3–7 |
| §8.2 AppButton / AppInput / AppModal 契约 | Task 4 / Task 6 / Task 5，props 逐条对齐 |
| §9 品牌标记 + favicon | Task 3 |
| §16 阶段 1 | Task 1、2、3、5 |
| §16 阶段 2 | Task 4、6、7 |
| §16 阶段 1 判据「旧界面在新 token 下可读」 | Task 2 Step 4 的逐项对照 |
| §17 风险「中文回退字体缺字」 | Task 1 Step 3 的 5 级回退栈 + `system-ui` |

**占位符扫描**：无 TBD / TODO / 「类似 Task N」/「添加适当的错误处理」。所有代码步骤含可直接粘贴的完整代码。

**类型一致性**：`AppButton.variant|size|loading|disabled|type|block`、`AppInput.modelValue|label|hint|error|type|mono|disabled|placeholder|min|max|step|id`、`AppSelect.modelValue|label|disabled|id`、`AppCheckbox.modelValue|label|disabled`、`AppBadge.tone`、`AppPanel.title`、`AppModal.modelValue|title|zIndex|closeOnOverlay`、`BrandMark.size` —— 各组件内 `<template>` 与 `defineProps` 逐字一致，且与 §8.2 spec 契约一致（`AppModal` 少了 spec 未提及但旧代码在用的 `backdrop`/`backdropBlur`，已在 Interfaces 里标为破坏性变更并给出对应的调用方校验步骤）。

**API 面收敛（YAGNI）**：本期刻意不为「将来可能需要」预留 prop / 插槽。`AppPanel` 不做 actions 插槽（没有调用点），`AppSelect` 不做 `hint` / `error` / `placeholder` / `ariaLabel`（`ariaLabel` 在第二期第一个真正需要它的调用点引入），`AppInput` 的 `size` 与 `ariaLabel` 在第三期表格行内控件处引入。唯一保留的「暂无调用点」的 prop 是 `AppSelect.disabled` —— 一个无法禁用的表单控件会逼着调用方绕开原语自己写，代价高于一个未使用的布尔 prop。`AppInput.error` 有真实调用点（第三期 Task 3 的补零位数越界提示）。

**Review Focus 落位**

| # | 条目 | 验证位置 |
|---|---|---|
| 1 | 字体族名不匹配 | Task 1 Step 4（`ls` woff2 + grep 族名）+ Step 5（Network 实测） |
| 2 | 模态三条关闭路径都要解锁滚动且还原 padding | Task 5 Step 3 的走查表第 1、7、8 项 |
| 3 | 模态内无可聚焦元素 | Task 5 Step 3 的第二段 Console 构造 |
| 4 | 焦点归位到已卸载元素 | Task 5 Step 3 的第一段 Console 构造 |
| 5 | `opacity-45` 生成与一致性 | Task 4 Step 2、Task 7 Step 4 的 grep；Global Constraints 禁止 `opacity-50` |

**未覆盖（有意）**：无前端自动化测试设施。spec §17「已知遗留」第 3 条明确把引入测试框架列为独立任务，因此本期的验证由「构建产物 grep」+「浏览器实跑走查」承担，每个失败模式都有可执行的检查步骤，而不是「看一眼」。
