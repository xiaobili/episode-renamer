# 前端重构 · 第三期：业务组件改造与设置接线 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把所有还没动过的业务组件改用第一期原语（**18 处手写输入框样式在本期清零**），把设置从「写进 `localStorage` 但没人读」修成真正生效的 Pinia store，并让补零位数设置端到端生效。

**Architecture:** 新增 `stores/settings.js`（Pinia）+ `stores/settingsSchema.js`（零依赖纯函数，可在 node 里直接跑断言）。`settingsSchema.js` 单独成文件是**为了可验证**：本项目没有前端测试设施（spec §17 遗留 3），而设置的读盘逻辑有 4 条健壮性要求（spec §12.2），把它隔离成零依赖模块后可以用 `node -e` 直接跑真断言，而不是「在浏览器里点一下看看」。

**Tech Stack:** Vue 3.5.43 / Vite 5 / Tailwind CSS v4 / Pinia 2 / lucide-vue-next / Node 20+（仅用于跑 schema 断言）

**Spec:** `docs/superpowers/specs/2026-09-25-frontend-refactor-design.md`（§5.2 语义降级、§6.2 等宽纪律、§8.3 组件改造、§10 状态设计、§12 设置断线修复、§13.5 前端请求带参、§16 阶段 4–6）

**前置:** 第一期、第二期已完成。本期直接使用新 token、六个 UI 原语、`stores/workspace.js`。

**关键外部依赖:** Task 8（补零位数前端接线）需要后端计划 **`docs/superpowers/plans/2026-09-25-backend-pad-digits.md` 已合入**。未合入时 Task 8 **必须跳过**，详见该任务的说明。

**后续:** `2026-09-25-frontend-4-polish.md`

---

## Global Constraints

- **本期的核心数字：18 处手写输入框样式必须清零。** 校验命令（本期末尾必须输出 `0`）：
  ```bash
  cd frontend && grep -rn "focus:border-primary focus:ring-2 focus:ring-primary/20" src/ | wc -l
  ```
- 圆角只允许 `rounded-[8px]`（控件）/ `rounded-[12px]`（面板 / 模态 / 下拉）。**禁止** `rounded-full` / `rounded-xl` / `rounded-2xl` / `rounded-md` / `rounded-lg`
- 默认无阴影，唯一例外 `shadow-overlay`（浮层：模态、下拉、Toast）
- 交互控件边框：**表单控件**（input / select / checkbox / textarea）用 `border-border-control`；**按钮不在此限**，其边框是装饰包装，按 spec §8.2 用 `border-line-strong`（理由见第一期 Global Constraints）。
- **不使用绿色表达「成功」**（spec §5.2）：成功态 = 中性底（`sunken`）+ `ink-2` 文字 + 对勾图标；只有「待确认」用 `warn`，失败用 `danger`
- 路径与文件名**不用** `font-mono`（spec §6.2）；表格数字列加 `tabular-nums`（spec §6.4）
- 补零位数合法区间 `[1, 6]`，与后端 `PadConfig` 一致（spec §13.2、§17）
- 每个任务结束时 `cd frontend && npm run build` 必须通过
- 路由路径、API 路径与响应结构不变

- **组件 `<style>` 块里不得出现 `var(--color-*)` 对「旧别名」的引用**（`--color-primary` / `--color-text` / `--color-border*` / `--color-surface-muted` / `--color-success*` / `--color-warning*` / `--color-error*`）。别名块是本期的过渡脚手架且**刻意非 `static`** —— 没有任何工具类引用它的别名会被 Tailwind tree-shake 掉，`var()` 于是静默解析为空；何况第四期会整块删除。需要颜色时一律用工具类（`bg-accent` / `text-ink-2` …）。本期新建或重写的组件如需自定义过渡，只用**新** token（`--color-ink` 等，它们在 `@theme static` 块里，一定存在）。

- **按钮光标由 `style.css` 的基线规则统一提供**（`button:not(:disabled) { cursor: pointer }`，Tailwind v4 的 preflight 删掉了 v3 的等价声明）。因此新写的裸 `<button>` **不需要**再写 `cursor-pointer`，也**不得**给它加与之冲突的 cursor 类。禁用态由 `disabled:cursor-not-allowed` 负责：`:not(:disabled)` 让两者不在同一个元素上竞争。**不要**把它简化成裸 `button { cursor: pointer }` —— 该基线规则是层外样式，按 CSS 级联层规则优先于 Tailwind 的层内工具类，**与特异性无关**，写成裸选择器会覆盖掉禁用态的 `not-allowed`。

- **源码文件的注释里不要写字面类名**（`.vue` / `.js`；`style.css` 的注释不受影响）。实测 Tailwind 4.3.3：CSS 入口文件注释里的 `border-line-strong` 不生成规则，而 **`.vue` 注释里的 `rounded-[12px]` 与 `grid-rows-[56px_1fr]` 各生成一条真实规则**。两个后果：①产出无人使用的死 CSS；②**类名闸门会因为「注释提过」而通过** —— 一个没有任何元素使用的类名，只要在源码注释里出现过就会命中，闸门于是为它开绿灯。需要提到某个类名时，**描述它而不要写字面量**（「两行 grid / 上方滚动区 / 下方 56px 底栏」而不是把类名抄一遍）。

## Review Focus

1. **前端改完补零位数却毫无变化，且零报错**（本期最高风险）—— 若后端未合入 `episode_pad_digits` 字段，Pydantic 会**静默丢弃**未知字段，请求返回 200，界面一切正常，只有「新文件名」列固执地显示 `S01E02`。期望：设置页把集数补零位数改成 3 → 表格新文件名列出现 `S01E001`。→ Task 8 Step 2 专门给出区分「后端未合入」与「前端没接上」的检查
2. **`localStorage` 里是残缺或损坏的 JSON** —— 旧的 `SettingsView` 写盘的字段名是 `defaultTemplate`，新 store 读的是 `defaultTemplateId`；用户浏览器里可能还躺着旧结构、缺字段、甚至被手工改坏的字符串。期望：不白屏、不抛错，缺的字段逐个回落默认值。→ Task 1
3. **`localStorage` 不可用**（隐私模式 / 禁用存储）—— 未捕获的异常会在 store 初始化时抛出，**整个应用白屏**。期望：退化为纯内存态，应用照常启动，只是设置不持久化。→ Task 1、Task 2
4. **补零位数输入框被清空后保存** —— `AppInput` 在 `type="number"` 下清空会 emit `null`。若把它当成 `0` 存下来，后端钳到 1、界面显示 0，两侧不一致；若存成 `null`，请求会发 `null`。期望：视为「未设置」回落默认值 2。→ Task 1。**另注（第一期 Task 6 的实现者实测）**：`type="number"` 下用户输入半截非法内容（`-`、`1e`）时浏览器会把 `value` 规范化成 `''`，于是也在 emit `null` —— 可见文本还在、值已是「未设置」。这与清空同义，行为可接受，但排查「设置没生效」时要记得这一条
5. **设置页有未保存改动时离开** —— 设置页保留「草稿 + 保存」语义，改动在点「保存设置」之前**不应**影响工作区。期望：改了补零位数但不点保存，切回工作区，预览仍是旧位数。→ Task 3

---

## 前期实测结论

| 结论 | 依据 |
|---|---|
| 当前 `SettingsView.vue` 用 `localStorage['episode-renamer:settings']` 存 5 个字段（`defaultTemplate` / `episodePadDigits` / `seasonPadDigits` / `conflictStrategy` / `openlist{serverUrl,concurrency,requestInterval}`），**没有任何其他文件读它** | 读代码 + `grep -rn "episode-renamer:settings" src/` |
| 旧的补零位数输入框是 `min="1" max="4"`，与后端 `PadConfig` 的 `[1, 6]` 不一致 | `SettingsView.vue:24,32` |
| `AppInput` 在 `type="number"` 下清空 emit `null`（第一期 Task 6 设计） | 第一期计划 |
| `node --input-type=module -e "import('./src/...').then(...)"` 配合 `process.exitCode = 1` 可以在无测试框架下跑真断言并让命令以非零码退出 | 本机实测 |
| `frontend/package.json` 有 `"type": "module"`，所以 `src/**/*.js` 直接被 node 当 ESM 处理，无需额外配置 | 读 `package.json` |
| `BrowseDialog.vue:32` 用 `font-mono` 显示目录路径、`ScanPanel.vue` 的路径字段（已改）也用过 —— 这些含中文的路径会让列对不齐（spec §6.2） | 读代码 |
| 第一期已成立：`bg-sunken` / `bg-warn-soft` / `bg-danger-soft` / `text-ink-2` / `border-line` / `border-border-control` / `shadow-overlay` / `rounded-[8px]` / `rounded-[12px]` 均可生成 | 第一期探针构建 |

---

## File Structure

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `frontend/src/stores/settingsSchema.js` | 设置的默认值、归一化、读盘 / 写盘（**零依赖纯函数**） | **新建** |
| `frontend/src/stores/settings.js` | 设置 Pinia store | **新建** |
| `frontend/src/main.js` | 应用入口 | 挂载前调用 `settingsStore.load()` |
| `frontend/src/views/SettingsView.vue` | 设置页 | **重写**：改用 store + 原语（7 处手写样式清零） |
| `frontend/src/stores/workspace.js` | 工作区 store | 接入 settings：默认模板 / 冲突策略初值 / 补零位数请求带参 |
| `frontend/src/components/ui/AppInput.vue` | 输入框原语 | 新增 `size` 与 `ariaLabel` 两个 prop |
| `frontend/src/components/ui/AppCheckbox.vue` | 复选框原语 | 新增 `ariaLabel` prop |
| `frontend/src/components/FileTable.vue` | 文件表格 | 改用原语 + `AppBadge`（3 处手写样式清零、最后一个 emoji 清零） |
| `frontend/src/components/ConfirmDialog.vue` | 确认对话框 | 适配新 token 与原语 |
| `frontend/src/components/ResultDialog.vue` | 结果对话框 | 同上；结果表改用 `AppBadge` |
| `frontend/src/components/BrowseDialog.vue` | 目录浏览对话框 | 同上；路径去 `font-mono`；补键盘导航 |
| `frontend/src/components/Toast.vue` | 轻提示 | 适配新 token；补 `role` |

---

### Task 1: `stores/settingsSchema.js`（纯函数 + node 可验证）

设置的读盘逻辑有 4 条健壮性要求（spec §12.2），而且是最容易出「白屏」级 bug 的地方。把它做成零依赖模块，就能在没有测试框架的前提下跑真断言。

**Files:**
- Create: `frontend/src/stores/settingsSchema.js`

**Interfaces:**
- Consumes: 无（**刻意不 import 任何东西** —— 这是它能被 node 直接 import 的前提）
- Produces:
  ```js
  export const SETTINGS_KEY = 'episode-renamer:settings'
  export function defaultSettings() -> {
    defaultTemplateId: string, episodePadDigits: number, seasonPadDigits: number,
    conflictStrategy: 'skip'|'abort'|'overwrite'|'rename_dup',
    openlist: { serverUrl: string, concurrency: number, requestInterval: number }
  }
  export function normalizeSettings(raw: unknown) -> Settings
  export function readSettings(storage: Storage | null) -> Settings
  export function writeSettings(storage: Storage | null, data: Settings) -> void
  ```
  `storage` 参数化的用途：浏览器传 `localStorage`；`localStorage` 不可用时传 `null`（退化为纯内存态）；node 断言里传一个 3 行的假对象。**不参数化就没法在 node 里验证「存储不可用」这条分支**，而它正是最会造成白屏的一条。

- [ ] **Step 1: 写断言脚本并确认它失败**

创建 `frontend/src/stores/settingsSchema.js` 时先只放一行占位，让断言能跑起来并失败：

```js
export {}
```

然后创建断言脚本 `frontend/scripts/check-settings-schema.mjs`（**注意 `.mjs` 后缀**，它要能在任何 node 版本下被当 ESM 执行）：

```js
import {
  SETTINGS_KEY,
  defaultSettings,
  normalizeSettings,
  readSettings,
  writeSettings,
} from '../src/stores/settingsSchema.js'

let failed = 0

function assert(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) {
    failed += 1
    console.log('FAIL', label, '得到', JSON.stringify(actual), '期望', JSON.stringify(expected))
  } else {
    console.log('PASS', label)
  }
}

function fakeStorage(initial) {
  const data = { ...(initial || {}) }
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v) },
    removeItem: (k) => { delete data[k] },
  }
}

// --- 默认值 ---
assert('默认值的补零位数是 2', defaultSettings().episodePadDigits, 2)
assert('默认值的冲突策略是 skip', defaultSettings().conflictStrategy, 'skip')
assert('默认值与后端 config.py 一致（2 位）', defaultSettings().seasonPadDigits, 2)

// --- Review Focus 4：清空输入框（null）视为未设置，回落默认 ---
assert('null 补零位数回落默认 2', normalizeSettings({ episodePadDigits: null }).episodePadDigits, 2)
assert('空字符串补零位数回落默认 2', normalizeSettings({ episodePadDigits: '' }).episodePadDigits, 2)
assert('undefined 补零位数回落默认 2', normalizeSettings({}).episodePadDigits, 2)

// --- 0 / 负数 / 超大值钳制到 [1, 6]，与后端 PadConfig 一致 ---
assert('0 被钳到 1', normalizeSettings({ episodePadDigits: 0 }).episodePadDigits, 1)
assert('负数被钳到 1', normalizeSettings({ episodePadDigits: -5 }).episodePadDigits, 1)
assert('99 被钳到 6', normalizeSettings({ episodePadDigits: 99 }).episodePadDigits, 6)
assert('季数同样钳制', normalizeSettings({ seasonPadDigits: 99 }).seasonPadDigits, 6)
assert('小数被截断', normalizeSettings({ episodePadDigits: 3.9 }).episodePadDigits, 3)
assert('字符串数字被接受', normalizeSettings({ episodePadDigits: '4' }).episodePadDigits, 4)
assert('非数字字符串回落默认', normalizeSettings({ episodePadDigits: 'abc' }).episodePadDigits, 2)

// --- Review Focus 2：逐字段合并，残缺对象不能让字段变 undefined ---
const partial = normalizeSettings({ conflictStrategy: 'overwrite' })
assert('只给一个字段时补零位数仍是默认', partial.episodePadDigits, 2)
assert('只给一个字段时 openlist 仍是完整对象', partial.openlist, {
  serverUrl: '', concurrency: 3, requestInterval: 0.5,
})
assert('openlist 半残缺也能补全', normalizeSettings({ openlist: { concurrency: 5 } }).openlist, {
  serverUrl: '', concurrency: 5, requestInterval: 0.5,
})
assert('非法冲突策略回落默认', normalizeSettings({ conflictStrategy: 'nuke' }).conflictStrategy, 'skip')

// --- 旧字段名迁移（旧的 SettingsView 写的是 defaultTemplate） ---
assert('旧字段 defaultTemplate 被迁移', normalizeSettings({ defaultTemplate: 'plex' }).defaultTemplateId, 'plex')
assert('新字段优先于旧字段', normalizeSettings({ defaultTemplate: 'plex', defaultTemplateId: 'emby_standard' }).defaultTemplateId, 'emby_standard')
assert('两者都没有时用默认', normalizeSettings({}).defaultTemplateId, 'emby_standard')

// --- 完全非法输入 ---
assert('null 输入返回全默认', normalizeSettings(null), defaultSettings())
assert('字符串输入返回全默认', normalizeSettings('nonsense'), defaultSettings())
assert('数组输入返回全默认', normalizeSettings([1, 2, 3]), defaultSettings())

// --- Review Focus 3：localStorage 不可用（隐私模式） ---
assert('storage 为 null 时返回全默认', readSettings(null), defaultSettings())

// --- 读盘：键不存在 ---
assert('键不存在时返回全默认', readSettings(fakeStorage()), defaultSettings())

// --- 读盘：JSON 损坏 ---
assert('JSON 损坏时返回全默认', readSettings(fakeStorage({ [SETTINGS_KEY]: '{不好' })), defaultSettings())

// --- 读盘：正常往返 ---
const storage = fakeStorage()
writeSettings(storage, { ...defaultSettings(), episodePadDigits: 3, conflictStrategy: 'abort' })
assert('写盘后读回补零位数', readSettings(storage).episodePadDigits, 3)
assert('写盘后读回冲突策略', readSettings(storage).conflictStrategy, 'abort')

// --- 写盘失败不能抛（存储配额满 / 只读） ---
const throwingStorage = {
  getItem: () => null,
  setItem: () => { throw new Error('QuotaExceededError') },
}
writeSettings(throwingStorage, defaultSettings())
console.log('PASS 写盘抛异常时被吞掉，不冒泡')

// --- 读盘时 getItem 抛异常也要托住 ---
const throwingRead = {
  getItem: () => { throw new Error('SecurityError') },
  setItem: () => {},
}
assert('getItem 抛异常时返回全默认', readSettings(throwingRead), defaultSettings())

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
```

- [ ] **Step 2: 运行断言确认失败**

```bash
cd frontend && node scripts/check-settings-schema.mjs
```

预期：抛 `SyntaxError` 或 `TypeError`（`defaultSettings is not a function`），退出码非 0。**这一步的作用是证明断言脚本真的会因为实现缺失而失败**，而不是一个永远打印 PASS 的空壳。

- [ ] **Step 3: 实现 `frontend/src/stores/settingsSchema.js`**

```js
// 设置的默认值、归一化与读写。刻意零依赖：不 import vue / pinia / 任何东西，
// 这样 node 可以直接 import 它跑断言（本项目没有前端测试设施，见 spec §17 遗留 3）。

export const SETTINGS_KEY = 'episode-renamer:settings'

const CONFLICT_STRATEGIES = ['skip', 'abort', 'overwrite', 'rename_dup']

// 与后端 app/core/template.py 的 PAD_MIN / PAD_MAX 一致。
// 两侧区间不同会让「界面显示 0 而实际补零 1 位」这种不一致出现。
const PAD_MIN = 1
const PAD_MAX = 6

export function defaultSettings() {
  return {
    defaultTemplateId: 'emby_standard',
    episodePadDigits: 2,
    seasonPadDigits: 2,
    conflictStrategy: 'skip',
    openlist: {
      serverUrl: '',
      concurrency: 3,
      requestInterval: 0.5,
    },
  }
}

function clampNumber(value, min, max, fallback, integer = false) {
  // null / undefined / '' 视为「未设置」，回落默认值。
  // AppInput 在 type="number" 下清空输入框会 emit null —— 若把它当 0，
  // 后端会钳到 1，界面却显示 0，两侧不一致。
  if (value === null || value === undefined || value === '') return fallback
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  const truncated = integer ? Math.trunc(n) : n
  return Math.min(max, Math.max(min, truncated))
}

function asString(value, fallback) {
  return typeof value === 'string' ? value : fallback
}

export function normalizeSettings(raw) {
  const def = defaultSettings()
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return def

  const openlist = (raw.openlist && typeof raw.openlist === 'object' && !Array.isArray(raw.openlist))
    ? raw.openlist
    : {}

  // defaultTemplate 是第一版的字段名。这里读一次做迁移，否则升级后
  // 用户已保存的默认模板会被静默丢掉、退回 emby_standard。
  const templateId = typeof raw.defaultTemplateId === 'string'
    ? raw.defaultTemplateId
    : (typeof raw.defaultTemplate === 'string' ? raw.defaultTemplate : def.defaultTemplateId)

  return {
    defaultTemplateId: templateId,
    episodePadDigits: clampNumber(raw.episodePadDigits, PAD_MIN, PAD_MAX, def.episodePadDigits, true),
    seasonPadDigits: clampNumber(raw.seasonPadDigits, PAD_MIN, PAD_MAX, def.seasonPadDigits, true),
    conflictStrategy: CONFLICT_STRATEGIES.includes(raw.conflictStrategy)
      ? raw.conflictStrategy
      : def.conflictStrategy,
    openlist: {
      serverUrl: asString(openlist.serverUrl, def.openlist.serverUrl),
      concurrency: clampNumber(openlist.concurrency, 1, 10, def.openlist.concurrency, true),
      requestInterval: clampNumber(openlist.requestInterval, 0.1, 5, def.openlist.requestInterval),
    },
  }
}

export function readSettings(storage) {
  // storage 为 null（隐私模式 / 存储被禁用）时退化为纯内存态，不阻塞启动。
  if (!storage) return defaultSettings()
  try {
    const raw = storage.getItem(SETTINGS_KEY)
    if (!raw) return defaultSettings()
    return normalizeSettings(JSON.parse(raw))
  } catch {
    // JSON 损坏、getItem 抛异常（SecurityError）都走这里
    return defaultSettings()
  }
}

export function writeSettings(storage, data) {
  if (!storage) return
  try {
    storage.setItem(SETTINGS_KEY, JSON.stringify(data))
  } catch {
    // 配额满 / 只读存储。设置不持久化不应让保存按钮崩掉。
  }
}
```

- [ ] **Step 4: 运行断言确认全部通过**

```bash
cd frontend && node scripts/check-settings-schema.mjs
```

预期：全部 `PASS`，最后一行 `全部通过`，退出码 `0`。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/stores/settingsSchema.js frontend/scripts/check-settings-schema.mjs
git commit -m "feat(frontend): 新增设置 schema 纯函数模块与 node 断言脚本"
```

---

### Task 2: `stores/settings.js` + `main.js` 启动加载

**Files:**
- Create: `frontend/src/stores/settings.js`
- Modify: `frontend/src/main.js`

**Interfaces:**
- Consumes: `settingsSchema.js` 的 `SETTINGS_KEY` / `defaultSettings` / `normalizeSettings` / `readSettings` / `writeSettings`（Task 1）
- Produces: `useSettingsStore()`：
  ```js
  // state（ref / reactive）
  defaultTemplateId      // ref<string>
  episodePadDigits       // ref<number>
  seasonPadDigits        // ref<number>
  conflictStrategy       // ref<string>
  openlist               // reactive<{ serverUrl, concurrency, requestInterval }>

  // actions
  load()        // 从 localStorage 读入并归一化（必须在 app.mount 之前调用）
  save()        // 把当前值写进 localStorage
  apply(data)   // 用一份（可能残缺的）普通对象覆盖当前值，逐字段归一化
  toObject()    // 返回一份普通对象快照，供 dirty 比较与持久化
  storageAvailable // ref<boolean>，false 表示退化为纯内存态
  ```
- 第三期 Task 3（SettingsView）、Task 4（workspace 接线）、Task 8（补零位数带参）全部依赖此契约

- [ ] **Step 1: 创建 `frontend/src/stores/settings.js`**

```js
import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'

import {
  defaultSettings,
  normalizeSettings,
  readSettings,
  writeSettings,
} from './settingsSchema'

function safeStorage() {
  // 隐私模式 / 禁用站点数据时，访问 localStorage 会抛 SecurityError。
  // 探测一次，失败就返回 null（纯内存态），绝不让它阻塞应用启动。
  try {
    const probe = '__episode_renamer_probe__'
    window.localStorage.setItem(probe, '1')
    window.localStorage.removeItem(probe)
    return window.localStorage
  } catch {
    return null
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const storage = safeStorage()
  const storageAvailable = ref(storage !== null)
  const initial = defaultSettings()

  // 初值用默认值，真正的读盘在 load() 里 —— 由 main.js 在挂载前调用。
  // 这样「什么时候读盘」是显式的，而不是藏在 store 创建的副作用里。
  const defaultTemplateId = ref(initial.defaultTemplateId)
  const episodePadDigits = ref(initial.episodePadDigits)
  const seasonPadDigits = ref(initial.seasonPadDigits)
  const conflictStrategy = ref(initial.conflictStrategy)
  const openlist = reactive({ ...initial.openlist })

  function apply(data) {
    const next = normalizeSettings(data)
    defaultTemplateId.value = next.defaultTemplateId
    episodePadDigits.value = next.episodePadDigits
    seasonPadDigits.value = next.seasonPadDigits
    conflictStrategy.value = next.conflictStrategy
    openlist.serverUrl = next.openlist.serverUrl
    openlist.concurrency = next.openlist.concurrency
    openlist.requestInterval = next.openlist.requestInterval
  }

  function toObject() {
    return {
      defaultTemplateId: defaultTemplateId.value,
      episodePadDigits: episodePadDigits.value,
      seasonPadDigits: seasonPadDigits.value,
      conflictStrategy: conflictStrategy.value,
      openlist: { ...openlist },
    }
  }

  function load() {
    apply(readSettings(storage))
  }

  function save() {
    writeSettings(storage, toObject())
  }

  return {
    defaultTemplateId, episodePadDigits, seasonPadDigits, conflictStrategy, openlist,
    storageAvailable,
    load, save, apply, toObject,
  }
})
```

- [ ] **Step 2: `main.js` 在挂载前加载设置**

```js
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'

import './style.css'

import App from './App.vue'
import router from './router'
import { useSettingsStore } from './stores/settings'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 必须在 mount 之前：任何组件读到设置之前，持久化的值必须已经就位。
// 漏掉这一行不会报错，只会让所有设置静默回到默认值 —— 见 Review Focus 2。
useSettingsStore().load()

app.mount('#app')
```

- [ ] **Step 3: 构建并验证设置真的会持久化与恢复**

```bash
cd frontend && npm run build && npm run dev
```

打开 `http://localhost:5173/`，在 Console 里执行：

```js
// 手动写入一条非默认设置，模拟「用户上次保存过的值」
localStorage.setItem('episode-renamer:settings', JSON.stringify({
  defaultTemplateId: 'plex',
  episodePadDigits: 4,
  seasonPadDigits: 1,
  conflictStrategy: 'abort',
  openlist: { serverUrl: 'http://demo:5244', concurrency: 7, requestInterval: 1.5 },
}))
location.reload()
```

刷新后在 Console 里执行：

```js
JSON.parse(localStorage.getItem('episode-renamer:settings'))
```

预期：数据原样保留（说明没有被别的地方用默认值覆写）。

再执行 `location.reload()`，重复确认 —— 若每次刷新后 `episodePadDigits` 都变回 2，说明 `load()` 没被调用或调用时机在挂载之后。

- [ ] **Step 4: 验证 `localStorage` 不可用时应用照常启动**

在 Console 里执行下面这段，它会让 `localStorage` 的读写**全部抛异常**，然后重新加载 store（新建一个 Pinia 实例）：

```js
// 模拟隐私模式：让 localStorage 的所有方法抛异常
const original = Object.getOwnPropertyDescriptor(window, 'localStorage')
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  get() { throw new DOMException('Access denied', 'SecurityError') },
})
location.reload()
```

加载完成后，**先恢复**（否则后续走查都会受影响）：

```js
Object.defineProperty(window, 'localStorage', original)
```

预期（`location.reload()` 之后）：
- 页面**正常渲染**，顶栏、左栏、工作区、底栏都在
- Console **没有**未捕获的异常
- 应用按默认设置运行（补零位数 2、冲突策略「跳过」）

**注意**：`Object.defineProperty` 的那次覆盖在 `location.reload()` 后即失效（页面重新加载，JS 环境重置）。所以真实操作是：先在 Console 里执行覆盖 → **不刷新**，观察应用是否仍正常；然后再手写一个会抛异常的 `window.localStorage` 需要刷新才生效 —— 两者不能同时满足。

因此这一步的**可靠做法**是用 DevTools 的站点数据设置：Chrome → Settings → Privacy and security → Site settings → 找到 `localhost:5173` → 把「Site data」设为 Blocked → 刷新页面。

预期同上：页面正常渲染、无未捕获异常、按默认值运行。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/stores/settings.js frontend/src/main.js
git commit -m "feat(frontend): 新增 settings store, 启动前加载持久化设置"
```

---

### Task 3: `SettingsView` 改用 store 与原语

重写设置页：接入 `settingsStore`，改用 `AppPanel` / `AppInput` / `AppSelect` / `AppButton`，**7 处手写输入框样式清零**。保留原有的「草稿 + 保存 + 重置 + dirty 提示」交互语义。

**Files:**
- Modify: `frontend/src/views/SettingsView.vue`（整文件重写）

**Interfaces:**
- Consumes: `useSettingsStore()`（Task 2）；`AppPanel` / `AppInput` / `AppSelect` / `AppButton`（第一期）；`getPresets`（既有 api）
- Produces: 无新接口

- [ ] **Step 1: 重写 `frontend/src/views/SettingsView.vue`**

```vue
<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto flex max-w-[680px] flex-col gap-4 p-6">
      <AppPanel title="通用设置">
        <div class="flex flex-col gap-4">
          <AppSelect v-model="draft.defaultTemplateId" label="默认模板">
            <option value="">跟随系统</option>
            <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
          </AppSelect>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <AppInput
              v-model="draft.episodePadDigits"
              type="number"
              label="集数补零位数"
              :min="1"
              :max="6"
              :error="episodePadError"
              hint="1–6 位，即 {episode_padded} 的位数"
            />
            <AppInput
              v-model="draft.seasonPadDigits"
              type="number"
              label="季数补零位数"
              :min="1"
              :max="6"
              :error="seasonPadError"
              hint="1–6 位，即 {season_padded} 的位数"
            />
          </div>

          <AppSelect v-model="draft.conflictStrategy" label="冲突默认策略">
            <option label="跳过" value="skip" />
            <option label="中止" value="abort" />
            <option label="覆盖" value="overwrite" />
            <option label="自动编号" value="rename_dup" />
          </AppSelect>
        </div>
      </AppPanel>

      <AppPanel title="OpenList 设置">
        <div class="flex flex-col gap-4">
          <AppInput
            v-model="draft.openlist.serverUrl"
            label="默认服务器地址"
            placeholder="http://localhost:5244"
          />
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <AppInput
              v-model="draft.openlist.concurrency"
              type="number"
              label="最大并发请求"
              :min="1"
              :max="10"
            />
            <AppInput
              v-model="draft.openlist.requestInterval"
              type="number"
              label="请求间隔 (秒)"
              :min="0.1"
              :max="5"
              :step="0.1"
            />
          </div>

          <div
            class="flex items-start gap-2 rounded-[8px] bg-sunken px-3 py-2.5 text-[12px] text-ink-2"
          >
            <Info class="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <p>
              这两项当前由**服务端**的 <code class="font-mono">openlist_max_concurrent</code> 与
              <code class="font-mono">openlist_request_interval</code> 决定。
              此处保存的值会被保留，但尚未下发到后端。
            </p>
          </div>
        </div>
      </AppPanel>

      <AppPanel title="说明">
        <div class="flex flex-col gap-2 text-[13px] leading-[1.8] text-ink-2">
          <p><strong class="text-ink">本地模式:</strong> 直接操作本机磁盘文件，支持撤销（通过 SQLite 日志）</p>
          <p><strong class="text-ink">OpenList 云盘模式:</strong> 通过 OpenList API 操作云盘文件，支持 115、阿里云盘、百度云盘等数十种云存储</p>
          <p>
            <strong class="text-ink">Emby/Jellyfin 规范:</strong> 建议使用 "Emby 标准" 预设模板，格式为
            <code class="rounded-[4px] bg-sunken px-1.5 py-0.5 font-mono text-[12px] text-ink">剧名 - SxxExx.mkv</code>
          </p>
          <p><strong class="text-ink">番剧注意:</strong> 番剧通常没有季数，会使用默认季数 1；支持父目录智能推断</p>
        </div>
      </AppPanel>

      <div v-if="!settingsStore.storageAvailable" class="text-[12px] text-warn">
        当前浏览器禁用了站点数据存储，设置只在本次会话内有效。
      </div>

      <div class="flex items-center justify-end gap-3">
        <span v-if="savedFlash" class="text-[12px] text-ink-2">{{ savedFlash }}</span>
        <AppButton variant="secondary" :disabled="!dirty" @click="reset">
          <RotateCcw class="h-4 w-4" aria-hidden="true" />
          重置
        </AppButton>
        <AppButton variant="primary" :disabled="!dirty" :loading="saving" @click="save">
          <Save class="h-4 w-4" aria-hidden="true" />
          {{ saving ? '保存中…' : '保存设置' }}
        </AppButton>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Info, RotateCcw, Save } from 'lucide-vue-next'

import { getPresets } from '../api/template'
import { useSettingsStore } from '../stores/settings'

import AppPanel from '../components/ui/AppPanel.vue'
import AppButton from '../components/ui/AppButton.vue'
import AppInput from '../components/ui/AppInput.vue'
import AppSelect from '../components/ui/AppSelect.vue'

const settingsStore = useSettingsStore()

const presets = ref([])
// 草稿语义：改动先落在 draft，点「保存设置」才写回 store 并落盘。
// 这样改坏了可以直接「重置」，也不会在没保存的情况下影响工作区（Review Focus 5）。
const draft = reactive(settingsStore.toObject())
const saving = ref(false)
const savedFlash = ref('')

const dirty = computed(() => JSON.stringify(draft) !== JSON.stringify(settingsStore.toObject()))

// 补零位数的越界提示（spec §10：表单错误内联于控件下方，不用 Toast）。
//
// 保存时 `settingsSchema.normalizeSettings` 会把越界值钳到 [1, 6]，与后端
// `PadConfig` 一致 —— 但**钳制是静默的**：用户输入 99、点保存、回来后看到 6，
// 中间没有任何解释。这个 error 就是把那次静默钳制说出来。
//
// 留空不算错误（视为「未设置」，回落默认值 2），所以空值返回空字符串。
function padRangeError(value) {
  if (value === null || value === undefined || value === '') return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return '请输入数字'
  if (n < 1 || n > 6) return '需在 1 到 6 之间，保存时会按就近边界处理'
  return ''
}

const episodePadError = computed(() => padRangeError(draft.episodePadDigits))
const seasonPadError = computed(() => padRangeError(draft.seasonPadDigits))

async function save() {
  if (!dirty.value) return
  saving.value = true
  try {
    settingsStore.apply(draft)
    settingsStore.save()
    Object.assign(draft, settingsStore.toObject())
    savedFlash.value = '设置已保存'
    setTimeout(() => { savedFlash.value = '' }, 1500)
  } finally {
    saving.value = false
  }
}

function reset() {
  Object.assign(draft, settingsStore.toObject())
}

onMounted(async () => {
  const res = await getPresets()
  if (res.data?.data) presets.value = res.data.data
})
</script>
```

重写后的文件**没有 `<style scoped>` 块**（原来那个 `fadeOut` keyframe 已由普通的文字提示替代 —— 无限/一次性 CSS 动画不在 spec §11 的动效表里）。

**注意 markdown 语法不要漏**：上面 `OpenList 设置` 面板里那两处 `**服务端**` 是**要原样写进 Vue 模板的字面文本**吗？不是 —— Vue 模板不解析 markdown。请写成：

```html
              这两项当前由<strong class="text-ink">服务端</strong>的
```

即把 `**服务端**` 替换为 `<strong class="text-ink">服务端</strong>`。

- [ ] **Step 2: 构建并确认 7 处手写样式清零**

```bash
cd frontend && npm run build && \
  echo "--- 剩余手写输入框样式处数（应为 3，全部在 FileTable）---" && \
  grep -rn "focus:border-primary focus:ring-2 focus:ring-primary/20" src/ && \
  grep -rn "focus:border-primary focus:ring-2 focus:ring-primary/20" src/ | wc -l
```

预期：`grep` 只列出 `components/FileTable.vue` 的 3 行，计数为 **3**。

- [ ] **Step 3: 走查设置页**

```bash
cd frontend && npm run dev
```

| # | 操作 | 预期 |
|---|---|---|
| 1 | 打开 `/#/settings` | 三个面板：「通用设置」「OpenList 设置」「说明」；面板是 `rounded-[12px]` + 1px 发丝线，**无阴影** |
| 2 | 看每个字段 | `label` 都在控件的**上方**（不是左侧），控件下方有 `hint` 灰色辅助文字 |
| 3 | 看补零位数两个输入框 | `min=1` `max=6`；点上下箭头不会超过 6 或低于 1 |
| 4 | 看 OpenList 的并发 / 间隔 | 下方有一条浅灰说明条，写清「这两项由服务端决定，尚未下发到后端」 |
| 5 | 改任意一个字段 | 「重置」「保存设置」按钮**解禁** |
| 6 | 点「重置」 | 字段回到修改前的值；两个按钮重新置灰 |
| 7 | 改「集数补零位数」为 3 → 点「保存设置」 | 短暂显示「保存设置」loading，然后出现「设置已保存」，约 1.5 秒后消失 |
| 8 | 刷新页面 | 集数补零位数**仍是 3**（已持久化） |
| 9 | 键盘 Tab 走一遍 | 焦点顺序合理，每个控件都有清晰的聚焦环 |
| 10 | 看整页有没有 `rounded-full` / 阴影 | 没有 |
| 11 | **Review Focus 5**：改「集数补零位数」为 5 → **不点保存** → 回工作区 | 工作区的预览位数**不变**（仍是已保存的值） |
| 12 | 在「集数补零位数」里输入 `99` | 输入框下方原本的灰色 `hint` **换成**红色错误文字「需在 1 到 6 之间，保存时会按就近边界处理」；输入框边框变红（`error` 优先于 `hint`） |
| 13 | 把它改回 `3` | 红色错误消失，灰色 `hint` 回来 |
| 14 | 输入 `-1` 再点保存 → 刷新 | 保存成功；刷新后该字段显示 **1**（钳制生效），且请求体里发的是 1 |
| 15 | 清空「集数补零位数」→ 点保存 → 刷新 | 该字段显示 **2**（留空回落默认值，不是 0、不是空） |

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/SettingsView.vue
git commit -m "refactor(frontend): SettingsView 接入 settings store 并改用 UI 原语"
```

---

### Task 4: 工作区接入设置（默认模板 + 冲突策略初值）

把设置页的两项接到工作区上（spec §12.2 的改动点）：默认模板决定工作区打开时用哪个预设，冲突默认策略决定底栏下拉的初值。

**Files:**
- Modify: `frontend/src/stores/workspace.js`

**Interfaces:**
- Consumes: `useSettingsStore()`（Task 2）
- Produces: 无新接口；`initialize()` 的行为变化：预设选择优先取 `settingsStore.defaultTemplateId`，冲突策略初值取 `settingsStore.conflictStrategy`

- [ ] **Step 1: 在 `workspace.js` 里接入 settings**

在 import 区加：

```js
import { useSettingsStore } from './settings'
```

在 store setup 顶部（其余 `use*Store()` 旁边）加：

```js
  const settingsStore = useSettingsStore()
```

把 `initialize()` 替换为：

```js
  async function initialize() {
    // 冲突策略：用设置页保存的默认值作初值。用户之后在底栏改的是本次会话的
    // 临时值，不回写设置（spec §12.2）。
    conflictStrategy.value = settingsStore.conflictStrategy

    const res = await getPresets()
    const presets = res.data?.data || []
    if (presets.length) {
      tplStore.presets = presets
      // 优先用设置页指定的默认模板；它失效时（预设被删或改名）退回模板 store
      // 自带的默认，而不是留下一个空的 currentTemplate。
      const wanted = settingsStore.defaultTemplateId
      const preset =
        presets.find(p => p.id === wanted) ||
        presets.find(p => p.id === tplStore.currentPresetId)
      if (preset) tplStore.setPreset(preset)
    }

    olForm.server_url = olStore.serverUrl || ''
    olForm.username = olStore.username || ''

    const statusRes = await apiOlStatus()
    if (statusRes.data?.connected) {
      olStore.setConnection(true, statusRes.data)
    }
  }
```

- [ ] **Step 2: 构建并验证设置真的影响工作区**

```bash
cd frontend && npm run build && npm run dev
```

后端也要起来（`cd backend && python run.py`）。

| # | 操作 | 预期 |
|---|---|---|
| 1 | `/#/settings` → 默认模板选「Plex 标准」（或任意非 Emby 的预设）→ 保存 | 出现「设置已保存」，刷新后仍是该预设 |
| 2 | 回工作区 `/#/` | 左栏「重命名模板」的**预设下拉显示刚选的预设**（不是 Emby 标准），模板输入框是对应的模板串 |
| 3 | `/#/settings` → 冲突默认策略选「覆盖」→ 保存 → 回工作区 | 底栏的冲突策略下拉显示「覆盖」 |
| 4 | 在工作区底栏把冲突策略改成「中止」→ 刷新页面 | 底栏回到「覆盖」（会话内改动不回写设置，符合 spec §12.2） |
| 5 | `/#/settings` → 默认模板选「跟随系统」（空值）→ 保存 → 回工作区 | 预设下拉回到模板 store 的默认预设，模板输入框**不是空的** |
| 6 | 在 Console 里 `localStorage.setItem('episode-renamer:settings', '{"defaultTemplateId":"不存在的id"}')` → 刷新 → 回工作区 | 预设下拉回落到默认预设，**无报错、无空白模板** |

- [ ] **Step 3: 提交**

```bash
git add frontend/src/stores/workspace.js
git commit -m "feat(frontend): 工作区接入默认模板与冲突策略设置"
```

---

### Task 5: `FileTable` 改用原语（3 处手写样式 + 最后一个 emoji 清零）

**Files:**
- Modify: `frontend/src/components/ui/AppInput.vue`（新增 `size` 与 `ariaLabel`）
- Modify: `frontend/src/components/ui/AppCheckbox.vue`（新增 `ariaLabel`）
- Modify: `frontend/src/components/FileTable.vue`

**Interfaces:**
- Consumes: `AppButton` / `AppInput` / `AppBadge` / `AppCheckbox`（第一期）；新 token
- Produces:
  ```js
  // AppInput 新增
  props: {
    size: 'sm' | 'md'          // default 'md'  sm = h-8 px-2.5 text-[13px]
    ariaLabel: String          // 无可见 label 时的无障碍名（表格行内用）
  }
  // AppCheckbox 新增
  props: { ariaLabel: String }
  ```
  `size="sm"` 是表格行内控件的需要：`md` 的 `h-9` 会让表格行高从 33px 涨到 37px，300 行的表格会明显变松。`ariaLabel` 与 `label` 的区别是前者不渲染可见文字 —— 表格单元格里没有空间放 label，但无障碍名不能省（`<input>` 没有名字时屏幕阅读器只会念「编辑框」）。

- [ ] **Step 1: 给 `AppInput` 加 `size` 与 `ariaLabel`**

编辑 `frontend/src/components/ui/AppInput.vue`。

在 `<script setup>` 里加两个 `SIZE_CLASSES` 常量与 `size` 计算：

```js
const SIZE_CLASSES = {
  sm: 'h-8 px-2.5',
  md: 'h-9 px-3',
}
```

在 `defineProps` 里加：

```js
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md'].includes(v),
  },
  ariaLabel: { type: String, default: '' },
```

把 `<input>` 的 `class` 拆成「固定部分 + 尺寸部分 + 条件部分」：

```html
      class="w-full rounded-[8px] border border-border-control bg-surface text-[13px] text-ink transition-colors duration-150 outline-none placeholder:text-ink-3 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35 disabled:opacity-45 disabled:cursor-not-allowed"
      :class="[SIZE_CLASSES[size], mono ? 'font-mono' : '', error ? 'border-danger' : '']"
```

并在 `<input>` 上补 `aria-label`：

```html
      :aria-label="ariaLabel || undefined"
```

- [ ] **Step 2: 给 `AppCheckbox` 加 `ariaLabel`**

编辑 `frontend/src/components/ui/AppCheckbox.vue`。

在 `defineProps` 里加：

```js
  ariaLabel: { type: String, default: '' },
```

在 `<input type="checkbox">` 上补：

```html
        :aria-label="ariaLabel || undefined"
```

- [ ] **Step 3: `FileTable` 改用原语**

编辑 `frontend/src/components/FileTable.vue`。`<script setup>` 改为：

```js
import { FileQuestion } from 'lucide-vue-next'

import AppButton from './ui/AppButton.vue'
import AppInput from './ui/AppInput.vue'
import AppBadge from './ui/AppBadge.vue'
import AppCheckbox from './ui/AppCheckbox.vue'

defineProps({
  filesStore: { type: Object, required: true },
  previewRows: { type: Array, default: () => [] },
  scannedInfo: Object,
  allSelected: Boolean,
  activeSource: String,
})
defineEmits([
  'preview-all', 'clear-all', 'toggle-all', 'select-row', 'update-row', 'quick-scan',
])
```

模板里逐处替换：

**（a）标题栏两个按钮 → `AppButton`**

```html
      <div class="flex shrink-0 items-center gap-2">
        <AppButton
          size="sm"
          variant="secondary"
          :disabled="!filesStore.files.length"
          @click="$emit('preview-all')"
        >
          预览
        </AppButton>
        <AppButton
          size="sm"
          variant="danger"
          :disabled="!filesStore.files.length"
          @click="$emit('clear-all')"
        >
          清空
        </AppButton>
      </div>
```

**（b）表头全选复选框 → `AppCheckbox`**

```html
            <th class="w-12 px-4 py-3 text-left font-semibold">
              <AppCheckbox
                :model-value="allSelected"
                aria-label="全选"
                @update:model-value="$emit('toggle-all', $event)"
              />
            </th>
```

**（c）行内复选框 → `AppCheckbox`**

```html
              <td class="px-4 py-2.5">
                <AppCheckbox
                  :model-value="row.selected"
                  :aria-label="`选择 ${row.filename}`"
                  @update:model-value="$emit('select-row', { row, val: $event })"
                />
              </td>
```

**（d）三个行内输入框 → `AppInput`**

```html
              <td class="hidden px-4 py-2.5 md:table-cell">
                <AppInput
                  v-model="row.show_name"
                  size="sm"
                  aria-label="解析剧名"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppInput
                  v-model.number="row.season"
                  size="sm"
                  type="number"
                  :min="1"
                  :max="30"
                  aria-label="季"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppInput
                  v-model.number="row.episode"
                  size="sm"
                  type="number"
                  :min="1"
                  :max="999"
                  aria-label="集"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
```

**（e）状态徽章 → `AppBadge`（同时清掉最后一个 emoji）**

```html
              <td class="px-4 py-2.5">
                <AppBadge :tone="row.needs_review ? 'warn' : 'neutral'">
                  <template #icon>
                    <AlertTriangle v-if="row.needs_review" class="h-3.5 w-3.5" aria-hidden="true" />
                    <Check v-else class="h-3.5 w-3.5" aria-hidden="true" />
                  </template>
                  {{ row.needs_review ? '待确认' : '已解析' }}
                </AppBadge>
              </td>
```

`AlertTriangle` 与 `Check` 需要一并 import：

```js
import { AlertTriangle, Check, FileQuestion } from 'lucide-vue-next'
```

**（f）空态按钮 → `AppButton`**

```html
                <AppButton
                  v-if="activeSource === 'local'"
                  variant="primary"
                  class="mt-2"
                  @click="$emit('quick-scan')"
                >
                  开始扫描
                </AppButton>
```

几处不是随手写的：

- **`AppInput` 上的 `@update:model-value` 触发 `update-row`**：`v-model="row.show_name"` 已经写回了行数据，`update-row` 只是把行数据同步进 `row.override`（供请求体使用）。换成组件后这个事件名从原生的 `@change` 变成了 `update:model-value`，**逐个控件都要改到**，漏一个的表现是「改了季号，试运行结果没跟着变」。
- **数字对齐必须在 `AppInput` 内部实现，不能靠调用点传 class**：`class="tabular-nums"` 传给 `AppInput` 会落在它的根 `<div>` 上（`AppInput` 没开 `inheritAttrs: false`），而 `font-variant-numeric` 必须落在真正渲染文字的 `<input>` 上才有效 —— 写在根 div 上**完全无效且不报错**。所以把 `tabular-nums` 写进 `AppInput` 在 `type === 'number'` 时的内部类：

  在 `AppInput.vue` 的 `:class` 数组里加：

  ```html
      :class="[SIZE_CLASSES[size], mono ? 'font-mono' : '', type === 'number' ? 'tabular-nums' : '', error ? 'border-danger' : '']"
  ```

  因此上面 `FileTable` 的两个数字框**都不要**写 `class="tabular-nums"` —— 数字框加等宽数字是无条件的正确选择（spec §6.4），放在原语内部比每个调用点都记一遍更可靠，也不会被漏掉。

- **表头 `text-ink-2`** 保持不变（spec §5.1 的硬约束）。

- [ ] **Step 4: 构建并确认 18 处清零**

```bash
cd frontend && npm run build && \
  echo "--- 手写输入框样式处数（必须为 0）---" && \
  grep -rn "focus:border-primary focus:ring-2 focus:ring-primary/20" src/ | wc -l && \
  echo "--- emoji 处数（必须为 0）---" && \
  grep -rn "🎬\|📁\|☁️\|⚠️\|✅" src/ | wc -l && \
  echo "--- shadow-sm 处数（必须为 0）---" && \
  grep -rn "shadow-sm" src/ | wc -l
```

预期：三个计数全部为 **0**。

若 `shadow-sm` 还有残留，说明第二、三期漏改了文件；逐行 `grep -rn "shadow-sm" src/` 定位并改为 `border border-line`（面板）或不加任何阴影。

- [ ] **Step 5: 走查表格**

```bash
cd frontend && npm run dev
```

| # | 操作 | 预期 |
|---|---|---|
| 1 | 扫描一个目录 | 「预览」「清空」是两个 `h-8` 圆角按钮；「清空」是**红色描边**（danger 变体） |
| 2 | 看状态列 | 「已解析」是**灰底深灰字 + 对勾图标**（不是绿色、不是 ✅ emoji）；「待确认」是浅黄底棕字 + 警告三角 |
| 3 | 看全表 | **没有任何 emoji** |
| 4 | 勾选表头复选框 | 所有行跟着勾选；复选框是**青绿底白勾**的方角样式 |
| 5 | 修改某行的「集」为 99 → 点「试运行」 | 结果里的新文件名按 99 生成（验证 `update-row` 事件确实接上了） |
| 6 | 修改某行「剧名」 | 同上，改完「新文件名」列立即重新计算 |
| 7 | 看季 / 集 / 行号三列 | 数字宽度对齐（`tabular-nums` 生效） |
| 8 | 键盘 Tab 进表格 | 每一行的复选框与三个输入框都能聚焦，且有聚焦环 |
| 9 | 用读屏或查 DOM | 行内输入框有 `aria-label`（「解析剧名」「季」「集」），复选框有「选择 xxx.mkv」 |

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/ui/AppInput.vue frontend/src/components/ui/AppCheckbox.vue frontend/src/components/FileTable.vue
git commit -m "refactor(frontend): FileTable 改用 UI 原语与 AppBadge, 清掉最后的 emoji"
```

---

### Task 6: 三个对话框适配新 token 与原语

`ConfirmDialog` / `ResultDialog` / `BrowseDialog` 都还带着旧 token（`rounded-xl`、`shadow-2xl`、`bg-success-light`、`text-primary`），且 `BrowseDialog` 的目录项是 `<div>`，键盘无法操作（spec §8.3 要求补键盘导航）。

**Files:**
- Modify: `frontend/src/components/ConfirmDialog.vue`
- Modify: `frontend/src/components/ResultDialog.vue`
- Modify: `frontend/src/components/BrowseDialog.vue`

**Interfaces:**
- Consumes: `AppModal`（第一期 Task 5，已支持 `title` / `zIndex` / `closeOnOverlay`）、`AppButton` / `AppBadge`（第一期）
- Produces: 三个组件的 props / emits **全部保持不变**；卡片样式改为 `rounded-[12px] shadow-overlay`

**本步必须一并修掉一个既有的、用户可见的潜伏 bug（第一期 F2-T1 评审发现）**：`AppModal` 在按 `Esc` 或点遮罩时会 emit `update:modelValue` 且值为 `false`；`ConfirmDialog` 目前把它原样转发给父组件，父组件只把 `ws.confirm.open` 置为 false，**从不调用 `resolveConfirm`** —— 于是 `askConfirm()` 返回的 promise **永远悬空**，`clearAll()` 的 `.then()` 再也不会执行：用户点「清空」后在确认框上按 Esc，清空会**静默地什么都不做**。

修法：在 `AppModal` 的 `@update:model-value` 处理里，把「值为假」当作用户取消，转发时补一次 `cancel`：

```html
  <AppModal
    :model-value="modelValue"
    title="确认执行"
    z-index="55"
    @update:model-value="onModalUpdate"
  >
```

```js
// AppModal 在 Esc / 点遮罩时会 emit(false)。那不是「确认」，必须让上层拿到 cancel，
// 否则 askConfirm() 的 promise 永远不 resolve，调用方的 .then() 静默不执行。
function onModalUpdate(value) {
  emit('update:modelValue', value)
  if (!value) emit('cancel')
}
```

`ResultDialog` 与 `BrowseDialog` 不需要这一步 —— 它们没有待 resolve 的 promise，关闭就是关闭。但 `BrowseDialog` 的 `confirm()` 仍要保证只在真正确认时 emit `confirm`。

- [ ] **Step 1: 重写 `frontend/src/components/ConfirmDialog.vue`**

```vue
<template>
  <AppModal
    :model-value="modelValue"
    title="确认执行"
    z-index="55"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="w-full max-w-[420px] overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex items-start gap-3.5 px-5 py-5">
        <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-warn-soft">
          <AlertTriangle class="h-4.5 w-4.5 text-warn" aria-hidden="true" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="text-[13px] leading-relaxed text-ink-2">{{ message }}</p>
        </div>
      </div>
      <div class="flex justify-end gap-2 border-t border-line bg-sunken px-5 py-3">
        <AppButton variant="secondary" @click="$emit('cancel')">取消</AppButton>
        <AppButton variant="primary" @click="$emit('ok')">确定</AppButton>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { AlertTriangle } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'

defineProps({
  modelValue: Boolean,
  message: { type: String, default: '' },
})
defineEmits(['update:modelValue', 'ok', 'cancel'])
</script>
```

改动点：`rounded-full` 的图标底 → `rounded-[8px]`（spec §5.3 取消 `rounded-full`）；`shadow-2xl` → `shadow-overlay`；`rounded-xl` → `rounded-[12px]`；`bg-warning-light`/`text-warning` → `bg-warn-soft`/`text-warn`；可见标题「确认执行」删掉（`AppModal` 的 `title` 已提供无障碍名，视觉上由消息本身承担）；两个按钮换成 `AppButton`。

注意 `title="确认执行"` 只渲染成屏幕阅读器可见的 `sr-only` `<h2>`，**视觉上不再重复出现**。

- [ ] **Step 2: 重写 `frontend/src/components/ResultDialog.vue`**

```vue
<template>
  <AppModal
    :model-value="modelValue"
    title="重命名结果"
    z-index="50"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="flex max-h-[85vh] w-full max-w-[700px] flex-col overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 class="text-[15px] font-semibold text-ink">重命名结果</h2>
        <button
          type="button"
          aria-label="关闭"
          class="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
          @click="$emit('update:modelValue', false)"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-5">
        <template v-if="result">
          <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">数据源</div>
              <div class="mt-1 text-[13px] font-semibold text-ink">{{ result.source }}</div>
            </div>
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">成功</div>
              <div class="mt-1 text-[13px] font-semibold tabular-nums text-ink">{{ result.executed }}</div>
            </div>
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">跳过</div>
              <div class="mt-1 text-[13px] font-semibold tabular-nums text-ink">{{ result.skipped }}</div>
            </div>
            <div
              class="rounded-[8px] p-3 text-center"
              :class="result.failed ? 'bg-danger-soft' : 'bg-sunken'"
            >
              <div class="text-[11px]" :class="result.failed ? 'text-danger' : 'text-ink-3'">失败</div>
              <div
                class="mt-1 text-[13px] font-semibold tabular-nums"
                :class="result.failed ? 'text-danger' : 'text-ink'"
              >{{ result.failed }}</div>
            </div>
          </div>

          <table v-if="result.results?.length" class="w-full text-[12px]">
            <thead class="bg-sunken">
              <tr class="text-ink-2">
                <th class="px-3 py-2 text-left font-semibold">原文件名</th>
                <th class="px-3 py-2 text-left font-semibold">新文件名</th>
                <th class="w-[100px] px-3 py-2 text-left font-semibold">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in result.results" :key="i" class="border-t border-line">
                <td class="max-w-[220px] truncate px-3 py-2 text-ink">{{ r.original_filename }}</td>
                <td class="max-w-[220px] truncate px-3 py-2 text-ink">{{ r.new_filename }}</td>
                <td class="px-3 py-2">
                  <AppBadge :tone="r.success ? 'neutral' : 'danger'">
                    <template #icon>
                      <AlertTriangle v-if="!r.success" class="h-3.5 w-3.5" aria-hidden="true" />
                      <Check v-else class="h-3.5 w-3.5" aria-hidden="true" />
                    </template>
                    {{ r.status }}
                  </AppBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>

      <div class="flex shrink-0 justify-end border-t border-line px-5 py-3">
        <AppButton variant="secondary" @click="$emit('update:modelValue', false)">关闭</AppButton>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { AlertTriangle, Check, X } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'
import AppBadge from './ui/AppBadge.vue'

defineProps({
  modelValue: Boolean,
  result: { type: Object, default: null },
})
defineEmits(['update:modelValue'])
</script>
```

改动点：**「成功」计数从绿底换成中性底**（spec §5.2：绿色只留给强调色；这里用 `bg-sunken` + `text-ink` 表达一个中性的数字，失败才用 `danger`）；逐条状态用 `AppBadge`（spec §10：「执行失败另在 `ResultDialog` 内以 danger 徽章逐条列出」）；卡片 `rounded-[12px] shadow-overlay`；关闭按钮补 `aria-label`。

内容区加了 `min-h-0 flex-1 overflow-y-auto` —— 卡片是 `flex flex-col` 且外层有 `max-h-[85vh]`，只有加上 `min-h-0` 内容区才会在超出时滚动，而不是把卡片撑破（与主布局同一个坑）。

- [ ] **Step 3: 重写 `frontend/src/components/BrowseDialog.vue` 的模板与键盘导航**

`<template>` 替换为：

```vue
<template>
  <AppModal
    :model-value="modelValue"
    title="选择目录"
    z-index="50"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="w-full max-w-[520px] overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 class="text-[15px] font-semibold text-ink">选择目录</h2>
        <button
          type="button"
          aria-label="关闭"
          class="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
          @click="$emit('update:modelValue', false)"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div class="p-5">
        <div class="mb-4 flex items-center gap-2 border-b border-line pb-3">
          <AppButton
            size="sm"
            variant="secondary"
            :disabled="!currentPath || currentPath === rootPath"
            @click="goParent"
          >
            上级
          </AppButton>
          <div class="flex min-w-0 flex-1 items-center gap-1 overflow-hidden text-[12px] text-ink-3">
            <template v-for="(seg, idx) in breadcrumbs" :key="idx">
              <button
                type="button"
                class="truncate rounded-[4px] transition-colors duration-150 hover:text-accent focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
                @click="navigate(seg.path)"
              >{{ seg.name }}</button>
              <ChevronRight v-if="idx < breadcrumbs.length - 1" class="h-3 w-3 shrink-0 text-ink-3" aria-hidden="true" />
            </template>
          </div>
        </div>

        <div class="mb-3 flex min-w-0 items-center gap-2 px-1 text-[12px]">
          <span class="shrink-0 text-ink-3">当前目录:</span>
          <span class="truncate text-ink">{{ currentPath }}</span>
          <AppBadge v-if="!selected" tone="accent">确定将选择此目录</AppBadge>
          <AppBadge v-else tone="neutral">已选中: {{ selected.name }}</AppBadge>
        </div>

        <div v-if="loading" class="py-12 text-center text-[13px] text-ink-3">加载中…</div>
        <div v-else-if="!dirs.length" class="py-12 text-center text-[13px] text-ink-3">此目录无子目录</div>
        <div
          v-else
          ref="listRef"
          class="max-h-[280px] overflow-auto"
          @keydown="onListKeydown"
        >
          <button
            v-for="d in dirs"
            :key="d.path"
            type="button"
            class="flex w-full items-center gap-2.5 rounded-[8px] px-3.5 py-2.5 text-left transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
            :class="selected?.path === d.path
              ? 'bg-accent-soft text-accent'
              : 'text-ink hover:bg-sunken'"
            :aria-pressed="selected?.path === d.path"
            @click="selected = d"
            @dblclick="navigate(d.path)"
          >
            <Folder
              class="h-[18px] w-[18px] shrink-0"
              :class="selected?.path === d.path ? 'text-accent' : 'text-ink-3'"
              aria-hidden="true"
            />
            <span class="truncate text-[14px] font-medium">{{ d.name }}</span>
          </button>
        </div>
      </div>

      <div class="flex justify-end gap-2 border-t border-line px-5 py-3">
        <AppButton variant="secondary" @click="$emit('update:modelValue', false)">取消</AppButton>
        <AppButton variant="primary" :disabled="confirmDisabled" @click="confirm">确定选择</AppButton>
      </div>
    </div>
  </AppModal>
</template>
```

`<script setup>` 里补三处：import、`listRef`、`onListKeydown`。

```js
import { computed, ref, watch } from 'vue'
import { ChevronRight, Folder, X } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'
import AppBadge from './ui/AppBadge.vue'
import { browseLocalDirectory } from '../api/scanner'
import { openlistBrowse } from '../api/openlist'

const listRef = ref(null)

// 目录项是 <button>，天然可 Tab 聚焦并可用 Enter / Space 激活。
// 这里再补上方向键与 Home / End，让长目录不必按很多次 Tab
// （spec §8.3：BrowseDialog「补 aria 与键盘导航」）。
function onListKeydown(event) {
  const KEYS = ['ArrowDown', 'ArrowUp', 'Home', 'End']
  if (!KEYS.includes(event.key)) return
  const items = Array.from(listRef.value?.querySelectorAll('button') || [])
  if (!items.length) return
  event.preventDefault()
  const current = items.indexOf(document.activeElement)
  let next
  if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = items.length - 1
  else if (current === -1) next = 0
  else next = event.key === 'ArrowDown'
    ? Math.min(items.length - 1, current + 1)
    : Math.max(0, current - 1)
  items[next].focus()
}
```

其余逻辑（`load` / `navigate` / `goParent` / `confirm` / `breadcrumbs` / `confirmDisabled` / `watch`）**原样保留**。

改动点：目录路径从 `font-mono` 改成普通字体（spec §6.2：含中文的路径在等宽字体下会回退到非等宽字形，反而对不齐）；目录项 `<div>` → `<button>`；面包屑 `<span @click>` → `<button>`；`bg-primary-light`/`text-primary` → `bg-accent-soft`/`text-accent`；两个小标签换成 `AppBadge`；卡片 `rounded-[12px] shadow-overlay`；两处 `<AppButton>` 的 `size="sm"`。

- [ ] **Step 4: 构建并确认旧 token 已从三个对话框消失**

```bash
cd frontend && npm run build && \
  echo "--- 旧 token 类名残留（必须为 0）---" && \
  grep -rnE "rounded-(xl|2xl|lg|md|full)|shadow-(sm|lg|2xl)|bg-(primary|success|warning|error)|text-(primary|success|warning|error)|bg-surface-muted|border-border-strong" \
    src/components/ConfirmDialog.vue src/components/ResultDialog.vue src/components/BrowseDialog.vue src/components/FileTable.vue src/views/ | wc -l
```

预期：计数为 **0**。

- [ ] **Step 5: 走查三个对话框**

```bash
cd frontend && npm run dev
```

| # | 对话框 | 触发方式 | 预期 |
|---|---|---|---|
| 1 | `ConfirmDialog` | 表格「清空」 | 卡片 `rounded-[12px]` + 一层克制阴影；图标底是**方角**浅黄块（不是圆）；两个按钮是 `AppButton` 样式 |
| 2 | `ConfirmDialog` | 按 `Esc` | 关闭，焦点回到「清空」按钮 |
| 3 | `ResultDialog` | 点「试运行」 | 四个统计块：数据源 / 成功 / 跳过都是**灰底**，失败为 0 时也是灰底 |
| 4 | `ResultDialog` | 制造一次失败（对只读目录执行） | 「失败」块变浅红底红字，计数为红；对应行状态是**红底红字徽章** |
| 5 | `ResultDialog` | 结果行超过一屏 | **内容区**滚动，卡片标题栏与底部「关闭」按钮**固定不动** |
| 6 | `BrowseDialog` | 点扫描源的「浏览」 | 卡片 `rounded-[12px]`；「当前目录」后面的路径是**普通字体**（不是等宽） |
| 7 | `BrowseDialog` | 点一个目录项 | 背景变浅青绿、文字变深青绿，右侧显示「已选中: xxx」徽章 |
| 8 | `BrowseDialog` | 用 `Tab` 进入目录列表 → 按 `↓` `↑` | 焦点在目录项之间移动，不跑出列表 |
| 9 | `BrowseDialog` | 聚焦某个目录项 → 按 `Enter` | 选中该目录（`aria-pressed` 变 true）；按两次（双击）进入该目录 |
| 10 | `BrowseDialog` | 按 `Esc` | 关闭，焦点回到「浏览」按钮 |
| 11 | 全部 | 快速连按 `Esc` 三次 | 无报错，页面正常 |

第 8 项的 `↓`/`↑` 是本任务新加的键盘导航。若不起作用，检查 `@keydown="onListKeydown"` 是否挂在**包含这些 button 的容器**上（事件冒泡），以及 `listRef` 是否绑到了同一个元素。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/ConfirmDialog.vue frontend/src/components/ResultDialog.vue frontend/src/components/BrowseDialog.vue
git commit -m "refactor(frontend): 三个对话框适配新 token 与原语, BrowseDialog 补键盘导航"
```

---

### Task 7: `Toast` 适配新 token 与语义

spec §10 要求成功用 `role="status"`、失败用 `role="alert"`；spec §5.2 要求不再用绿色表达成功。

**Files:**
- Modify: `frontend/src/components/Toast.vue`

**Interfaces:**
- Consumes: 新 token `surface` `line` `sunken` `ink` `ink-2` `warn` `warn-soft` `danger` `danger-soft` `shadow-overlay`
- Produces: props 不变（`show` / `type` / `msg`）；本期只补 `role`

- [ ] **Step 1: 重写 `frontend/src/components/Toast.vue`**

```vue
<template>
  <div
    v-if="show"
    :role="isAlert ? 'alert' : 'status'"
    :aria-live="isAlert ? 'assertive' : 'polite'"
    class="fixed top-4 right-4 z-[100] flex items-center gap-2 rounded-[8px] border px-3.5 py-2.5 text-[13px] font-medium shadow-overlay"
    :class="TONE_CLASSES[type] || TONE_CLASSES.info"
  >
    <AlertTriangle v-if="type === 'error' || type === 'warning'" class="h-4 w-4 shrink-0" aria-hidden="true" />
    <Check v-else class="h-4 w-4 shrink-0" aria-hidden="true" />
    <span class="max-w-[320px]">{{ msg }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { AlertTriangle, Check } from 'lucide-vue-next'

// 成功不再是绿色（spec §5.2：颜色只承担「强调」与「告警」两种职责）。
//
// 这不违反 toast 的最佳实践 —— 通行做法是「严重度要靠颜色、图标、文案三者中
// 至少两个来区分，不能只靠颜色」（WCAG 1.4.1 Use of Color）。这里的分配是：
//   · 图标：warning/error 用警告三角，success/info 用对勾 —— 有区分
//   · 文案：四种类型的文案本身不同 —— 有区分
//   · 底色：只有**需要用户注意**的 warning / error 上色 —— 这恰恰是最佳实践
//     里颜色的正确用途：把有限的色彩预算花在需要打断用户的地方。
// success 与 info 都是非可操作的确认，靠图标 + 文案足矣；给它们再上一次色
// 只会稀释 warning / error 的视觉优先级，并且会和作为强调色的深青绿打架。
const TONE_CLASSES = {
  success: 'border-line bg-surface text-ink-2',
  info: 'border-line bg-surface text-ink-2',
  warning: 'border-warn bg-warn-soft text-warn',
  error: 'border-danger bg-danger-soft text-danger',
}

const props = defineProps({
  show: Boolean,
  type: { type: String, default: 'info' },
  msg: { type: String, default: '' },
})

const isAlert = computed(() => props.type === 'error')
</script>

<style scoped>
/* Toast 进出 200ms（spec §11 的动效表）。 */
.toast-enter-active {
  transition: opacity 0.2s ease-out, transform 0.2s ease-out;
}
.toast-leave-active {
  transition: opacity 0.18s ease-in, transform 0.18s ease-in;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(12px);
}
</style>
```

改动点：

- `role` 按类型动态绑定：错误用 `alert` + `assertive`（打断当前朗读），其余用 `status` + `polite`（排队朗读）。这是 spec §10 的原文要求。
- 绿色 `bg-success-light text-success` 换成中性 `bg-surface text-ink-2` + 对勾。
- `rounded-lg` → `rounded-[8px]`；`shadow-lg` → `shadow-overlay`。
- 动画从「从右侧 120% 滑入」改成「淡入 + 12px 位移」：120% 的横滑是营销页的语汇，且位移距离过大时在秒级停留的提示上会显得吵（spec §11 的 MOTION_INTENSITY 是 3）。
- 外层从 `<Transition>` 换成 `v-if` + CSS 类：`Transition` 需要元素始终存在才能播放离场动画，而父组件（`HomeView`）在 Task 5 之后传的是 `v-if="ws.toast.show"`。**保持一致**：现在 `HomeView` 里写的是 `<Toast v-if="ws.toast.show" :show="ws.toast.show" ... />`，`v-if` 在外层会直接卸载元素、离场动画不播放。为了让离场动画工作，把 `HomeView` 里的 `v-if` **删掉**，只保留组件内部的 `v-if="show"` 与 `<Transition>`。

  即 `HomeView.vue` 中改为：

  ```html
    <Toast :show="ws.toast.show" :type="ws.toast.type" :msg="ws.toast.msg" />
  ```

- [ ] **Step 2: 构建并走查**

```bash
cd frontend && npm run build && npm run dev
```

| # | 操作 | 预期 |
|---|---|---|
| 1 | 扫描成功 | 右上角出现**白底深灰字 + 对勾**的提示「扫描完成，发现 N 个文件」，**不是绿色** |
| 2 | 在路径为空时点扫描 | 出现浅黄底棕字 + 警告三角的提示 |
| 3 | 让一次扫描失败（填一个不存在的路径） | 出现浅红底红字 + 警告三角的提示 |
| 4 | 观察提示消失 | 淡出 + 轻微右移，约 180ms，不是横滑入 |
| 5 | 用 DevTools 看 DOM | 错误提示的 `role="alert"`；其余提示的 `role="status"` |

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/Toast.vue frontend/src/views/HomeView.vue
git commit -m "refactor(frontend): Toast 适配新 token 与 role 语义"
```

---

### Task 8: 补零位数端到端接线（§13.5）

把设置里的补零位数发到后端请求里，让「设置页改位数 → 预览立即反映」这条闭环成立。

**⚠️ 前置条件：`docs/superpowers/plans/2026-09-25-backend-pad-digits.md` 必须已合入。** 未合入时**跳过本任务**，并在第四期的完成清单里标注「补零位数闭环未验证」。

未合入时强行做本任务的表现是：请求带上了字段、后端 Pydantic **静默丢弃**未知字段、返回 200、界面一切正常、但「新文件名」列纹丝不动，**零报错**。这正是 Review Focus 第 1 条要防的失败模式。

**Files:**
- Modify: `frontend/src/stores/workspace.js`

**Interfaces:**
- Consumes: `useSettingsStore()` 的 `episodePadDigits` / `seasonPadDigits`（Task 2）；后端 `RenamePreviewRequest` / `RenameExecuteRequest` 的 `episode_pad_digits` / `season_pad_digits` 两个可选整数字段（后端计划 Task 3）
- Produces: `buildPreview()` 与 `executeAction()` 的请求体各多两个字段

- [ ] **Step 1: 先确认后端已支持这两个字段**

**在做任何前端改动之前**先跑这一步，否则无法区分「后端未合入」与「前端没接上」：

```bash
cd backend && python -c "
from app.models.api import RenamePreviewRequest, RenameExecuteRequest
for model in (RenamePreviewRequest, RenameExecuteRequest):
    fields = model.model_fields
    assert 'episode_pad_digits' in fields, f'{model.__name__} 缺 episode_pad_digits'
    assert 'season_pad_digits' in fields, f'{model.__name__} 缺 season_pad_digits'
    print(model.__name__, 'OK')
"
```

预期：两行 `OK`。

若抛 `AssertionError`：**后端计划尚未实施，停止本任务**，去做第四期。

- [ ] **Step 2: 用 curl 确认后端真的按字段改变输出**

```bash
curl -s -X POST http://localhost:8000/api/rename/preview \
  -H 'Content-Type: application/json' \
  -d '{"file_ids":[],"template":"{show} - S{season_padded}E{episode_padded}{extension}","source":"local","path":"/media"}' \
  | head -c 200
```

更直接的验证是走一次真实扫描 + 预览（见 Step 4 的表格第 5 项）。这里只需确认接口接受字段、不返回 422：

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/api/rename/preview \
  -H 'Content-Type: application/json' \
  -d '{"file_ids":[],"template":"{episode_padded}","source":"local","path":"/media","episode_pad_digits":3,"season_pad_digits":3}'
```

预期：`200`。

- [ ] **Step 3: 给两个请求体加上补零字段**

编辑 `frontend/src/stores/workspace.js`。

`buildPreview()` 里的 `previewRename({...})` 请求体，在 `create_season_folder` 之后加两行：

```js
      previewRename({
        file_ids: ids,
        source: filesStore.source,
        path: filesStore.files[0].path.replace(filesStore.files[0].filename, ''),
        template: tplStore.currentTemplate,
        folder_template: tplStore.folderTemplate,
        create_season_folder: tplStore.createSeasonFolder,
        episode_pad_digits: settingsStore.episodePadDigits,
        season_pad_digits: settingsStore.seasonPadDigits,
      })
```

`executeAction()` 里的 `fn({...})` 请求体，在 `overrides` 之后加同样两行：

```js
      const res = await fn({
        file_ids: ids,
        source: filesStore.source,
        path: selected[0].path.replace(selected[0].filename, ''),
        template: tplStore.currentTemplate,
        folder_template: tplStore.folderTemplate,
        create_season_folder: tplStore.createSeasonFolder,
        conflict_strategy: conflictStrategy.value,
        overrides,
        episode_pad_digits: settingsStore.episodePadDigits,
        season_pad_digits: settingsStore.seasonPadDigits,
      })
```

两处都要加 —— **只加 `buildPreview` 一处**的话，表格里的预览是正确的，但真正执行重命名时后端用回全局默认值，写出的文件名与预览**不一致**。这是本任务最容易犯的错。

- [ ] **Step 4: 构建并验证闭环**

```bash
cd frontend && npm run build && npm run dev
```

后端也要起来。走查（**这就是 spec §15 第 3 条要求的闭环验证**）：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 扫描一个含 `S01E02` 类文件的目录 | 表格「新文件名」列显示形如 `剧名 - S01E02.mkv` |
| 2 | `/#/settings` → 集数补零位数改 3 → 保存 | 「设置已保存」 |
| 3 | 回工作区，点表格「预览」按钮 | 「新文件名」列变成 `剧名 - S01E002.mkv`（**这是闭环成立的唯一证据**） |
| 4 | `/#/settings` → 季数补零位数也改 3 → 保存 → 回工作区 → 预览 | 变成 `剧名 - S001E002.mkv` |
| 5 | `/#/settings` → 集数补零位数改 6 → 保存 → 回工作区 → 预览 | 变成 `剧名 - S001E000002.mkv` |
| 6 | `/#/settings` → 集数补零位数**清空**输入框 → 保存 → 回工作区 → 预览 | 回到 2 位（`S001E02`）；设置页重新进入时该字段显示 **2**，不是 0、不是空 |
| 7 | 集数补零位数设为 3 → 对 1 个文件点「执行重命名」 | `ResultDialog` 里的新文件名是 `...E002.mkv`，**与表格预览一致** |
| 8 | 去磁盘上核对实际文件名 | 与 `ResultDialog` 里显示的一致（验证 Step 3 两处都改了） |

第 3 项没有变化时，按顺序排查：

1. 打开 DevTools → Network → 找 `preview` 请求 → 看 Payload 里有没有 `episode_pad_digits: 3`。**没有** → 前端没接上，回 Step 3。
2. Payload 里有、但响应里的 `new_filename` 还是 `E02` → 后端没生效，回 Step 1 / Step 2，或检查后端计划是否真的合入了。
3. Payload 里是 `episode_pad_digits: null` → `settingsSchema.js` 的 `clampNumber` 把清空误当成未设置回落了默认，或 `AppInput` 的 `null` 语义在 SettingsView 的草稿里被改坏了。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/stores/workspace.js
git commit -m "feat(frontend): 预览与执行请求下发补零位数设置"
```

---

## 本期完成后的状态

- **18 处手写输入框样式清零**，emoji 清零，`shadow-sm` 清零
- 设置真正生效：默认模板、冲突默认策略、补零位数三项都接到了工作区
- 补零位数闭环打通（依赖后端计划已合入）
- 新增 `settingsSchema.js` + `scripts/check-settings-schema.mjs`，用 34 条 node 断言覆盖设置读盘的全部健壮性分支
- 技术债清偿进度（spec §3）：#5 手写输入框 18 处（清零）、#7 圆角混用（对话框与表格已清零）、#8 阴影（清零）、#10 设置断线（解决）、#11 补零位数假设置（解决）、#12 emoji（清零）、#13 空态（第四期）、#15 动效无意图（第四期）

下一步：`docs/superpowers/plans/2026-09-25-frontend-4-polish.md`

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
| §5.2 「成功」语义降级 | Task 5（表格徽章）、Task 6（结果表与统计块）、Task 7（Toast） |
| §6.2 等宽纪律（路径去 mono） | Task 6 Step 3（`BrowseDialog` 的当前目录与面包屑） |
| §6.4 数字对齐 | Task 5 Step 3（`AppInput` 内建 `type="number"` → `tabular-nums`）、Task 6（结果统计） |
| §8.3 `SettingsView` 改用新组件、接入 settings store | Task 3 |
| §8.3 `FileTable` 改造 | Task 5 |
| §8.3 `ConfirmDialog` / `ResultDialog` / `BrowseDialog` 适配 | Task 6 |
| §8.3 `BrowseDialog` 补 aria 与键盘导航 | Task 6 Step 3（`<button>` + 方向键 / Home / End + `aria-pressed`） |
| §8.3 `Toast` 补 `role` | Task 7 |
| §10 表格「已解析」中性徽章 + 对勾图标 | Task 5 Step 3（e） |
| §10 执行失败在 `ResultDialog` 内以 danger 徽章逐条列出 | Task 6 Step 2 |
| §10 成功 Toast 用 `role="status"`、失败用 `role="alert"` | Task 7 |
| §10 表单错误内联于控件下方（不用 Toast） | Task 3（补零位数的越界提示用 `AppInput` 的 `error` 通道内联显示，替代静默钳制；走查表第 12–13 项验证） |
| §12.1 现状（写 localStorage 但没人读） | Task 2、Task 3、Task 4 修复 |
| §12.2 `stores/settings.js` 的 state / `load()` / `save()` | Task 2 |
| §12.2 `load()` 的 4 条健壮性要求 | Task 1（键不存在 / JSON 失败 / 逐字段合并 / storage 不可用，各有断言） |
| §12.2 `main.js` 挂载前调用 `load()` | Task 2 Step 2 |
| §12.2 `HomeView` 用 `defaultTemplateId` 初始化预设 | Task 4（落在 `workspace.initialize()`，`HomeView` 只是调用方） |
| §12.2 底栏用 `conflictStrategy` 作初值 | Task 4 |
| §12.2 `SettingsView` 改用 store、删除本地 `SETTINGS_KEY` 逻辑 | Task 3 |
| §12.2 OpenList 并发 / 间隔加说明标注为服务端决定 | Task 3 Step 1 的说明条 |
| §13.5 `buildPreview()` / `executeAction()` 请求体加两个字段 | Task 8 Step 3 |
| §15.3 补零位数闭环验证 | Task 8 Step 4 |
| §17 风险「设置值越界」 | Task 1（`clampNumber` 钳到 `[1, 6]`，与后端 `PadConfig` 同区间，7 条断言覆盖） |

**占位符扫描**：无 TBD / TODO / 「类似 Task N」/「添加适当的错误处理」。Task 6 的键盘导航、Task 8 的排查顺序都给了完整代码与可执行判据。

**类型一致性**：`useSettingsStore()` 的成员表在 Task 2 的 Interfaces 里定义一次；Task 3（`toObject` / `apply` / `save` / `storageAvailable`）、Task 4（`conflictStrategy` / `defaultTemplateId`）、Task 8（`episodePadDigits` / `seasonPadDigits`）全部按此名引用。`AppInput` 新增的 `size` / `ariaLabel` 与 `AppCheckbox` 新增的 `ariaLabel` 在 Task 5 的 Interfaces 里声明并在同任务内使用。`AppSelect` 的 `ariaLabel` 在第二期 Task 3 Step 2 引入，本期 Task 6 的 `BrowseDialog` 未使用它（那里有可见 label），无冲突。

**Review Focus 落位**

| # | 条目 | 验证位置 |
|---|---|---|
| 1 | 前端改完补零位数毫无变化且零报错 | Task 8 Step 1（后端字段存在性断言）+ Step 2（接口接受字段）+ Step 4 第 3 项（唯一证据）+ 三条排查路径 |
| 2 | 残缺 / 损坏的 JSON | Task 1 的断言脚本（`defaultTemplate` 迁移、半残缺 `openlist`、JSON 损坏、数组/字符串/null 输入） |
| 3 | `localStorage` 不可用 | Task 1 断言（`readSettings(null)`、`getItem` 抛异常）+ Task 2 Step 4（DevTools 屏蔽站点数据后应用仍正常）+ Task 3 Step 1（设置页显示降级提示条） |
| 4 | 补零位数清空后保存 | Task 1 断言（`null` / `''` / `undefined` 三条回落默认）+ Task 8 Step 4 第 6 项 |
| 5 | 未保存改动不应影响工作区 | Task 3 Step 3 第 11 项 |

**未覆盖（有意）**：`focus-visible` 全量收口、`prefers-reduced-motion` 兜底、`ExecutingOverlay` 精简、骨架屏与空态重做、过渡别名层的删除、全量验证与截图留档 —— 全部属第四期。本期只保证「新增/重写的元素自带 `focus-visible`」与「对话框内容区可滚动」。
