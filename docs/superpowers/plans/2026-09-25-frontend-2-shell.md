# 前端重构 · 第二期：App Shell 与三栏工作台 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「5 张同款白卡片竖排 + 主操作沉底」变成**三栏工作台**：顶栏 56px、左栏 280px、底栏 56px 常驻，表格撑满剩余高度并在内部滚动。这是本次重构**风险最高**的一期（spec §16 阶段 3），每一步都是独立提交点，便于单独回退。

**Architecture:** 换成 Pinia `stores/workspace.js` 承接工作区的全部状态与流程，`HomeView` 退化为纯模板；`App.vue` 成为真正的 App Shell（顶栏 + 路由出口），工作区的三栏结构由 `HomeView` 在路由出口内实现。这样底栏不会出现在设置页上。

**Tech Stack:** Vue 3.5.43 / Vue Router 4（hash 模式）/ Vite 5 / Tailwind CSS v4 / Pinia 2 / lucide-vue-next

**Spec:** `docs/superpowers/specs/2026-09-25-frontend-refactor-design.md`（§7 布局架构、§3.1 结构问题、§16 阶段 3）

**前置:** `docs/superpowers/plans/2026-09-25-frontend-1-foundation.md` 已完成。本期直接使用第一期产出的新 token、过渡别名层、`BrandMark` 与六个 UI 原语（`AppButton` / `AppInput` / `AppSelect` / `AppCheckbox` / `AppBadge` / `AppPanel`）以及重写后的 `AppModal`。**开工前确认第一期已合入。**

**后续:** `2026-09-25-frontend-3-features.md`、`2026-09-25-frontend-4-polish.md`

---

## Global Constraints

四期通用约束（与第一期完全一致，此处重申本期最相关的几条）：

- **中间层必须有 `min-h-0`**（spec §7.2）。Grid / Flex 子项默认 `min-height: auto`，会被内容撑破，导致表格内部滚动失效、整页滚动。这是本布局能成立的**前提**，不是可选项
- 根容器用 `h-dvh` 而非 `h-screen`（spec §7.2），移动端地址栏收放时高度才正确
- 圆角只允许 `rounded-[8px]`（控件）/ `rounded-[12px]`（面板 / 模态 / 下拉）。**禁止** `rounded-md` / `rounded-lg` / `rounded-xl` / `rounded-2xl` / `rounded-full`
- **默认无阴影**，唯一例外 `shadow-overlay`
- 表格表头文字用 `text-ink-2`（对 `sunken` 底 `ink-3` 只有 4.23:1，低于 AA）
- 路径与文件名**不用** `font-mono`（spec §6.2）；表格数字列加 `tabular-nums`（spec §6.4）
- 每个任务结束时 `cd frontend && npm run build` 必须通过，且应用可运行 —— **不做「中间态全坏、最后一次性跑通」的重构**
- 路由路径与 URL 不变（spec §2）：仍是 `/` 与 `/settings`，仍是 hash 模式
- 不做暗色主题

### 本期的组件改造规则（避免同一文件被改两遍）

> **第二期新建或重写的文件，直接使用新 token 名与 UI 原语；第二期未触碰的旧文件，留到第三期改造。**

据此分配 spec §3.2 第 5 条那 **18 处**手写输入框样式：

| 来源文件 | 手写处数 | 本期处理 |
|---|---|---|
| `views/SettingsView.vue` | 7 | 第三期（本期只给它加外层滚动容器） |
| `components/ScanPanel.vue` | 4 | **本期**：改写为 `SourceConfigPanel`，直接用原语 |
| `components/TemplateConfig.vue` | 3 | **本期**：移入左栏时直接改用原语 |
| `components/FileTable.vue` | 3 | 第三期（本期只改容器与滚动结构） |
| `components/ActionBar.vue` | 1 | **本期**：文件删除，内容并入 `AppBottomBar`，直接用原语 |

本期消化 8 处，第三期消化 10 处，合计 18 处清零。

- **组件 `<style>` 块里不得出现 `var(--color-*)` 对「旧别名」的引用**（`--color-primary` / `--color-text` / `--color-border*` / `--color-surface-muted` / `--color-success*` / `--color-warning*` / `--color-error*`）。别名块是本期的过渡脚手架且**刻意非 `static`** —— 没有任何工具类引用它的别名会被 Tailwind tree-shake 掉，`var()` 于是静默解析为空；何况第四期会整块删除。需要颜色时一律用工具类（`bg-accent` / `text-ink-2` …）。本期新建或重写的组件如需自定义过渡，只用**新** token（`--color-ink` 等，它们在 `@theme static` 块里，一定存在）。

- **按钮光标由 `style.css` 的基线规则统一提供**（`button:not(:disabled) { cursor: pointer }`，Tailwind v4 的 preflight 删掉了 v3 的等价声明）。因此新写的裸 `<button>` **不需要**再写 `cursor-pointer`，也**不得**给它加与之冲突的 cursor 类。禁用态由 `disabled:cursor-not-allowed` 负责：`:not(:disabled)` 让两者不在同一个元素上竞争。**不要**把它简化成裸 `button { cursor: pointer }` —— 该基线规则是层外样式，按 CSS 级联层规则优先于 Tailwind 的层内工具类，**与特异性无关**，写成裸选择器会覆盖掉禁用态的 `not-allowed`。

## 本任务需携带的前序评审发现

**F2-T1 评审的 Minor（在你的改动之后会变成可达）**：`stores/workspace.js` 的 `browseConfirm()` 把结果写到 `path.value`（即**当前**源的路径），而浏览对话框自己的来源被单独记在 `browse.source` 里。两者的不变式是隐式的：今天的入口只有 ScanPanel 内部，而 ScanPanel 的渲染受 `v-if="source === 'local'"` 约束，所以它们总是一致。

**本任务把源切换搬到顶栏之后，那个窗口就可达了** —— 顶栏的 segmented 可以在数据源切换的 180ms `mode="out-in"` 离场过渡期内被点击，此时「正在离场的 ScanPanel」仍可点、而 `ws.activeSource` 已经翻转，于是一次浏览选择会被写进**另一个源**的路径。

如果你在实现顶栏时发现这个窗口真的可达，顺手收紧 `browseConfirm()`：改成写 `sourceStates[browse.source].path = pick.path`，或在 `browse.source !== activeSource.value` 时直接 return。这不是本任务的验收项，只是把评审记录带过来。

---

- **源码文件的注释里不要写字面类名**（`.vue` / `.js`；`style.css` 的注释不受影响）。实测 Tailwind 4.3.3：CSS 入口文件注释里的 `border-line-strong` 不生成规则，而 **`.vue` 注释里的 `rounded-[12px]` 与 `grid-rows-[56px_1fr]` 各生成一条真实规则**。两个后果：①产出无人使用的死 CSS；②**类名闸门会因为「注释提过」而通过** —— 一个没有任何元素使用的类名，只要在源码注释里出现过就会命中，闸门于是为它开绿灯。需要提到某个类名时，**描述它而不要写字面量**（「两行 grid / 上方滚动区 / 下方 56px 底栏」而不是把类名抄一遍）。

## Review Focus

1. **`min-h-0` 链断了任意一环** —— 链路上共有 5 个容器（`App.vue` 的路由出口 → `HomeView` 根 → 中段 → `WorkArea` → `FileTable` 根）。断任何一环，表格都不再内部滚动，而是把整页撑高、底栏被推到屏外 —— 正是本次重构要消灭的那个 bug。期望：150cm 高的长表格下，底栏仍钉在视口底部。
2. **底栏出现在设置页上** —— 底栏是工作区专属。若把它提到 `App.vue`，设置页会显示一个「执行重命名」按钮，点下去操作的是用户看不见的文件列表。期望：`/#/settings` 上没有任何执行入口。
3. **切换数据源时丢失已扫结果** —— 顶栏的源切换移出了 `HomeView`，原来由 `watch(activeSource)` 做的「存旧源 / 载新源」很容易在迁移中丢掉。期望：本地扫出文件 → 切到 OpenList → 切回本地，**文件列表与预览行原样还在**。
4. **窄屏下「原文件名」与「新文件名」不能同屏** —— DOM 顺序是 `# | ☑ | 原文件名 | 解析剧名 | 季 | 集 | 状态 | 新文件名`，这一对需要对照的列被中间四列隔开，在 375px 上无法同时完整显示。**已定的取舍**：窄屏隐去 `解析剧名` 与 `#`、并收缩其余列宽（表宽 552px），把必须的横向滚动压到**一次约 180px 的短滑**；桌面端不受影响。**不做**冻结列（冻结「复选框 + 原文件名」占 268px，会让 220px 宽的「新文件名」在 375px 上永远显示不全，比不冻结更糟）；**不做**窄屏卡片式行布局（通行最佳实践，但需为数据行写第二套模板，对桌面优先的自托管工具收益不抵成本，已显式记为不在本轮范围）。→ Task 6 Step 1 的三层做法 + Step 2 走查表第 8、9 项测量实际表宽
5. **模板/预设变更后预览不刷新** —— 原来由 `HomeView` 的 `watch` 触发 `buildPreview()`，迁到 store 后 `watch` 也必须一起迁。期望：改模板输入框任意一个字符，表格「新文件名」列立即变。

---

## 前期实测结论

| 结论 | 依据 |
|---|---|
| 当前 `App.vue` 是「左侧 240px 固定侧栏 + 右侧路由内容」，侧栏内含 🎬 emoji 与两个导航项；`ActionBar` / `SourceTabs` 都由 `HomeView` 渲染 | 读代码 |
| `HomeView.vue` 522 行，其中约 390 行是 `<script setup>`：状态、扫描、预览、执行、浏览、toast、confirm 全在里面 | 读代码 |
| `FileTable.vue` 的滚动容器写死 `style="max-height: 480px"`，表头已是 `sticky top-0`；卡片外层 `rounded-xl shadow-sm` | `FileTable.vue:39,41` |
| `ScanPanel.vue` 是**横向**一行排放（路径 `min-w-[280px]` + 两个复选框 + 扫描按钮），直接塞进 280px 左栏会溢出 | `ScanPanel.vue:5-34` |
| `SourceTabs.vue` 共 29 行，就是一个 tab bar 套了一层卡片壳 | 读代码 |
| `ActionBar.vue` 共 48 行：冲突策略 select + 两个按钮 | 读代码 |
| `HomeView.vue` 与 `App.vue` 各有一个路由/源切换的过渡动画（`source-fade` / `page-fade`），**都不在 spec §11 的动效表里** | `HomeView.vue:507-522`、`App.vue:59-72` |
| 第一期已验证可用的类：`min-h-0`、`grid-rows-[56px_1fr]`、`grid-cols-[280px_1fr]`、`h-dvh`、`tabular-nums`、`lg:hidden` / `lg:block` / `lg:grid-cols-[280px_1fr]` 等任意值与响应式前缀均可生成 | 第一期探针构建 |

---

## File Structure

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `frontend/src/stores/workspace.js` | 工作区状态与流程（源切换 / 扫描 / 预览 / 执行 / 浏览 / 确认 / toast） | **新建** |
| `frontend/src/components/layout/AppTopBar.vue` | 顶栏：品牌标记 + 源切换 segmented + 设置入口 | **新建** |
| `frontend/src/components/layout/AppLeftRail.vue` | 左栏容器：两级折叠（窄屏整体折叠 + 分组折叠） | **新建** |
| `frontend/src/components/layout/AppBottomBar.vue` | 底栏：冲突策略 + 已选计数 + 试运行 / 执行 | **新建** |
| `frontend/src/components/SourceConfigPanel.vue` | 扫描源配置（垂直布局，替代横向的 ScanPanel） | **新建**（由 `ScanPanel.vue` 改写） |
| `frontend/src/App.vue` | App Shell：顶栏 + 路由出口 | **重写** |
| `frontend/src/views/HomeView.vue` | 工作区布局：左栏 / 工作区 / 底栏 | **重写**（状态迁出后只剩模板） |
| `frontend/src/views/SettingsView.vue` | 设置页 | 仅加外层滚动容器（整体改造在第三期） |
| `frontend/src/components/TemplateConfig.vue` | 模板配置 | 去卡片壳、垂直化、改用原语 |
| `frontend/src/components/FileTable.vue` | 文件表格 | 撑满高度、sticky 表头、内部滚动 |
| `frontend/src/components/ScanPanel.vue` | — | **删除** |
| `frontend/src/components/SourceTabs.vue` | — | **删除** |
| `frontend/src/components/ActionBar.vue` | — | **删除** |
| `frontend/src/components/layout/AppPanel`（无）| — | 本期左栏不使用 `AppPanel` —— 左栏的分组是「分节 + 发丝线」，不是卡片 |

---

### Task 1: 抽出 `stores/workspace.js`

把 `HomeView.vue` 里那 390 行 `<script setup>` 原样迁进一个 Pinia store。**这一步不改任何布局、不改任何外观**，只做状态搬家 —— 目的是让后面的顶栏 / 底栏能在 `HomeView` 之外读到工作区状态。搬完之后应用行为必须与搬之前**完全一致**。

**Files:**
- Create: `frontend/src/stores/workspace.js`
- Modify: `frontend/src/views/HomeView.vue`（`<script setup>` 大幅缩减，`<template>` 暂不动）

**Interfaces:**
- Consumes: 既有的 `stores/files.js` / `stores/template.js` / `stores/openlist.js`、`api/*`、第一期的 token 与别名层
- Produces: `useWorkspaceStore()`，导出以下成员 —— 第二、三期的顶栏 / 底栏 / 表格全部依赖此契约

  ```js
  // 状态（ref / reactive）
  activeSource        // 'local' | 'openlist'
  sourceStates        // { local: {...}, openlist: {...} } 各源独立的 files / scanResult / previewRows / scannedInfo / path
  recursive, includeSubs, scanning, executing, executeDryRun
  conflictStrategy    // 'skip' | 'abort' | 'overwrite' | 'rename_dup'
  resultDialog, lastResult
  olForm              // { server_url, username, password }
  browse              // { open, source, initialPath, rootPath, disallowRoot }
  confirm             // { open, message }
  toast               // { show, type, msg }

  // 计算属性
  path             // 当前源的路径，可写（get/set）
  previewRows      // 当前源的预览行，可写（get/set）
  scannedInfo      // 当前源的扫描汇总，可写（get/set）
  allSelected      // Boolean
  selectedCount    // Number
  totalCount       // Number

  // 动作
  initialize()                             // 拉预设 / 应用默认预设 / 恢复 OpenList 连接态
  switchSource(name)                       // 存旧源 + 载新源 + 清空预览
  doScan() / doOpenListScan()
  doOpenListLogin() / doOpenListLogout()
  onMountChange()
  openOpenListBrowseDialog() / openLocalBrowseDialog() / browseConfirm(pick)
  onPresetChange(value) / onTemplateEdit(value)
  buildPreview() / previewAll() / updatePreview(row)
  toggleAll(val) / clearAll()
  doDryRun() / doExecute() / executeAction(dryRun)
  askConfirm(message) -> Promise<Boolean>   // 由视图渲染 ConfirmDialog，store 只持 promise
  resolveConfirm(ok)
  showToast(msg, type)
  ```

- [ ] **Step 1: 创建 `frontend/src/stores/workspace.js`**

逐行照搬 `HomeView.vue:88-505` 的逻辑，只做两处机械调整：把 `ref` 提升为 store 的顶层 `ref`，把原来在 `onMounted` 里的内容收进 `initialize()`。

```js
import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import { scanDirectory } from '../api/scanner'
import { previewRename, executeRename, dryRunRename } from '../api/renamer'
import { getPresets } from '../api/template'
import {
  openlistLogin,
  openlistLogout as apiLogout,
  openlistStatus as apiOlStatus,
} from '../api/openlist'

import { useFilesStore } from './files'
import { useTemplateStore } from './template'
import { useOpenListStore } from './openlist'

export const useWorkspaceStore = defineStore('workspace', () => {
  const filesStore = useFilesStore()
  const tplStore = useTemplateStore()
  const olStore = useOpenListStore()

  const activeSource = ref('local')

  const sourceStates = reactive({
    local: { files: [], scanResult: null, previewRows: [], scannedInfo: null, path: '' },
    openlist: { files: [], scanResult: null, previewRows: [], scannedInfo: null, path: '' },
  })

  const recursive = ref(true)
  const includeSubs = ref(true)
  const scanning = ref(false)
  const executing = ref(false)
  const executeDryRun = ref(false)
  const conflictStrategy = ref('skip')
  const resultDialog = ref(false)
  const lastResult = ref(null)
  const olForm = reactive({ server_url: '', username: '', password: '' })

  const browse = reactive({
    open: false,
    source: 'local',
    initialPath: '',
    rootPath: '',
    disallowRoot: false,
  })

  const confirm = reactive({ open: false, message: '' })
  const toast = reactive({ show: false, type: 'info', msg: '' })

  let confirmResolver = null
  let toastTimer = null

  const path = computed({
    get: () => sourceStates[activeSource.value].path,
    set: (v) => { sourceStates[activeSource.value].path = v },
  })

  const previewRows = computed({
    get: () => sourceStates[activeSource.value].previewRows,
    set: (v) => { sourceStates[activeSource.value].previewRows = v },
  })

  const scannedInfo = computed({
    get: () => sourceStates[activeSource.value].scannedInfo,
    set: (v) => { sourceStates[activeSource.value].scannedInfo = v },
  })

  const allSelected = computed(() => {
    const selected = previewRows.value.filter(r => r.selected)
    return selected.length > 0 && selected.length === previewRows.value.length
  })

  const selectedCount = computed(() => previewRows.value.filter(r => r.selected).length)

  const totalCount = computed(() => previewRows.value.length)

  function showToast(msg, type = 'info') {
    toast.msg = msg
    toast.type = type
    toast.show = true
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { toast.show = false }, 2800)
  }

  async function initialize() {
    const res = await getPresets()
    if (res.data?.data) {
      tplStore.presets = res.data.data
      const def = tplStore.presets.find(p => p.id === tplStore.currentPresetId)
      if (def) tplStore.setPreset(def)
    }

    olForm.server_url = olStore.serverUrl || ''
    olForm.username = olStore.username || ''

    const statusRes = await apiOlStatus()
    if (statusRes.data?.connected) {
      olStore.setConnection(true, statusRes.data)
    }
  }

  function switchSource(name) {
    if (name === activeSource.value) return
    const prev = activeSource.value
    sourceStates[prev].files = [...filesStore.files]
    sourceStates[prev].scanResult = filesStore.scanResult

    activeSource.value = name
    filesStore.source = name
    filesStore.setFiles(sourceStates[name].files)
    filesStore.scanResult = sourceStates[name].scanResult
    // previewRows / scannedInfo 不需要恢复：它们是 `path` 那样的可写 computed，
    // 直接读写 activeSource 对应那一份 sourceStates，切源后自动指向新源。

    if (name === 'openlist') {
      tplStore.createSeasonFolder = false
    }
  }

  async function doScan() {
    if (!path.value) {
      showToast('请输入目录路径', 'warning')
      return
    }
    scanning.value = true
    try {
      const res = await scanDirectory({
        source: 'local',
        path: path.value,
        recursive: recursive.value,
        include_subtitles: includeSubs.value,
      })
      const data = res.data
      filesStore.source = 'local'
      filesStore.setFiles(data.files || [])
      filesStore.scanResult = data
      scannedInfo.value = data
      showToast(`扫描完成，发现 ${data.total_files} 个文件`, 'success')
      await buildPreview()
    } catch (e) {
      showToast('扫描失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      scanning.value = false
    }
  }

  async function doOpenListLogin() {
    olStore.loading = true
    try {
      const res = await openlistLogin({
        server_url: olForm.server_url,
        username: olForm.username,
        password: olForm.password,
      })
      olStore.setConnection(true, res.data)
      showToast('连接成功', 'success')
    } catch (e) {
      showToast('连接失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      olStore.loading = false
    }
  }

  async function doOpenListLogout() {
    await apiLogout()
    olStore.disconnect()
    showToast('已断开', 'info')
  }

  async function doOpenListScan() {
    if (!path.value || path.value === olStore.selectedMount) {
      showToast('请浏览选择具体的子目录后再扫描', 'warning')
      openOpenListBrowseDialog()
      return
    }
    scanning.value = true
    try {
      const res = await scanDirectory({
        source: 'openlist',
        path: path.value,
        recursive: recursive.value,
        include_subtitles: includeSubs.value,
      })
      const data = res.data
      filesStore.source = 'openlist'
      filesStore.setFiles(data.files || [])
      filesStore.scanResult = data
      scannedInfo.value = data
      showToast(`扫描完成，发现 ${data.total_files} 个文件`, 'success')
      await buildPreview()
    } catch (e) {
      showToast('扫描失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      scanning.value = false
    }
  }

  function onMountChange() {
    path.value = ''
  }

  function openOpenListBrowseDialog() {
    const mount = olStore.selectedMount || ''
    browse.source = 'openlist'
    browse.initialPath = mount
    browse.rootPath = mount
    browse.disallowRoot = true
    browse.open = true
  }

  function openLocalBrowseDialog() {
    browse.source = 'local'
    browse.initialPath = path.value || ''
    browse.rootPath = ''
    browse.disallowRoot = false
    browse.open = true
  }

  function browseConfirm(pick) {
    if (!pick) return
    if (browse.source === 'openlist') {
      if (pick.path === olStore.selectedMount) {
        showToast('不能选择云盘根目录，请进入子文件夹后再选择', 'warning')
        return
      }
      path.value = pick.path
    } else {
      path.value = pick.path
    }
    browse.open = false
  }

  function onPresetChange(value) {
    const preset = tplStore.presets.find(p => p.id === value)
    if (preset) tplStore.setPreset(preset)
    buildPreview()
  }

  function onTemplateEdit(value) {
    tplStore.setTemplate(value)
    buildPreview()
  }

  async function buildPreview() {
    if (!filesStore.files.length) {
      previewRows.value = []
      return
    }
    try {
      const ids = filesStore.files.map(f => f.id)
      const res = await previewRename({
        file_ids: ids,
        source: filesStore.source,
        path: filesStore.files[0].path.replace(filesStore.files[0].filename, ''),
        template: tplStore.currentTemplate,
        folder_template: tplStore.folderTemplate,
        create_season_folder: tplStore.createSeasonFolder,
      })
      const previews = res.data.results || []
      previewRows.value = filesStore.files.map(f => {
        const pv = previews.find(p => p.original_path === f.path) || {}
        return {
          ...f,
          selected: true,
          show_name: pv.show_name || '',
          season: pv.season,
          episode: pv.episode,
          new_filename: pv.new_filename || '',
          needs_review: pv.needs_review || false,
          confidence: pv.confidence || 0,
          override: {},
        }
      })
    } catch (e) {
      console.error(e)
    }
  }

  function updatePreview(row) {
    row.override = {
      show_name: row.show_name,
      season: row.season,
      episode: row.episode,
    }
  }

  function toggleAll(val) {
    previewRows.value.forEach(r => { r.selected = val })
  }

  async function previewAll() {
    await buildPreview()
    showToast('预览已刷新', 'success')
  }

  function clearAll() {
    askConfirm('确定清空文件列表？这将移除当前扫描到的所有文件。').then(ok => {
      if (!ok) return
      filesStore.clear()
      previewRows.value = []
      scannedInfo.value = null
      sourceStates[activeSource.value].files = []
      sourceStates[activeSource.value].scanResult = null
    })
  }

  function askConfirm(message) {
    confirm.message = message
    confirm.open = true
    return new Promise(resolve => { confirmResolver = resolve })
  }

  function resolveConfirm(ok) {
    confirm.open = false
    if (confirmResolver) {
      confirmResolver(ok)
      confirmResolver = null
    }
  }

  async function doDryRun() {
    await executeAction(true)
  }

  async function doExecute() {
    const ok = await askConfirm(`将对 ${selectedCount.value} 个文件执行重命名操作，确认继续？`)
    if (!ok) return
    await executeAction(false)
  }

  async function executeAction(dryRun = false) {
    const selected = previewRows.value.filter(r => r.selected)
    if (!selected.length) {
      showToast('请先选择文件', 'warning')
      return
    }

    executing.value = !dryRun
    executeDryRun.value = dryRun
    try {
      const overrides = {}
      selected.forEach(r => {
        if (r.override) overrides[r.id] = r.override
      })
      const ids = selected.map(r => r.id)
      const fn = dryRun ? dryRunRename : executeRename
      const res = await fn({
        file_ids: ids,
        source: filesStore.source,
        path: selected[0].path.replace(selected[0].filename, ''),
        template: tplStore.currentTemplate,
        folder_template: tplStore.folderTemplate,
        create_season_folder: tplStore.createSeasonFolder,
        conflict_strategy: conflictStrategy.value,
        overrides,
      })
      lastResult.value = res.data
      resultDialog.value = true
      if (!dryRun) {
        await buildPreview()
      }
    } catch (e) {
      showToast('操作失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      executing.value = false
    }
  }

  // 模板变更后立即重建预览。原来这个 watch 在 HomeView 的 setup 里，
  // 状态搬进 store 后它必须一起搬，否则改模板不再刷新「新文件名」列。
  watch(
    () => [tplStore.currentTemplate, tplStore.folderTemplate, tplStore.createSeasonFolder],
    () => { if (filesStore.files.length) buildPreview() },
    { deep: true },
  )

  return {
    activeSource, sourceStates,
    recursive, includeSubs, scanning, executing, executeDryRun,
    conflictStrategy, resultDialog, lastResult, olForm,
    browse, confirm, toast,
    path, previewRows, scannedInfo, allSelected, selectedCount, totalCount,
    initialize, switchSource,
    doScan, doOpenListScan, doOpenListLogin, doOpenListLogout, onMountChange,
    openOpenListBrowseDialog, openLocalBrowseDialog, browseConfirm,
    onPresetChange, onTemplateEdit,
    buildPreview, previewAll, updatePreview, toggleAll, clearAll,
    askConfirm, resolveConfirm, showToast,
    doDryRun, doExecute, executeAction,
  }
})
```

注意两处与原文的**有意差异**，都是消除原有 bug：

- **原来 `HomeView` 用两个独立的 `computed`（`localPath` / `openlistBrowsePath`）分别指向两个源的路径**，`switchSource()` 里则直接改 `activeSource`，路径的读写靠 `sourceStates[x].path` 各自成立。现在统一成单个可写的 `path` computed，语义相同但少一个中途会失同步的 `filesStore.clear()`（原 `switchSource` 会清空 `filesStore`，紧接着 `watch(activeSource)` 又把它填回去，是冗余的往返）。
- 原 `switchSource()` 里那句 `previewRows.value = []` / `scannedInfo.value = null` 在切源时**丢弃了目标源已缓存的预览行**，而 `watch(activeSource)` 又立刻从 `sourceStates[name]` 恢复。两条路径互相打架。新实现只保留恢复，不保留清空 —— 这直接决定了 Review Focus 第 3 条能否通过。

- [ ] **Step 2: 把 `HomeView.vue` 改为消费 store**

`frontend/src/views/HomeView.vue` 的 `<script setup>` 替换为：

```js
import { onMounted } from 'vue'

import { useFilesStore } from '../stores/files'
import { useTemplateStore } from '../stores/template'
import { useOpenListStore } from '../stores/openlist'
import { useWorkspaceStore } from '../stores/workspace'

import SourceTabs from '../components/SourceTabs.vue'
import ScanPanel from '../components/ScanPanel.vue'
import TemplateConfig from '../components/TemplateConfig.vue'
import FileTable from '../components/FileTable.vue'
import ActionBar from '../components/ActionBar.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ExecutingOverlay from '../components/ExecutingOverlay.vue'
import ResultDialog from '../components/ResultDialog.vue'
import BrowseDialog from '../components/BrowseDialog.vue'
import Toast from '../components/Toast.vue'

const ws = useWorkspaceStore()

// 这三个 store 实例**必须保留**：模板里仍要把它们当 prop 传给本期尚未改造
// 的子组件（FileTable 的 :files-store、TemplateConfig 的 :tpl-store、
// ScanPanel 的 :ol-store）。漏掉任何一个，对应的 prop 会收到 undefined。
// filesStore 会一直留到第四期 FileTable 彻底改用 workspace store 之后。
const filesStore = useFilesStore()
const tplStore = useTemplateStore()
const olStore = useOpenListStore()

// 旧 SourceTabs 的数据源列表（含 emoji）。Task 2 会用顶栏的 segmented
// control 取代 SourceTabs 并删掉这个数组；本任务先原样保留，否则中间态里
// SourceTabs 收不到 sources，会渲染成一个空的 tab bar 而报不出错。
const sources = [
  { name: 'local', label: '本地磁盘', icon: '📁' },
  { name: 'openlist', label: 'OpenList 云盘', icon: '☁️' },
]

onMounted(() => { ws.initialize() })
```

`<template>` 里所有原来的 `localPath` / `previewRows` / `scannedInfo` / `allSelected` / `activeSource` / `conflictStrategy` / `selectedCount` / `executing` / 各 `@event` 处理器，统一改成 `ws.` 前缀。具体替换对照：

| 原写法 | 新写法 |
|---|---|
| `v-model="activeSource"`（在 `<SourceTabs>` 上） | `:model-value="ws.activeSource"` + `@update:model-value="ws.switchSource($event)"`（**不能用 `v-model`**，见下） |
| `:local-path="localPath"` | `:local-path="ws.path"` |
| `:recursive="recursive"` | `:recursive="ws.recursive"` |
| `:include-subs="includeSubs"` | `:include-subs="ws.includeSubs"` |
| `:scanning="scanning"` | `:scanning="ws.scanning"` |
| `:openlist-browse-path="openlistBrowsePath"` | `:openlist-browse-path="ws.path"` |
| `@update:local-path="localPath = $event"` | `@update:local-path="ws.path = $event"` |
| `@update:recursive="recursive = $event"` | `@update:recursive="ws.recursive = $event"` |
| `@update:include-subs="includeSubs = $event"` | `@update:include-subs="ws.includeSubs = $event"` |
| `@scan="activeSource === 'local' ? doScan() : doOpenListScan()"` | `@scan="ws.activeSource === 'local' ? ws.doScan() : ws.doOpenListScan()"` |
| `@login="doOpenListLogin"` | `@login="ws.doOpenListLogin"` |
| `@logout="doOpenListLogout"` | `@logout="ws.doOpenListLogout"` |
| `@browse="openOpenListBrowseDialog"` | `@browse="ws.openOpenListBrowseDialog"` |
| `@browse-local="openLocalBrowseDialog"` | `@browse-local="ws.openLocalBrowseDialog"` |
| `@mount-change="onMountChange"` | `@mount-change="ws.onMountChange"` |
| `@preset-change="onPresetChange"` | `@preset-change="ws.onPresetChange"` |
| `@template-edit="onTemplateEdit"` | `@template-edit="ws.onTemplateEdit"` |
| `@preview-all="previewAll"` | `@preview-all="ws.previewAll"` |
| `@clear-all="clearAll"` | `@clear-all="ws.clearAll"` |
| `@toggle-all="toggleAll"` | `@toggle-all="ws.toggleAll"` |
| `@select-row="({ row, val }) => row.selected = val"` | 不变 |
| `@update-row="updatePreview"` | `@update-row="ws.updatePreview"` |
| `@quick-scan="doScan"` | `@quick-scan="ws.doScan"` |
| `:preview-rows="previewRows"` | `:preview-rows="ws.previewRows"` |
| `:scanned-info="scannedInfo"` | `:scanned-info="ws.scannedInfo"` |
| `:all-selected="allSelected"` | `:all-selected="ws.allSelected"` |
| `:active-source="activeSource"` | `:active-source="ws.activeSource"` |
| `:conflict-strategy="conflictStrategy"` | `:conflict-strategy="ws.conflictStrategy"` |
| `:selected-count="selectedCount"` | `:selected-count="ws.selectedCount"` |
| `:executing="executing"` | `:executing="ws.executing"` |
| `@update:conflict-strategy="conflictStrategy = $event"` | `@update:conflict-strategy="ws.conflictStrategy = $event"` |
| `@dry-run="doDryRun"` | `@dry-run="ws.doDryRun"` |
| `@execute="doExecute"` | `@execute="ws.doExecute"` |
| `v-model="confirmDialog"` + `:message="confirmMessage"` | `v-model="ws.confirm.open"` + `:message="ws.confirm.message"` |
| `@ok="onConfirmOk"` / `@cancel="onConfirmCancel"` | `@ok="ws.resolveConfirm(true)"` / `@cancel="ws.resolveConfirm(false)"` |
| `v-model="executing"` + `:dry-run="executeDryRun"` | `v-model="ws.executing"` + `:dry-run="ws.executeDryRun"` |
| `v-if="!executeDryRun"` | `v-if="!ws.executeDryRun"` |
| `v-model="resultDialog"` + `:result="lastResult"` | `v-model="ws.resultDialog"` + `:result="ws.lastResult"` |
| `v-model="browseDialog"` + `:source="browseSource"` + `:initial-path="browseInitialPath"` + `:root-path="browseRootPath"` + `:disallow-root="browseDisallowRoot"` | `v-model="ws.browse.open"` + `:source="ws.browse.source"` + `:initial-path="ws.browse.initialPath"` + `:root-path="ws.browse.rootPath"` + `:disallow-root="ws.browse.disallowRoot"` |
| `@confirm="browseConfirm"` | `@confirm="ws.browseConfirm"` |
| `@error="(m) => showToast(m, 'error')"` | `@error="(m) => ws.showToast(m, 'error')"` |
| `:show="toast.show" :type="toast.type" :msg="toast.msg"` | `:show="ws.toast.show" :type="ws.toast.type" :msg="ws.toast.msg"` |
| `:files-store="filesStore"`（FileTable） | **不变** —— `filesStore` 保留在 HomeView |
| `:tpl-store="tplStore"`（TemplateConfig） | **不变** —— `tplStore` 保留 |
| `@update:createSeasonFolder="v => tplStore.createSeasonFolder = v"` | **不变**（引用的 `tplStore` 仍在） |
| `@update:folderTemplate="v => tplStore.folderTemplate = v"` | **不变** |
| `:ol-store="olStore"` / `:ol-form="olForm"`（ScanPanel） | `:ol-store="olStore"` **不变**；`:ol-form="ws.olForm"` |
| `:sources="sources"`（SourceTabs） | **不变** —— `sources` 数组保留到 Task 2 |

**为什么 `SourceTabs` 上不能用 `v-model="ws.activeSource"`：** `v-model` 只是给 `ws.activeSource` 直接赋值，会**绕过 `switchSource()`** —— 而「存下旧源的文件列表、载入新源的文件列表」正是 `switchSource()` 在做的事。绕过它的话，切源后 `activeSource` 变了、`path`/`previewRows` 也跟着变（它们是按 `activeSource` 取值的 computed），但 `filesStore.files` 仍停留在旧源，表格会显示错的文件。Task 2 把源切换搬进顶栏后同样用 `ws.switchSource($event)`，不要图省事改成 `v-model`。

`<style scoped>` 块暂时**保留不动**（`source-fade` 过渡到 Task 3 再删）。

- [ ] **Step 3: 构建**

```bash
cd frontend && npm run build
```

预期：通过，无错误。

- [ ] **Step 4: 确认行为与搬家前逐项一致**

```bash
cd frontend && npm run dev
```

后端也要起来（`cd backend && python run.py`），否则扫描会失败。逐项走查：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 打开首页，看「重命名模板」预设下拉 | 已选中「Emby 标准」（或后端返回的默认预设），模板输入框有值 |
| 2 | 选一个含视频的本地目录 → 扫描 | toast「扫描完成，发现 N 个文件」；表格出现 N 行；「新文件名」列有值 |
| 3 | 改模板输入框任意一个字符 | 表格「新文件名」列**立即**变化（Review Focus 第 5 条） |
| 4 | 取消勾选几行 → 看底栏 | 「已选 X / N」随勾选变化 |
| 5 | 全部取消勾选 → 看 ActionBar | 「试运行」「执行重命名」两个按钮都**置灰** |
| 6 | 点「试运行」 | 弹出结果对话框，标题「重命名结果」 |
| 7 | 点表格「清空」 | 弹确认框 → 确定 → 表格回到空态，底栏计数归零 |
| 8 | 切到「OpenList 云盘」再切回「本地磁盘」 | **文件列表与预览行原样还在**（Review Focus 第 3 条） |
| 9 | 修改某行的「季」输入框 → 点「试运行」 | 结果里的新文件名按修改后的季号生成 |

任何一项不符，说明搬迁过程中改了逻辑 —— 回 `stores/workspace.js` 与 `HomeView.vue:88-505` 逐行对照。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/stores/workspace.js frontend/src/views/HomeView.vue
git commit -m "refactor(frontend): 工作区状态与流程抽入 workspace store"
```

---

### Task 2: AppTopBar + App Shell 骨架

`App.vue` 从「左侧 240px 侧栏 + 右侧路由内容」变成真正的 App Shell：「顶栏 56px + 路由出口」。源切换从 `SourceTabs` 卡片移进顶栏成为 segmented control（spec §7.4），`SourceTabs.vue` 删除。

**Files:**
- Create: `frontend/src/components/layout/AppTopBar.vue`
- Modify: `frontend/src/App.vue`（整文件重写）
- Modify: `frontend/src/views/HomeView.vue`（移除 `<SourceTabs>` 用法与 import）
- Modify: `frontend/src/views/SettingsView.vue`（加外层滚动容器）
- Delete: `frontend/src/components/SourceTabs.vue`

**Interfaces:**
- Consumes: `useWorkspaceStore()` 的 `activeSource` / `switchSource`（Task 1）；`BrandMark`（第一期 Task 3）；新 token `surface` `sunken` `accent` `accent-soft` `line` `ink` `ink-2`
- Produces:
  ```js
  // AppTopBar
  props: { source: String, showSourceSwitch: Boolean }   // default false
  emits: ['update:source']
  ```
- 注意 `switchSource` 不是简单赋值（它要存旧源、载新源），所以 `App.vue` 里**不能**写 `v-model:source="ws.activeSource"`，必须显式绑 `@update:source="ws.switchSource($event)"`

- [ ] **Step 1: 创建 `frontend/src/components/layout/AppTopBar.vue`**

```vue
<template>
  <header
    class="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-surface px-4"
  >
    <div class="flex min-w-0 items-center gap-2.5">
      <BrandMark :size="28" class="text-accent" />
      <span class="truncate text-[14px] font-semibold text-ink">Episode Renamer</span>
    </div>

    <div
      v-if="showSourceSwitch"
      role="group"
      aria-label="文件来源"
      class="flex shrink-0 items-center gap-0.5 rounded-[8px] bg-sunken p-0.5"
    >
      <button
        v-for="src in SOURCES"
        :key="src.name"
        type="button"
        :aria-pressed="source === src.name"
        class="h-7 rounded-[6px] px-3 text-[12px] font-medium transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
        :class="source === src.name ? 'bg-accent-soft text-accent' : 'text-ink-2 hover:text-ink'"
        @click="$emit('update:source', src.name)"
      >
        {{ src.label }}
      </button>
    </div>

    <RouterLink
      :to="onSettings ? '/' : '/settings'"
      :aria-label="onSettings ? '返回工作区' : '设置'"
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
    >
      <ArrowLeft v-if="onSettings" class="h-4 w-4" />
      <SettingsIcon v-else class="h-4 w-4" />
    </RouterLink>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Settings as SettingsIcon } from 'lucide-vue-next'

import BrandMark from '../BrandMark.vue'

// 本地磁盘 / OpenList 两段。这里不再有表示数据源的图标符号 —— 被取代的那个
// 页签组件用的是文件夹与云朵 emoji，随它一起清掉
// （spec §3.5 第 12 条）。
const SOURCES = [
  { name: 'local', label: '本地磁盘' },
  { name: 'openlist', label: 'OpenList' },
]

defineProps({
  source: { type: String, default: 'local' },
  showSourceSwitch: { type: Boolean, default: false },
})
defineEmits(['update:source'])

const route = useRoute()
const onSettings = computed(() => route.name === 'Settings')
</script>
```

**一处 spec 未画出的补充，需要评审时知情：** spec §7.1 的示意图只画了工作区态的顶栏（`BrandMark · [本地磁盘|OpenList] · ⚙`）。设置页没有自己的出口 —— 旧的左侧栏导航被本次重构整体取消，所以这里的 ⚙ 在设置页会变成返回箭头。spec §2 明确「路由结构、URL 不变」，因此 `/settings` 仍然可直达。

`h-14` 是 56px。spec §7.4 要求顶栏**所有内容单行**：品牌名用 `truncate` + `min-w-0` 兜住窄屏，其余元素 `shrink-0`。

- [ ] **Step 2: 重写 `frontend/src/App.vue`**

```vue
<template>
  <div class="grid h-dvh grid-rows-[56px_1fr] overflow-hidden bg-canvas">
    <AppTopBar
      :source="ws.activeSource"
      :show-source-switch="route.name === 'Home'"
      @update:source="ws.switchSource($event)"
    />

    <!-- min-h-0 是整条链的第一环。少了它的症状**不是**「整页滚动」——
         外壳是 h-dvh + overflow-hidden，根本没有页面滚动条；真正的症状是
         路由内容把第二行（1fr）撑破，其底部被裁掉且**无从滚动到**，等于静默丢失。
         这比能滚更糟：能滚至少内容还在。 -->
    <div class="min-h-0 overflow-hidden">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'

import AppTopBar from './components/layout/AppTopBar.vue'
import { useWorkspaceStore } from './stores/workspace'

const route = useRoute()
const ws = useWorkspaceStore()
</script>
```

原来的 `page-fade` 路由过渡与整个 `<style>` 块**删除**：spec §11 的动效表只保留「色彩过渡 / `:active` 微压 / 模态进出 / Toast 进出 / 行 hover」五条，路由淡入淡出不在其中。

- [ ] **Step 3: 从 `HomeView` 摘掉 `SourceTabs`**

编辑 `frontend/src/views/HomeView.vue`：

1. 删除 `<template>` 里整个 `<SourceTabs ... />` 元素（Task 1 之后它长这样：`:model-value="ws.activeSource"` + `@update:model-value="ws.switchSource($event)"` + `:sources="sources"`）
2. 删除 `<script setup>` 里 `import SourceTabs from '../components/SourceTabs.vue'` 那一行
3. 删除 `<script setup>` 里的 `sources` 数组（Task 1 保留了它，现在它唯一的消费者 SourceTabs 没了，留着就是死代码）
4. 下面这个 `<Transition name="source-fade" mode="out-in"><div :key="ws.activeSource" ...>` 包裹层**先保留不动**（Task 3 统一处理）

- [ ] **Step 4: 给 `SettingsView` 加外层滚动容器**

`App.vue` 的路由出口是 `overflow-hidden`，所以每个路由必须自己管滚动。把 `frontend/src/views/SettingsView.vue` 的 `<template>` 最外层改成：

```vue
<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto flex max-w-[680px] flex-col gap-4 p-6">
      <!-- 以下内容原样不动，只把缩进多一级 -->
    </div>
  </div>
</template>
```

即：在原有的 `<div class="flex flex-col gap-4 max-w-[680px]">` 外面再套一层 `h-full overflow-y-auto`，并给内层加 `mx-auto` 与 `p-6`（原来这份 padding 由 `App.vue` 的 `p-8` 提供，现在没有了）。

`SettingsView` 的其余部分（表单、按钮、保存逻辑）本期不动，第三期整体改用原语。

**注意上文代码块里的注释措辞**：它刻意**不写** `SourceTabs` 这个标识符、也不写那两个 emoji 字形本身。因为本步的校验是 `grep -rn "SourceTabs" src/` 要**无输出**，而第三期还有一道 `grep -rn "🎬\|📁\|☁️\|⚠️\|✅" src/ | wc -l` 要**为 0** —— 源码注释里只要出现这两个字面量，两道检查都会假失败，而它们检查的是「代码里还有没有引用」，不是「注释里有没有提过」。要提就描述它，不要写字面量。

- [ ] **Step 5: 删除 `SourceTabs.vue`**

```bash
cd frontend && rm src/components/SourceTabs.vue && grep -rn "SourceTabs" src/
```

预期：`grep` **无输出**（退出码 1）。

- [ ] **Step 6: 构建并确认 min-h-0 链的第一环生效**

```bash
cd frontend && npm run build
```

预期：通过。

```bash
cd frontend && npm run dev
```

走查：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 打开 `http://localhost:5173/` | 顶部有一条 56px 白色顶栏：左侧青绿标记 + 「Episode Renamer」，中间是「本地磁盘 / OpenList」两段，右侧 ⚙ |
| 2 | 看「本地磁盘」段 | 底色 `#E6F4F2`（浅青绿）、文字 `#0F766E`；「OpenList」段是普通灰字 |
| 3 | 点「OpenList」 | 选中态切过去；页面主体仍在（旧卡片栈），底部的扫描源面板变成 OpenList 的登录表单 |
| 4 | 点右上角 ⚙ | 跳到 `/#/settings`，顶栏的源切换**消失**，⚙ 变成 ← |
| 5 | 设置页上下滚动 | 内容可滚动，顶栏**不动**（顶栏在 shell 里，不在滚动区） |
| 6 | 点 ← | 回到 `/#/`，源切换重新出现 |
| 7 | 在设置页看整页 | **没有**「执行重命名」「试运行」按钮（Review Focus 第 2 条的早期检查） |
| 8 | 缩放窗口到很窄 | 顶栏内容**不换行**、不溢出；品牌名被截断省略 |

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/layout/AppTopBar.vue frontend/src/App.vue frontend/src/views/HomeView.vue frontend/src/views/SettingsView.vue
git rm frontend/src/components/SourceTabs.vue
git commit -m "feat(frontend): App Shell 顶栏 + 源切换改为 segmented, 删除 SourceTabs"
```

---

### Task 3: AppBottomBar + HomeView 两行骨架

把主操作从文档流底部移到**常驻底栏**（spec §7.2 —— 这是本次重构最大的可用性收益），`ActionBar.vue` 删除。同时删掉不在 spec §11 动效表里的 `source-fade` 过渡。

**Files:**
- Create: `frontend/src/components/layout/AppBottomBar.vue`
- Modify: `frontend/src/views/HomeView.vue`（根容器改成 `grid grid-rows-[1fr_56px]`）
- Delete: `frontend/src/components/ActionBar.vue`

**Interfaces:**
- Consumes: `AppButton` / `AppSelect`（第一期）；`useWorkspaceStore()` 的 `conflictStrategy` / `selectedCount` / `totalCount` / `executing` / `doDryRun` / `doExecute`（Task 1）
- Produces:
  ```js
  // AppBottomBar
  props: {
    conflictStrategy: String   // default 'skip'
    selectedCount: Number      // default 0
    totalCount: Number         // default 0
    executing: Boolean         // default false
  }
  emits: ['update:conflictStrategy', 'dry-run', 'execute']
  ```

- [ ] **Step 1: 创建 `frontend/src/components/layout/AppBottomBar.vue`**

```vue
<template>
  <footer
    class="flex h-14 shrink-0 items-center justify-between gap-3 border-t border-line bg-surface px-4"
  >
    <div class="flex min-w-0 items-center gap-3">
      <AppSelect
        :model-value="conflictStrategy"
        aria-label="冲突策略"
        class="w-[132px]"
        @update:model-value="$emit('update:conflictStrategy', $event)"
      >
        <option label="跳过" value="skip" />
        <option label="中止" value="abort" />
        <option label="覆盖" value="overwrite" />
        <option label="自动编号" value="rename_dup" />
      </AppSelect>

      <span class="truncate text-[13px] text-ink-2">
        已选 <span class="tabular-nums text-ink">{{ selectedCount }}</span>
        / <span class="tabular-nums">{{ totalCount }}</span>
      </span>
    </div>

    <div class="flex shrink-0 items-center gap-2">
      <AppButton variant="secondary" :disabled="!selectedCount" @click="$emit('dry-run')">
        试运行
      </AppButton>
      <AppButton
        variant="primary"
        :loading="executing"
        :disabled="!selectedCount"
        @click="$emit('execute')"
      >
        {{ executing ? '执行中…' : '执行重命名' }}
      </AppButton>
    </div>
  </footer>
</template>

<script setup>
import AppButton from '../ui/AppButton.vue'
import AppSelect from '../ui/AppSelect.vue'

defineProps({
  conflictStrategy: { type: String, default: 'skip' },
  selectedCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
  executing: { type: Boolean, default: false },
})
defineEmits(['update:conflictStrategy', 'dry-run', 'execute'])
</script>
```

几处不是随手写的：

- **计数用 `tabular-nums` 而不是 `font-mono`**：spec §6.4 明确要求「表格内所有数字列加 `tabular-nums`」，而 §6.2 的等宽白名单（季数、集数、模板变量名、并发数、补零位数）指的是**用户输入或作为标识读取的技术值**，不是派生计数器。`tabular-nums` 已经能消掉 `1` 与 `8` 的宽度差，就不必再切字体。若评审认为计数也该走等宽，改一个 class 即可。
- **「试运行」不带 `loading`**：`executing` 只在真正执行时置位（`executeAction` 里 `executing.value = !dryRun`），试运行不阻塞界面，按钮保持可点是对的。
- **`AppSelect` 只传 `aria-label` 不传 `label`**：底栏里没有空间放可见 label，但无障碍名不能省。`aria-label` 会透传到根元素（`AppSelect` 用 `defineProps` 而非 `inheritAttrs: false`，未声明的attrs 落到根 `div` 上，屏幕阅读器仍能从 select 自身读到吗 —— **不会**）。因此这里**必须**改为在 `AppSelect` 上支持无障碍名透传：见 Step 2。

- [ ] **Step 2: 给 `AppSelect` 补无障碍名透传**

上面的 `aria-label` 会落在 `AppSelect` 根 `<div>` 上，而根 `<div>` 不是表单控件，屏幕阅读器读不到。打开 `frontend/src/components/ui/AppSelect.vue`，把 `<select>` 元素改为显式接收无障碍名：

在 `defineProps` 里加一个 `ariaLabel`（Vue 约定：模板里写 `aria-label` 会映射到 `ariaLabel` prop）：

```js
  ariaLabel: { type: String, default: '' },
```

并在 `<select>` 上补：

```html
        :aria-label="ariaLabel || undefined"
```

于是 `AppBottomBar` 里写 `aria-label="冲突策略"` 时，`AppSelect` 声明了同名 prop，就不会再落到根 div 上，而是被显式绑到 `<select>`。**这个改动必须落在 `AppSelect.vue` 上**，不是 `AppBottomBar.vue`。

- [ ] **Step 3: `HomeView` 根容器改成两行骨架**

编辑 `frontend/src/views/HomeView.vue`，把 `<template>` 的根元素与包裹层改成：

```vue
<template>
  <div class="grid h-full min-h-0 grid-rows-[1fr_56px] overflow-hidden">
    <div class="flex min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <ScanPanel
        :source="ws.activeSource"
        ...（原样，含全部 :props 与 @events）
      />

      <TemplateConfig
        ...（原样）
      />

      <FileTable
        ...（原样）
      />
    </div>

    <AppBottomBar
      :conflict-strategy="ws.conflictStrategy"
      :selected-count="ws.selectedCount"
      :total-count="ws.totalCount"
      :executing="ws.executing"
      @update:conflict-strategy="ws.conflictStrategy = $event"
      @dry-run="ws.doDryRun"
      @execute="ws.doExecute"
    />

    <ConfirmDialog ... />   <!-- 以下各对话框原样保留 -->
    <ExecutingOverlay ... />
    <ResultDialog ... />
    <BrowseDialog ... />
    <Toast ... />
  </div>
</template>
```

具体三处机械改动：

1. 根元素换成 `<div class="grid h-full min-h-0 grid-rows-[1fr_56px] overflow-hidden">`。
   **注意根当前的类不是 Task 2 之前的 `flex flex-col gap-4`** —— Task 2 的修复轮给它加了 `h-full` 与 `overflow-y-auto`（为了让被裁剪的旧卡片栈重新可达），并在上方留了注释说明这是**临时代管**。那两处 `h-full`/`overflow-y-auto` 以及那段注释随本次替换一并删除：滚动改由内层容器承担，且**新的根必须带 `min-h-0`**。
   **替换前先读一遍当前文件的根元素**，不要按记忆机械替换。
2. 原来的 `<Transition name="source-fade" mode="out-in"><div :key="ws.activeSource" class="flex flex-col gap-4">` 与其闭合标签**整段删除**，里面的三个组件提到新加的 `<div class="flex min-h-0 flex-col gap-4 overflow-y-auto p-4">` 里。理由：spec §11 的动效表里没有「切换数据源淡入淡出」这一条，而过渡包裹层在 grid 布局下会成为多余的一层容器，破坏 `min-h-0` 链
3. `<ActionBar ... />` 整块替换为 `<AppBottomBar ... />`，并把 `import ActionBar from '../components/ActionBar.vue'` 换成 `import AppBottomBar from '../components/layout/AppBottomBar.vue'`
4. 删除文件末尾整个 `<style scoped>` 块（`source-fade` 已无用）

同一个 `<div class="grid ...">` 里既有 grid 行（中段 + 底栏）又有对话框组件 —— 对话框都是 `Teleport to="body"`（第一期 Task 5）或 `fixed` 定位，会脱离 grid 流，作为额外 grid 子项会产生隐式行。**必须**给它们加 `v-if` 或确认它们渲染时不影响布局。`ConfirmDialog` / `ResultDialog` / `BrowseDialog` 的第一层是 `Teleport`（不占网格位），`ExecutingOverlay` 已经有 `v-if`，`Toast` 的第一层是 `Transition` 包裹的 `fixed` 元素。

为稳妥起见，给 `Toast` 也加上 `v-if`，并把三个对话框统一放到根 `<div>` **之外**用一个空的 `<>` 片段承载 —— 见下一步的最终模板。

- [ ] **Step 4: 确认最终模板结构**

改完后 `frontend/src/views/HomeView.vue` 的完整骨架应形如：

```vue
<template>
  <div class="grid h-full min-h-0 grid-rows-[1fr_56px] overflow-hidden">
    <div class="flex min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <ScanPanel ... />
      <TemplateConfig ... />
      <FileTable ... />
    </div>

    <AppBottomBar ... />
  </div>

  <ConfirmDialog ... />
  <ExecutingOverlay ... />
  <ResultDialog ... />
  <BrowseDialog ... />
  <Toast v-if="ws.toast.show" ... />
</template>
```

Vue 3 支持多根节点模板。把对话框全部挪到 grid 容器**外面**，grid 就只有两个子项（中段 + 底栏），不会产生隐式的空行。

- [ ] **Step 5: 删除 `ActionBar.vue`**

```bash
cd frontend && rm src/components/ActionBar.vue && grep -rn "ActionBar" src/
```

预期：除 `components/layout/AppBottomBar.vue` 自身外**无输出**。

- [ ] **Step 6: 构建并验证底栏常驻**

```bash
cd frontend && npm run build
```

预期：通过。

```bash
cd frontend && npm run dev
```

走查（**Review Focus 第 1 条的核心验收**）：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 打开首页 | 视口**最底部**有一条 56px 白底发丝线底栏：左边冲突策略下拉 + 「已选 0 / 0」，右边「试运行」「执行重命名」，两个都置灰 |
| 2 | 扫描一个文件数**很多**（≥100）的目录 | 中段内容在**自己内部滚动**；底栏**不动**，始终钉在视口底部 |
| 3 | 滚到中段最底部 | 滚到底后**没有**第二个「执行重命名」按钮（旧的 ActionBar 已删） |
| 4 | 拖动窗口高度到很矮（如 500px） | 底栏仍然可见；中段被压缩并内部滚动 |
| 5 | 勾选几行 | 「已选 X / N」实时变化；按钮解禁 |
| 6 | 切到 OpenList 段 | 底栏**仍然在**（它在 shell 里，不随源切换消失） |
| 7 | 点「试运行」/「执行重命名」 | 行为与 Task 1 验收时一致 |
| 8 | 观察切换数据源的过程 | **不再有**淡入淡出动画（`source-fade` 已删） |

第 2、4 项不通过 = `min-h-0` 链断了。逐环检查 `App.vue` 的路由出口、`HomeView` 根、中段 `<div>` 是否都带 `min-h-0`。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/layout/AppBottomBar.vue frontend/src/components/ui/AppSelect.vue frontend/src/views/HomeView.vue
git rm frontend/src/components/ActionBar.vue
git commit -m "feat(frontend): 主操作移入常驻底栏, 删除 ActionBar 与源切换过渡"
```

---

### Task 4: `ScanPanel` → `SourceConfigPanel`（垂直布局 + 原语）

`ScanPanel` 现在是**横向**一行排放（路径字段 `min-w-[280px]` + 两个复选框 + 扫描按钮），塞进 280px 左栏必然溢出。本任务把它改写成垂直的 `SourceConfigPanel`，并直接改用第一期的原语（按本期的组件改造规则）。**这一步还不搬进左栏** —— 它先在中段全宽下工作，视觉上就已经是正常的一列，不会出现「中间态坏掉」。

**Files:**
- Create: `frontend/src/components/SourceConfigPanel.vue`
- Delete: `frontend/src/components/ScanPanel.vue`
- Modify: `frontend/src/views/HomeView.vue`（换组件名与 import）

**Interfaces:**
- Consumes: `AppButton` / `AppInput` / `AppCheckbox`（第一期）；`useWorkspaceStore()` 的相关状态（Task 1）
- Produces: `SourceConfigPanel.vue`，props / emits 与旧 `ScanPanel` **完全一致**（只去掉 `openlistBrowsePath` 之外的命名差异），第二期的 Task 5 与第三期都按此契约使用：

  ```js
  props: {
    source: String          // 'local' | 'openlist'
    localPath: String
    recursive: Boolean
    includeSubs: Boolean
    scanning: Boolean
    openlistBrowsePath: String
    olStore: Object
    olForm: Object
  }
  emits: [
    'update:localPath', 'update:recursive', 'update:includeSubs',
    'scan', 'login', 'logout', 'browse', 'mount-change', 'browse-local',
  ]
  ```

- [ ] **Step 1: 创建 `frontend/src/components/SourceConfigPanel.vue`**

```vue
<template>
  <div class="flex flex-col gap-2.5">
    <template v-if="source === 'local'">
      <div class="flex items-end gap-2">
        <AppInput
          :model-value="localPath"
          label="目录路径"
          placeholder="点击右侧浏览，或直接输入"
          class="min-w-0 flex-1"
          @update:model-value="$emit('update:localPath', $event)"
        />
        <AppButton variant="secondary" @click="$emit('browse-local')">浏览</AppButton>
      </div>

      <AppCheckbox
        :model-value="recursive"
        label="递归扫描"
        @update:model-value="$emit('update:recursive', $event)"
      />
      <AppCheckbox
        :model-value="includeSubs"
        label="包含字幕"
        @update:model-value="$emit('update:includeSubs', $event)"
      />

      <AppButton
        variant="primary"
        block
        :loading="scanning"
        :disabled="!localPath"
        @click="$emit('scan')"
      >
        {{ scanning ? '扫描中…' : '扫描' }}
      </AppButton>
    </template>

    <template v-else>
      <template v-if="!olStore.connected">
        <AppInput
          v-model="olForm.server_url"
          label="服务器"
          placeholder="http://localhost:5244"
        />
        <AppInput v-model="olForm.username" label="用户名" placeholder="admin" />
        <AppInput
          v-model="olForm.password"
          label="密码"
          type="password"
          placeholder="••••••"
        />
        <AppButton
          variant="primary"
          block
          :loading="olStore.loading"
          @click="$emit('login')"
        >
          {{ olStore.loading ? '连接中…' : '连接' }}
        </AppButton>
      </template>

      <template v-else>
        <div class="flex items-center gap-1.5 text-[12px] font-medium text-ink-2">
          <CheckCircle2 class="h-3.5 w-3.5 text-accent" aria-hidden="true" />
          <span class="truncate">已连接: {{ olStore.serverUrl }}</span>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-[13px] font-medium text-ink-2" for="ol-mount">挂载点</label>
          <AppSelect
            id="ol-mount"
            :model-value="olStore.selectedMount"
            @update:model-value="$emit('mount-change', $event)"
          >
            <option v-for="m in olStore.mountPoints" :key="m" :value="m">{{ m }}</option>
          </AppSelect>
        </div>

        <div class="flex items-end gap-2">
          <AppInput
            :model-value="openlistBrowsePath"
            label="目录路径"
            placeholder="点击右侧浏览选择"
            class="min-w-0 flex-1"
            @update:model-value="$emit('update:localPath', $event)"
          />
          <AppButton variant="secondary" @click="$emit('browse')">浏览</AppButton>
        </div>

        <AppButton
          variant="primary"
          block
          :loading="scanning"
          :disabled="!openlistBrowsePath"
          @click="$emit('scan')"
        >
          {{ scanning ? '扫描中…' : '扫描' }}
        </AppButton>
        <AppButton variant="ghost" block @click="$emit('logout')">断开连接</AppButton>
      </template>
    </template>
  </div>
</template>

<script setup>
import { CheckCircle2 } from 'lucide-vue-next'

import AppButton from './ui/AppButton.vue'
import AppSelect from './ui/AppSelect.vue'
import AppInput from './ui/AppInput.vue'
import AppCheckbox from './ui/AppCheckbox.vue'

defineProps({
  source: { type: String, required: true },
  localPath: { type: String, default: '' },
  recursive: { type: Boolean, default: true },
  includeSubs: { type: Boolean, default: true },
  scanning: { type: Boolean, default: false },
  openlistBrowsePath: { type: String, default: '' },
  olStore: { type: Object, required: true },
  olForm: { type: Object, required: true },
})
defineEmits([
  'update:localPath', 'update:recursive', 'update:includeSubs',
  'scan', 'login', 'logout', 'browse', 'mount-change', 'browse-local',
])
</script>
```

几处不是随手写的：

- **OpenList 的路径字段复用 `update:localPath` 事件** —— store 里的 `path` 是所有源共用的单个可写 computed（Task 1），本地与云盘共用一条通路。旧 `ScanPanel` 用 `openlistBrowsePath` 只做显示，写入走 `browseConfirm`；现在允许用户直接在字段里键入或粘贴路径。
- **`AppInput` 的 label 让控件高度变成 58px**，所以「浏览」按钮的容器用 `items-end` 对齐到输入框底边，而不是 `items-center`（后者会让按钮浮在半空）。
- **`class="min-w-0 flex-1"` 必须同时给**：`min-w-0` 允许输入框在窄容器里收缩（Flex 子项默认 `min-width: auto` 会被 input 的固有宽度撑破），`flex-1` 吃掉剩余宽度。
- **删掉了旧代码里那个无效的 `show-password` 属性**（`ScanPanel.vue:64`）——它不是浏览器认识的属性，密码框一直是明文 toggle 缺失的状态。现在统一 `type="password"`。
- **扫描按钮用 `block` + `loading`** —— spec §10 要求「扫描中按钮进入 loading 态（禁用 + 文字变「扫描中…」）」，`AppButton` 的 `loading` 会在文字前加 spinner 并自动禁用。

- [ ] **Step 2: `HomeView` 换用新组件**

编辑 `frontend/src/views/HomeView.vue`：

1. `import ScanPanel from '../components/ScanPanel.vue'` → `import SourceConfigPanel from '../components/SourceConfigPanel.vue'`
2. 模板里的 `<ScanPanel` 与 `</ScanPanel>` → `<SourceConfigPanel` / `</SourceConfigPanel>`
3. `:openlist-browse-path="ws.path"` 保持不变（契约同名）

- [ ] **Step 3: 删除 `ScanPanel.vue`**

```bash
cd frontend && rm src/components/ScanPanel.vue && grep -rn "ScanPanel" src/
```

预期：`grep` **无输出**。

- [ ] **Step 4: 构建并统计手写输入框样式的清偿进度**

```bash
cd frontend && npm run build && \
  echo "--- 剩余手写输入框样式处数（应为 10）---" && \
  grep -rn "focus:border-primary focus:ring-2 focus:ring-primary/20" src/ | wc -l && \
  grep -rln "focus:border-primary focus:ring-2 focus:ring-primary/20" src/
```

预期：数字为 **10**，文件列表只剩 `views/SettingsView.vue`（7）与 `components/FileTable.vue`（3）。若数字大于 10，说明还有本期该清掉的没清。

- [ ] **Step 5: 视觉与功能走查**

```bash
cd frontend && npm run dev
```

| # | 操作 | 预期 |
|---|---|---|
| 1 | 打开首页（本地磁盘） | 「扫描源」变成一列竖排：`目录路径` label + 输入框 + 「浏览」按钮 → 两个复选框（垂直堆叠）→ 一个**通栏**「扫描」按钮 |
| 2 | 点「浏览」 | 弹出目录选择对话框（`BrowseDialog` 行为不变） |
| 3 | 选目录 → 点「扫描」 | 按钮变成「扫描中…」+ 前置 spinner 且**置灰**；扫完恢复 |
| 4 | 清空路径输入框 | 「扫描」按钮置灰 |
| 5 | 切到 OpenList（未连接） | 竖排三个字段：服务器 / 用户名 / 密码（密码框**打码显示**）+ 通栏「连接」按钮 |
| 6 | 缩放窗口到 400px 宽 | 输入框跟着变窄，**不横向溢出**，label 与输入框不错位 |
| 7 | 聚焦任意输入框，按 `Tab` | 能看见**清晰的聚焦环**（这是全项目第一次有 `focus-visible`，spec §3.4） |

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/SourceConfigPanel.vue frontend/src/views/HomeView.vue
git rm frontend/src/components/ScanPanel.vue
git commit -m "refactor(frontend): ScanPanel 改写为垂直的 SourceConfigPanel, 改用 UI 原语"
```

---

### Task 5: AppLeftRail + TemplateConfig 移入左栏 —— 三栏成型

本期的结构核心。左栏 280px 常驻，`SourceConfigPanel` 与 `TemplateConfig` 各占一个可折叠分组，`TemplateConfig` 去掉卡片外壳、改成垂直布局并改用原语。

**Files:**
- Create: `frontend/src/components/layout/AppLeftRail.vue`
- Modify: `frontend/src/components/TemplateConfig.vue`（去卡片壳、垂直化、改用原语）
- Modify: `frontend/src/views/HomeView.vue`（中段改成 `lg:grid lg:grid-cols-[280px_1fr]`）

**Interfaces:**
- Consumes: `SourceConfigPanel`（Task 4）；`AppSelect` / `AppInput` / `AppCheckbox`（第一期）；新 token `canvas` `line` `ink` `ink-2` `ink-3` `accent` `accent-soft` `sunken`
- Produces:
  ```js
  // AppLeftRail —— 两个具名插槽，无 props、无 emits
  //   #source   → 扫描源分组内容
  //   #template → 重命名模板分组内容
  ```
  `TemplateConfig` 的 props / emits **保持不变**（`tplStore` / `source` / `preset-change` / `template-edit` / `update:createSeasonFolder` / `update:folderTemplate`），只是内部视觉重写

- [ ] **Step 1: 创建 `frontend/src/components/layout/AppLeftRail.vue`**

```vue
<template>
  <aside
    class="flex max-h-[45dvh] min-h-0 shrink-0 flex-col overflow-y-auto border-b border-line bg-canvas lg:h-full lg:max-h-none lg:w-[280px] lg:shrink-0 lg:border-b-0 lg:border-r"
  >
    <!-- 窄屏（<1024px）整体折叠头：spec §7.3 要求此档默认收起。
         大屏下 lg:hidden 隐藏它，内容由下面的 lg:block 强制展开。 -->
    <button
      type="button"
      class="flex shrink-0 items-center justify-between gap-2 px-4 py-3 text-[13px] font-medium text-ink-2 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none lg:hidden"
      :aria-expanded="railOpen"
      @click="railOpen = !railOpen"
    >
      扫描源与模板
      <ChevronDown
        class="h-4 w-4 shrink-0 transition-transform duration-150"
        :class="railOpen ? 'rotate-180' : ''"
        aria-hidden="true"
      />
    </button>

    <div :class="railOpen ? 'block' : 'hidden'" class="lg:block">
      <section class="border-b border-line">
        <button
          type="button"
          class="flex w-full items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold text-ink-2 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
          :aria-expanded="groups.source"
          @click="groups.source = !groups.source"
        >
          <ChevronRight
            class="h-3.5 w-3.5 shrink-0 transition-transform duration-150"
            :class="groups.source ? 'rotate-90' : ''"
            aria-hidden="true"
          />
          扫描源
        </button>
        <div v-show="groups.source" class="px-4 pb-4">
          <slot name="source" />
        </div>
      </section>

      <section>
        <button
          type="button"
          class="flex w-full items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold text-ink-2 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
          :aria-expanded="groups.template"
          @click="groups.template = !groups.template"
        >
          <ChevronRight
            class="h-3.5 w-3.5 shrink-0 transition-transform duration-150"
            :class="groups.template ? 'rotate-90' : ''"
            aria-hidden="true"
          />
          重命名模板
        </button>
        <div v-show="groups.template" class="px-4 pb-4">
          <slot name="template" />
        </div>
      </section>
    </div>
  </aside>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'

// 两级折叠：
//   1. railOpen —— 只在 <1024px 生效（spec §7.3：此档左栏折叠为顶栏下的可展开面板，
//      默认收起）。默认 false；大屏靠 lg:block 强制展开，不受此值影响。
//   2. groups.* —— 分组级折叠，与 spec §7.1 示意图里的 ▸ 对应，两档都生效。
//
// 折叠规则显式声明在本组件内部，不依赖 Tailwind 的自动兜底（spec §7.3 末句）。
const railOpen = ref(false)
const groups = reactive({ source: true, template: true })
</script>
```

几处不是随手写的：

- **`railOpen` 默认 `false` 而大屏仍然完整展开**：靠的是内容容器上的 `lg:block` —— 它无条件覆盖 `hidden`。这样不需要 `matchMedia` 监听，纯 CSS 就实现了「窄屏默认收起、宽屏强制展开」。
- **`max-h-[45dvh]` + `overflow-y-auto` 只在窄屏起作用**：窄屏下左栏在中段之上，若不限高，展开后会把工作区挤到 0 高度。`lg:max-h-none` 在大屏解除限制。
- **`bg-canvas` 而工作区是 `bg-surface`** —— 层级靠明度差表达，左栏比工作区低一档（spec §5.4），不靠阴影。
- **不使用 `AppPanel`**：spec §7.1 的左栏是「分节 + 发丝线」，不是卡片。spec §8.3 也明确写了 `TemplateConfig` 要「去卡片外壳」。

- [ ] **Step 2: 重写 `frontend/src/components/TemplateConfig.vue`**

去卡片外壳、垂直布局、改用原语。`<script setup>` 里的 `VARIABLE_DEFS` 数据表与 `insertVariable()` 逻辑**原样保留**，只把 `tplInputRef` 的绑定从原生 `<input>` 换成 `AppInput` 的 `$ref` 透传。

```vue
<template>
  <div class="flex flex-col gap-3">
    <AppSelect
      :model-value="tplStore.currentPresetId"
      label="预设模板"
      @update:model-value="$emit('preset-change', $event)"
    >
      <option value="">选择预设模板</option>
      <option v-for="p in tplStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
    </AppSelect>

    <AppInput
      ref="tplInputRef"
      :model-value="tplStore.currentTemplate"
      label="文件模板"
      mono
      placeholder="如 {show} - S{season_padded}E{episode_padded}{extension}"
      @update:model-value="$emit('template-edit', $event)"
    />

    <div class="flex flex-col gap-3">
      <AppCheckbox
        :model-value="tplStore.createSeasonFolder"
        :disabled="source === 'openlist'"
        :label="source === 'openlist' ? '创建季文件夹（OpenList 暂不支持）' : '创建季文件夹'"
        @update:model-value="$emit('update:createSeasonFolder', $event)"
      />
      <AppInput
        :model-value="tplStore.folderTemplate"
        :disabled="!tplStore.createSeasonFolder || source === 'openlist'"
        label="季文件夹模板"
        mono
        placeholder="如 Season {season_padded}"
        @update:model-value="$emit('update:folderTemplate', $event)"
      />
    </div>

    <div class="flex flex-col gap-2">
      <div class="flex items-center gap-1.5 text-[12px] text-ink-3">
        <Info class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        可用变量（点击插入）
      </div>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="v in VARIABLE_DEFS"
          :key="v.tag"
          type="button"
          :title="v.desc"
          class="rounded-[8px] border border-line bg-surface px-2 py-1 font-mono text-[12px] text-accent transition-colors duration-150 hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
          @click="insertVariable(v.tag)"
        >
          {{ v.tag }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Info } from 'lucide-vue-next'

import AppSelect from './ui/AppSelect.vue'
import AppInput from './ui/AppInput.vue'
import AppCheckbox from './ui/AppCheckbox.vue'

const VARIABLE_DEFS = [
  { tag: '{show}', desc: '剧名（自动从路径/文件名解析）', example: '绝命毒师' },
  { tag: '{show_clean}', desc: '剧名（已清洗，去除特殊字符）', example: '绝命毒师' },
  { tag: '{season}', desc: '季数（阿拉伯数字）', example: '1' },
  { tag: '{season_padded}', desc: '季数（补零）', example: '01' },
  { tag: '{episode}', desc: '集数（阿拉伯数字）', example: '5' },
  { tag: '{episode_padded}', desc: '集数（补零）', example: '05' },
  { tag: '{title}', desc: '集标题（部分资源可解析）', example: 'PILOT' },
  { tag: '{quality}', desc: '画质标记', example: '1080p WEB-DL' },
  { tag: '{source}', desc: '来源标记', example: 'WEB-DL AMZN' },
  { tag: '{extension}', desc: '文件扩展名', example: '.mkv' },
  { tag: '{sub_lang}', desc: '字幕语言标记', example: 'CHS' },
]

const props = defineProps({
  tplStore: { type: Object, required: true },
  source: { type: String, required: true },
})
defineEmits([
  'preset-change', 'template-edit',
  'update:createSeasonFolder', 'update:folderTemplate',
])

const tplInputRef = ref(null)

function insertVariable(tag) {
  const wrapper = tplInputRef.value
  const input = wrapper?.$el?.querySelector('input')
  if (!input) return
  const current = props.tplStore.currentTemplate || ''
  const start = input.selectionStart ?? current.length
  const end = input.selectionEnd ?? current.length
  const next = current.slice(0, start) + tag + current.slice(end)
  props.tplStore.currentTemplate = next
  input.focus()
  const pos = start + tag.length
  requestAnimationFrame(() => {
    input.setSelectionRange(pos, pos)
  })
}
</script>
```

几处不是随手写的：

- **`insertVariable` 的取值路径变了**：`tplInputRef` 现在指向 `AppInput` 组件的实例，不再是原生 `<input>`。`AppInput` 没开 `inheritAttrs: false`，`ref` 拿到的是组件实例，所以要 `.$el.querySelector('input')`。这是把原生控件换成组件后**唯一**会静默失效的地方 —— 光标位置插入会变成无操作（`if (!input) return` 直接返回），界面上看不出报错。
- **变量卡片从「两行描述卡」压成「单行 chip」**：280px 宽放不下原来的 `grid-cols-2` 卡片（每张卡有 tag + desc + example 三行），会溢出。描述挪到 `title` 属性（悬停可见），tag 本身仍然等宽字体 —— 符合 spec §6.2「模板变量名走等宽」。
- **`source === 'openlist'` 时不再用 `cursor-not-allowed` + `title` 提示**，改成直接写进 label 文案。280px 宽度下，可见的说明比悬停提示更可靠。
- **原来的 `FileText` 图标与面板标题「重命名模板」删掉** —— 标题现在由 `AppLeftRail` 的分组头承担，避免同一句话出现两次。

- [ ] **Step 3: `HomeView` 中段改成两栏**

编辑 `frontend/src/views/HomeView.vue`，把中段那一层：

```vue
    <div class="flex min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <SourceConfigPanel ... />
      <TemplateConfig ... />
      <FileTable ... />
    </div>
```

替换为：

```vue
    <div class="flex min-h-0 flex-col overflow-hidden lg:grid lg:grid-cols-[280px_1fr]">
      <AppLeftRail>
        <template #source>
          <SourceConfigPanel
            ...（原样，含全部 :props 与 @events）
          />
        </template>
        <template #template>
          <TemplateConfig
            ...（原样，含全部 :props 与 @events）
          />
        </template>
      </AppLeftRail>

      <main class="flex min-h-0 flex-1 flex-col overflow-hidden">
        <FileTable
          ...（原样，含全部 :props 与 @events）
        />
      </main>
    </div>
```

并在 `<script setup>` 补 `import AppLeftRail from '../components/layout/AppLeftRail.vue'`。

窄屏用 `flex flex-col`、`lg:` 起用 `grid grid-cols-[280px_1fr]` —— 因为窄屏下左栏是「可展开的横向条带 + 下面的工作区」，两行的高度关系是内容驱动；大屏下才是严格的两列等高分栏。

- [ ] **Step 4: 构建并验证三栏成型**

```bash
cd frontend && npm run build
```

预期：通过。

```bash
cd frontend && npm run dev
```

**Review Focus 第 1 条在此做第一次完整验收。**

| # | 视口 | 操作 | 预期 |
|---|---|---|---|
| 1 | ≥1024px | 打开首页 | 左侧 280px 浅灰栏（`#F6F7F8`），右侧白色工作区；两者之间一条发丝线；**没有阴影** |
| 2 | ≥1024px | 看左栏 | 两个分组：「扫描源」（展开，内含垂直的表单）与「重命名模板」（展开，含预设 / 文件模板 / 复选框 / 季模板 / 变量 chips） |
| 3 | ≥1024px | 点「重命名模板」分组头 | 内容收起，`▸` 旋成 `▾`；再点展开 |
| 4 | ≥1024px | 扫描 200+ 文件 | **底栏钉在视口底部**；表格在右栏内部滚动；左栏与顶栏都不动 |
| 5 | ≥1024px | 滚左栏（内容超出时） | 左栏**自己**滚动，工作区不动 |
| 6 | 900px | 打开首页 | 左栏变成顶栏下方的一条「扫描源与模板」折叠条，**默认收起** |
| 7 | 900px | 点折叠条 | 展开显示两个分组；展开后高度不超过视口的 45%，工作区仍可见 |
| 8 | 900px | 扫描文件 | 底栏**仍然常驻**（spec §7.3：768–1023px 底栏常驻） |
| 9 | 任意 | 点变量 chip（如 `{season}`） | 文本被插入「文件模板」输入框的**光标处**，且输入框重新获得焦点、光标落在插入内容之后 |
| 10 | 任意 | 看变量 chip | 文字是等宽字体（`Geist Mono Variable`） |
| 11 | 任意 | 看左栏里有没有白底卡片 + 阴影 | **没有** —— 左栏只有分节与发丝线 |

第 9 项是本任务最容易静默失败的点（`insertVariable` 的 ref 路径）。若点了没反应且 Console 无报错，检查 `tplInputRef.value.$el.querySelector('input')` 是否拿到了元素。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/layout/AppLeftRail.vue frontend/src/components/TemplateConfig.vue frontend/src/views/HomeView.vue
git commit -m "feat(frontend): 左栏成型, TemplateConfig 去卡片壳并垂直化"
```

---

### Task 6: `FileTable` 撑满高度 + 内部滚动

表格是工作区的核心，也是 `min-h-0` 链的最后一环。当前滚动容器写死 `style="max-height: 480px"`，必须换成「撑满剩余高度并在内部滚动」。

**Files:**
- Modify: `frontend/src/components/FileTable.vue`（容器结构；表头、空态、行控件本期不动，第三期改造）

**Interfaces:**
- Consumes: 新 token `surface` `line` `sunken` `ink` `ink-2` `ink-3`（第一期 Task 2）
- Produces: `FileTable` 的 props / emits **完全不变**；外壳结构变为 `flex min-h-0 flex-1 flex-col`，第三期在内部替换控件与状态设计

- [ ] **Step 1: 改写 `FileTable.vue` 的容器结构**

把整个 `<template>` 替换为：

```vue
<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface">
    <div class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-3">
      <div class="flex min-w-0 items-center gap-2 text-[14px] font-semibold text-ink">
        <span class="truncate">文件列表</span>
        <span v-if="filesStore.files.length" class="truncate text-[12px] font-normal text-ink-3">
          共 {{ filesStore.files.length }} 个文件
          <span v-if="scannedInfo"> (视频 {{ scannedInfo.videos }} / 字幕 {{ scannedInfo.subtitles }})</span>
        </span>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <button
          class="h-8 rounded-[8px] border border-line-strong bg-surface px-3 text-[12px] font-medium text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none disabled:opacity-45 disabled:cursor-not-allowed"
          :disabled="!filesStore.files.length"
          @click="$emit('preview-all')"
        >
          预览
        </button>
        <button
          class="h-8 rounded-[8px] border border-danger bg-surface px-3 text-[12px] font-medium text-danger transition-colors duration-150 hover:bg-danger-soft focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none disabled:opacity-45 disabled:cursor-not-allowed"
          :disabled="!filesStore.files.length"
          @click="$emit('clear-all')"
        >
          清空
        </button>
      </div>
    </div>

    <!-- 滚动容器。flex-1 + min-h-0 让它吃掉父容器剩余高度并在内部滚动，
         而不是把页面撑高（spec §7.2）。 -->
    <div class="min-h-0 flex-1 overflow-auto">
      <table class="w-full min-w-[560px] text-[13px]">
        <thead class="sticky top-0 z-[1] bg-sunken">
          <tr class="text-ink-2">
            <th class="hidden w-12 px-4 py-3 text-left font-semibold sm:table-cell">#</th>
            <th class="w-12 px-4 py-3 text-left font-semibold">
              <input
                type="checkbox"
                :checked="allSelected"
                aria-label="全选"
                class="h-4 w-4 accent-accent"
                @change="$emit('toggle-all', $event.target.checked)"
              />
            </th>
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[220px]">原文件名</th>
            <th class="hidden w-[160px] px-4 py-3 text-left font-semibold md:table-cell">解析剧名</th>
            <th class="w-[72px] px-4 py-3 text-left font-semibold md:w-[80px]">季</th>
            <th class="w-[72px] px-4 py-3 text-left font-semibold md:w-[80px]">集</th>
            <th class="w-[80px] px-4 py-3 text-left font-semibold md:w-[96px]">状态</th>
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[220px]">新文件名</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="previewRows.length">
            <tr
              v-for="(row, idx) in previewRows"
              :key="row.id"
              class="border-t border-line transition-colors duration-150 hover:bg-sunken/60"
            >
              <td class="hidden px-4 py-2.5 text-ink-3 tabular-nums sm:table-cell">{{ idx + 1 }}</td>
              <td class="px-4 py-2.5">
                <input
                  type="checkbox"
                  :checked="row.selected"
                  :aria-label="`选择 ${row.filename}`"
                  class="h-4 w-4 accent-accent"
                  @change="$emit('select-row', { row, val: $event.target.checked })"
                />
              </td>
              <td class="px-4 py-2.5">
                <div class="max-w-[320px] truncate text-ink">{{ row.filename }}</div>
                <div class="max-w-[320px] truncate text-[11px] text-ink-3">{{ row.path }}</div>
              </td>
              <td class="hidden px-4 py-2.5 md:table-cell">
                <input
                  v-model="row.show_name"
                  aria-label="解析剧名"
                  @change="$emit('update-row', row)"
                  class="h-8 w-full rounded-[8px] border border-border-control bg-surface px-2.5 text-[13px] text-ink transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35"
                />
              </td>
              <td class="px-4 py-2.5">
                <input
                  v-model.number="row.season"
                  type="number" min="1" max="30"
                  aria-label="季"
                  @change="$emit('update-row', row)"
                  class="h-8 w-full rounded-[8px] border border-border-control bg-surface px-2.5 text-[13px] text-ink tabular-nums transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35"
                />
              </td>
              <td class="px-4 py-2.5">
                <input
                  v-model.number="row.episode"
                  type="number" min="1" max="999"
                  aria-label="集"
                  @change="$emit('update-row', row)"
                  class="h-8 w-full rounded-[8px] border border-border-control bg-surface px-2.5 text-[13px] text-ink tabular-nums transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35"
                />
              </td>
              <td class="px-4 py-2.5">
                <span
                  class="inline-flex items-center gap-1 whitespace-nowrap rounded-[8px] px-2 py-0.5 text-[12px] font-medium"
                  :class="row.needs_review ? 'bg-warn-soft text-warn' : 'bg-sunken text-ink-2'"
                >
                  {{ row.needs_review ? '待确认' : '已解析' }}
                </span>
              </td>
              <td class="px-4 py-2.5">
                <div class="truncate font-medium text-ink" :class="row.new_filename ? '' : 'text-ink-3'">
                  {{ row.new_filename || '(未解析)' }}
                </div>
              </td>
            </tr>
          </template>
          <tr v-else>
            <td colspan="8" class="px-4 py-16 text-center">
              <div class="flex flex-col items-center gap-2 text-ink-2">
                <FileQuestion class="h-10 w-10 text-ink-3" aria-hidden="true" />
                <div class="text-[13px]">扫描目录以加载文件</div>
                <button
                  v-if="activeSource === 'local'"
                  class="mt-2 h-9 rounded-[8px] bg-accent px-4 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
                  @click="$emit('quick-scan')"
                >开始扫描</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
```

`<script setup>` 里的 `import { List, ... }` 去掉不再使用的 `List` / `Eye` / `Trash2`（按钮改成纯文字），保留 `FileQuestion`。props / emits 声明**一行不动**。

几处不是随手写的：

- **`bg-sunken/60` 的 hover 行底色**：直接用 `bg-sunken` 会与表头同色，滚动时表头与行混在一起；60% 透明度让 hover 行与表头可区分。
- **表头 `text-ink-2` 而不是 `text-ink-3`** —— spec §5.1 的使用约束：「表头文字必须用 `ink-2`，不得用 `ink-3`。`ink-3` 对 `sunken` 底仅 4.23:1，低于 AA」。
- **窄屏的列宽收缩 + 隐去两个最低价值列**：这是 Review Focus 第 4 条的落点，做法分三层 ——
  1. `#` 列在 `<640px` 隐去（行号是装饰性信息），`解析剧名` 在 `<768px` 隐去（它的值已经在「新文件名」里体现）。
  2. 剩下的列在窄屏用**更小的宽度**（两个文件名列 `min-w-[140px] md:min-w-[220px]`，季/集 `w-[72px] md:w-[80px]`，状态 `w-[80px] md:w-[96px]`），`<table>` 的 `min-w` 相应从 `md:` 的 640px 降到 560px。
     窄屏下表宽 ≈ 48 + 140 + 72 + 72 + 80 + 140 = **552px**，在 375px 视口上只需**一次约 180px 的短横滑**就能读到最右的「新文件名」。
  3. `md:` 起恢复原宽度。此时各列宽度之和为 48 + 220 + 160 + 80 + 80 + 96 + 220 ≈ **900px** —— 这就是 `md:` 档表格的实际横向下限（`<table>` 上的 `w-full` 在容器更宽时接管，所以不再给 `md:min-w` 一个会误导人的小数值）。
     直接后果：**视口窄于约 1180px 时，`md:` 档的表格也会横向滚动**（1024px 视口下工作区只有 1024 − 280 = 744px）。这不是回归 —— 改造前那 7 列同样有约 900px 的宽度需求，只是当时没有内部滚动容器去承接它。

  **为什么不做冻结列（sticky column）**：冻结「复选框 + 原文件名」需要 268px，在 375px 上只剩 107px 给滚动区，220px 宽的「新文件名」**永远无法完整显示** —— 它不但没解决「原文件名与新文件名要对照」这个真实任务，反而让情况更糟。冻结单个复选框列（48px）能解决的是「选择上下文不丢失」，与这个任务的痛点是两件事，不值得为它引入 sticky 单元格与 sticky 表头之间的层叠上下文管理（`thead` 需提到 `z-[3]`、角落的 `th` 需 `z-[4]`、冻结的 `td` 需 `z-[2]`，且冻结单元格必须有不透明底色，会让行 hover 在冻结列与滚动列上呈现两种底色）。
  **为什么不做窄屏卡片式行布局**：那是宽表在移动端的通行最佳实践，但它要求为数据行写第二套模板（整行控件在 `<768px` 下重排成堆叠卡片）。对「自托管的桌面优先工具」而言，代价是行模板永久翻倍、且本计划无法在真实设备上验证它 —— 收益不抵成本。**已显式记为不在本轮范围**：若日后移动端成为主要使用场景，应作为独立任务重出这一块的交互稿。
- **数字列加 `tabular-nums`**（季、集、行号）—— spec §6.4。
- **`#` 列的行号也用 `tabular-nums`**，否则 1 与 8 宽度不同会让整列轻微抖动。
- **状态徽章直接内联，没有用 `AppBadge`** —— `AppBadge` 是第三期的改造目标，本期保持内联但按 spec §5.2 改成「中性 + 待确认用 warn」的配色（去掉 ✅⚠️ emoji，去掉绿色）。
- **`min-h-0 flex-1` 必须同时给滚动容器**：`flex-1` 让它吃满剩余高度，`min-h-0` 允许它比内容矮。只有 `flex-1` 而没有 `min-h-0`，容器会被内容撑高，滚动失效。

- [ ] **Step 2: 构建并验证长表格**

```bash
cd frontend && npm run build
```

预期：通过。

```bash
cd frontend && npm run dev
```

准备一个 ≥300 个视频文件的目录。走查：

| # | 视口 | 操作 | 预期 |
|---|---|---|---|
| 1 | 1280×800 | 扫描 300+ 文件 | 表格**自己**滚动；顶栏、左栏、底栏全都**不动**（Review Focus 第 1 条，full check） |
| 2 | 1280×800 | 滚到表格中部 | 表头**仍然可见**（sticky）且底色是 `#EDEFF1`，与行有清晰分界 |
| 3 | 1280×800 | 悬停任意一行 | 行底色轻微变化（150ms 过渡） |
| 4 | 1280×800 | 看最右列「新文件名」 | 有值的行是深色 `#15181B` 粗体，`(未解析)` 的行是灰色 |
| 5 | 1280×800 | 看行号列与季/集列 | 数字宽度对齐，不抖动 |
| 6 | 1280×800 | 快速上下滚动 | **整页不滚动**；只有表格内部滚（滚轮在表格上时） |
| 7 | 1280×800 | 缩小窗口高度到 400px | 表格仍能滚动，底栏仍可见 |
| 8 | 800×900 | 扫描文件 | 表格隐藏「解析剧名」列；`#` 列仍在；季/集/状态列比 1280px 下更窄 |
| 9 | 375×812 | 扫描文件 | 表格横向可滚动；首屏看到「复选框 + 原文件名 + 季」；`解析剧名` 与 `#` 都不在 |
| 9b | 375×812 | 在 Console 里量 `document.querySelector('table').getBoundingClientRect().width` | 结果 ≈ **552px**（允许 ±20px）。远大于 552 → 窄屏列宽收缩没生效；远小于 → `min-w` 写小了，文件名会被截得太狠 |
| 9c | 375×812 | 从最左滑到最右 | 约一次 180px 的横滑就能看到「新文件名」列，且该列在此宽度下**完整可见**（不要求「原文件名」同时可见 —— 这是已记录的取舍，见 Review Focus 第 4 条） |
| 9d | 1024×900 | 扫描文件并量 `document.querySelector('table').getBoundingClientRect().width` | 结果 ≈ **900px**，大于工作区的 744px，所以此档**也有横向滚动**。这是已知且有据的行为（改造前 7 列同样需要约 900px），不是本任务的缺陷；只要滚动发生在表格内部、整页仍不滚动即可 |
| 10 | 任意 | 点表头复选框 | 全选 / 全不选；行复选框状态同步 |
| 11 | 任意 | 修改某行的「集」 | 表格不重排；「新文件名」列在预览重建后更新 |

第 1、6 项不通过 = `min-h-0` 链断了。此时逐环检查：`App.vue` 路由出口 → `HomeView` 根 → 中段 `<div>` → `<main>` → `FileTable` 根 → 滚动容器，**六个容器**都必须是 `min-h-0`（或 `overflow-hidden` 的等价约束）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/FileTable.vue
git commit -m "feat(frontend): 文件表格撑满剩余高度并在内部滚动, 表头 sticky"
```

---

### Task 7: 响应式三档收口

Task 5 与 Task 6 已经内联声明了各档行为，本任务做**交叉验证与补齐**（spec §7.3 要求「各档显式声明」，且「移动端折叠规则在每个多列组件的同一文件内显式声明，不依赖 Tailwind 自动兜底」）。

**Files:**
- Modify: `frontend/src/components/layout/AppTopBar.vue`（若窄屏溢出）
- Modify: `frontend/src/components/layout/AppBottomBar.vue`（若窄屏溢出）
- Modify: `frontend/src/components/layout/AppLeftRail.vue`（若窄屏溢出）

**Interfaces:**
- Consumes: Task 2–6 的全部产物
- Produces: 无新接口；本任务只改样式类

- [ ] **Step 1: 四档实跑并记录问题**

```bash
cd frontend && npm run dev
```

用 DevTools 设备工具栏，四档各走一遍（1280 / 1024 / 768 / 375）。逐档记录下表，**有问题的行在 Step 2 修**：

| 断点 | spec §7.3 要求 | 检查点 |
|---|---|---|
| ≥1024px | 三栏：左栏 280px + 工作区 | 左栏在左、宽度 280px、有右发丝线；底栏常驻；表格内部滚动。**1024px 档的表格会有横向滚动**（列宽合计约 900px > 工作区 744px），1280px 及以上不出现 —— 属已知行为，见 Task 6 Step 2 的 9d |
| 768–1023px | LeftRail 折叠为顶栏下的可展开面板，**默认收起**；BottomBar 常驻 | 顶栏下出现「扫描源与模板」条；初始为收起；点开高度 ≤ 45% 视口；底栏可见 |
| <768px | 表格横向滚动，关键列优先可见；**BottomBar 保持常驻** | 表格可横向滚动且表宽 ≈ 552px（一次约 180px 的短滑即可看到「新文件名」）；首屏可见复选框与原文件名列；底栏**没有**被挤掉或换行 |
| 375px | 同上 | 顶栏单行不溢出；底栏的按钮与计数**不换行**；扫描按钮通栏 |

- [ ] **Step 2: 修掉 Step 1 发现的问题**

三个出现概率最高、且修法确定的窄屏问题：

**（a）底栏在 375px 下溢出。** 冲突策略下拉 + 计数 + 两个按钮（「试运行」+「执行重命名」，`whitespace-nowrap`）总宽约 380px。修法是在 `AppBottomBar.vue` 里让计数在极窄屏隐藏：

```html
      <span class="hidden truncate text-[13px] text-ink-2 sm:inline">
        已选 <span class="tabular-nums text-ink">{{ selectedCount }}</span>
        / <span class="tabular-nums">{{ totalCount }}</span>
      </span>
```

**（b）底栏在 375px 下把「执行重命名」挤出视口。** 把「试运行」在极窄屏收起 icon 之外的宽度 —— 它本来就没有 icon，所以改为隐藏整个「试运行」按钮并在移动端只留主操作。**不要这样做**（会丢掉试运行这个安全入口）。正确修法是缩短主按钮文案：

```html
        <span class="sm:hidden">{{ executing ? '执行中…' : '执行' }}</span>
        <span class="hidden sm:inline">{{ executing ? '执行中…' : '执行重命名' }}</span>
```

**（c）顶栏在 375px 下品牌名被压成零宽。** 已由 `min-w-0` + `truncate` 处理；若仍溢出，把品牌名在极窄屏隐藏：

```html
      <span class="hidden truncate text-[14px] font-semibold text-ink sm:inline">Episode Renamer</span>
```

**不要**用 `overflow-x-hidden` 之类的兜底去「隐藏」溢出 —— 那只会把内容切掉而不解决布局。

- [ ] **Step 3: 构建并复跑四档**

```bash
cd frontend && npm run build && npm run dev
```

重跑 Step 1 的四档表格。

预期：四档全部通过；**底栏在四档下都不换行、不溢出、不消失**。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/layout/
git commit -m "fix(frontend): 补齐 375px 档的底栏与顶栏布局"
```

---

## 本期完成后的状态

- 三栏工作台可见，表格撑满剩余高度并在内部滚动，**主操作常驻底栏**（spec §1 的核心目标）
- `SourceTabs.vue` / `ActionBar.vue` / `ScanPanel.vue` 三个文件删除
- 工作区状态全部收进 `stores/workspace.js`，`HomeView` 退化为约 90 行模板
- 技术债清偿进度（spec §3）：#1 卡片汤（左栏已无卡片）、#2 主操作离手最远（解决）、#3 `SourceTabs` 独立成卡（解决）、#4 宽屏左侧 600px 全空（解决）、#12 emoji 从 3 处降到 1 处（剩余 `FileTable` 的状态徽章，第三期清）
- 18 处手写输入框样式清偿 8 处，剩 10 处在第三期

下一步：`docs/superpowers/plans/2026-09-25-frontend-3-features.md`

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

4. 跑一次 `cd frontend && node scripts/check-sfc-compile.mjs` —— 本阶段新建但尚未接线的组件不在 Vite 的模块图里，`npm run build` 不会编译它们（脚本在第一期 Task 7 建立）。

**任务内的纪律**：计划里每个任务给出的 `git add <具体文件>` 列表都**不含** dist，照做即可。构建后 dist 会在工作区里显示为已修改但未暂存 —— 这**不影响**任务评审，因为评审包用的是 BASE..HEAD 的**提交**区间，不是工作区。不要去 `git checkout` 还原 dist（Task 1 的实现者那样做是多余的），也不要顺手 `git add` 它。

## Self-Review

**Spec 覆盖**

| spec 条目 | 落位 |
|---|---|
| §7.1 App Shell 三段式 | Task 2（顶栏 + 路由出口）、Task 3（底栏）、Task 5（左栏） |
| §7.1 TopBar 56px，内容单行 | Task 2 Step 1（`h-14` + `min-w-0` / `truncate` / `shrink-0`） |
| §7.1 LeftRail 280px，`overflow-y-auto` | Task 5 Step 1 |
| §7.1 BottomBar 56px，冲突策略 + 已选计数 + 两个操作 | Task 3 Step 1 |
| §7.1 左栏两个折叠分组（`▸ 扫描源` / `▸ 重命名模板`） | Task 5 Step 1（两级折叠） |
| §7.2 中间层 `min-h-0` | Task 2 Step 2 / Task 3 Step 3 / Task 6 Step 1，并在 Task 6 Step 2 与本期 Self-Review 各设一道验收 |
| §7.2 `h-dvh` 而非 `h-screen` | Task 2 Step 2 |
| §7.2 主操作从文档流底部移到常驻底栏 | Task 3 |
| §7.3 三档响应式 | Task 5 Step 4、Task 6 Step 2、Task 7 全档收口 |
| §7.3 折叠规则在同文件内显式声明 | Task 5 Step 1 的组件注释 + `AppLeftRail` 内部 `railOpen` / `groups` |
| §7.4 `SourceTabs` tab bar 移入顶栏改为 segmented，文件删除 | Task 2 Step 1、Step 5 |
| §8.3 `App.vue` 重写为三段式 shell | Task 2 Step 2 |
| §8.3 `HomeView` 布局重组；状态上提 | Task 1（状态）+ Task 3、Task 5（布局） |
| §8.3 `ScanPanel` 拆为 `SourceConfigPanel` 移入左栏 | Task 4（改写）+ Task 5 Step 3（移入左栏） |
| §8.3 `TemplateConfig` 移入左栏、去卡片外壳 | Task 5 Step 2 |
| §8.3 `FileTable` 撑满高度、sticky 表头 | Task 6 |
| §8.4 删除 `SourceTabs.vue` / `ActionBar.vue` | Task 2 Step 5 / Task 3 Step 5 |
| §3.1 结构问题 1–4 | 全部在 Task 3 / Task 5 / Task 6 解决 |
| §11 动效表（`source-fade` / `page-fade` 不在表内） | Task 2 Step 2、Task 3 Step 3 删除 |

**占位符扫描**：无 TBD / TODO / 「类似 Task N」/「添加适当的错误处理」。Task 7 的 Step 2 给出三条**具体**的窄屏修法与代码，而非「视情况调整」。

**类型一致性**：`useWorkspaceStore()` 的成员表在 Task 1 的 Interfaces 里定义一次，Task 2（`activeSource` / `switchSource`）、Task 3（`conflictStrategy` / `selectedCount` / `totalCount` / `executing` / `doDryRun` / `doExecute`）、Task 4（`path` / `recursive` / `includeSubs` / `scanning` / `olForm` / `confirm` / `toast` / `browse` / `lastResult` / `resultDialog` / `executeDryRun`）全部按此名引用，无别名漂移。`SourceConfigPanel` 的 props/emits 与旧 `ScanPanel` 逐字相同，`TemplateConfig` 的 props/emits 保持不变 —— 两者在 Task 5 移入左栏时无需再改调用点。

**Review Focus 落位**

| # | 条目 | 验证位置 |
|---|---|---|
| 1 | `min-h-0` 链断环 | Task 3 Step 6（首次）、Task 5 Step 4 第 4 项、Task 6 Step 2 第 1/6 项（完整验收，并列出六个容器的清单） |
| 2 | 底栏出现在设置页 | Task 2 Step 6 第 7 项；底栏在 `HomeView` 而非 `App.vue` 由 Task 3 Step 3 保证 |
| 3 | 切换数据源丢失已扫结果 | Task 1 Step 1 的差异说明（删掉了互相打架的清空/恢复两条路径）+ Task 1 Step 4 第 8 项 |
| 4 | 窄屏下「原文件名」与「新文件名」不能同屏 | Task 6 Step 1 的三层做法（隐列 + 收缩列宽 + `md:` 恢复）；Task 6 Step 2 第 9/9b/9c 项（含实测量表宽的硬判据）；两个被否决的替代方案（冻结列、卡片式行布局）及理由写在 Review Focus 第 4 条与 Task 6 的实现说明里 |
| 5 | 模板变更后预览不刷新 | Task 1 Step 1 的 `watch` 随状态一起迁入 store + Task 1 Step 4 第 3 项 |

**未覆盖（有意）**：FileTable 的骨架屏、空态重做、`aria` 与 `focus-visible` 的全量收口、`reduced-motion` 兜底、`ExecutingOverlay` 精简，全部属第四期。
