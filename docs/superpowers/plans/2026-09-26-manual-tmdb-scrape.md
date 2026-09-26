# 手动刮削 TMDB 标题 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让扫描路径不再查询 TMDB —— 刮削改由一个独立的「刮削标题」按钮显式触发，未刮削时界面如实说明成因。

**Architecture:** 前端一个**每源一份**的 `scraped` 状态位门控 preview / execute 的载荷：未置位时**显式发 `tmdb_enabled: false`**，后端 `resolve_tmdb_client` 的首个分支即返回 `None`，`TmdbResolver` 根本不被构造 → 零出网。**后端一行不改。** 载荷构造与「刮削」相关的判定各抽成一个纯函数模块，配 node 断言（本仓库刻意没有前端测试框架，这是它认可的替代）。

**Tech Stack:** Vue 3 `<script setup>` + Pinia + Vite + Tailwind v4；验证工具是既有 node 断言脚本（无测试框架）。

**Spec:** `docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md` 的 **§17**（本计划的权威），以及 §12.3 / §12.4 / §13 / §14 / §16 的相关条目。执行者必须读 §17。

## Global Constraints

以下每条都逐字来自 spec 或本项目 ledger，**每个任务的要求都隐含包含本节**：

- **后端零改动。** 本设计的前提就是后端不需要任何改动（§17.2）。若发现"顺手"的后端修改看起来必要 —— **停下来报告**，不要改：它会推翻 §17.2 的论证。
- **未刮削的唯一表达是 `tmdb_enabled: false`。** 不得改成"省略字段"或"发空 Key" —— 两者都会让后端回退到 `.env` 的 Key 而**照样出网**（§17.2，也是 R49-1 修过的形态）。
- **不新增「Key 是否存在」的前端判断。** Key 可能在服务端 `.env`，前端判不准；只有 `enabled === false` 可判（§17.4）。
- **不新建前端测试设施**（vitest / vite test 等）。本仓库刻意没有（§17.7 沿用项目惯例）。机械判据只有：`scripts/check-*.mjs`、`scripts/check-sfc-compile.mjs`、`npm run build`、源码与产物的 grep。
- **`dist/` 不进任务提交。** 每个任务只 `git add` 实际改动的文件，**不要 `git add -A`**；构建产物在 Task 5 单独打一个 `build:` 提交（项目惯例，见 ledger R45）。
- **文案里的状态字面值必须与后端逐字一致**（`nfo_scope` 四值 `disabled`/`unsupported_source`/`episode_only`/`full`；`tmdb_status` 六值）。
- **每个提交只含本任务的文件**，且提交信息说明「为什么」，不只说「改了什么」。
- **不要用 `cmd | tail -N; echo $?` 这种写法读退出码** —— `$?` 取的是 **`tail`** 的状态，恒为 0，
  于是这条检查**永远不会失败**。要既截断输出又拿到真实退出码，用重定向：
  `cmd > /tmp/x.log 2>&1; echo "exit=$?"; tail -3 /tmp/x.log`。
  （本计划初稿在四处的 `npm run build` 检查上都犯了这个错，由 Task 3 的实施者实测发现 —— 见 ledger R9。
  它和 T1 那个同值 fixture 是同一族：**一条不可能变红的检查**。）

## Review Focus

spec 隐含、但**没有任何任务的自动化测试能覆盖**的五类输入/故障（按最可能咬人的顺序）。前端的 store 与组件无法被 node 加载（R44 已记录），故其中四条只能靠**精确的 deferred-to-human 步骤**兜住 —— 那不是"跳过验证"，而是本项目对前端已接受且被文档化的补偿方式。每条的落点写在括号里。

1. **未刮削 + 勾了「生成 NFO」+ 执行** → NFO 一个都不写，用户以为功能坏了。（Task 4 的左栏提示与结果对话框提示；Task 5 走查第 3 项）
2. **切换数据源（本地已刮削 → 云盘）** → 云盘那批不得开始查 TMDB、不得显示出标题。（Task 2 的"每源一份"；Task 5 走查第 4 项。无自动化判据 —— store 无法被 node 加载）
3. **扫描后「新文件名」列应尽快出现**（本地解析，不出网）。这是本改动的全部意义。（Task 1 的载荷断言；Task 5 走查第 1 项做计时观察）
4. **未刮削时点「刮削标题」而设置页 TMDB 关着** → 必须弹既有文案，且**不置位、不发请求**。（Task 2 的守卫；Task 5 走查第 5 项）
5. **未刮削时用 🔍 重选剧集** → 必须自动置位并真的生效，不能"点了毫无变化"。（Task 2 的 `pickShow` 置位；Task 5 走查第 6 项）

---

### Task 1: 纯函数模块与 node 断言

**Files:**
- Create: `frontend/src/stores/scrapeGate.js`
- Create: `frontend/src/stores/renamePayload.js`
- Create: `frontend/scripts/check-scrape-gate.mjs`
- Create: `frontend/scripts/check-rename-payload.mjs`

**Interfaces:**
- Consumes: 无（纯函数，不 import 任何东西 —— 必须如此，否则 node 加载不了）
- Produces:
  - `isTmdbDisabled(tmdb) -> boolean`
  - `tmdbPendingScrape({ scraped, tmdbDisabled }) -> boolean`
  - `nfoBlockedByScrape({ generateNfo, scraped, tmdbDisabled }) -> boolean`
  - `buildRenamePayload({ mode, fileIds, path, source, template, folderTemplate, createSeasonFolder, conflictStrategy, overrides, episodePadDigits, seasonPadDigits, tmdb, tmdbOverrides, scraped, generateNfo, nfoOverwrite }) -> object`

- [ ] **Step 1: 先写断言脚本（RED 用）**

创建 `frontend/scripts/check-scrape-gate.mjs`：

```js
import {
  isTmdbDisabled,
  tmdbPendingScrape,
  nfoBlockedByScrape,
} from '../src/stores/scrapeGate.js'

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

// --- isTmdbDisabled：只有显式 false 才算关（与后端 enabled is False 对齐）---
assert('enabled=false 算关闭', isTmdbDisabled({ enabled: false }), true)
assert('enabled=true 不算关闭', isTmdbDisabled({ enabled: true }), false)
assert('enabled 缺失（未表态）不算关闭', isTmdbDisabled({}), false)
assert('tmdb 整个缺失不算关闭', isTmdbDisabled(undefined), false)

// --- tmdbPendingScrape：预览表 TMDB 列该说「未刮削」吗 ---
assert('未刮削且 TMDB 开着 → 该说「未刮削」',
  tmdbPendingScrape({ scraped: false, tmdbDisabled: false }), true)
assert('已刮削 → 不说', tmdbPendingScrape({ scraped: true, tmdbDisabled: false }), false)
assert('设置页关着 → 不说（成因是那个开关，且它可行动）',
  tmdbPendingScrape({ scraped: false, tmdbDisabled: true }), false)

// --- nfoBlockedByScrape：NFO 会因为「本次没刮削」而写不出来吗 ---
assert('勾了 NFO + 未刮削 + TMDB 开着 → 是',
  nfoBlockedByScrape({ generateNfo: true, scraped: false, tmdbDisabled: false }), true)
assert('没勾 NFO → 否（那时 NFO 列说「未启用」才是对的成因）',
  nfoBlockedByScrape({ generateNfo: false, scraped: false, tmdbDisabled: false }), false)
assert('已刮削 → 否',
  nfoBlockedByScrape({ generateNfo: true, scraped: true, tmdbDisabled: false }), false)
assert('设置页关着 → 否（成因是那个开关）',
  nfoBlockedByScrape({ generateNfo: true, scraped: false, tmdbDisabled: true }), false)

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
```

创建 `frontend/scripts/check-rename-payload.mjs`：

```js
import { buildRenamePayload } from '../src/stores/renamePayload.js'

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

// 键存在性单独断言：assert 比的是值，比不出「字段该不该出现」
// （字段缺失与值为 undefined 在 JSON 里同样看不见）。
function assertKey(label, obj, key, present) {
  const ok = Object.prototype.hasOwnProperty.call(obj, key) === present
  if (!ok) {
    failed += 1
    console.log('FAIL', label, '得到', Object.prototype.hasOwnProperty.call(obj, key) ? '有' : '无',
      '期望', present ? '有' : '无')
  } else {
    console.log('PASS', label)
  }
}

const base = {
  mode: 'preview',
  fileIds: ['f1', 'f2'],
  path: '/media/绝命毒师/Season 02/',
  source: 'local',
  template: '{show} - S{season_padded}E{episode_padded}{extension}',
  folderTemplate: 'Season {season_padded}',
  createSeasonFolder: true,
  conflictStrategy: 'skip',
  overrides: { f1: { title: '我的标题' } },
  // 补零位数与 NFO 两项**必须取不同的值**。取同值时「互换实现里这两个字段」
  // 会让两条断言都拿到同一个数 → 双双通过，那对断言就成了零鉴别力的摆设。
  // 而互换的后果是真损失：补零位数互换会让每个文件按错的位数改名，NFO 两项
  // 互换会让用户勾了生成却不生成 —— 两处都静默。故 2/3 与 true/false 是
  // **有意的**，不要「顺手统一」成同值。
  episodePadDigits: 2,
  seasonPadDigits: 3,
  tmdb: { apiKey: 'THE-KEY', language: 'zh-CN', enabled: true },
  tmdbOverrides: { 绝命毒师: 1396 },
  scraped: true,
  generateNfo: true,
  nfoOverwrite: false,
}

// --- 未刮削：唯一的正确表达是显式 tmdb_enabled: false（spec §17.2）---
const off = buildRenamePayload({ ...base, scraped: false })
assert('未刮削时 tmdb_enabled 严格为布尔 false', off.tmdb_enabled, false)
assertKey('未刮削时载荷不含 tmdb_api_key', off, 'tmdb_api_key', false)
assertKey('未刮削时载荷不含 tmdb_language', off, 'tmdb_language', false)
assertKey('未刮削时载荷不含 tmdb_overrides', off, 'tmdb_overrides', false)

// --- 已刮削：四项都在，且取设置值 ---
const on = buildRenamePayload({ ...base, scraped: true })
assert('已刮削时带上 Key', on.tmdb_api_key, 'THE-KEY')
assert('已刮削时带上语言', on.tmdb_language, 'zh-CN')
assert('已刮削时带上重选表', on.tmdb_overrides, { 绝命毒师: 1396 })
assert('已刮削时 tmdb_enabled 取设置值', on.tmdb_enabled, true)
assert('重选表是浅拷贝而非同一引用', on.tmdb_overrides === base.tmdbOverrides, false)

// --- 设置页关着：即使已刮削也照实下发 false（前端不替后端决定）---
assert('设置页关闭时 tmdb_enabled 为 false',
  buildRenamePayload({ ...base, tmdb: { apiKey: '', language: 'zh-CN', enabled: false } }).tmdb_enabled,
  false)

// --- 两种模式共用的字段一个都不能少（两份副本漂移就是在这里被抓住的）---
assert('file_ids 原样透传', on.file_ids, ['f1', 'f2'])
assert('source 透传', on.source, 'local')
assert('path 透传', on.path, '/media/绝命毒师/Season 02/')
assert('template 透传', on.template, base.template)
assert('folder_template 透传', on.folder_template, 'Season {season_padded}')
assert('create_season_folder 透传', on.create_season_folder, true)
assert('overrides 透传', on.overrides, { f1: { title: '我的标题' } })
assert('episode_pad_digits 透传', on.episode_pad_digits, 2)
assert('season_pad_digits 透传', on.season_pad_digits, 3)
assert('generate_nfo 透传', on.generate_nfo, true)
assert('nfo_overwrite 透传', on.nfo_overwrite, false)

// --- conflict_strategy 只属于 execute（RenamePreviewRequest 没有这个字段）---
assertKey('preview 载荷不含 conflict_strategy', off, 'conflict_strategy', false)
assert('execute 载荷带 conflict_strategy',
  buildRenamePayload({ ...base, mode: 'execute' }).conflict_strategy, 'skip')

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
```

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd frontend && node scripts/check-scrape-gate.mjs; echo "exit=$?"`
Expected: FAIL —— `Cannot find module .../src/stores/scrapeGate.js`，exit≠0。

Run: `cd frontend && node scripts/check-rename-payload.mjs; echo "exit=$?"`
Expected: FAIL —— `Cannot find module .../src/stores/renamePayload.js`，exit≠0。

（**这是真的 RED**：脚本先于实现存在，且失败原因就是"模块不存在"，不是别的东西。）

- [ ] **Step 3: 实现 `scrapeGate.js`**

创建 `frontend/src/stores/scrapeGate.js`：

```js
// 「刮削」相关的判定集中在这里 —— 它们是**四处**界面共用的谓词：
// 预览表的 TMDB 列、NFO 列、左栏的 NFO 提示、结果对话框的 NFO 提示。
// 四处各写一份的后果不是重复，而是**成因说错**：未刮削时后端一律报 disabled，
// 于是四处都可能把「去点刮削标题」说成「去设置页打开 TMDB 开关」。
// 本仓库反复在修的就是这类「让用户去改一个没问题的东西」（spec §17.5）。
//
// 与 settingsSchema.js 同规格：纯函数 + node 断言（scripts/check-scrape-gate.mjs）。
// 本仓库刻意没有前端测试框架（spec §17.7），这是它认可的替代。
//
// 本模块**不得** import 任何东西 —— 否则 node 加载不了它，断言脚本就失效。

// 设置页显式关闭了 TMDB。判据是 `=== false` 而不是 `!enabled`：与后端
// resolve_tmdb_client 的 `enabled is False` 对齐 —— 未表态（undefined / 老客户端）
// 不等于关，否则一个被手工改坏的 localStorage 会让前端拒绝刮削，而同时发出去的
// tmdb_enabled 并没让后端禁用，两边不一致。
export function isTmdbDisabled(tmdb) {
  return tmdb?.enabled === false
}

// 预览表的 TMDB 列该说「未刮削」吗。
// 设置页关着时**不说** —— 那时「未启用」才是对的成因，且它可行动（去设置页打开）。
export function tmdbPendingScrape({ scraped, tmdbDisabled }) {
  return !scraped && !tmdbDisabled
}

// NFO 会因为「本次没刮削」而写不出来吗。三个条件缺一不可：
//   · generateNfo   —— 没勾「生成 NFO」时 NFO 列本就说「未启用」，与刮削无关；
//   · !scraped      —— 已刮削就不是这个成因；
//   · !tmdbDisabled —— 设置页关着时成因是那个开关，不是「忘了点按钮」。
export function nfoBlockedByScrape({ generateNfo, scraped, tmdbDisabled }) {
  return Boolean(generateNfo) && !scraped && !tmdbDisabled
}
```

- [ ] **Step 4: 实现 `renamePayload.js`**

创建 `frontend/src/stores/renamePayload.js`：

```js
// 预览 / 执行 / 干跑的请求载荷**只有这一处**构造。
//
// 为什么必须收敛到一处：这 16 个字段原先在 workspace.js 里有两份副本
// （buildPreview 一份、executeAction 一份），而「两处都要下发 TMDB 设置」
// 正是本功能设计里的头号风险（ledger R46）—— 漏一处会让预览显示标题、执行却
// 写出别的文件名，全程零报错（本仓库有前科）。两份副本还会各自漂移：新增字段时
// 漏改一处没有任何机械判据能发现（前端没有测试框架）。
//
// 与 settingsSchema.js 同规格：纯函数 + node 断言（scripts/check-rename-payload.mjs）。
// 本模块**不得** import 任何东西 —— 否则 node 加载不了它。
export function buildRenamePayload({
  // 'preview' 走 RenamePreviewRequest；'execute' 走 RenameExecuteRequest。
  // **干跑也用 'execute'** —— 它与真执行共用同一个请求模型，只是换个端点。
  mode,
  fileIds,
  // 批次路径。两种调用点各自算好传进来：预览用扫描到的首行、执行用选中的首行
  // （递归扫描下两者可能不同）。后端目前**不读** path（api/renamer.py 只用到
  // file_ids / source / conflict_strategy），故这里不做「改进」，逐字保留原行为。
  path,
  source,
  template,
  folderTemplate,
  createSeasonFolder,
  // 仅 mode === 'execute' 进入载荷：RenamePreviewRequest 没有这个字段。
  conflictStrategy,
  // 已收集好的逐行覆盖。**由调用方收集**：预览从全部预览行收集、执行只从选中行
  // 收集 —— 两者的行集合不同（首次预览时 previewRows 还是空的，而 file_ids 来自
  // filesStore.files），把它收进这里只会把这件事实藏起来。
  overrides,
  episodePadDigits,
  seasonPadDigits,
  tmdb,
  tmdbOverrides,
  // 本次扫描是否已刮削（spec §17）。
  scraped,
  generateNfo,
  nfoOverwrite,
}) {
  return {
    file_ids: fileIds,
    source,
    path,
    template,
    folder_template: folderTemplate,
    create_season_folder: createSeasonFolder,
    overrides,
    ...(mode === 'execute' ? { conflict_strategy: conflictStrategy } : {}),
    episode_pad_digits: episodePadDigits,
    season_pad_digits: seasonPadDigits,
    // 未刮削时**只发 tmdb_enabled: false**，且不发 Key / 语言 / 重选表。
    //
    // 「不查 TMDB」的唯一有效表达就是显式 false。另两种写法都是错的：
    //   · 省略字段 → 后端拿到 None → 回退到 .env 的 Key → **照样出网**；
    //   · 发空 Key '' → 后端按真值判断把 '' 当「未提供」→ 同样回退 .env → **照样出网**。
    // 这正是 R49-1 修过的形态（Docker 只配 .env 的部署会被它破坏），故由
    // check-rename-payload.mjs 的三条断言钉住，且那三种错误实现都必须被打红。
    //
    // 顺带：没要用的请求不该带上 Key，这是密钥卫生。
    ...(scraped
      ? {
          tmdb_api_key: tmdb.apiKey,
          tmdb_language: tmdb.language,
          tmdb_overrides: { ...tmdbOverrides },
          tmdb_enabled: tmdb.enabled,
        }
      : { tmdb_enabled: false }),
    generate_nfo: generateNfo,
    nfo_overwrite: nfoOverwrite,
  }
}
```

- [ ] **Step 5: 跑两个脚本确认 GREEN**

Run: `cd frontend && node scripts/check-scrape-gate.mjs && node scripts/check-rename-payload.mjs; echo "exit=$?"`
Expected: 两个脚本都打印全部 PASS，末行「全部通过」，`exit=0`。

- [ ] **Step 6: 做变异验证（本步是本任务的鉴别力证明，不可省）**

对以下**四种**变异各做一次「改坏 → 必须红 → 还原 → 必须绿」，并在报告里附上每次的失败输出：

1. `renamePayload.js` 里把 `...(scraped ? {...} : { tmdb_enabled: false })` 改成 `...(scraped ? {...} : {})`
   → 必须红在 `未刮削时 tmdb_enabled 严格为布尔 false`（得到 `undefined`）。
2. 把 `{ tmdb_enabled: false }` 改成 `{ tmdb_enabled: '' }`
   → 必须红在同一条（得到 `""`，与 `false` 严格不等）。
3. `scrapeGate.js` 里把 `nfoBlockedByScrape` 的 `!scraped` 删掉
   → 必须红在 `已刮削 → 否`。
4. `renamePayload.js` 里把 `episode_pad_digits: episodePadDigits, season_pad_digits: seasonPadDigits`
   两个字段**互换**，以及 `generate_nfo: generateNfo, nfo_overwrite: nfoOverwrite` 两个字段**互换**
   → 必须红在 `episode_pad_digits 透传` / `season_pad_digits 透传` 与
   `generate_nfo 透传` / `nfo_overwrite 透传` 这四条。
   （**这条是任务审查抓出来的**：fixture 原先把两对字段取成同值，互换后全绿 —— 那四条断言
   当时是零鉴别力的。fixture 已改成 2/3 与 true/false，本变异就是它的证明。）

Run（每轮）：`cd frontend && node scripts/check-scrape-gate.mjs; node scripts/check-rename-payload.mjs`
Expected: 变异后**恰好**上述那一条（或那几条）FAIL、其余 PASS；还原后全部 PASS。

- [ ] **Step 7: 提交**

```bash
cd /home/billy/Projects/episode-renamer
git add frontend/src/stores/scrapeGate.js frontend/src/stores/renamePayload.js \
        frontend/scripts/check-scrape-gate.mjs frontend/scripts/check-rename-payload.mjs
git commit -m "feat(frontend): 刮削判定与请求载荷各抽成纯函数 + node 断言

为「刮削改为手动触发」（spec §17）打地基：把两处判定收敛到一处并配上机械判据。

- scrapeGate.js：isTmdbDisabled / tmdbPendingScrape / nfoBlockedByScrape。
  这四个谓词被四处界面共用（TMDB 列、NFO 列、左栏提示、结果对话框），各写一份
  的后果不是重复而是**成因说错** —— 未刮削时后端一律报 disabled，于是都可能把
  「去点刮削标题」说成「去设置页打开 TMDB 开关」。
- renamePayload.js：预览/执行/干跑的载荷唯一构造点。原先 workspace.js 里有两份
  副本，而「两处都要下发 TMDB 设置」是本设计的头号风险（R46）；漏一处会让预览
  显示标题、执行写出别的文件名，且零报错。
- 未刮削时**只发 tmdb_enabled: false**：省略字段或发空串都会让后端回退 .env 的
  Key 而照样出网（R49-1 修过的形态）。三种错误实现各有一条断言钉住。

验证：两个脚本全绿；三种变异（省略字段 / 发空串 / 去掉 !scraped）各自被打红。"
```

---

### Task 2: workspace store 接入（`scraped` 生命周期与载荷改用纯函数）

**Files:**
- Modify: `frontend/src/stores/workspace.js`

**Interfaces:**
- Consumes: Task 1 的 `buildRenamePayload` / `isTmdbDisabled` / `tmdbPendingScrape` / `nfoBlockedByScrape`
- Produces（供 Task 3/4 的组件消费，名字逐字如此）：
  - `scraped`（可写 computed，boolean）
  - `scraping`（ref，boolean）
  - `tmdbDisabled`（computed，boolean）
  - `tmdbPendingScrape`（computed，boolean）—— 注意 store 里 import 的谓词要**别名**，见 Step 2 的说明
  - `nfoNeedsScrape`（computed，boolean）
  - `scrapeTitles()`（async action）
  - `lastResult` 上新增字段 `nfo_blocked_by_scrape`（boolean）

**关键事实（决定下面的代码长什么样，别按直觉改）：**

- **`file_ids` 与 `overrides` 来自不同的行集合。** `buildPreview` 的 `file_ids` 取自 `filesStore.files`（全部文件），而 `overrides` 取自 `previewRows`（上一次的行）—— 首次扫描后 `previewRows` 还是空的。故 `buildRenamePayload` 的两个入参分别传，**不要**为了"统一"而都改成 `previewRows`：那会让首次预览发出空 `file_ids`，整个预览失效。
- **`path` 后端不读**（`api/renamer.py` 只用 `file_ids` / `source` / `conflict_strategy`）。预览用「扫描到的首行」、执行用「选中的首行」是既有差异，逐字保留。
- **`overrides` 的收集循环保留原地**：它的映射同时被下面的行重建复用（`override: overrides[f.id] || {}`），不能挪进纯函数。

- [ ] **Step 1: 给 `sourceStates` 加 `scraped`，并加 `scraping` ref**

把 `workspace.js` 的 `sourceStates`（约 28-31 行）改成：

```js
  const sourceStates = reactive({
    local: { files: [], scanResult: null, previewRows: [], scannedInfo: null, path: '', scraped: false },
    openlist: { files: [], scanResult: null, previewRows: [], scannedInfo: null, path: '', scraped: false },
  })
```

在 `const scanning = ref(false)`（约 35 行）下方加：

```js
  // 「刮削标题」按钮的进行中状态。它是唯一会慢的动作（其余预览都是本地解析），
  // 所以只有它需要 loading 反馈。
  const scraping = ref(false)
```

- [ ] **Step 2: 加 import 与三个 computed（`scraped` / `tmdbDisabled` / 两个谓词）**

在文件顶部的 import 区（`import { resolveOpenListServerUrl } from './settingsSchema'` 之后）加：

```js
import {
  isTmdbDisabled,
  nfoBlockedByScrape,
  // 必须**别名**：下面有一个同名的 computed（`tmdbPendingScrape`），而
  // `const x = computed(() => x(...))` 里的 x 会被 const 遮蔽 —— 调用时拿到的是
  // 那个 ref 而不是函数，运行期报「not a function」。别名让两者都保住好名字。
  tmdbPendingScrape as isTmdbPendingScrape,
} from './scrapeGate'
import { buildRenamePayload } from './renamePayload'
```

在 `const scannedInfo = computed({...})`（约 84-87 行）之后加：

```js
  // 「本次扫描是否已刮削 TMDB 标题」（spec §17.3）。**每源一份** ——
  // switchSource 会把文件列表换成另一源已扫过的那一份（见 switchSource 里的注释），
  // 若它是全局的，「本地刮削过 → 切到云盘」会让一个从未刮削的源显示出标题，
  // 并让云盘那批**未经用户同意**地开始查 TMDB。与 path / previewRows / scannedInfo
  // 同住 sourceStates 正是为此。
  const scraped = computed({
    get: () => sourceStates[activeSource.value].scraped,
    set: (v) => { sourceStates[activeSource.value].scraped = v },
  })

  // 设置页显式关闭了 TMDB。判据收敛在 scrapeGate.isTmdbDisabled 一处
  // （与后端 resolve_tmdb_client 的 `enabled is False` 对齐）—— 前端另有四处
  // 需要同一个判断，各写一份就会漂移。
  const tmdbDisabled = computed(() => isTmdbDisabled(settingsStore.tmdb))

  // 预览表 TMDB 列该说「未刮削」吗（设置页关着时不说，见 scrapeGate 的注释）。
  const tmdbPendingScrape = computed(() => isTmdbPendingScrape({
    scraped: scraped.value,
    tmdbDisabled: tmdbDisabled.value,
  }))

  // 「勾了生成 NFO，但本次没刮削，所以一个 NFO 也写不出来」——
  // 左栏提示与 NFO 列共用这一个判据（spec §17.5）。
  const nfoNeedsScrape = computed(() => nfoBlockedByScrape({
    generateNfo: generateNfo.value,
    scraped: scraped.value,
    tmdbDisabled: tmdbDisabled.value,
  }))
```

- [ ] **Step 3: `tmdbOff()` 改为委托给 `tmdbDisabled`**

把（约 515-517 行）：

```js
  function tmdbOff() {
    return settingsStore.tmdb.enabled === false
  }
```

改成：

```js
  function tmdbOff() {
    return tmdbDisabled.value
  }
```

（保留函数名，四个调用点不用改；判定本身只有一处。）

- [ ] **Step 4: 加 `scrapeTitles()` 动作**

在 `TMDB_OFF_TOAST` 那一行之后、`function rematchShow(row)` 之前插入：

```js
  // 「刮削标题」按钮 —— 唯一的显式刮削入口（另一个置位点是 pickShow，见那里）。
  //
  // 置位后本次扫描的**后续所有**预览/执行都会带上 TMDB 设置（见 buildRenamePayload），
  // 所以改模板、改补零位数都不会把已刮到的标题弄丢。
  //
  // 关着开关时不置位、也不发请求 —— 与 rematchShow 同一道守卫、同一句文案，
  // 免得出现「点了按钮什么都没发生」。**不检查 Key 是否为空**：Key 可能在服务端
  // .env 里，前端判不准（spec §17.4）。
  async function scrapeTitles() {
    if (tmdbOff()) {
      showToast(TMDB_OFF_TOAST, 'warning')
      return
    }
    scraped.value = true
    scraping.value = true
    try {
      await refreshPreviewReportingFailure()
    } finally {
      scraping.value = false
    }
  }
```

- [ ] **Step 5: 两个扫描动作与 `clearAll` 重置刮削状态**

`doScan`（约 162-187 行）里，在 `filesStore.setFiles(data.files || [])` 之后、`showToast(...)` 之前插入：

```js
      // 新扫描 = 新文件集（file_id 每次扫描都是全新随机值），旧标题本来就留不住；
      // 这条同时保证「扫描路径绝不出网」—— 下面的预览回刷不会带 TMDB 设置。
      scraped.value = false
```

`doOpenListScan`（约 212-238 行）里做**同样**的插入（同样在 `filesStore.setFiles(data.files || [])` 之后）。

`clearAll`（约 418-426 行）里，在 `scannedInfo.value = null` 之后插入：

```js
      scraped.value = false
```

- [ ] **Step 6: `pickShow` 置位**

在 `pickShow` 里，`tmdbOverrides[showName] = item.tv_id` 与 `tmdbDialog.open = false` 之后、`if (await refreshPreviewReportingFailure())` 之前插入：

```js
    // 重选**就是**一次刮削意图：不置位的话这次刷新不会带 TMDB 设置，用户的选择
    // 会被后端丢弃而界面毫无变化 —— 正是 R32 / pickShow 修过的那类缺陷。
    scraped.value = true
```

- [ ] **Step 7: `buildPreview` 改用纯函数**

把 `buildPreview` 里 `const res = await previewRename({ ... })` 那一整段请求对象替换为：

```js
      const res = await previewRename(buildRenamePayload({
        mode: 'preview',
        fileIds: filesStore.files.map(f => f.id),
        // 与改动前逐字一致：从**扫描到的**首行推出父目录（不是预览行）。
        path: filesStore.files[0].path.replace(filesStore.files[0].filename, ''),
        source: filesStore.source,
        template: tplStore.currentTemplate,
        folderTemplate: tplStore.folderTemplate,
        createSeasonFolder: tplStore.createSeasonFolder,
        overrides,
        episodePadDigits: settingsStore.episodePadDigits,
        seasonPadDigits: settingsStore.seasonPadDigits,
        tmdb: settingsStore.tmdb,
        tmdbOverrides,
        scraped: scraped.value,
        generateNfo: generateNfo.value,
        nfoOverwrite: nfoOverwrite.value,
      }))
```

`overrides` 的收集循环与它上面那段注释**原样保留**（那份映射同时供下面的行重建使用）。

- [ ] **Step 8: `executeAction` 改用纯函数，并把「NFO 因未刮削写不出」记在结果上**

把 `const res = await fn({ ... })` 那一整段请求对象替换为：

```js
      const res = await fn(buildRenamePayload({
        mode: 'execute',
        fileIds: ids,
        path: selected[0].path.replace(selected[0].filename, ''),
        source: filesStore.source,
        template: tplStore.currentTemplate,
        folderTemplate: tplStore.folderTemplate,
        createSeasonFolder: tplStore.createSeasonFolder,
        conflictStrategy: conflictStrategy.value,
        overrides,
        episodePadDigits: settingsStore.episodePadDigits,
        seasonPadDigits: settingsStore.seasonPadDigits,
        tmdb: settingsStore.tmdb,
        tmdbOverrides,
        scraped: scraped.value,
        generateNfo: generateNfo.value,
        nfoOverwrite: nfoOverwrite.value,
      }))
```

把 `lastResult.value = { ...res.data, dry_run: dryRun }` 替换为：

```js
      lastResult.value = {
        ...res.data,
        dry_run: dryRun,
        // NFO 的跳过原因由后端给（「TMDB 未匹配, 不写残缺 NFO」），但那条文案在
        // 「本次没刮削」时会把成因说成「没匹配到」。这个标志在**执行那一刻**算好
        // 记在结果上（与 dry_run 同样的做法：载荷里没有能区分的东西），
        // 结果对话框据此把真实成因补上（spec §17.5）。
        nfo_blocked_by_scrape: nfoNeedsScrape.value,
      }
```

- [ ] **Step 9: 导出新名字**

在 `return { ... }`（约 620-635 行）里补上：

```js
    scraped, scraping, tmdbDisabled, tmdbPendingScrape, nfoNeedsScrape, scrapeTitles,
```

（放在 `generateNfo, nfoOverwrite,` 那一行附近即可。）

- [ ] **Step 10: 机械验证**

Run: `cd frontend && node scripts/check-sfc-compile.mjs; echo "sfc=$?"`
Expected: 全部 `OK`，`sfc=0`。

Run: `cd frontend && npm run build > /tmp/build.log 2>&1; echo "build=$?"; tail -3 /tmp/build.log`
Expected: `✓ built in ...`，`build=0`。

Run（源码级接线检查 —— 证明两个调用点都用了同一个构造器，而不是各留一份字面量）：

```bash
cd frontend
grep -c "buildRenamePayload" src/stores/workspace.js   # 期望 3 = 1 个 import + 2 个调用点
grep -n "previewRename(\|dryRunRename(\|executeRename(" src/stores/workspace.js
```

（若计数大于 3，说明有注释提到了这个名字 —— 以 `grep -n` 打印出的**行位置**为准，别去凑那个数字。）

Expected: 计数为 `3`；且三条调用**紧邻**的都是 `buildRenamePayload({`，不再是裸的对象字面量。

**诚实声明其能力边界**：这两条 grep 只证明源码里的接线存在，**不证明运行时行为**（store 无法被 node 加载，见 R44）。行为由 Task 5 的走查步骤兜住。

- [ ] **Step 11: 提交**

```bash
cd /home/billy/Projects/episode-renamer
git add frontend/src/stores/workspace.js
git commit -m "feat(frontend): scraped 门控扫描路径不出网 + 载荷改用纯函数（spec §17）

- scraped 状态位**每源一份**（随 files / previewRows 住 sourceStates）：switchSource
  会换成另一源已扫过的文件列表，全局标志会让从未刮削的源显示出标题、并让那批
  未经用户同意地查 TMDB。
- 生命周期：doScan / doOpenListScan / clearAll 重置；置位只有 scrapeTitles 与
  pickShow（后者必须置位，否则重选被后端丢弃而界面毫无变化 —— R32 那类缺陷）。
- tmdbOff() 改为委托 tmdbDisabled，判定收敛到 scrapeGate 一处。
- buildPreview / executeAction 改用 buildRenamePayload：原先是两份 15 字段副本，
  而「两处都要下发」是本设计的头号风险（R46）。file_ids 与 overrides 仍分别来自
  扫描文件与预览行（首次预览时 previewRows 为空），这点刻意不统一。
- lastResult 记 nfo_blocked_by_scrape：后端那条「TMDB 未匹配」在未刮削时会把成因
  说错，对话框据此补上真实成因（§17.5）。

验证：check-sfc-compile 与 npm run build 通过；源码级接线检查计数为 3。"
```

---

### Task 3: 「刮削标题」按钮与两列的「未刮削」文案

**Files:**
- Modify: `frontend/src/components/FileTable.vue`
- Modify: `frontend/src/views/HomeView.vue`

**Interfaces:**
- Consumes: Task 2 的 `ws.tmdbPendingScrape` / `ws.nfoNeedsScrape` / `ws.scraping` / `ws.scrapeTitles`
- Produces: 无（叶子组件）

**这一任务的两个要点：**

- **按钮是 `FileTable` 工具条的第三个动作**，放在「预览」之前（它是更重要的动作），`secondary` 变体 —— 主操作是底栏的「执行重命名」。
- **两列的文案只改「成因」**：未刮削时后端报的是 `disabled`，而 `TMDB_LABELS.disabled` 是「未启用」。把「未刮削」显示成「未启用」会把用户推去设置页翻一个**本来就开着**的开关 —— 这正是本设计一直在修的错误诊断类别（spec §17.5）。

- [ ] **Step 1: 工具条加按钮**

在 `FileTable.vue` 的工具条里，`预览` 那个 `<AppButton>` **之前**插入：

```html
        <AppButton
          size="sm"
          variant="secondary"
          :loading="scraping"
          :disabled="!filesStore.files.length || scanning"
          @click="$emit('scrape')"
        >
          刮削标题
        </AppButton>
```

（`loading` 的用法与底栏「执行重命名」一致；刮削是唯一会慢的动作，需要反馈。）

- [ ] **Step 2: 加三个 prop 与一个 emit**

把 `defineProps({...})`（约 371-378 行）改成：

```js
const props = defineProps({
  filesStore: { type: Object, required: true },
  previewRows: { type: Array, default: () => [] },
  scannedInfo: Object,
  allSelected: Boolean,
  activeSource: String,
  scanning: { type: Boolean, default: false },
  // 未刮削时 TMDB 列该说「未刮削」（设置页关着时不算 —— 见 scrapeGate 的注释）。
  tmdbPendingScrape: { type: Boolean, default: false },
  // 「勾了生成 NFO 但本次没刮削」：NFO 列要说「未刮削」而不是「未启用」。
  nfoNeedsScrape: { type: Boolean, default: false },
  scraping: { type: Boolean, default: false },
})
defineEmits([
  'preview-all', 'clear-all', 'toggle-all', 'select-row', 'update-row', 'quick-scan', 'rematch',
  'scrape',
])
```

- [ ] **Step 3: TMDB 列的文案与色调**

把 `tmdbLabel` 与 `tmdbTone`（约 303-311 行）改成：

```js
function tmdbLabel(status) {
  // 未刮削时后端报的是 disabled（它确实没被启用），但把这个成因说成「未启用」
  // 会把用户推去设置页翻一个本来就开着的开关。成因必须说对（spec §17.5）。
  if (props.tmdbPendingScrape) return '未刮削'
  return TMDB_LABELS[status] || '未知'
}

function tmdbTone(status) {
  if (props.tmdbPendingScrape) return 'neutral'
  if (status === 'matched') return 'accent'
  if (status === 'disabled') return 'neutral'
  return 'warn'
}
```

（`props` 在文件里声明于这两个函数**之后**，但函数只在渲染期被调用，那时 `props` 已初始化 —— 与文件里既有的 `showsWithShowLevelNfo` / `emptyState` 同一模式。不要为此挪动 `defineProps` 的位置，那会扩大无关 diff。）

- [ ] **Step 4: NFO 列的文案**

把 `nfoNullHint`（约 359-369 行）改成：

```js
function nfoNullHint(row) {
  // is_subtitle 由扫描器给（local_scanner 的 _build_file_info）, 经扫描响应的
  // model_dump 与 workspace 的 `...f` 原样到达行上 —— 不需要在这里再嗅扩展名。
  if (row.is_subtitle) {
    return { text: '字幕不写 NFO', warn: false, title: undefined }
  }
  // 「勾了生成 NFO 但本次没刮削」：后端此时同样报 disabled，而「未启用」会把用户
  // 推去设置页翻一个本来就开着的开关。它是**批次级**成因，故与下面 disabled /
  // unsupported_source 同一位置（在 is_subtitle 之后，与该分支的既有次序一致）。
  // nfoNeedsScrape 已经含了「勾了 NFO」这个条件 —— 没勾时这里仍是「未启用」，对的。
  if (props.nfoNeedsScrape) {
    return { text: '未刮削', warn: false, title: '未刮削标题：NFO 的内容全部来自 TMDB' }
  }
  if (BATCH_NFO_SCOPES.has(row.nfo_scope)) {
    return { text: nfoScopeHint(row.nfo_scope), warn: false, title: undefined }
  }
  return { text: '本集无 NFO', warn: true, title: 'TMDB 未匹配到本集，不写本集 NFO' }
}
```

（`nfoNullHint` 上方那段解释三支成因的长注释**保留**，并在其末尾补一句：「第四支（未刮削）由 spec §17.5 追加，它也是批次级成因，故紧跟在字幕之后。」）

- [ ] **Step 5: HomeView 接线**

把 `HomeView.vue` 里 `<FileTable ... />` 那段（约 59-73 行）改成：

```html
        <FileTable
          :files-store="filesStore"
          :preview-rows="ws.previewRows"
          :scanned-info="ws.scannedInfo"
          :all-selected="ws.allSelected"
          :active-source="ws.activeSource"
          :scanning="ws.scanning"
          :tmdb-pending-scrape="ws.tmdbPendingScrape"
          :nfo-needs-scrape="ws.nfoNeedsScrape"
          :scraping="ws.scraping"
          @preview-all="ws.previewAll"
          @clear-all="ws.clearAll"
          @toggle-all="ws.toggleAll"
          @select-row="({ row, val }) => row.selected = val"
          @update-row="ws.updatePreview"
          @quick-scan="ws.doScan"
          @rematch="ws.rematchShow"
          @scrape="ws.scrapeTitles"
        />
```

- [ ] **Step 6: 机械验证**

Run: `cd frontend && node scripts/check-sfc-compile.mjs; echo "sfc=$?"`
Expected: `OK src/components/FileTable.vue` 与 `OK src/views/HomeView.vue` 在列，`sfc=0`。

Run: `cd frontend && npm run build > /tmp/build.log 2>&1; echo "build=$?"; tail -3 /tmp/build.log`
Expected: `✓ built in ...`，`build=0`。

Run（确认新文案进入源码，且没有把「未启用」误删 —— 设置页关着时那条仍是必需的）：

```bash
cd frontend
grep -n "'未刮削'" src/components/FileTable.vue        # 期望 2 行：TMDB 列一处、NFO 列一处
grep -n "disabled: '未启用'" src/components/FileTable.vue  # 期望仍在（设置页关着时仍需要它）
```

（用带引号的字面量而不是裸的「未刮削」：注释里也会出现这三个字，裸串的计数会随注释措辞变化 —— 本项目有过多次「陈旧数字」的教训。）

- [ ] **Step 7: 提交**

```bash
cd /home/billy/Projects/episode-renamer
git add frontend/src/components/FileTable.vue frontend/src/views/HomeView.vue
git commit -m "feat(frontend): 「刮削标题」按钮 + 未刮削时两列如实报成因（spec §17.4/§17.5）

- FileTable 工具条加「刮削标题」（secondary，与「预览」「清空」并列；刮削是唯一
  会慢的动作，故带 loading）。禁用条件：无文件 / 正在扫描。
- TMDB 列与 NFO 列在未刮削时说「未刮削」而不是「未启用」—— 后者会把用户推去
  设置页翻一个本来就开着的开关。两处的判据来自 store 的两个 computed，不是各写
  一份（四处界面共用同一谓词，见 scrapeGate.js）。
- NFO 列的分支位置与既有次序一致：字幕 → 批次级成因（未刮削 / disabled /
  云盘不支持）→ 本行自己的「本集无 NFO」。

验证：check-sfc-compile 与 npm run build 通过；源码 grep 计数与「未启用」仍在。"
```

---

### Task 4: 可见性提示（左栏 NFO 勾选框旁 + 结果对话框）

**Files:**
- Modify: `frontend/src/components/TemplateConfig.vue`
- Modify: `frontend/src/components/ResultDialog.vue`

**Interfaces:**
- Consumes: Task 2 的 `ws.nfoNeedsScrape` 与 `lastResult.nfo_blocked_by_scrape`
- Produces: 无（叶子组件）

**为什么这两条提示是必需的、不是润色**：用户已明确接受「未刮削时 NFO 零产出」这个代价（§17.1），但本项目对这类「代价换取的取舍」有一条既定标准 —— **可见性即安全阀**（spec §9.4 / ledger R86-2：接受一个已知类别的理由，正是它在执行前可见）。不点明的话，用户勾了「生成 NFO」、执行完发现一个文件都没写，只会以为功能坏了。后端此时给的原因串是「TMDB 未匹配, 不写残缺 NFO」—— **它在语义上没错**（确实没匹配到），但作为诊断会把用户推去核对文件名或怀疑 TMDB 配置，而真实成因是本次根本没刮削。

- [ ] **Step 1: TemplateConfig 加 prop**

把 `TemplateConfig.vue` 的 `defineProps({...})`（约 99-104 行）改成：

```js
const props = defineProps({
  tplStore: { type: Object, required: true },
  source: { type: String, required: true },
  generateNfo: { type: Boolean, default: false },
  nfoOverwrite: { type: Boolean, default: false },
  // 「勾了生成 NFO，但本次没刮削」—— 由 workspace 的同一个谓词给出（spec §17.5）。
  nfoNeedsScrape: { type: Boolean, default: false },
})
```

- [ ] **Step 2: TemplateConfig 加提示**

把 NFO 那一段里现有的那条说明（约 51-53 行）：

```html
      <p v-if="generateNfo && source !== 'openlist'" class="text-[11px] leading-relaxed text-ink-3">
        生成 tvshow.nfo、season.nfo 与每集 .nfo。剧集级文件需要该目录下只有一部剧，否则只写每集 NFO。
      </p>
```

改成（保留原段，在其后追加新段）：

```html
      <p v-if="generateNfo && source !== 'openlist'" class="text-[11px] leading-relaxed text-ink-3">
        生成 tvshow.nfo、season.nfo 与每集 .nfo。剧集级文件需要该目录下只有一部剧，否则只写每集 NFO。
      </p>
      <!-- 未刮削 + 勾了 NFO = 一个文件都不会写。用 warn 色而不是次要文字色：
           它是一个「你现在这样做会得到零产出」的警告，不是背景说明。 -->
      <p
        v-if="nfoNeedsScrape && source !== 'openlist'"
        class="text-[11px] leading-relaxed text-warn"
      >
        尚未刮削标题：NFO 的内容全部来自 TMDB，点文件列表上方的「刮削标题」后才会写出。
      </p>
```

- [ ] **Step 3: ResultDialog 加提示**

在 `ResultDialog.vue` 的 NFO 汇总块里，`hint` 那一段（约 71-73 行）：

```html
            <p v-if="nfoStats.hint" class="mt-1 text-[11px] leading-relaxed text-warn">
              {{ nfoStats.hint }}
            </p>
```

之后追加：

```html
            <!-- 未刮削而执行：后端给的跳过原因（「TMDB 未匹配, 不写残缺 NFO」）在这一次
                 会把成因说成「没匹配到」。不点明的话用户会去核对文件名或怀疑 TMDB 配置，
                 而真实成因是本次根本没刮削（spec §17.5）。 -->
            <p v-if="nfoStats.scrapeNote" class="mt-1 text-[11px] leading-relaxed text-warn">
              {{ nfoStats.scrapeNote }}
            </p>
```

- [ ] **Step 4: ResultDialog 的 computed 加一项**

在 `nfoStats` 的返回对象里，`hint` 那一项之后加：

```js
    // 标志由 workspace.executeAction 在**执行那一刻**算好记在结果上（与 dry_run
    // 同样的做法）—— 不在这里重算，因为对话框打开时 scraped 可能已经变了。
    scrapeNote: props.result?.nfo_blocked_by_scrape
      ? '本次未刮削标题，NFO 没有元数据可写：点文件列表上方的「刮削标题」后重新执行即可。'
      : '',
```

- [ ] **Step 5: HomeView 接线**

在 `HomeView.vue` 里给 `<TemplateConfig ... />`（约 40-51 行）补一个 prop：

```html
            :nfo-needs-scrape="ws.nfoNeedsScrape"
```

（`ResultDialog` 不需要新 prop —— 它读的是 `lastResult` 上已经记好的标志。）

- [ ] **Step 6: 机械验证**

Run: `cd frontend && node scripts/check-sfc-compile.mjs; echo "sfc=$?"`
Expected: `OK src/components/TemplateConfig.vue` 与 `OK src/components/ResultDialog.vue` 在列，`sfc=0`。

Run: `cd frontend && npm run build > /tmp/build.log 2>&1; echo "build=$?"; tail -3 /tmp/build.log`
Expected: `✓ built in ...`，`build=0`。

Run:

```bash
cd frontend
grep -n "nfoNeedsScrape\|nfo-needs-scrape" src/components/TemplateConfig.vue src/views/HomeView.vue
grep -n "nfo_blocked_by_scrape\|scrapeNote" src/components/ResultDialog.vue
```

Expected: `TemplateConfig.vue` 两行（prop 声明 + `v-if` 使用）；`HomeView.vue` 两行（一个给 `FileTable`、一个给 `TemplateConfig`）；`ResultDialog.vue` 两行（computed 里读 `nfo_blocked_by_scrape`、模板里渲染 `scrapeNote`）。用 `grep -n` 看行而不是计数：要确认的是**接线在正确的位置**，一个数字证明不了这件事。

**诚实声明其能力边界**：以上都只证明源码接线与编译，**不证明这两条提示在浏览器里出现**。它们由 Task 5 的走查第 2、3 项兜住。

- [ ] **Step 7: 提交**

```bash
cd /home/billy/Projects/episode-renamer
git add frontend/src/components/TemplateConfig.vue frontend/src/components/ResultDialog.vue \
        frontend/src/views/HomeView.vue
git commit -m "feat(frontend): 未刮削导致 NFO 零产出时给出可见提示（spec §17.5）

用户已接受「未刮削则 NFO 零产出」这个代价，但按本项目的标准它不能是静默的
（§9.4 的可见性即安全阀；R86-2 接受一个已知类别的理由正是它在执行前可见）。

- 左栏：勾了「生成 NFO」而本次未刮削时，在 NFO 勾选框下方给 warn 色提示，
  并点明去哪操作（文件列表上方的「刮削标题」）。
- 结果对话框：后端给的跳过原因是「TMDB 未匹配, 不写残缺 NFO」—— 语义上没错，
  但会把用户推去核对文件名。标志由 executeAction 在执行那一刻算好记在结果上
  （与 dry_run 同法），对话框据此补上真实成因。

验证：check-sfc-compile 与 npm run build 通过；源码 grep 计数符合预期。"
```

---

### Task 5: 收尾与验收

**Files:**
- Modify: `frontend/dist/**`（构建产物，**只在本任务提交**）

**Interfaces:**
- Consumes: Task 1–4 的全部产物
- Produces: 一个可交付的分支状态 + 一份 deferred-to-human 走查清单

- [ ] **Step 1: 证明后端一行未改**

Run:

```bash
cd /home/billy/Projects/episode-renamer
# 本计划的起点 = 本计划文件被提交时的那个提交（自足，不需要外部记录）
BASE=$(git log --format=%H -1 -- docs/superpowers/plans/2026-09-26-manual-tmdb-scrape.md)
git diff --stat $BASE..HEAD -- backend/
```

Expected: **无输出**（后端零改动是本设计的前提，§17.2）。

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: `214 passed` —— 与改动前**逐字相同**的条数。

- [ ] **Step 2: 跑齐四个前端机械判据**

Run:

```bash
cd /home/billy/Projects/episode-renamer/frontend
node scripts/check-settings-schema.mjs; echo "schema=$?"
node scripts/check-scrape-gate.mjs;     echo "scrapeGate=$?"
node scripts/check-rename-payload.mjs;  echo "payload=$?"
node scripts/check-sfc-compile.mjs;     echo "sfc=$?"
```

Expected: 四个 `exit=0`，各自末行是「全部通过」或「全部 SFC 可编译」。

- [ ] **Step 3: 构建并做产物级检查**

Run: `cd frontend && npm run build > /tmp/build.log 2>&1; echo "build=$?"; tail -3 /tmp/build.log`
Expected: `✓ built in ...`，`build=0`。

Run:

```bash
cd frontend
grep -rl "未刮削" dist/assets/                      # 期望：命中 HomeView 那个 chunk
grep -o "刮削标题" dist/assets/HomeView-*.js | wc -l # 期望：≥1
grep -o "tmdb_enabled:[^,}]*" dist/assets/HomeView-*.js | sort | uniq -c
```

Expected: 第三条要能看到**两个**取值 —— 已刮削那一支取设置值、未刮削那一支是布尔假（esbuild 生产构建通常压成 `!1`）。若压缩形态与预期不同，以「两个分支的取值都在产物里」为准，并在报告里附上实际输出。

**这条判据的能力边界**：它证明新代码进了产物，**不证明门控在运行时生效** —— 那是走查第 1 项的事（ledger R50 记过同一类误判：产物 grep 只能证明不陈旧）。

- [ ] **Step 4: 提交构建产物**

```bash
cd /home/billy/Projects/episode-renamer
git add frontend/dist
git commit -m "build: 更新前端构建产物（手动刮削按钮 + 未刮削成因文案）

与 Task 1–4 配对提交，避免出现「源码已改、产物未更」的状态（本项目有过一次：
checkout HEAD 仍能复现原始症状，见 ledger 的「设置不生效」那期 Critical 1）。"
```

- [ ] **Step 5: 交付 deferred-to-human 走查清单**

把下面这份清单原样写进报告（不要改写成「已验证」）。每一项都给了**具体操作**与**预期观察**，因为本仓库的前端没有自动化判据（§17.7）：

1. **扫描不再被 TMDB 拖慢**（本改动的全部意义）。选一个含十几集的目录点「扫描」：文件列表出现后，「新文件名」列应**立刻**跟着填满（本地解析）；此时「标题」列为空、「TMDB」列显示**未刮削**。若「新文件名」列仍要等数秒，说明门控没生效 —— 回 Task 2 查载荷。
2. **按钮可用且诚实**。点「刮削标题」：按钮应进入 loading，随后「标题」列出现集标题、「TMDB」列变为已匹配/未匹配等真实状态。设置页把「启用 TMDB 元数据」取消勾选后再点：应弹「TMDB 元数据已关闭，请在设置中启用」，且**不进入 loading、不置位**（再点扫描后 TMDB 列仍应是「未启用」而不是「未刮削」）。
3. **NFO 零产出是可见的**。勾上「同时生成 NFO 文件」但不点刮削：左栏 NFO 勾选框下方应出现橙色提示「尚未刮削标题：…」。此时直接执行（或试运行）：结果对话框的 NFO 跳过原因旁应出现「本次未刮削标题，NFO 没有元数据可写：…」，且确实一个 NFO 都没写。
4. **切源不串味**。本地源扫一个目录并刮削（标题出现），切到云盘源：云盘的列表**不得**显示任何标题，「TMDB」列应是「未刮削」。切回本地：原来的标题**应该还在**（每源一份）。
5. **未刮削时重选剧集要生效**。未刮削状态下点某行的 🔍 并选一部剧：应自动完成一次刮削（标题列随之出现），且弹出「已选用 …」。**不得**出现「选了但界面毫无变化」。
6. **刮削后改模板不丢标题**。刮削完成后再改文件模板（在模板框里敲一个字）：重建预览后「标题」列应**仍然有标题**（因为已置位，重建会带上 TMDB 设置，且命中进程级缓存）。

- [ ] **Step 6: 与 spec 对表**

逐条核对实现与 spec §17 是否一致，把结论写进报告：

- §17.2 门控机制：未刮削时载荷**只有** `tmdb_enabled: false`（无 Key / 语言 / 重选表）。
- §17.3 生命周期：重置点（两个扫描动作 + clearAll）与置位点（按钮 + `pickShow`）**各只有一个来源**；标志**每源一份**。
- §17.4 UI：按钮在 FileTable 工具条、`secondary`、loading、禁用条件、`tmdbOff()` 文案、**没有**新增 Key 存在性判断。
- §17.5 四行文案表逐行对应到代码位置。
- §14 的两条新限制（未刮削时 NFO 零产出、每次扫描重置）与实现一致。

**若发现实现与 spec 不符**：以 spec 为准，改实现；若认为 spec 本身该改，**停下来报告**，不要自行改 spec。

- [ ] **Step 7: 报告**

报告里必须包含（本项目派发的固定要求）：

- 每个任务的提交哈希；
- 变异验证的**原始失败输出**（不是"我验证过了"）；
- 上述走查清单的**逐项结论**（做了就说做了并给出观察，没做就写"未执行"）；
- 任何与计划的偏离，以及为什么。

---

## Self-Review

**1. Spec 覆盖**（§17 逐节 → 落点）：

| spec 节 | 落点 |
|---|---|
| §17.1 背景与动机 | 无代码；由 Task 5 走查第 1 项验收 |
| §17.2 门控机制 | Task 1（`buildRenamePayload` 的 `tmdb_enabled: false` 分支 + 3 条断言 + 3 个变异） |
| §17.3 状态生命周期 | Task 2 Step 1/5/6（每源一份、重置点、置位点） |
| §17.4 UI | Task 3 Step 1/2（按钮、loading、禁用）+ Task 2 Step 4（`tmdbOff` 守卫） |
| §17.5 呈现（4 行） | TMDB 列 → Task 3 Step 3；NFO 列 → Task 3 Step 4；左栏提示 → Task 4 Step 2；对话框 → Task 4 Step 3/4 |
| §17.6 一致性 | Task 1（纯函数）+ Task 2 Step 7/8（两处调用） |
| §17.7 验证 | Task 1（两个脚本 + 变异）+ Task 5 Step 2/3/5 |
| §17.8 不在本期 | 无落点（有意） |
| §17.9 修订 #2 | 无代码；spec 已记录 |

无遗漏。

**2. 占位符扫描**：无 TBD / TODO / 「类似 Task N」/ 「加上适当的错误处理」。每个代码步骤都给了可直接粘贴的完整代码。

**3. 类型与命名一致性**（逐字核对过）：

- `scrapeGate.js` 导出三个函数，Task 2 的 import 逐字对应（`tmdbPendingScrape` 以 `isTmdbPendingScrape` 别名引入，避开与同名 computed 的遮蔽 —— 这一条是自查时抓出来的，原稿会运行期报「not a function」）。
- `renamePayload.js` 的 `buildRenamePayload` 入参名（`fileIds` / `folderTemplate` / `createSeasonFolder` / `episodePadDigits` / `seasonPadDigits` / `tmdbOverrides` / `generateNfo` / `nfoOverwrite`）在 Task 2 的两个调用点逐字一致；`mode` 取 `'preview'` / `'execute'`。
- store 导出 `scraped` / `scraping` / `tmdbDisabled` / `tmdbPendingScrape` / `nfoNeedsScrape` / `scrapeTitles`，Task 3/4 消费的名字逐字对应（模板里是 kebab-case：`ws.tmdbPendingScrape` → `:tmdb-pending-scrape`）。
- 结果上的字段名 `nfo_blocked_by_scrape` 在 Task 2（写）与 Task 4（读）逐字一致。

**4. Review Focus**：五条已列在开头，每条的落点写在括号里。其中四条**没有**自动化判据 —— 这是本仓库前端的既知缺口（R44 已记录并接受），补偿是 Task 5 Step 5 的六项精确走查，而非假装覆盖。

**5. 一处需要执行者注意的既有事实**（不是本计划引入，但会碰到）：`payload.path` 后端**不读**（`api/renamer.py` 只用 `file_ids` / `source` / `conflict_strategy`）。计划逐字保留了它，不做删除 —— 删它属于另一个改动，且会让本计划的断言多一条无关的失败面。




