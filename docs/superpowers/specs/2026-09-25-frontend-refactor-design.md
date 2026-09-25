# Episode Renamer 前端重构设计

日期：2026-09-25
分支：`feat/frontend-refactor`
状态：待用户审核

---

## 1. 目标

把前端从「5 张同款白卡片竖排 + 主操作沉底」的通用后台脸，重构为**三栏工作台**：主操作常驻、配置与结果空间分离、层级靠发丝线与背景明度而非阴影。

同时消灭三类技术债：18 处复制粘贴的表单样式、0 处 `aria-*`、0 处 `focus-visible`。

## 2. 范围

**在范围内**
- 布局架构重构（App shell 三段式）
- 设计 token 全量重写（含新强调色）
- UI 组件抽取（Button / Input / Select / Checkbox / Badge / Panel / Modal）
- 无障碍：焦点环、模态语义与焦点管理、reduced-motion、aria 标签
- 状态设计：骨架屏、空态、错误态
- 去 emoji，换 SVG 品牌标记
- 设置断线修复（前端 store 化）
- 补零位数后端支持（让设置真生效）

**不在范围内**
- 暗色主题（本设计为浅色锁定，见 §5.4）
- 路由结构、URL、API 路径变更
- 后端除补零位数以外的任何改动
- 新增功能特性

## 3. 现状审计结论

全部结论已在代码中核实。

### 3.1 结构问题

| # | 问题 | 证据 |
|---|---|---|
| 1 | **卡片汤** —— 5 个面板各占一张同款白卡片竖排，层级为零 | `HomeView.vue:3-61` |
| 2 | **主操作离手最远** —— 执行按钮在文档流最底部，需滚过 480px 表格 | `HomeView.vue:54-61` + `FileTable.vue:39` |
| 3 | `SourceTabs` 独立成卡，内含仅一个 tab bar | `SourceTabs.vue:2` |
| 4 | 宽屏下左侧约 600px 全空 | 配置与结果上下排而非并列 |

### 3.2 一致性问题

| # | 问题 | 证据 |
|---|---|---|
| 5 | 输入框样式手写 18 处 | Settings 7 / ScanPanel 4 / TemplateConfig 3 / FileTable 3 / ActionBar 1 |
| 6 | 按钮 3 套手写变体散落 6 个文件 | `ActionBar.vue:19,30` 等 |
| 7 | 圆角混用 `xl` / `lg` / `md`，形状读不出层级 | 卡片 `xl`、主按钮 `lg`、小按钮 `md` |
| 8 | `shadow-sm` 全场同款，不承载层级信息 | 全部面板 |
| 9 | `--color-secondary: #7C3AED` 是死 token，零引用 | `style.css:7` |

### 3.3 功能缺陷

| # | 问题 | 证据 |
|---|---|---|
| 10 | **设置断线** —— SettingsView 写 `localStorage`，HomeView 从不读 | `SettingsView.vue:133,149,165` vs `HomeView.vue` 全文无 `localStorage` |
| 11 | **补零位数是假设置** —— 后端读 `config.py` 常量，请求里无对应字段 | `config.py:29-30`；`RenamePreviewRequest` / `RenameExecuteRequest` 均无该字段 |

问题 11 的严重性高于 10：不是"没接上"，而是**无处可传**，前端改动永远无效。

### 3.4 可访问性

全项目 `grep` 结果：`focus-visible` **0 处**、`aria-*` **0 处**、`prefers-reduced-motion` **0 处**。模态无 `role="dialog"`、无 Esc 关闭、无焦点陷阱、无滚动锁。

### 3.5 符号与状态

| # | 问题 | 证据 |
|---|---|---|
| 12 | Emoji 当图标 4 处 | `App.vue:5` 🎬 / `HomeView.vue:112-113` 📁☁️ / `FileTable.vue:104` ⚠️✅ |
| 13 | 空态仅一行字 + 按钮 | `FileTable.vue:116-128` |
| 14 | 扫描中用 `bg-white/60` 蒙层而非骨架屏 | `FileTable.vue:33-38` |
| 15 | `ExecutingOverlay` 叠了 spinner + `animate-bounce`，动效无意图 | `ExecutingOverlay.vue:12-14` |

## 4. 设计方向

### 4.1 Design Read

> 面向自托管技术用户的**媒体运维工具**（非营销页）。当前是"没人做过选择"的通用蓝 SaaS 后台脸。倾向 Tailwind v4 tokens + 单一锁定强调色 + Geist / Geist Mono + 发丝线分隔替代卡片阴影，重构为三栏工作台。

### 4.2 三档 dial

```
DESIGN_VARIANCE:   4
MOTION_INTENSITY:  3
VISUAL_DENSITY:    6
```

理由：工具界面要**可预测、可扫描**，不能 asymmetry（variance 低）；动效只做反馈与状态转换，不做滚动编排（motion 低）；文件表格是核心，密度要够但不能到 cockpit（density 中高）。

这三个值与营销页基线 `8/6/4` 完全不同，是刻意为之。

### 4.3 技能适用边界（诚实声明）

`design-taste-frontend` 的 Section 13 明确将「仪表盘 / 密集产品 UI / 数据表格 / 管理面板」排除在适用范围外。本项目正属该类。

因此本设计**不套用**该技能的营销页范式（bento 网格、hero 视口规则、marquee、滚动劫持、logo 墙）。**套用**的是其通用硬规则：

- 色彩一致性锁（一个强调色贯穿全站）
- 形状一致性锁（一套圆角体系）
- 中文界面下的排版纪律与等宽字体使用纪律
- AI tells 清理（emoji 当图标、无意识默认蓝、假数据）
- CTA / 表单对比度、按钮不换行
- 动效必须有意图 + reduced-motion 兜底
- 空态 / 加载态 / 错误态完整设计
- 真实资产而非 div 假截图（此处对应：SVG 品牌标记替代 emoji）

### 4.4 刻意偏离技能的两点

1. **字号基线 14px 而非技能的 16px**。技能的 `text-base` 基线面向 landing page；工具界面 14px 是正确密度选择。
2. **保留 Lucide**。技能将 Lucide 列为「劝退，除非项目已依赖」—— 本项目已依赖，且换成 Phosphor 只会增加体积而不改善结果。

## 5. 设计 Token

### 5.1 色彩

强调色选定 **深青绿 `#0F766E`**。理由：冷中性基座上的天然搭子；媒体工具语境下有"信号"气质；完全脱离"无意识默认蓝"。

```css
/* 背景三级 —— 用明度差做层级，不用阴影 */
--color-canvas:       #F6F7F8;   /* 页面底，比纯白低一档 */
--color-surface:      #FFFFFF;   /* 面板 / 表格底 */
--color-sunken:       #EDEFF1;   /* 凹陷：表头、代码块、骨架 */

/* 边界三级 —— 角色不同，不可互换 */
--color-line:           #E2E5E8;  /* 装饰性分隔（表格行、面板间）。非交互 */
--color-line-strong:    #CDD2D7;  /* 更强的装饰边界。非交互 */
--color-border-control: #8A9199;  /* 交互控件边框（input/select/checkbox） */

/* 文字三级 —— 无第四级；禁用态用 opacity，不新增 token */
--color-ink:   #15181B;   /* 主文字 */
--color-ink-2: #4B5257;   /* 次文字 / label */
--color-ink-3: #6B7278;   /* 辅助文字 / 占位符 */

/* 强调 —— 全站唯一 */
--color-accent:       #0F766E;
--color-accent-hover: #0B5F59;
--color-accent-soft:  #E6F4F2;

/* 语义 —— 只留两个 */
--color-warn:         #8A5F00;
--color-warn-soft:    #FDF6E3;
--color-danger:       #B3261E;
--color-danger-hover: #8E1D17;
--color-danger-soft:  #FDECEA;
```

**边界三级的存在理由（不可合并）：** 装饰性分隔只需可见，交互控件边框须满足 WCAG 1.4.11 非文本对比度 3:1。`#CDD2D7` 对白底仅 1.52:1，用作 input 边框是**不合格**的；`#8A9199` 对白底 3.19:1，合格。当前代码把两者混用同一个 `--color-border`，是现存的无障碍缺陷。

#### 对比度验证表

| 前景 | 背景 | 比值 | 要求 | 结论 |
|---|---|---|---|---|
| `ink` #15181B | canvas #F6F7F8 | 16.6:1 | 4.5:1 | 通过 |
| `ink-2` #4B5257 | surface #FFFFFF | 7.95:1 | 4.5:1 | 通过 |
| `ink-3` #6B7278 | surface #FFFFFF | 4.88:1 | 4.5:1 | 通过 |
| 白 | accent #0F766E | 5.48:1 | 4.5:1 | 通过 |
| 白 | danger #B3261E | 6.53:1 | 4.5:1 | 通过 |
| accent | accent-soft #E6F4F2 | 4.85:1 | 4.5:1 | 通过 |
| warn #8A5F00 | warn-soft #FDF6E3 | 5.24:1 | 4.5:1 | 通过 |
| danger | danger-soft #FDECEA | 5.71:1 | 4.5:1 | 通过 |
| `border-control` #8A9199 | surface #FFFFFF | 3.19:1 | 3:1 | 通过 |

#### 使用约束（易错点，实现时须遵守）

- **表头文字必须用 `ink-2`，不得用 `ink-3`**。`ink-3` 对 `sunken` 底仅 4.23:1，低于 AA。
- **占位符文字用 `ink-3`**，不得更浅。
- **禁用态用 `opacity: 0.45` 叠加**，不引入更浅的文字 token。
- **`line` / `line-strong` 禁用于交互控件边框**。

### 5.2 「成功」语义的降级

强调色占用了绿系，与惯用的"成功绿"冲突。因此：

- **不再使用绿色表达"成功"**。表格 `已解析` 改为**中性徽章（`sunken` 底 + `ink-2` 文字）+ 对勾图标**。
- 只有 `待确认` 使用 `warn` 色徽章。
- 执行结果里的失败计数使用 `danger`。

这同时满足「颜色要克制」：全站颜色只承担**强调**与**告警**两种职责。

### 5.3 形状一致性锁

| 角色 | 圆角 |
|---|---|
| 控件（Button / Input / Select / Checkbox / Badge） | `8px` |
| 面板 / 模态 / 下拉 | `12px` |
| 品牌标记 | `8px` |

**取消 `rounded-full`**。当前 `xl`/`lg`/`md` 混用会让形状读不出层级；统一后"圆角大小 = 元素角色"。

### 5.4 层级与阴影

**默认无阴影。** 层级由三级背景明度差 + 发丝线表达。全站删除 `shadow-sm`（当前它不承载任何信息）。

**唯一例外**：真正浮起于内容之上的元素（模态、下拉浮层、Toast）保留一层克制阴影：

```css
--shadow-overlay: 0 8px 28px -6px rgb(21 24 27 / 0.14), 0 2px 6px -2px rgb(21 24 27 / 0.08);
```

阴影带冷调基色而非纯黑，避免在冷灰底上发脏。

**浅色锁定**：本设计不做暗色主题。原因：`<html>` 无 `dark` 类，任何 `dark:` 变体都不会触发，属于死代码。若日后要暗色，应作为独立设计任务重出两套 token，而非在本轮塞入半成品。

## 6. 排版

### 6.1 字体栈

中文界面的关键约束：**Geist 无中文字形**，必须显式声明中文回退。

```css
--font-sans: Geist, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
             "Noto Sans SC", system-ui, -apple-system, sans-serif;
--font-mono: "Geist Mono", "JetBrains Mono", ui-monospace,
             "SFMono-Regular", Menlo, monospace;
```

拉丁字符走 Geist，中文回退系统无衬线。

**引入方式**：自托管，`npm i geist` 后在 `main.js` 引入其 CSS。**不使用 CDN `<link>`**（会阻塞首屏且受网络影响）。

### 6.2 等宽字体的使用纪律

**等宽只用于纯技术值**：季数、集数、模板变量名（`{season_padded}`）、并发数、补零位数。

**路径与文件名走 sans**。它们含中文，等宽字体下中文会回退到非等宽字形，导致列无法对齐 —— 这是当前 `ScanPanel.vue:13` 用 `font-mono` 显示路径的实际问题。

### 6.3 字号阶梯

```
11px  辅助标注（变量卡片描述）
12px  次级辅助、徽章
13px  控件内文字、表格正文
14px  正文、label（基准）
20px  区块标题
24px  页面标题
```

不设更大的 display 字号 —— 工具界面不需要。

### 6.4 数字对齐

表格内所有数字列加 `font-variant-numeric: tabular-nums`，避免 `1` 与 `8` 宽度不同导致列抖动。

## 7. 布局架构

### 7.1 App Shell

```
AppShell:  h-dvh grid grid-rows-[56px_1fr_56px] overflow-hidden

┌─────────────────────────────────────────────────────────────┐
│ TopBar  56px   BrandMark · [本地磁盘|OpenList] segmented · ⚙ │
├────────────────┬────────────────────────────────────────────┤
│ LeftRail 280px │ WorkArea   min-h-0 overflow-hidden         │
│  overflow-y-auto│  ┌ 表头 sticky ────────────────────────┐ │
│                 │  │ # │ ☑ │ 原文件名 │剧名│季│集│ 新文件名│ │
│  ▸ 扫描源       │  ├──────────────────────────────────────┤ │
│    路径 / 递归  │  │  ⋮ 表体 overflow-y-auto 撑满剩余高度 │ │
│    / 字幕 / 扫描│  │                                     │ │
│                 │  └──────────────────────────────────────┘ │
│  ▸ 重命名模板   │                                            │
│    预设 / 模板  │                                            │
│    / 变量       │                                            │
├────────────────┴────────────────────────────────────────────┤
│ BottomBar 56px   冲突[跳过▾] · 已选 96/128  [试运行][执行]  │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 关键技术点

**中间层必须有 `min-h-0`。** Grid 子项默认 `min-height: auto`，会被内容撑破，导致表格内部滚动失效。这是本布局能成立的前提。

**使用 `h-dvh` 而非 `h-screen`。** App shell 不应整页滚动，滚动发生在表格内部。`h-dvh` 在移动端可正确响应地址栏收放。

**主操作从文档流底部移到常驻底栏。** 这是本次重构最大的可用性收益：无论表格多长，执行按钮始终可见。

### 7.3 响应式（各档显式声明）

| 断点 | 行为 |
|---|---|
| `≥1024px` | 三栏如上图 |
| `768–1023px` | LeftRail 折叠为顶栏下的可展开面板（默认收起）；BottomBar 常驻 |
| `<768px` | 表格横向滚动，关键列（复选框、原文件名、新文件名）优先可见；**BottomBar 保持常驻** |

移动端折叠规则在**每个多列组件的同一文件内**显式声明，不依赖 Tailwind 自动兜底。

### 7.4 顶栏的源切换

`SourceTabs.vue` 的 tab bar 移入 `AppTopBar`，改为 segmented control（两段，`accent-soft` 底 + `accent` 文字表示选中）。`SourceTabs.vue` 文件删除。

顶栏高度 56px，**所有内容单行**。

## 8. 组件清单

### 8.1 新增

```
src/components/ui/
  AppButton.vue      变体 primary / secondary / danger / ghost；尺寸 sm / md
  AppInput.vue       text / number；label 在上，helper / error 在下
  AppSelect.vue
  AppCheckbox.vue
  AppBadge.vue       状态表达统一入口
  AppPanel.vue       发丝线容器，替代「卡片」
  AppModal.vue       重写（见 §8.3）
src/components/layout/
  AppTopBar.vue
  AppLeftRail.vue
  AppBottomBar.vue
src/components/BrandMark.vue
src/stores/settings.js
```

### 8.2 组件契约

**AppButton**

```js
props: {
  variant: 'primary' | 'secondary' | 'danger' | 'ghost'  // default 'secondary'
  size:    'sm' | 'md'                                   // default 'md'
  loading: Boolean
  disabled: Boolean
  type:    'button' | 'submit' | 'reset'                 // default 'button'
  block:   Boolean
}
```

基础类：
```
inline-flex items-center justify-center gap-2 rounded-[8px] font-medium
transition-colors duration-150 select-none
focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent
focus-visible:ring-offset-2 focus-visible:ring-offset-canvas
disabled:opacity-45 disabled:cursor-not-allowed
active:scale-[.98]
```

| 变体 | 类 |
|---|---|
| `primary` | `bg-accent text-white hover:bg-accent-hover` |
| `secondary` | `bg-surface text-ink-2 border border-line-strong hover:bg-sunken hover:text-ink` |
| `danger` | `bg-danger text-white hover:bg-danger-hover` |
| `ghost` | `text-ink-2 hover:bg-sunken hover:text-ink` |

尺寸：`sm` = `h-8 px-3 text-[12px]`；`md` = `h-9 px-4 text-[13px]`。

**AppInput**

```js
props: {
  modelValue: [String, Number]
  label: String            // 渲染在控件上方
  hint:  String            // 控件下方辅助说明
  error: String            // 控件下方错误说明，优先于 hint
  type:  String            // 'text' | 'number' | 'password'
  mono:  Boolean           // 仅纯技术值设为 true
  disabled, placeholder, min, max, step
}
```

约束（来自技能 4.6）：**label 在控件上方**；**禁止用 placeholder 充当 label**；错误文字在控件下方；输入块间距 `gap-2`。

**AppModal**

```js
props: { modelValue: Boolean; title: String; zIndex: Number }
emits: ['update:modelValue']
```

必须实现（当前全部缺失）：
- `role="dialog"` `aria-modal="true"` `aria-labelledby` 指向标题
- **Esc 关闭**
- **焦点陷阱**：Tab / Shift+Tab 循环限制在模态内
- **打开时锁定 body 滚动**
- **关闭后焦点归位**到触发元素
- 点击遮罩关闭（可配置）

### 8.3 改造

| 文件 | 改动 |
|---|---|
| `App.vue` | 重写为三段式 App Shell |
| `HomeView.vue` | 布局重组；状态上提到 shell 层 |
| `SettingsView.vue` | 改用新组件；接入 settings store |
| `ScanPanel.vue` | 拆为 `SourceConfigPanel`，移入左栏 |
| `TemplateConfig.vue` | 移入左栏，去卡片外壳 |
| `FileTable.vue` | 撑满高度、sticky 表头、骨架屏、空态重做 |
| `ConfirmDialog.vue` | 适配新 token 与 Modal |
| `ResultDialog.vue` | 同上；结果表用 `AppBadge` |
| `BrowseDialog.vue` | 同上；补 aria 与键盘导航 |
| `Toast.vue` | 补 `role="status"` / `role="alert"` |
| `ExecutingOverlay.vue` | 移除动画堆叠（见 §11） |

### 8.4 删除

- `src/components/SourceTabs.vue` → 内容并入 `AppTopBar`
- `src/components/ActionBar.vue` → 内容并入 `AppBottomBar`

## 9. 品牌标记

替换 `App.vue:5` 的 🎬 emoji。手绘一个极简几何 SVG：**方框 + 内部重命名箭头**，语义直白。

技能对手绘装饰性 SVG 是劝退的，但对 logo 标记明确开例外（"a single, simple geometric mark"）。此标记满足该例外：单色、几何、两三个图元。

同时更新 `frontend/index.html` 的 favicon（当前是 emoji data URI）。

## 10. 状态设计

| 状态 | 设计 |
|---|---|
| 表格加载中 | **骨架行**，行高与真实行一致，不跳布局。替代当前 `bg-white/60` 蒙层 |
| 表格空态 | 图标 + 标题 + 一句说明 + 主操作按钮，垂直居中于表格区 |
| 扫描中 | 扫描按钮进入 `loading` 态（禁用 + 文字变「扫描中…」） |
| 执行中 | 保留阻断式 overlay（破坏性操作需明确阻断），但**单一进度指示** |
| 成功 | Toast，`role="status"` |
| 失败 | Toast，`role="alert"`；执行失败另在 `ResultDialog` 内以 danger 徽章逐条列出 |
| 表单错误 | 内联于控件下方（错误文字），不用 Toast |

## 11. 动效（MOTION_INTENSITY: 3）

只保留**反馈**与**状态转换**两类，每条均可一句话说明意图：

| 动效 | 意图 | 时长 |
|---|---|---|
| 色彩/边框过渡 | 反馈：悬停可交互 | 150ms |
| `:active` 微压 `scale-[.98]` | 反馈：确认按下 | 即时 |
| 模态进出 | 状态转换：层级来源 | 200ms |
| Toast 进出 | 状态转换：结果送达 | 200ms |
| 表格行 hover 底色 | 反馈：行可选中 | 150ms |

**删除** `ExecutingOverlay.vue:12-14` 的动画堆叠（旋转环 + `animate-bounce` 火箭）。理由：三者叠加不传达任何额外信息，且 `animate-bounce` 是无限循环，在"处理中"这种已有明确语义的场景下属于无意图动效。

**全局 reduced-motion 兜底**（当前 0 处）：

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
}
```

## 12. 设置断线修复

### 12.1 现状

`SettingsView` 把设置写入 `localStorage['episode-renamer:settings']`，`HomeView` 从不读取。设置页的「默认模板」「冲突默认策略」改了**对工作区无任何影响**。

### 12.2 方案

新建 `src/stores/settings.js`（Pinia），持有全部设置并负责 localStorage 持久化：

```
state:   { defaultTemplateId, episodePadDigits, seasonPadDigits,
           conflictStrategy, openlist: { serverUrl, concurrency, requestInterval } }
actions: load()   // 应用启动时读 localStorage
         save()   // 写 localStorage
```

`load()` 的健壮性要求（对齐现有 `SettingsView.vue:147-161` 的容错精神）：
- 键不存在 → 返回全默认值
- JSON 解析失败 → 捕获异常，返回全默认值
- **逐字段合并**：`{ ...defaults, ...parsed, openlist: { ...defaults.openlist, ...parsed.openlist } }`，旧版本写入的残缺对象不会导致字段 `undefined`
- `localStorage` 不可用（隐私模式）→ 捕获异常，退化为纯内存态，不阻塞启动

改动点：
- `main.js` 在挂载前调用 `settingsStore.load()`
- `HomeView` 用 `settingsStore.defaultTemplateId` 初始化 `tplStore` 的当前预设
- `ActionBar`（→ `AppBottomBar`）用 `settingsStore.conflictStrategy` 作冲突策略初值
- `SettingsView` 改用该 store，删除本地 `SETTINGS_KEY` 逻辑

**注**：`openlist.concurrency` / `requestInterval` 目前同样只存不生效（后端读 `config.py` 的 `openlist_max_concurrent` / `openlist_request_interval`）。本设计**不修**这两项，但会在设置页对它们加一行说明，标注当前由服务端配置决定。理由：避免范围蔓延，且诚实标注优于静默失效。

## 13. 后端改动：补零位数

让「集数补零位数 / 季数补零位数」真正生效。保持向后兼容：两个字段均可选，不传时行为与现在完全一致（回退到 `config.py` 默认值）。

### 13.1 `app/models/api.py`

给 `RenamePreviewRequest` 与 `RenameExecuteRequest` 各加：

```python
episode_pad_digits: Optional[int] = None
season_pad_digits:  Optional[int] = None
```

### 13.2 `app/core/template.py`

引入一个轻量的 pad 载体（`NamedTuple` 或 `dataclass`），默认 `None` 表示用全局配置：

```python
@dataclass(frozen=True)
class PadConfig:
    episode: int
    season: int
```

`_resolve_variable` 增加 `pad` 参数，取值逻辑：

```python
digits = pad.season if pad else settings.season_pad_digits
```

`apply_template` / `apply_folder_template` 各增加 `pad: PadConfig | None = None` 并向下透传。

**取值钳制**：`PadConfig` 构造时对 `episode` / `season` 做 `max(1, min(6, v))` 钳制。前端数字输入可能传出 0、负数或超大值，`zfill` 对负数会产生 `-1` → `.zfill(2)` = `-1` 这类错误文件名。

**顺带清理**：`generate_full_path`（`template.py:71`）全项目无调用点 —— `local_renamer.py:14` 导入它但从未调用，grep 已核实。**删除该函数及 `local_renamer.py:14` 的对应 import**。（它内部调用的 `apply_template` / `apply_folder_template` 在 `local_renamer.py:51,58` 与 `openlist_renamer.py:33,37` 有直接调用，删除不影响功能。）

### 13.3 `app/core/local_renamer.py` / `app/core/openlist_renamer.py`

- `build_rename_plan(..., pad=None)` → 透传给渲染调用（`local_renamer.py:51,58`；`openlist_renamer.py:33,37`）
- `build_openlist_rename_plan(..., pad=None)`
- `batch_rename(..., pad=None)`

### 13.4 `app/api/renamer.py`

三个路由（`/rename/preview`、`/rename/execute`、`/rename/dry-run`）各自从请求构造 `PadConfig` 并透传：

```python
pad = None
if req.episode_pad_digits or req.season_pad_digits:
    pad = PadConfig(
        episode=req.episode_pad_digits or settings.episode_pad_digits,
        season=req.season_pad_digits or settings.season_pad_digits,
    )
```

### 13.5 前端

`buildPreview()`（`HomeView.vue:348`）与 `executeAction()`（`HomeView.vue:446`）的请求体各加两个字段，值取自 `settingsStore`。

**结果**：设置页改补零位数 → 预览立即反映。

## 14. 文件改动清单

**新增（12）**
```
src/components/ui/AppButton.vue
src/components/ui/AppInput.vue
src/components/ui/AppSelect.vue
src/components/ui/AppCheckbox.vue
src/components/ui/AppBadge.vue
src/components/ui/AppPanel.vue
src/components/layout/AppTopBar.vue
src/components/layout/AppLeftRail.vue
src/components/layout/AppBottomBar.vue
src/components/BrandMark.vue
src/stores/settings.js
docs/superpowers/specs/2026-09-25-frontend-refactor-design.md
```

**重写（5）**
```
src/style.css
src/App.vue
src/main.js              引入 Geist
src/views/HomeView.vue
src/views/SettingsView.vue
```

**改造 · 前端（11）**
```
src/components/ScanPanel.vue          → SourceConfigPanel，移入左栏
src/components/TemplateConfig.vue     → 移入左栏，去卡片外壳
src/components/FileTable.vue          → 撑满高度 + sticky 表头 + 骨架屏 + 空态
src/components/ConfirmDialog.vue      → 适配新 token 与 AppModal
src/components/ResultDialog.vue       → 同上，结果表改用 AppBadge
src/components/BrowseDialog.vue       → 同上，补 aria 与键盘导航
src/components/ui/AppModal.vue        → 重写：焦点陷阱 / Esc / aria / 滚动锁 / 焦点归位
src/components/Toast.vue              → 补 role="status" / role="alert"
src/components/ExecutingOverlay.vue   → 移除 animate-bounce 与双层 spinner 堆叠
frontend/index.html                   → favicon 换 SVG 标记 + Geist 预加载
frontend/package.json                 → 新增 geist
```

**改造 · 后端（5）**
```
backend/app/models/api.py             → 两个请求模型各加两个可选 pad 字段
backend/app/core/template.py          → PadConfig + pad 参数透传 + 删 generate_full_path
backend/app/core/local_renamer.py     → build_rename_plan / batch_rename 接受 pad
backend/app/core/openlist_renamer.py  → build_openlist_rename_plan 接受 pad
backend/app/api/renamer.py            → 三个路由构造 PadConfig 并透传
```

**删除（3）**
```
src/components/SourceTabs.vue         → 内容并入 AppTopBar
src/components/ActionBar.vue          → 内容并入 AppBottomBar
backend/app/core/template.py 的 generate_full_path() 函数（无调用点）
```

## 15. 验证方式

1. **构建**：`npm run build` 通过，无警告
2. **功能实跑**：起后端（`python run.py`）+ 前端（`npm run dev`），走通四条路径
   - 本地扫描 → 预览 → 试运行 → 执行
   - OpenList 连接 → 浏览 → 扫描 → 试运行
3. **补零位数闭环**：设置页改「集数补零位数」为 3 → 预览列立即显示 `S01E001` → 证明 §13 打通
4. **键盘走查**：Tab 顺序合理；Esc 关模态；焦点不逃逸模态；关闭后归位触发元素
5. **对比度抽检**：按 §5.1 表格逐项复核实际渲染值
6. **reduced-motion**：系统开启后确认动效全关（含模态与 Toast）
7. **响应式**：1280 / 1024 / 768 / 375 四档实跑
8. **长表格**：扫描 ≥300 文件，确认底栏常驻、表头 sticky、内部滚动正确
9. **截图对比**：改前（`screenshot/` 现有三张）改后同角度留档

## 16. 实施顺序

分 8 个阶段。**每一阶段结束时应用都必须可构建可运行** —— 不做"中间态全坏、最后一次性跑通"的重构。

| 阶段 | 内容 | 完成判据 |
|---|---|---|
| 1 | 设计地基：`style.css` token 重写、Geist 引入、`BrandMark.vue`、`AppModal.vue` 重写 | `npm run build` 通过；旧界面在新 token 下可读 |
| 2 | UI 原语：`AppButton` / `AppInput` / `AppSelect` / `AppCheckbox` / `AppBadge` / `AppPanel` | 六个组件就位，尚无调用方 |
| 3 | App Shell：`AppTopBar` / `AppLeftRail` / `AppBottomBar` + `App.vue` + `HomeView` 布局重组 | 三栏工作台可见；表格撑满；底栏常驻 |
| 4 | 业务组件改造：`ScanPanel` / `TemplateConfig` / `FileTable` / 三个对话框 / `Toast` | 全站改用原语；18 处手写表单样式清零 |
| 5 | `stores/settings.js`；接上默认模板与冲突策略 | 设置页改动 → 工作区初值随之变化 |
| 6 | 后端补零位数（§13）+ 前端请求带参 | §15.3 的闭环验证通过 |
| 7 | 收尾：骨架屏 / 空态 / aria 补全 / `focus-visible` 全量 / reduced-motion 兜底 / `ExecutingOverlay` 精简 | §15.4–15.6 验证通过 |
| 8 | 全量验证 + 截图留档 | §15 全部 9 项通过 |

阶段 3 是风险最高的一步（布局重构），独立的 git 提交点，便于单独回退。

## 17. 风险与遗留

| 风险 | 说明 | 应对 |
|---|---|---|
| `min-h-0` 遗漏 | 表格内部滚动失效，页面整页滚动 | §15.8 长表格专项验证 |
| 中文回退字体缺字 | 极端精简系统无中文字体 | 字体栈含 5 级回退 + `system-ui` |
| 强调色与语义色混淆 | 深青绿与绿系语义色同族 | 已通过「成功」降级为中性徽章解决（§5.2） |
| 后端签名变更波及 | `apply_template` 增加可选参数 | 全部新参数有默认值，向后兼容 |
| 设置值越界 | 前端数字输入可能传出 0 / 负数 / 超大补零位数 | 已在 §13.2 规定 `PadConfig` 构造时钳制到 `[1, 6]` |

**已知遗留（不在本轮范围）**

1. `openlist.concurrency` / `requestInterval` 仍是假设置（后端读 `config.py`）。将在设置页标注说明。
2. 无暗色主题。
3. 无前端自动化测试 —— 本项目当前无任何测试设施，引入测试框架属独立任务。

---

## 附：设计决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 重构方向 | 浅色工作台 · 结构重构 | 结构问题（主操作沉底）比视觉问题更严重 |
| 强调色 | 深青绿 `#0F766E` | 脱离无意识默认蓝；冷灰基座天然搭子 |
| 「成功」语义 | 降级为中性徽章 + 图标 | 让出绿系给强调色；颜色只承担强调与告警 |
| 圆角 | 控件 8px / 面板 12px，取消 full | 形状应能读出角色 |
| 阴影 | 默认删除，仅浮层保留 | 当前阴影不承载层级信息 |
| 字号基线 | 14px | 工具界面密度，刻意偏离技能 16px 基线 |
| 图标库 | 保留 Lucide | 项目已依赖，更换只增体积 |
| 补零位数 | 改后端使其生效 | 假设置比缺设置更糟 |
| 暗色主题 | 不做 | 避免半成品死代码 |

