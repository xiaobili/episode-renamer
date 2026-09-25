# 前端重构 · 第四期：收尾与全量验证 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收掉最后一批 spec §3 的技术债（骨架屏、空态、动效意图、`focus-visible`/`aria` 全量、`reduced-motion` 兜底），删除第一期的过渡别名层让 `style.css` 只剩一套 token，最后按 spec §15 的 9 项做全量验证并留档截图。

**Architecture:** 前三个任务是小范围收尾，第四、五任务是**全局兜底**（`reduced-motion` 与无障碍），第六任务是**删除临时脚手架**（过渡别名层）。第七任务是纯验证，不改代码。删别名层放在其余收尾之后、全量验证之前 —— 这样 9 项验证跑在最终的 `style.css` 上。

**Tech Stack:** Vue 3.5.43 / Vite 5 / Tailwind CSS v4 / Pinia 2 / lucide-vue-next

**Spec:** `docs/superpowers/specs/2026-09-25-frontend-refactor-design.md`（§5.1 对比度、§6.2–6.4 排版、§10 状态设计、§11 动效、§15 验证方式、§16 阶段 7–8、§17 风险与遗留）

**前置:** 第一期、第二期、第三期已完成。第三期的 Task 8（补零位数接线）若因后端未合入而跳过，本期 Task 7 的第 3 项验证需相应标注为「不适用」。

---

## Global Constraints

- 圆角只允许 `rounded-[8px]`（控件）/ `rounded-[12px]`（面板 / 模态 / 下拉）。**禁止** `rounded-full` / `rounded-xl` / `rounded-2xl` / `rounded-md` / `rounded-lg`
- 默认无阴影，唯一例外 `shadow-overlay`
- 字号只允许 `11px / 12px / 13px / 14px / 20px / 24px`
- **只保留 spec §11 动效表里的 5 类动效**：色彩/边框过渡 150ms、`:active` 微压、模态进出 200ms、Toast 进出 200ms、表格行 hover 150ms。任何其他动画都属「无意图动效」
- 全站禁用绿色表达「成功」
- 每个任务结束时 `cd frontend && npm run build` 必须通过
- 路由路径、API 路径与响应结构不变
- 不做暗色主题

- **按钮光标由 `style.css` 的基线规则统一提供**（`button:not(:disabled) { cursor: pointer }`，Tailwind v4 的 preflight 删掉了 v3 的等价声明）。因此新写的裸 `<button>` **不需要**再写 `cursor-pointer`，也**不得**给它加与之冲突的 cursor 类。禁用态由 `disabled:cursor-not-allowed` 负责：`:not(:disabled)` 让两者不在同一个元素上竞争。**不要**把它简化成裸 `button { cursor: pointer }` —— 该基线规则是层外样式，按 CSS 级联层规则优先于 Tailwind 的层内工具类，**与特异性无关**，写成裸选择器会覆盖掉禁用态的 `not-allowed`。

## Review Focus

1. **`prefers-reduced-motion` 兜底不能漏掉任何一种动效承载方式** —— 本项目的动效分布在三个地方：Tailwind 的 `transition-*` / `animate-*` 工具类、`AppModal` 与 `Toast` 的 `<style>` 块里的 `transiton`、以及 `ExecutingOverlay` 与 `AppButton` 的 `animate-spin`。兜底用的是 `*, *::before, *::after` 通配选择器 + `!important`，能覆盖全部三者。期望：系统开启「减弱动态效果」后，模态直接出现/消失、Toast 不再位移、`loading` 图标不再旋转，**且功能完全不受影响**。→ Task 4
2. **删掉过渡别名层后某个类名静默失效** —— 别名层删除后，任何还写着旧 token 名（`bg-surface-muted` / `text-text-secondary` / `border-border-strong` / `bg-success-light` …）的元素会**静默丢掉样式**：按钮变透明、边框消失、文字变默认黑色。Tailwind 不报错，构建照常通过。期望：删除前用正则审计到 0 命中。→ Task 6
3. **骨架行与真实行高不一致导致跳布局** —— spec §10 的原文要求是「行高与真实行一致，不跳布局」。真实行高由内容最高的单元格决定（原文件名是两行文字、季/集是 `h-8` 输入框），无法纸上推算，必须在浏览器里量。→ Task 2 Step 3 给出测量与校准步骤
4. **空态在窄屏被压成一条** —— 空态要「垂直居中于表格区」，若外层没有可用的高度（flex 链断了），它会缩成顶端的一小条。期望：在 375px 与 1280px 下都居中。→ Task 3 Step 3
5. **`aria-busy` 与 `role="status"` 叠加导致读屏重复播报** —— 扫描中既有骨架屏的 `aria-busy`，执行中又有 `role="status"`。两个都是「正在忙」的语义，挂错位置会让读屏在每次状态变化时念两遍。期望：`aria-busy` 只挂在表格容器上，`role="status"` 只挂在执行遮罩上，两者不嵌套在同一个可聚焦子树里。→ Task 5 Step 1

---

## 前期实测结论

| 结论 | 依据 |
|---|---|
| **`FileTable.vue:34` 的 `v-if="filesStore.scanning"` 蒙层是死代码**：`stores/files.js:7` 声明了 `scanning` 并 export，但**全项目没有任何地方给它赋值**（工作区的扫描状态是 `HomeView.vue:168` 那个同名的**局部** `ref`，第二期已迁入 `workspace` store）。所以 spec §3.5 第 14 条描述的「用 `bg-white/60` 蒙层」实际**从未渲染过** | `grep -rn "scanning" src/` 实测 |
| 旧 token 类名的正则审计在本机可用且**准确**：`grep -P` 支持前瞻/后顾；基线命中 **178** 处，分布于 12 个文件；对合成样本行自检无误报（`border-border-control` / `bg-surface` / `text-ink-2` / `ring-offset-canvas` 均不命中，`bg-surface-muted` / `border-border-strong` / `text-text-secondary` / `bg-error-light` / `ring-primary/20` 均命中） | 本机实测 |
| `ExecutingOverlay` 当前叠了三个动画：静态圆环、旋转圆环（`animate-[spin_0.9s_linear_infinite]`）、`animate-bounce` 的火箭 | `ExecutingOverlay.vue:8-11` |
| 现有截图尺寸：`home.png` 2538×908、`settings.png` 1240×906、`browse.png` 523×545 | 读 PNG 头实测 |
| 第一期已确认：`animate-spin`、`rounded-[4px]`、`bg-sunken`、`shadow-overlay`、`sr-only`、`bg-ink/50` 均可生成 | 第一期探针构建 |

---

## File Structure

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `frontend/src/components/ExecutingOverlay.vue` | 执行中的阻断遮罩 | **重写**：单一进度指示 + `role="status"` |
| `frontend/src/components/FileTable.vue` | 文件表格 | 骨架屏（替换死代码蒙层）、空态重做、`aria-busy`、`aria-label` |
| `frontend/src/style.css` | 设计 token + 全局基线 | 加 `reduced-motion` 兜底；**删除过渡别名层** |
| `frontend/src/views/HomeView.vue` | 工作区布局 | 给 `FileTable` 传 `scanning` |
| `frontend/src/stores/files.js` | 文件 store | 删除从未被赋值的 `scanning`（死代码） |
| `screenshot/after-*.png` | 改后留档 | **新建** 6 张 |

---

### Task 1: `ExecutingOverlay` 精简为单一进度指示

spec §11 原文：删除 `ExecutingOverlay.vue:12-14` 的动画堆叠（旋转环 + `animate-bounce` 火箭）—— 三者叠加不传达任何额外信息，且 `animate-bounce` 是无限循环，在「处理中」这种已有明确语义的场景下属于无意图动效。spec §10 要求「保留阻断式 overlay（破坏性操作需明确阻断），但**单一进度指示**」。

**Files:**
- Modify: `frontend/src/components/ExecutingOverlay.vue`（整文件重写）

**Interfaces:**
- Consumes: 新 token `ink` `surface` `ink-2` `accent` `shadow-overlay`；`Loader2`（lucide）
- Produces: props 不变（`modelValue` / `dryRun`）；**无 emits**（该遮罩不可关闭，这是有意的）

- [ ] **Step 1: 重写 `frontend/src/components/ExecutingOverlay.vue`**

```vue
<template>
  <Transition name="overlay">
    <div
      v-if="modelValue"
      ref="overlayRef"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-ink/50"
      tabindex="-1"
      aria-busy="true"
      @keydown.tab.prevent
    >
      <div
        role="status"
        aria-live="polite"
        class="flex w-[320px] flex-col items-center gap-3 rounded-[12px] bg-surface p-6 shadow-overlay"
      >
        <Loader2 class="h-6 w-6 animate-spin text-accent" aria-hidden="true" />
        <div class="text-center">
          <div class="text-[14px] font-semibold text-ink">
            {{ dryRun ? '试运行中…' : '正在执行重命名…' }}
          </div>
          <div class="mt-1 text-[12px] text-ink-2">请稍候，操作进行中请勿关闭</div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Loader2 } from 'lucide-vue-next'

defineProps({
  modelValue: Boolean,
  dryRun: Boolean,
})

// 唯一的进度指示：一个旋转的 Loader2。删掉了原来的三层动画堆叠
// （静态圆环 + 旋转圆环 + 弹跳火箭）—— 三者不传达任何额外信息
// （spec §11）。animate-spin 与 AppButton 的 loading 态用的是同一个图标，
// 全站「正在处理」只有一个视觉语汇。
const overlayRef = ref(null)

// 遮罩打开时把焦点收进来，配合 @keydown.tab.prevent 让键盘也无法
// 操作背后的界面 —— 破坏性操作需要明确阻断（spec §10）。
// 没有用 AppModal：AppModal 支持 Esc 关闭，而这里**不能**被关闭。
onMounted(() => {
  overlayRef.value?.focus()
})
</script>

<style scoped>
/* 遮罩进出 200ms（spec §11 的动效表）。 */
.overlay-enter-active {
  transition: opacity 0.2s ease-out;
}
.overlay-leave-active {
  transition: opacity 0.15s ease-in;
}
.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}
</style>
```

几处不是随手写的：

- **`@keydown.tab.prevent` 吞掉 Tab**：遮罩内没有任何可聚焦元素，不吞掉的话 Tab 会把焦点送到背后的表格输入框上，用户会在一个「看起来不能用」的界面上打字。吞掉 Tab 是这类瞬时阻断态的正确取舍。
- **`role="status"` + `aria-live="polite"` 挂在卡片上，`aria-busy` 挂在遮罩外层**：两者语义不同 —— `aria-busy` 表达「这个区域正在更新」，`role="status"` 表达「这条消息请朗读」。合在同一个元素上会让读屏对同一次状态变化播报两遍（Review Focus 第 5 条）。`aria-busy` 在 Task 5 会同时挂到表格容器上。
- **`bg-ink/50` 而不是 `bg-black/50`**：遮罩带冷调基色，避免在冷灰画布上发脏（spec §5.4 同一理由）。
- **卡片 `rounded-[12px]` + `shadow-overlay`**：它是真正浮起于内容之上的元素，属于 spec §5.4 允许的那一类例外。原来是 `rounded-2xl` + `shadow-2xl`，两样都在禁用清单里。
- **`transition` 从 `transform: scale` 改成纯 `opacity`**：缩放在阻断态上没有信息量，且与模态的进出动效（第一期定为「层级来源」）重复。

- [ ] **Step 2: 构建并验证**

```bash
cd frontend && npm run build && npm run dev
```

| # | 操作 | 预期 |
|---|---|---|
| 1 | 勾选若干文件 → 点「执行重命名」→ 确认 | 出现半透明深色遮罩 + 一张居中卡片；卡片里**只有**一个旋转图标 + 两行文字 |
| 2 | 盯住卡片 3 秒 | **没有**第二个圆环、**没有**上下弹跳的元素；只有那一个旋转图标 |
| 3 | 执行中按 `Tab` / `Shift+Tab` | 焦点**不动**，不会跑到背后的表格或左栏 |
| 4 | 执行中按 `Esc` | 遮罩**不**关闭（破坏性操作需明确阻断） |
| 5 | 执行中按 `Enter` | 无任何反应 |
| 6 | 执行结束 | 遮罩淡出（约 150ms）后消失，`ResultDialog` 出现 |
| 7 | 尝试在遮罩覆盖期间点击背后的按钮 | 点不到（遮罩在最上层捕获指针） |

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ExecutingOverlay.vue
git commit -m "refactor(frontend): ExecutingOverlay 精简为单一进度指示并补 role"
```

---

### Task 2: `FileTable` 骨架屏

spec §10 要求：表格加载中用**骨架行**替代当前的蒙层，「行高与真实行一致，不跳布局」。

**⚠️ 本任务同时修掉一个死代码**（见「前期实测结论」）：当前 `FileTable` 的蒙层绑的是 `filesStore.scanning`，而这个值**从未被赋值**，所以蒙层从来没渲染过。骨架屏必须绑到真正会变的状态 —— `workspace` store 的 `scanning`，通过新增的 prop 传进来。

**Files:**
- Modify: `frontend/src/components/FileTable.vue`
- Modify: `frontend/src/views/HomeView.vue`（传 `:scanning="ws.scanning"`）
- Modify: `frontend/src/stores/files.js`（删除死代码 `scanning`）

**Interfaces:**
- Consumes: 新 token `sunken` `line`
- Produces:
  ```js
  // FileTable 的 props 新增一项（其余不变）
  scanning: Boolean   // default false —— 由 HomeView 传 ws.scanning
  ```
  同时 `stores/files.js` 的 `scanning` **被删除**，其返回值不再包含该字段（全项目无其他引用，第四期 Task 5 的审计会再确认一次）

- [ ] **Step 1: 删除 `stores/files.js` 里的死代码**

编辑 `frontend/src/stores/files.js`，删掉第 7 行的 `const scanning = ref(false)`，并把第 29 行的 return 改为：

```js
  return { files, loading, source, scanResult, setFiles, updateFile, getFileById, clear }
```

先确认它确实没有别的引用：

```bash
cd frontend && grep -rn "filesStore.scanning\|\.scanning" src/stores/files.js src/components/FileTable.vue
```

预期：只输出 `FileTable.vue` 里那一行 `v-if="filesStore.scanning"` —— 该行在本任务 Step 2 会被替换掉。

- [ ] **Step 2: 给 `FileTable` 加 `scanning` prop 与骨架行**

编辑 `frontend/src/components/FileTable.vue`。

在 `<script setup>` 的 `defineProps` 里加一项：

```js
  scanning: { type: Boolean, default: false },
```

在 `<script setup>` 顶部加常量：

```js
// 骨架行数：取一个能填满常见视口的高度，不必等于真实文件数 ——
// 骨架的职责是「占住版面、表达正在加载」，不是「预告有多少行」。
const SKELETON_ROWS = 8
```

把 `<template>` 里那个蒙层 div 与表格容器之间做如下替换。

**删除**这一段（它永远不会渲染）：

```html
      <div
        v-if="filesStore.scanning"
        class="absolute inset-0 bg-white/60 z-10 flex items-center justify-center"
      >
        <div class="text-text-muted text-[13px]">扫描中...</div>
      </div>
```

同时把包裹它的 `<div class="relative">` 也删掉（不再需要定位上下文）。

**把 `<tbody>` 的内容改成分支结构** —— 在 `<tbody>` 内最前面插入骨架分支：

```html
        <tbody>
          <tr
            v-for="n in SKELETON_ROWS"
            v-if="scanning && !previewRows.length"
            :key="`skeleton-${n}`"
            class="h-[58px] border-t border-line"
            aria-hidden="true"
          >
            <td class="hidden px-4 py-2.5 sm:table-cell">
              <div class="h-4 w-6 rounded-[4px] bg-sunken" />
            </td>
            <td class="px-4 py-2.5">
              <div class="h-4 w-4 rounded-[4px] bg-sunken" />
            </td>
            <td class="px-4 py-2.5">
              <div class="h-4 w-[240px] rounded-[4px] bg-sunken" />
              <div class="mt-1 h-3 w-[180px] rounded-[4px] bg-sunken" />
            </td>
            <td class="hidden px-4 py-2.5 md:table-cell">
              <div class="h-8 w-[120px] rounded-[4px] bg-sunken" />
            </td>
            <td class="px-4 py-2.5">
              <div class="h-8 w-12 rounded-[4px] bg-sunken" />
            </td>
            <td class="px-4 py-2.5">
              <div class="h-8 w-12 rounded-[4px] bg-sunken" />
            </td>
            <td class="px-4 py-2.5">
              <div class="h-6 w-16 rounded-[4px] bg-sunken" />
            </td>
            <td class="px-4 py-2.5">
              <div class="h-4 w-[200px] rounded-[4px] bg-sunken" />
            </td>
          </tr>

          <template v-else-if="previewRows.length">
            <!-- 原有的数据行 -->
          </template>
          <tr v-else>
            <!-- 原有的空态 -->
          </tr>
        </tbody>
```

注意 Vue 的一条约束：`v-for` 与 `v-if` **不能挂在同一个元素上**（Vue 3 中 `v-if` 优先级更高，会拿不到循环变量）。上面的写法把 `v-if` 与 `v-for` 放在同一个 `<tr>` 上是**错误的**。请改成用一个 `<template>` 包一层：

```html
        <tbody>
          <template v-if="scanning && !previewRows.length">
            <tr
              v-for="n in SKELETON_ROWS"
              :key="`skeleton-${n}`"
              class="h-[58px] animate-pulse border-t border-line"
              aria-hidden="true"
            >
              <!-- 上面那 8 个 <td> 原样放在这里 -->
            </tr>
          </template>

          <template v-else-if="previewRows.length">
            <!-- 原有的数据行（v-for 那段） -->
          </template>

          <tr v-else>
            <!-- 原有的空态 -->
          </tr>
        </tbody>
```

几处不是随手写的：

- **骨架一律 `aria-hidden="true"`**：占位方块对读屏是纯噪音。加载状态由 Task 5 挂到表格容器上的 `aria-busy` 表达。
- **骨架块用 `bg-sunken`**：`sunken` 就是 spec §5.1 给「凹陷：表头、代码块、**骨架**」这一角色定义的那一档。
- **骨架行加 `animate-pulse`（呼吸）**：这是骨架屏的通行做法（shadcn/ui、Vercel Geist、Material 的 skeleton 都带脉动），它承担 spec §11 允许的第二类动效 —— 「状态转换：内容正在加载」。静态灰块会被误读成「页面坏了」，这不是克制而是省略。
  - **放在 `<tr>` 而不是 9 个 `<div>` 上**：`opacity` 是群组属性，父元素脉动会带着整个子树的方块一起呼吸，一个类顶九个，且天然同步。
  - **`opacity` 作用在 `<tr>` 上**是这条唯一的实现风险（个别浏览器对表格行上的 `opacity` 有历史怪癖）。Step 3 走查表第 7 项专门验证脉动是否真的可见；**若看不到脉动**，把 `animate-pulse` 从 `<tr>` 挪到那 8 个 `<td>` 上即可，其余不变。
  - **无障碍面已闭合**：Task 4 的全局 `reduced-motion` 兜底会把 `animation-iteration-count` 压到 1、`animation-duration` 压到 `.01ms`，于是开启「减弱动态效果」时骨架自动退化为**静态灰块** —— 正是原本的克制设计，不需要额外分支。
- **`h-[58px]` 是一个**待校准**的初值**，见 Step 3。
- **条件用 `scanning && !previewRows.length` 而不是 `scanning`**：重新扫描一个已经扫过的目录时，`filesStore.files` 与 `previewRows` 都还在，无条件显示骨架会在一段可能长达数秒的扫描期间把**有效内容**替换成灰块。这个条件让首屏加载显示骨架、重新扫描保持旧内容可见。

- [ ] **Step 3: 校准骨架行高（必须在浏览器里量）**

`h-[58px]` 是按「原文件名两行文字（13px×1.6 + 11px×1.6）与 `h-8` 输入框取最大，再加 `py-2.5 × 2`」估出来的，**纸上算不准**。

```bash
cd frontend && npm run dev
```

1. 扫描一个目录，等数据出来
2. DevTools → Elements → 选中任意一个数据行 `<tr>`
3. 看 Computed 面板里的 `height`
4. 把这个像素值填回骨架行的 `h-[Npx]`

然后验证：趁骨架显示时截图，与数据行截图叠加对比。

| # | 操作 | 预期 |
|---|---|---|
| 1 | 扫描一个大目录（≥300 文件） | 表格区域出现 8 行灰块，**没有任何一层白色蒙层** |
| 2 | 数据到达的瞬间盯住表格 | 行**不发生上下跳动** —— 骨架行与数据行高度一致（Review Focus 第 3 条） |
| 3 | 对比骨架与数据的列位置 | 各列的灰块与数据列的左边界对齐（列宽由 `<th>` 决定，两边共用同一个 `<table>`，天然对齐） |
| 4 | 扫描完成后再点「预览」重新拉预览（此时 `previewRows` 非空） | **不出现骨架**，旧数据一直在（`scanning && !previewRows.length` 分支） |
| 5 | 点「清空」后再扫描 | 出现骨架（此时 `previewRows` 为空） |
| 6 | 用读屏或查 DOM | 骨架行是 `aria-hidden="true"` 的；表格容器上有 `aria-busy`（Task 5 补，本步可先跳过） |
| 7 | 盯住骨架行 3 秒 | 灰块有**轻微的呼吸（透明度明暗往复）**。**看不到脉动**时把 `animate-pulse` 从 `<tr>` 挪到 8 个 `<td>` 上 |

第 2 项不通过时，重复 Step 3 的测量直到两个高度一致。

- [ ] **Step 4: `HomeView` 传入 `scanning`**

编辑 `frontend/src/views/HomeView.vue`，给 `<FileTable>` 加一个 prop：

```html
        <FileTable
          :files-store="filesStore"
          :preview-rows="ws.previewRows"
          :scanned-info="ws.scannedInfo"
          :all-selected="ws.allSelected"
          :active-source="ws.activeSource"
          :scanning="ws.scanning"
          @preview-all="ws.previewAll"
          @clear-all="ws.clearAll"
          @toggle-all="ws.toggleAll"
          @select-row="({ row, val }) => row.selected = val"
          @update-row="ws.updatePreview"
          @quick-scan="ws.doScan"
        />
```

`ws` 是第二期 Task 1 引入的 `useWorkspaceStore()` 实例；若 `HomeView` 里目前没有 `const ws = useWorkspaceStore()`，补上。

- [ ] **Step 5: 构建并确认死代码已清**

```bash
cd frontend && npm run build && \
  echo "--- filesStore.scanning 残留（必须为 0）---" && \
  grep -rn "filesStore.scanning" src/ | wc -l && \
  echo "--- files.js 里的 scanning（必须为 0）---" && \
  grep -c "scanning" src/stores/files.js
```

预期：两个计数都是 **0**。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/FileTable.vue frontend/src/views/HomeView.vue frontend/src/stores/files.js
git commit -m "feat(frontend): 表格改用骨架行, 删除从未渲染的扫描蒙层死代码"
```

---

### Task 3: 表格空态重做

spec §10 要求：表格空态 = **图标 + 标题 + 一句说明 + 主操作按钮**，垂直居中于表格区。当前只有「图标 + 一行字 + 一个按钮」。

**Files:**
- Modify: `frontend/src/components/FileTable.vue`

**Interfaces:**
- Consumes: `AppButton`（第一期）；新 token `ink` `ink-2` `ink-3`
- Produces: 无新接口；空态的按钮在 `openlist` 源下换成「去连接 OpenList」，在 `local` 源下是「开始扫描」

- [ ] **Step 1: 把空态从 `<tbody>` 里挪出来**

空态要「垂直居中于表格区」，就不能待在 `<td>` 里 —— `<td>` 的高度由行内容决定，`h-full` 在那里无效。把空态改为**替换掉整个表格**：

编辑 `frontend/src/components/FileTable.vue`，把滚动容器那一段改成三选一：

```html
    <!-- 空态：图标 + 标题 + 说明 + 主操作，垂直居中于表格区 -->
    <div
      v-if="!scanning && !previewRows.length"
      class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-8 text-center"
    >
      <FileQuestion class="h-10 w-10 text-ink-3" aria-hidden="true" />
      <div class="text-[14px] font-medium text-ink">{{ emptyState.title }}</div>
      <p class="max-w-[420px] text-[13px] leading-relaxed text-ink-2">{{ emptyState.description }}</p>
      <AppButton
        v-if="emptyState.action"
        variant="primary"
        class="mt-1"
        @click="$emit(emptyState.action.event)"
      >
        {{ emptyState.action.label }}
      </AppButton>
    </div>

    <div v-else class="min-h-0 flex-1 overflow-auto">
      <table class="w-full min-w-[560px] text-[13px]">
        <!-- 表头与 tbody 原样保留；tbody 里删掉原来那个 v-else 的空态 <tr> -->
      </table>
    </div>
```

即：`<tbody>` 里只剩「骨架分支」与「数据行分支」两支，**空态那一支整段删除**（它已经被上面的独立空态块取代）。`<td colspan="8">` 那个元素连同它的 `FileQuestion` / 文案 / 按钮一起删掉。

- [ ] **Step 2: 补空态文案的计算属性**

在 `<script setup>` 里加：

```js
import { computed } from 'vue'
import { AlertTriangle, Check, FileQuestion } from 'lucide-vue-next'

// 空态文案随数据源变化：本地源可以直接去扫描，云盘源得先连上才有目录可选。
const props = defineProps({
  filesStore: { type: Object, required: true },
  previewRows: { type: Array, default: () => [] },
  scannedInfo: Object,
  allSelected: Boolean,
  activeSource: String,
  scanning: { type: Boolean, default: false },
})
defineEmits([
  'preview-all', 'clear-all', 'toggle-all', 'select-row', 'update-row', 'quick-scan',
])

const emptyState = computed(() => {
  if (props.activeSource === 'openlist') {
    return {
      title: '尚未加载文件',
      description: '在左侧「扫描源」里连接 OpenList、选择挂载点与目录，然后点扫描。',
      action: null,
    }
  }
  return {
    title: '尚未加载文件',
    description: '在左侧「扫描源」里选择目录并点击扫描，文件会在这里列出并自动生成新文件名预览。',
    action: { label: '开始扫描', event: 'quick-scan' },
  }
})
```

**注意**：原来的 `defineProps({...})` 是**赋值给一个变量还是裸调用**取决于写入时的实现 —— 现在需要 `props.activeSource`，所以必须写成 `const props = defineProps({...})`。`defineEmits` 保持裸调用。

`v-if="emptyState.action"` + `@click="$emit(emptyState.action.event)"` 用动态事件名 —— 事件名必须是编译期可静态分析的字符串常量吗？`$emit` 的第一个参数是运行期求值的，动态值完全合法。这里 `emptyState.action.event` 恒为 `'quick-scan'`，写成动态只是为了将来加第二种操作时不用改模板。

- [ ] **Step 3: 构建并验证空态**

```bash
cd frontend && npm run build && npm run dev
```

| # | 视口 | 操作 | 预期 |
|---|---|---|---|
| 1 | 1280×900 | 打开首页（未扫描） | 空态**垂直居中于右侧工作区**，不是贴在顶部 |
| 2 | 1280×900 | 看空态结构 | 灰色图标 → 「尚未加载文件」标题 → 一句说明 → 青绿主按钮「开始扫描」 |
| 3 | 1280×900 | 点「开始扫描」 | 与左栏「扫描」按钮行为一致 |
| 4 | 1280×900 | 扫描出文件 | 空态消失，出现表格 |
| 5 | 1280×900 | 点「清空」→ 确认 | 表格消失，空态回来并仍然居中 |
| 6 | 375×812 | 打开首页 | 空态仍居中；说明文字自动换行，**不横向溢出** |
| 7 | 375×812 | 看主按钮 | 通栏或自适应，文字**不换行**（`AppButton` 内置 `whitespace-nowrap`） |
| 8 | 1280×900 | 切到「OpenList」且未连接 | 空态**没有按钮**，说明文字变成「在左侧『扫描源』里连接 OpenList…」 |
| 9 | 1280×900 | 连上 OpenList 后 | 空态**仍然没有按钮**（要先去浏览选目录），文案指向左栏 |
| 10 | 任意 | 用读屏 | 图标 `aria-hidden`，标题与说明正常朗读 |

第 1、6 项不通过 = 空态容器的 flex 链断了。检查它是否同时有 `flex-1` 与 `min-h-0`，以及 `FileTable` 根元素是否有 `min-h-0 flex-1 flex-col`（第二期 Task 6 建立）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/FileTable.vue
git commit -m "feat(frontend): 表格空态改为图标+标题+说明+主操作并垂直居中"
```

---

### Task 4: 全局 `prefers-reduced-motion` 兜底

spec §3.4 实测：全项目 `prefers-reduced-motion` **0 处**。spec §11 要求加全局兜底。

**Files:**
- Modify: `frontend/src/style.css`

**Interfaces:**
- Consumes: 无
- Produces: 一个全局 `@media (prefers-reduced-motion: reduce)` 块

- [ ] **Step 1: 在 `frontend/src/style.css` 末尾追加**

```css
/* ==========================================================================
   动效兜底：系统开启「减弱动态效果」时，全站动效一并关停（spec §11）。
   --------------------------------------------------------------------------
   用通配选择器 + !important 是有意的：本项目的动效分布在三处 ——
   Tailwind 的 transition-* / animate-* 工具类、各组件 <style> 块里的
   transition、以及 AppButton / ExecutingOverlay 的 animate-spin。
   通配符是唯一能一次覆盖全部三处、且新增组件时不会漏的写法。

   duration 用 .01ms 而不是 0：Vue 的 <Transition> 依赖 transitionend
   事件来收尾，duration: 0 时事件可能不触发，元素会卡在离场状态。
   ========================================================================== */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 2: 构建并验证兜底覆盖到全部三类动效**

```bash
cd frontend && npm run build && \
  echo "--- 兜底块已在产物中 ---" && \
  grep -o "prefers-reduced-motion" dist/assets/*.css | head -1 && \
  echo "--- 三类动效的载体都在产物中 ---" && \
  grep -o "animate-spin" dist/assets/*.css | head -1 && \
  grep -o "\.modal-enter-active" dist/assets/*.css | head -1 && \
  grep -o "\.toast-enter-active" dist/assets/*.css | head -1 && \
  grep -o "\.overlay-enter-active" dist/assets/*.css | head -1
```

预期：五条 grep 各输出一次，无缺失。

**开启系统级「减弱动态效果」后逐项走查**（Linux/GNOME：设置 → 无障碍 → 减弱动画；或 Chrome DevTools → Rendering → Emulate CSS media feature `prefers-reduced-motion: reduce`）：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 触发确认对话框 | 模态**直接出现**，无缩放/位移过渡 |
| 2 | 关闭模态 | 直接消失 |
| 3 | 触发 Toast | 直接出现、直接消失，**无右移** |
| 4 | 点「扫描」 | 按钮上的 spinner **不旋转**（静止的加载图标），文字变「扫描中…」，功能正常 |
| 5 | 勾选某行 → 点「执行重命名」 | 遮罩直接出现，spinner 静止，执行正常完成 |
| 6 | 悬停表格行 | 行底色**瞬间**变化（无 150ms 过渡） |
| 7 | 扫描一个大目录，看骨架行 | 灰块是**静态**的，不再呼吸（`animate-pulse` 被兜底关掉）—— 这正是「骨架屏的克制版本」，不是 bug |
| 8 | 点任意按钮 | `:active` 的 `scale-[.98]` 仍生效（它是即时变换，不是过渡） |
| 9 | 关闭「减弱动态效果」 | 上述动效全部恢复（骨架重新开始呼吸） |

第 4、7 项的「spinner 静止 / 骨架不呼吸」是正确行为，不是 bug —— `animate-spin` 与 `animate-pulse` 都是无限循环动画，被兜底规则压到 1 次、`.01ms` 正是设计意图。**本项目的动效兜底不需要任何 `@media` 分支写在组件里**，Task 4 的通配符规则一次覆盖 Tailwind 工具类、组件 `<style>` 里的 transition、以及这两处 keyframes 动画。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/style.css
git commit -m "feat(frontend): 加全局 prefers-reduced-motion 兜底"
```

---

### Task 5: `aria` 与 `focus-visible` 全量收口

spec §3.4 实测的两项零值（`aria-*` 0 处、`focus-visible` 0 处）在前三期已由原语与布局组件填上大部分。本任务做**审计 + 补齐剩余的具体缺口**。

**Files:**
- Modify: `frontend/src/components/FileTable.vue`
- Modify: `frontend/src/components/layout/AppTopBar.vue`（若审计发现问题）
- 其他由审计结果决定

**Interfaces:**
- Consumes: 前三期的全部产物
- Produces: 无新接口；表格容器新增 `aria-busy`、表格元素新增 `aria-label`

- [ ] **Step 1: 审计 —— 找出所有缺 `focus-visible` 的原生控件**

```bash
cd frontend && for f in $(grep -rl "<button\|<input\|<select\|<a " src --include=*.vue); do
  n=$(grep -c "<button\|<input\|<select\|<a " "$f")
  fv=$(grep -c "focus-visible" "$f")
  if [ "$fv" -eq 0 ]; then
    echo "缺 focus-visible: $f （$n 个原生控件）"
  fi
done
echo "--- 审计结束 ---"
```

预期：`--- 审计结束 ---` 之前**没有输出**。

若有输出：逐个打开列出的文件，给每个原生控件补上与其他元素一致的聚焦样式：

```html
focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none
```

（背景是 `canvas` 的元素把 `ring-offset-surface` 换成 `ring-offset-canvas`。）

- [ ] **Step 2: 审计 —— 确认 `aria-*` 不再是零**

```bash
cd frontend && echo "--- 各文件的 aria 属性数（不应有 0）---" && \
  for f in $(grep -rl "<button\|<input\|<select\|role=" src --include=*.vue); do
    n=$(grep -c "aria-\|role=" "$f")
    printf "%-52s %s\n" "$f" "$n"
  done
```

预期：列出的每个文件计数都 ≥ 1。

- [ ] **Step 3: 补表格本身的 `aria-label` 与容器的 `aria-busy`**

编辑 `frontend/src/components/FileTable.vue`：

`<table>` 加无障碍名（表格没有 `<caption>`，读屏会把一堆表格单元格念成一串数字）：

```html
      <table class="w-full min-w-[560px] text-[13px]" aria-label="文件重命名预览">
```

滚动容器加 `aria-busy`（骨架显示期间告诉读屏「这个区域正在更新」，这是 `aria-busy` 的正确归属 —— 见 Review Focus 第 5 条）：

```html
    <div class="min-h-0 flex-1 overflow-auto" :aria-busy="scanning ? 'true' : undefined">
```

**不要**把 `aria-busy` 加到 `ExecutingOverlay` 的 `role="status"` 卡片上（它已经有了，重复挂会让同一次状态变化被播报两遍）。

- [ ] **Step 4: 构建并做键盘走查**

```bash
cd frontend && npm run build && npm run dev
```

**全站键盘走查**（spec §15 第 4 条）—— 全程**只用键盘**，不用鼠标：

| # | 起点 | 操作 | 预期 |
|---|---|---|---|
| 1 | 页面加载后 | 连按 `Tab` | 焦点顺序：顶栏源切换 → 设置入口 → 左栏折叠头 → 左栏分组头 → 左栏表单 → 模板表单 → 变量 chips → 表格按钮 → 表头复选框 → 行控件 → 底栏 → 回到顶栏 |
| 2 | 任意位置 | 看焦点指示 | **每一站**都有清晰的青绿聚焦环，没有一处「焦点消失」 |
| 3 | 顶栏源切换 | 按 `Enter` | 切换数据源 |
| 4 | 左栏分组头 | 按 `Enter` | 分组收起 / 展开 |
| 5 | 表格行输入框 | 输入后按 `Tab` | 正常移出，不触发提交 |
| 6 | 底栏 | `Tab` 到「执行重命名」→ `Enter` | 弹出确认对话框 |
| 7 | 对话框内 | 按 `Tab` 循环 | 焦点在对话框内循环，**不逃逸**到背景 |
| 8 | 对话框内 | 按 `Esc` | 关闭；焦点**回到**触发它的「执行重命名」按钮 |
| 9 | 变量 chip | `Tab` 到某个 chip → `Enter` | 变量插入模板输入框，且焦点回到输入框 |
| 10 | 全流程 | 打开读屏 | 表格被念作「文件重命名预览，表格」；扫描中读到「忙」；执行中读到「正在执行重命名…」 |

第 2 项若在某处失败，回到 Step 1 的审计命令，扩大正则（当前审计只覆盖 `<button` / `<input` / `<select` / `<a `，漏掉了 `<textarea` 与带 `@click` 的 `<div>`）。补一条：

```bash
cd frontend && grep -rn "textarea\|<div[^>]*@click" src --include=*.vue
```

预期：无输出。若有，把那些 `<div @click>` 换成 `<button type="button">`。

- [ ] **Step 5: 提交**

```bash
git add frontend/src
git commit -m "a11y(frontend): 补表格 aria-label 与 aria-busy, 全量收口 focus-visible"
```

---

### Task 6: 删除过渡别名层

第一期为让旧组件在新配色下继续渲染而加的临时别名层，到这里所有组件都已改用新 token，可以删了。**删除的前提是正则审计到 0 命中** —— 否则被删的类名会静默失效（按钮变透明、边框消失），构建不报错。

**Files:**
- Modify: `frontend/src/style.css`

**Interfaces:**
- Consumes: 无
- Produces: `style.css` 只剩**一套** token；旧名 `primary` / `primary-hover` / `primary-light` / `bg` / `surface-muted` / `border` / `border-strong` / `text` / `text-secondary` / `text-muted` / `text-faint` / `success` / `success-light` / `warning` / `warning-light` / `error` / `error-light` **全部失效**

- [ ] **Step 1: 审计 —— 旧 token 类名必须 0 命中**

```bash
cd frontend && PAT='(?<![\w-])(bg|text|border|ring|ring-offset|divide|fill|stroke|placeholder|caret|accent|outline|shadow)-(primary|primary-hover|primary-light|bg|surface-muted|border|border-strong|text|text-secondary|text-muted|text-faint|success|success-light|warning|warning-light|error|error-light)(?![\w-])'; \
  echo "命中数（必须为 0）: $(grep -rnP "$PAT" src/ | wc -l)" && \
  grep -rnP "$PAT" src/
```

预期：命中数 **0**，且 `grep` 无输出。

> **注意正则里没有 `border-control`**：`border-border-control` 是**新** token（交互控件边框），把它写进禁用名单会让审计永远无法归零。第一期实测已确认这条正则对 `border-border-control` / `bg-surface` / `text-ink-2` / `ring-offset-canvas` 均无误报，对 `bg-surface-muted` / `border-border-strong` / `text-text-secondary` / `bg-error-light` / `ring-primary/20` 均能命中。基线（改造前）是 **178** 处、分布于 12 个文件。

若有命中：逐个改写成新 token 名后再回到这一步。映射表：

| 旧名 | 新名 |
|---|---|
| `primary` / `primary-hover` / `primary-light` | `accent` / `accent-hover` / `accent-soft` |
| `bg`（背景） | `canvas` |
| `surface-muted` | `sunken` |
| `border`（装饰分割） | `line` |
| `border-strong` | `line-strong` |
| `text` / `text-secondary` / `text-muted` / `text-faint` | `ink` / `ink-2` / `ink-3` / `ink-3` |
| `success` / `success-light` | `ink-2` / `sunken`（spec §5.2：不再用绿色表达成功） |
| `warning` / `warning-light` | `warn` / `warn-soft` |
| `error` / `error-light` | `danger` / `danger-soft` |

- [ ] **Step 2: 删除别名块**

编辑 `frontend/src/style.css`，删掉整段「过渡别名层」，即从这一行开始：

```css
/* ==========================================================================
   过渡别名层 —— 第四期删除
```

到该 `@theme { ... }` 块的闭合 `}` 为止（含块前的注释）。

删除后 `style.css` 应该只剩：`@import "tailwindcss";` → 一个 `@theme` 块（新 token + 字体 + 阴影）→ `html/body/#app` 基线 → `*` / `button` / `input,select,textarea` → 滚动条样式 → `prefers-reduced-motion` 兜底块（Task 4 加的）。

- [ ] **Step 3: 构建并验证没有样式静默失效**

```bash
cd frontend && npm run build && \
  echo "--- 旧 token 在产物 CSS 中应已消失 ---" && \
  grep -oE -- "--color-(primary|primary-hover|primary-light|bg|surface-muted|border|border-strong|text|text-secondary|text-muted|text-faint|success|success-light|warning|warning-light|error|error-light)(:|\b)" dist/assets/*.css | sort -u
```

预期：**无输出**。

若仍出现，说明 `@theme` 里还有别处定义（不该有），或删除范围不完整。

- [ ] **Step 4: 视觉回归 —— 逐页对照改前的截图**

```bash
cd frontend && npm run dev
```

对照 `screenshot/` 里的三张旧图与 Task 7 将要留档的新图，逐页确认**没有任何元素丢掉样式**：

| # | 页面 | 检查点 |
|---|---|---|
| 1 | `/#/` 工作区 | 顶栏白底 + 底边发丝线；左栏浅灰；表格白底 + 发丝线；**没有透明按钮、没有无边框输入框、没有默认黑字** |
| 2 | `/#/` 表格 | 表头浅灰底深灰字；行 hover 有底色；状态徽章有底色 |
| 3 | `/#/` 底栏 | 白底 + 顶边发丝线；两个按钮样式正常 |
| 4 | 三个对话框 | 卡片白底 + 阴影；按钮与徽章样式正常 |
| 5 | `/#/settings` | 三个面板白底 + 发丝线；表单控件边框可见 |
| 6 | Toast | 四种类型的底色都在 |
| 7 | 执行遮罩 | 半透明深色 + 白卡片 |
| 8 | 全站扫一遍 | **任何地方都不该出现「本来是彩色的现在变透明/变黑」** |

第 8 项是这一步的核心。一旦发现，用 Step 1 的正则重新定位（正则可能漏了某个工具前缀，比如 `decoration-` / `from-` / `to-` / `via-`，或写在 `<style>` 块里的 `var(--color-primary)` 这类直接引用）。

**顺带确认没有 `var(--color-*)` 直接引用**：

```bash
cd frontend && grep -rn "var(--color-\(primary\|text\|border\|success\|warning\|error\)" src/ ; echo "(以上应为空)"
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/style.css
git commit -m "refactor(frontend): 删除过渡别名层, style.css 只剩一套 token"
```

---

### Task 7: spec §15 全量验证 + 截图留档

**本任务不改代码**（除非验证发现问题）。逐项跑 spec §15 的 9 条，每条留下可复核的证据。

**Files:**
- Create: `screenshot/after-home.png`
- Create: `screenshot/after-home-long-table.png`
- Create: `screenshot/after-home-rail-collapsed.png`
- Create: `screenshot/after-mobile.png`
- Create: `screenshot/after-settings.png`
- Create: `screenshot/after-browse.png`

**Interfaces:**
- Consumes: 前六期与本期前六任务的全部产物
- Produces: 一个可归档的验证结论

- [ ] **Step 1: §15.1 构建**

```bash
cd frontend && rm -rf dist && npm run build 2>&1 | tee /tmp/build.log
```

预期：`✓ built in …`，且日志里**没有 warning**。检查：

```bash
grep -iE "warn|error" /tmp/build.log ; echo "(以上应为空)"
```

- [ ] **Step 2: §15.2 功能实跑 —— 四条路径**

```bash
cd backend && python run.py
```

另开一个终端：

```bash
cd frontend && npm run dev
```

准备：一个含 ≥300 个视频文件与部分字幕的本地目录；一个可连的 OpenList 服务（连不上时第 3、4 条标注为「环境不可用，未验证」）。

| # | 路径 | 预期 |
|---|---|---|
| 1 | 本地：扫描 → 预览 → 试运行 | 扫描出文件；`新文件名` 列有值；结果对话框显示成功数且 `failed` 为 0 |
| 2 | 本地：执行重命名 | 结果对话框逐条列出；去磁盘核对，文件名与对话框一致；`失败` 块为灰底（0 个失败） |
| 3 | OpenList：连接 → 浏览 → 扫描 | 连接成功；挂载点下拉有值；浏览对话框能进目录；扫描出文件 |
| 4 | OpenList：试运行 | 结果对话框显示将要生成的文件名，**磁盘未被改动** |
| 5 | 本地：制造一次失败（把某个文件设为只读，或对无权限目录执行） | 结果对话框里该行是**红底红字徽章**，「失败」计数为红；界面无崩溃 |

- [ ] **Step 3: §15.3 补零位数闭环**

（若第三期 Task 8 因后端未合入而跳过，本步记为「不适用 —— 后端未合入」并在结论里写明。）

| # | 操作 | 预期 |
|---|---|---|
| 1 | `/#/settings` → 集数补零位数改 **3** → 保存 | 「设置已保存」 |
| 2 | 回工作区 → 点「预览」 | 新文件名列出现形如 `剧名 - S01E001.mkv` |
| 3 | 检查 Network | `preview` 请求的 Payload 里 `episode_pad_digits: 3` |

出现 `S01E001` = §13 打通。

- [ ] **Step 4: §15.4 键盘走查**

直接复用 Task 5 Step 4 的 10 项走查表，重跑一遍并记录结果。

- [ ] **Step 5: §15.5 对比度抽检**

用 DevTools 的取色器 + 对比度检查器，对实际渲染值逐项复核 spec §5.1 的表：

| 前景 | 背景 | 要求 | 取样位置 |
|---|---|---|---|
| `ink` `#15181B` | `canvas` `#F6F7F8` | ≥ 4.5:1 | 左栏的说明文字 |
| `ink-2` `#4B5257` | `surface` `#FFFFFF` | ≥ 4.5:1 | 表格**表头**文字 |
| `ink-3` `#6B7278` | `surface` `#FFFFFF` | ≥ 4.5:1 | 设置页输入框的 placeholder |
| 白 | `accent` `#0F766E` | ≥ 4.5:1 | 「执行重命名」按钮文字 |
| 白 | `danger` `#B3261E` | ≥ 4.5:1 | 「清空」按钮悬停态 |
| `accent` | `accent-soft` `#E6F4F2` | ≥ 4.5:1 | 顶栏选中的源切换段 |
| `warn` `#8A5F00` | `warn-soft` `#FDF6E3` | ≥ 4.5:1 | 「待确认」徽章 |
| `danger` | `danger-soft` `#FDECEA` | ≥ 4.5:1 | 结果对话框的失败徽章 |
| `border-control` `#8A9199` | `surface` `#FFFFFF` | ≥ 3:1 | 任意输入框的边框 |

**另外抽检两处 spec §5.1 特意点名的易错点：**

| 检查点 | 预期 |
|---|---|
| 表头文字颜色 | 是 `ink-2`，**不是** `ink-3`（`ink-3` 对 `sunken` 底只有 4.23:1，不合格） |
| 任意输入框边框颜色 | 是 `border-control` `#8A9199`，**不是** `line-strong` `#CDD2D7`（后者对白底只有 1.52:1） |

任一不合格：定位到具体元素，改用正确的 token，然后从 Step 1 重跑。

- [ ] **Step 6: §15.6 reduced-motion**

复用 Task 4 Step 2 的 8 项走查表，重跑并记录。

- [ ] **Step 7: §15.7 响应式四档**

| 断点 | 检查点 |
|---|---|
| 1280×900 | 三栏：左栏 280px + 工作区；底栏常驻；表格内部滚动；顶栏单行 |
| 1024×900 | 三栏成立（这是三栏的下界）；表格此时**会有横向滚动**（列宽合计约 900px > 工作区 744px），滚动发生在表格内部、整页不滚动 |
| 768×900 | 左栏变成顶栏下的折叠条且**默认收起**；展开后高度 ≤ 45% 视口；底栏常驻 |
| 375×812 | 表格横向滚动；首屏可见复选框与原文件名列；底栏**不换行、不溢出、不消失**；顶栏单行 |

逐档截图，归入 Step 9 的留档。

- [ ] **Step 8: §15.8 长表格专项**

这是 spec §17 风险表第一行（`min-h-0` 遗漏）的专项验证。

| # | 操作 | 预期 |
|---|---|---|
| 1 | 扫描 ≥300 文件 | **整页不滚动** —— 用 DevTools 的 Elements 面板确认 `document.documentElement.scrollHeight` 不超过视口高度 |
| 2 | 用鼠标滚轮在表格上滚动 | 只有表格内部滚；顶栏、左栏、底栏全不动 |
| 3 | 滚到表格中部 | 表头仍然粘在表格区顶部 |
| 4 | 滚到底部 | 底栏仍然钉在视口底部 |
| 5 | 在 Console 里 `document.documentElement.scrollHeight - window.innerHeight` | 结果 ≤ 1（即无整页溢出） |

第 5 项是本项最硬的判据。若结果远大于 1，说明 `min-h-0` 链断了，逐环排查（`App.vue` 路由出口 → `HomeView` 根 → 中段 → `<main>` → `FileTable` 根 → 滚动容器）。

- [ ] **Step 9: §15.9 截图留档**

用同一台机器、同一个浏览器窗口，按下列尺寸存图到 `screenshot/`。文件名带 `after-` 前缀，与改造前的三张并列，便于前后对比。

| 文件名 | 尺寸 | 内容 |
|---|---|---|
| `after-home.png` | 1280×900 | 工作区，已扫描出文件、预览列有值 |
| `after-home-long-table.png` | 1280×900 | 300+ 文件的表格，滚到中部（表头 sticky 可见、底栏在底部） |
| `after-home-rail-collapsed.png` | 900×900 | 左栏折叠条为收起态 |
| `after-mobile.png` | 375×812 | 表格横向滚动状态 |
| `after-settings.png` | 1240×906 | 设置页（与 `settings.png` 同尺寸，可直接叠图对比） |
| `after-browse.png` | 523×545 | 目录选择对话框（与 `browse.png` 同尺寸） |

- [ ] **Step 10: 汇总验证结论**

把 Step 1–9 的结果整理成一份清单，附在提交信息或 PR 描述里。每一项写「通过 / 不通过 / 不适用（原因）」，**不通过与不适用的必须写明**。

spec 已知遗留（不在本轮范围，验证结论里一并声明）：

1. `openlist.concurrency` / `requestInterval` 仍是假设置（后端读 `config.py`），设置页已标注说明
2. 无暗色主题
3. 无前端自动化测试 —— 本轮只新增了 `frontend/scripts/check-settings-schema.mjs` 这一个设置 schema 断言脚本，未引入测试框架

- [ ] **Step 11: 提交**

```bash
git add screenshot/after-*.png
git commit -m "docs: 前端重构改后截图留档"
```

---

## 全系列完成后的状态

对照 spec §3 的 15 条技术债：

| # | 问题 | 状态 |
|---|---|---|
| 1 | 卡片汤 | ✅ 左栏为分节 + 发丝线，工作区为表格主区（第二期） |
| 2 | 主操作离手最远 | ✅ 执行按钮移入常驻底栏（第二期） |
| 3 | `SourceTabs` 独立成卡 | ✅ 内容并入顶栏，文件删除（第二期） |
| 4 | 宽屏左侧约 600px 全空 | ✅ 三栏工作台（第二期） |
| 5 | 输入框样式手写 18 处 | ✅ 清零（第二期清 8 处 + 第三期清 10 处） |
| 6 | 按钮 3 套手写变体 | ✅ 收敛到 `AppButton` 四个变体（第二、三期） |
| 7 | 圆角混用 | ✅ 控件 8px / 面板 12px 两档（第一至三期） |
| 8 | `shadow-sm` 全场同款 | ✅ 默认无阴影，仅 `shadow-overlay`（第一至三期） |
| 9 | `--color-secondary` 死 token | ✅ 第一期重写时不再保留 |
| 10 | 设置断线 | ✅ `settings` store 接通（第三期） |
| 11 | 补零位数是假设置 | ✅ 后端 + 前端端到端打通（第三期，依赖后端计划） |
| 12 | Emoji 当图标 4 处 | ✅ 清零（第一期 1 处 + 第二期 2 处 + 第三期 1 处） |
| 13 | 空态仅一行字 | ✅ 图标 + 标题 + 说明 + 主操作（本期 Task 3） |
| 14 | 扫描中用蒙层而非骨架屏 | ✅ 骨架行（本期 Task 2）；顺带发现原蒙层是**死代码**，从未渲染过 |
| 15 | `ExecutingOverlay` 动效无意图 | ✅ 精简为单一进度指示（本期 Task 1） |
| — | 全项目 `focus-visible` 0 处 | ✅ 由原语内置 + 全量收口（本期 Task 5） |
| — | 全项目 `aria-*` 0 处 | ✅ 同上 |
| — | 全项目 `prefers-reduced-motion` 0 处 | ✅ 全局兜底（本期 Task 4） |

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
| §10 表格加载中用骨架行、行高与真实行一致、不跳布局 | Task 2（含浏览器内量高校准步骤） |
| §10 表格空态 = 图标 + 标题 + 一句说明 + 主操作，垂直居中 | Task 3 |
| §10 扫描中按钮 loading 态 | 第二期 Task 4（`SourceConfigPanel`）；本期 Task 4 Step 2 第 4 项验证它在 reduced-motion 下仍可用 |
| §10 执行中保留阻断式 overlay，但单一进度指示 | Task 1 |
| §10 成功 Toast `role="status"` / 失败 `role="alert"` | 第三期 Task 7；本期 Task 5 复核 |
| §11 删除 `ExecutingOverlay` 的动画堆叠 | Task 1 |
| §11 全局 `prefers-reduced-motion` 兜底 | Task 4 |
| §11 动效表之外的动画一律不加 | Task 2 Step 2 的骨架「不加 `animate-pulse`」、Task 1 的遮罩改纯 opacity、第三期 Task 7 的 Toast 改淡入 |
| §5.1 对比度逐项复核 | Task 7 Step 5（照抄 spec §5.1 的表，逐行取样） |
| §5.1 表头必须 `ink-2`、控件边框必须 `border-control` | Task 7 Step 5 的「易错点抽检」 |
| §6.3 字号阶梯只有 6 档 | Global Constraints；本期 Task 7 Step 4 的视觉回归覆盖 |
| §15.1 构建无警告 | Task 7 Step 1 |
| §15.2 四条功能路径 | Task 7 Step 2（列了 5 条，含失败路径） |
| §15.3 补零位数闭环 | Task 7 Step 3 |
| §15.4 键盘走查 | Task 5 Step 4 + Task 7 Step 4 |
| §15.5 对比度抽检 | Task 7 Step 5 |
| §15.6 reduced-motion | Task 4 Step 2 + Task 7 Step 6 |
| §15.7 响应式四档 | 第二期 Task 7 + 本期 Task 7 Step 7 |
| §15.8 长表格 | Task 7 Step 8（给出 `scrollHeight - innerHeight ≤ 1` 的硬判据） |
| §15.9 截图对比留档 | Task 7 Step 9（6 张，含 2 张与旧图同尺寸可直接叠图） |
| §16 阶段 7 收尾 | Task 1–6 |
| §16 阶段 8 全量验证 + 截图 | Task 7 |
| §3.4 `focus-visible` / `aria-*` / `reduced-motion` 三项零值 | Task 4、Task 5 |
| §17 遗留 1（假设置）| Task 7 Step 10 声明 + 第三期 Task 3 的页面标注 |
| §17 遗留 2（无暗色）| Task 7 Step 10 声明 |
| §17 遗留 3（无前端测试设施）| Task 7 Step 10 声明；本期未引入测试框架，只新增了第三期的 schema 断言脚本 |

**占位符扫描**：无 TBD / TODO / 「类似 Task N」/「视情况调整」。Task 2 的 `h-[58px]` 明确标注为**待校准初值**并给了测量与回填步骤，不是占位符 —— 它是一个我无法在无浏览器环境下测得的真实数值，用步骤代替猜测。

**类型一致性**：`FileTable` 的 props 在前三期保持不变，本期**新增 `scanning: Boolean`**，并在 Task 2 的 Interfaces 里显式声明；`HomeView` 同任务内同步传入。`stores/files.js` 的 `scanning` 被删除，Task 2 Step 5 用 grep 确认无残留。`emptyState` 计算属性在同任务内定义并使用。Task 6 的映射表与第一期 Task 2 的别名块逐行对应（17 个旧名 → 新名，无遗漏、无多出）。

**Review Focus 落位**

| # | 条目 | 验证位置 |
|---|---|---|
| 1 | reduced-motion 需覆盖三类动效载体 | Task 4 Step 1 的注释说明为何用通配符 + Step 2 的五条产物 grep + 8 项走查（其中第 4、5 项专测 `animate-spin`） |
| 2 | 删别名层后类名静默失效 | Task 6 Step 1（正则审计归零，含正则为何不含 `border-control` 的说明）+ Step 3（产物 CSS 无旧变量）+ Step 4（8 项视觉回归） |
| 3 | 骨架行与真实行高不一致 | Task 2 Step 3（浏览器内量高的完整步骤）+ Step 3 走查表第 2 项 |
| 4 | 空态在窄屏被压成一条 | Task 3 Step 1（挪出 `<td>` 的理由）+ Step 3 走查表第 1、6 项 |
| 5 | `aria-busy` 与 `role="status"` 重复播报 | Task 1 Step 1 的注释（两者语义不同、分挂两处）+ Task 5 Step 3（`aria-busy` 挂表格容器、明确不挂 `ExecutingOverlay`） |

**未覆盖（有意）**：无。spec §15 的 9 项全部有对应步骤；spec §16 阶段 7–8 全部覆盖。
