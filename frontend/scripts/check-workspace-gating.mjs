// 「扫描路径绝不出网 / scraped 门控」的**运行期**判据。
//
// 为什么需要它：`check-rename-payload.mjs` 只钉得住纯函数 `buildRenamePayload` 的
// 输出，钉不住「谁在什么时刻把 `scraped` 传了进去」。而本功能最贵的两个缺陷都不在
// 纯函数里 —— 它们住在 workspace store 的状态生命周期里：
//   · `scraped` 在 await **之前**乐观置位 → 刮削在途时「载荷已带 TMDB、表还是旧表」
//     （用户此时发起执行会写出没见过的文件名，spec §17.4）；
//   · 刮削**失败**时不回退 → 一次 401 之后 TMDB 列一直说「未启用」，把「Key 无效」
//     说成「去设置页打开开关」，且后续每次自动回刷都继续带着被拒的 Key 重试（§17.3）。
// 两者都只有在**真加载 store、真发请求**时才看得见，故这里在 node 里加载真实的
// workspace store，用自定义 axios adapter 截获请求载荷。
//
// 本文件的前身是一次性探针（不在仓库内）。它被提升为仓库判据的理由，正是本计划
// 反复栽的那个形态：**一次性跑过的东西不会在回归时再跑**。
//
// 自包含、零依赖（与 check-settings-schema.mjs 同规格）：
//   · 自注册一个「补 .js」的 ESM loader —— 仓库源码用打包器风格的无扩展名相对导入；
//   · 桩掉 localStorage / window（settings store 建在它们之上）；
//   · 装一个 axios adapter。
// 运行：node scripts/check-workspace-gating.mjs

import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { registerHooks } from 'node:module'

// registerHooks 是同步、同线程的钩子 —— 关键在「同步」：钩子只影响**注册之后**的
// 动态 import，而下面所有 import 都在注册之后。用 module.register + 外部 loader
// 文件则做不到自包含，用 register + data: URL 又多一层解析差异。
if (typeof registerHooks !== 'function') {
  // 静默跳过是最坏的选择（那又是一条「永远不会失败的检查」）—— 明确非零退出。
  console.error('需要 node >= 22.15（module.registerHooks）。')
  process.exit(2)
}
registerHooks({
  resolve(specifier, context, nextResolve) {
    // 只补**无扩展名**的相对导入（'./files' → './files.js'）。有扩展名的、裸包名
    // 一律原样交给 node —— 改错一个就会让 node_modules 的解析路径跟着变。
    if (
      (specifier.startsWith('./') || specifier.startsWith('../')) &&
      context.parentURL &&
      !/\.[a-z]+$/i.test(specifier)
    ) {
      const url = new URL(specifier + '.js', context.parentURL)
      if (existsSync(fileURLToPath(url))) return nextResolve(specifier + '.js', context)
    }
    return nextResolve(specifier, context)
  },
})

// 内存版 localStorage：settings store 在模块顶层就会读它，缺了直接抛。
const mem = new Map()
const ls = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
}
globalThis.localStorage = ls
globalThis.window = globalThis
globalThis.window.localStorage = ls

const FE = new URL('..', import.meta.url)
const { createPinia, setActivePinia } = await import(new URL('node_modules/pinia/dist/pinia.mjs', FE).href)
const request = (await import(new URL('src/api/request.js', FE).href)).default
const { useWorkspaceStore } = await import(new URL('src/stores/workspace.js', FE).href)

const results = []
function check(name, cond, extra = '') {
  results.push(`${cond ? 'PASS' : 'FAIL'} ${name}${cond ? '' : '  <<< ' + extra}`)
}
const tick = (ms = 0) => new Promise(r => setTimeout(r, ms))

// ---------------------------------------------------------------------------
// axios adapter：截获载荷，并按开关模拟「挂起的预览」与「401」两种后端行为。
//
// **陷阱（审查者已为此付过一个周期）**：adapter 对非 2xx 必须**显式 reject**。
// `validateStatus` 不作用于 adapter 的返回值 —— 直接 resolve `{ status: 401 }`
// 会被 axios 当成**成功**，于是「刮削失败要回退置位」这条用例永远不会红，
// 写出来就是又一条「永远不会失败的检查」。
// ---------------------------------------------------------------------------
let calls = []
let scanFiles = []
let hold = null // 非 null 时预览请求挂起，直到 release()；用来观察「在途」状态
let heldResolvers = []
let failPreview = null // 非 null 时预览请求以 401 reject
const release = () => {
  hold = null
  const pending = heldResolvers
  heldResolvers = []
  pending.forEach(fn => fn())
}

request.defaults.adapter = async (config) => {
  const body = config.data ? JSON.parse(config.data) : null
  calls.push({ url: config.url, body })

  if (config.url === '/rename/preview' && failPreview) {
    const err = new Error('Request failed with status code 401')
    err.response = { status: 401, data: { detail: failPreview }, headers: {}, config }
    throw err
  }
  if (config.url === '/rename/preview' && hold) {
    // 挂着不返回：让调用方能在「请求已发出、响应未到」的那一段上做断言。
    await new Promise(resolve => heldResolvers.push(resolve))
  }

  let data = {}
  if (config.url === '/scan') {
    data = { files: scanFiles, total_files: scanFiles.length }
  } else if (config.url === '/rename/preview') {
    // 响应随载荷里的 tmdb_enabled 变化 —— 与后端一致：未刮削的那一发返回**刮削前**
    // 的文件名（后端此时给每行都是 disabled / 无标题）。这样「在途」那一段里
    // 「载荷已带 TMDB、表还是旧表」才是可断言的事实，而不是一句注释。
    const scrapedReq = body?.tmdb_enabled === true
    data = {
      results: scanFiles.map(f => ({
        original_path: f.path,
        show_name: 'Some Show',
        season: 1,
        episode: 1,
        new_filename: scrapedReq ? 'Some Show - S01E01 - A Title.mkv' : f.filename,
        tmdb_status: scrapedReq ? 'matched' : 'disabled',
        title: scrapedReq ? 'A Title' : '',
      })),
    }
  } else if (config.url === '/rename/dry-run' || config.url === '/rename/execute') {
    data = { renamed: [], skipped: [], errors: [], nfo_written: [], nfo_skipped: [] }
  }
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

setActivePinia(createPinia())
const ws = useWorkspaceStore()
const last = url => [...calls].reverse().find(c => c.url === url)

// ---------------------------------------------------------------------------
// 0. 静态判据：`scraped` 的生命周期点与「传进去的是状态而不是字面量」。
//    运行期断言看不出「载荷里写死 true」，而写死 true 会让整条门控静默失效
//    （而且它**看起来**完全正常：所有请求都带 TMDB 设置）—— 故必须读源码。
// ---------------------------------------------------------------------------
const wsSrc = readFileSync(new URL('src/stores/workspace.js', FE), 'utf8')

// 取某个函数名之后的**那一个**函数体（按花括号配平），而不是「文件里某处出现过」。
// 不这么做的话，删掉 doScan 里那一行，lazy 正则会在 doOpenListScan 里找到替身，
// 检查照绿 —— 正是本计划栽过的「查错了东西」。
function bodyOf(src, marker) {
  const start = src.indexOf(marker)
  if (start < 0) return ''
  let depth = 0
  for (let i = src.indexOf('{', start); i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(start, i + 1)
    }
  }
  return src.slice(start)
}

check('buildPreview 的载荷用的是 scraped.value，不是字面量',
  bodyOf(wsSrc, 'async function buildPreview').includes('scraped: scraped.value'))
check('executeAction 的载荷用的是 scraped.value，不是字面量',
  bodyOf(wsSrc, 'async function executeAction').includes('scraped: scraped.value'))

// 生命周期点（spec §17.3）：初始每源一份 + 重置三处 + 置位两处 + 失败回退一处。
check('初始值「每源一份」（sourceStates 里两个 scraped: false）',
  (wsSrc.match(/scraped: false/g) || []).length === 2,
  String((wsSrc.match(/scraped: false/g) || []).length))
check('doScan 重置 scraped', bodyOf(wsSrc, 'async function doScan').includes('scraped.value = false'))
check('doOpenListScan 重置 scraped', bodyOf(wsSrc, 'async function doOpenListScan').includes('scraped.value = false'))
check('clearAll 重置 scraped', bodyOf(wsSrc, 'function clearAll').includes('scraped.value = false'))
check('scrapeTitles 置位 scraped', bodyOf(wsSrc, 'async function scrapeTitles').includes('scraped.value = true'))
check('pickShow 置位 scraped', bodyOf(wsSrc, 'async function pickShow').includes('scraped.value = true'))
check('scrapeTitles 失败回退到 previous（不是硬编码 false）',
  bodyOf(wsSrc, 'async function scrapeTitles').includes('scraped.value = previous'))

// ---------------------------------------------------------------------------
scanFiles = [
  { id: 'id-1', path: '/media/tv/Show/Show.S01E01.mkv', filename: 'Show.S01E01.mkv' },
  { id: 'id-2', path: '/media/tv/Show/Show.S01E02.mkv', filename: 'Show.S01E02.mkv' },
]
ws.path = '/media/tv/Show'

// --- 1. 扫描路径绝不出网 ---
calls = []
await ws.doScan()
const scanCall = last('/scan')
const p1 = last('/rename/preview').body
check('扫描请求本身不带任何 TMDB 字段',
  !('tmdb_enabled' in scanCall.body) && !('tmdb_api_key' in scanCall.body) && !('tmdb_language' in scanCall.body),
  JSON.stringify(Object.keys(scanCall.body)))
check('doScan 后 scraped === false', ws.scraped === false, String(ws.scraped))
check('扫描后的预览 tmdb_enabled 严格为 false', p1.tmdb_enabled === false, JSON.stringify(p1.tmdb_enabled))
check('扫描后的预览不含 tmdb_api_key', !('tmdb_api_key' in p1), JSON.stringify(Object.keys(p1)))
check('扫描后的预览不含 tmdb_language', !('tmdb_language' in p1))
check('扫描后的预览不含 tmdb_overrides', !('tmdb_overrides' in p1))
check('预览载荷不含 conflict_strategy', !('conflict_strategy' in p1))
check('预览 file_ids 来自扫描文件', JSON.stringify(p1.file_ids) === JSON.stringify(['id-1', 'id-2']), JSON.stringify(p1.file_ids))
check('预览 path 用扫描首行父目录', p1.path === '/media/tv/Show/', p1.path)
check('previewRows 已重建（2 行）', ws.previewRows.length === 2, String(ws.previewRows.length))
// 未刮削时后端返回的就是刮削前的文件名 —— 这张表就是用户看到的表。
check('未刮削时表里是刮削前的文件名', ws.previewRows[0].new_filename === 'Show.S01E01.mkv', ws.previewRows[0].new_filename)

// --- 2. tmdbPendingScrape / nfoNeedsScrape 谓词（设置页的开关也参与）---
check('未刮削 + TMDB 开着 → tmdbPendingScrape true', ws.tmdbPendingScrape === true)
check('未勾 NFO → nfoNeedsScrape false', ws.nfoNeedsScrape === false)
ws.generateNfo = true
check('勾 NFO + 未刮削 → nfoNeedsScrape true', ws.nfoNeedsScrape === true)

// --- 3. scrapeTitles 成功 ---
calls = []
await ws.scrapeTitles()
const p2 = last('/rename/preview').body
check('scrapeTitles 后 scraped === true', ws.scraped === true)
check('scraping 已复位', ws.scraping === false)
check('刮削后的预览带 tmdb_api_key', 'tmdb_api_key' in p2)
check('刮削后的预览带 tmdb_language', 'tmdb_language' in p2)
check('刮削后的预览带 tmdb_overrides', 'tmdb_overrides' in p2)
check('刮削后的预览 tmdb_enabled 取设置值(true)', p2.tmdb_enabled === true, JSON.stringify(p2.tmdb_enabled))
check('刮削后 nfoNeedsScrape false', ws.nfoNeedsScrape === false)
check('刮削后 tmdbPendingScrape false', ws.tmdbPendingScrape === false)
check('刮削后表里是带标题的新文件名', ws.previewRows[0].new_filename === 'Some Show - S01E01 - A Title.mkv', ws.previewRows[0].new_filename)

// --- 4. 设置页关闭 TMDB 时 scrapeTitles 不置位 ---
ws.scraped = false
const st = (await import(new URL('src/stores/settings.js', FE).href)).useSettingsStore()
st.tmdb.enabled = false
// 设置变更会触发 workspace 的 watch → 自动回刷一次预览；先让它落地，再清空计数，
// 否则会把那次回刷误记成 scrapeTitles 发的请求。
await tick(20)
calls = []
await ws.scrapeTitles()
check('TMDB 关闭时 scrapeTitles 不置位', ws.scraped === false)
check('TMDB 关闭时 scrapeTitles 不发请求', calls.length === 0, JSON.stringify(calls.map(c => c.url)))
check('TMDB 关闭时 nfoNeedsScrape false', ws.nfoNeedsScrape === false)
check('TMDB 关闭时 tmdbPendingScrape false', ws.tmdbPendingScrape === false)
st.tmdb.enabled = true

// --- 5. 重新扫描会重置 ---
ws.scraped = true
calls = []
await ws.doScan()
check('重新扫描重置 scraped', ws.scraped === false)
check('重新扫描的预览回到 tmdb_enabled false', last('/rename/preview').body.tmdb_enabled === false)

// --- 6. pickShow 置位 ---
ws.tmdbDialog.row = ws.previewRows[0]
ws.previewRows[0].show_name = 'Some Show'
calls = []
await ws.pickShow({ tv_id: 42, name: 'Some Show', year: 2020 })
check('pickShow 后 scraped === true', ws.scraped === true)
const p3 = last('/rename/preview').body
check('pickShow 的预览带重选表', JSON.stringify(p3.tmdb_overrides) === JSON.stringify({ 'Some Show': 42 }), JSON.stringify(p3.tmdb_overrides))
check('pickShow 的预览带 tmdb_api_key', 'tmdb_api_key' in p3)

// --- 7. executeAction（干跑）载荷与结果标记 ---
calls = []
await ws.executeAction(true)
const ex = last('/rename/dry-run').body
check('执行载荷带 conflict_strategy', 'conflict_strategy' in ex)
check('执行载荷 scraped=true 时带 Key', 'tmdb_api_key' in ex)
check('执行 file_ids 只含选中行', JSON.stringify(ex.file_ids) === JSON.stringify(['id-1', 'id-2']), JSON.stringify(ex.file_ids))
check('执行 path 用选中首行父目录', ex.path === '/media/tv/Show/', ex.path)
check('lastResult.dry_run 为 true', ws.lastResult.dry_run === true)
check('lastResult.nfo_blocked_by_scrape 为 false（已刮削）', ws.lastResult.nfo_blocked_by_scrape === false, String(ws.lastResult.nfo_blocked_by_scrape))

// 未刮削 + 勾了 NFO 时该标记为 true
ws.scraped = false
await ws.executeAction(true)
check('未刮削 + 勾 NFO → nfo_blocked_by_scrape true', ws.lastResult.nfo_blocked_by_scrape === true)
check('未刮削时执行载荷 tmdb_enabled false', last('/rename/dry-run').body.tmdb_enabled === false)
check('未刮削时执行载荷不含 Key', !('tmdb_api_key' in last('/rename/dry-run').body))

// --- 8. 每源一份 ---
ws.scraped = true
ws.switchSource('openlist')
check('切到未刮削的源 → scraped false', ws.scraped === false, String(ws.scraped))
ws.switchSource('local')
check('切回已刮削的源 → scraped true', ws.scraped === true, String(ws.scraped))

// --- 9. 在途刮削视为「未刮削」（spec §17.3，I2(b) 的运行期证据）---
// 这一段是谓词里 `|| scraping` 的**唯一**运行期证据：删掉那一项，下面两条立刻红。
// 先把 scraped 复位**再**勾 NFO：两次变更都会触发 watch 回刷，回刷落地后表里才是
// 「刮削前」的样子（若顺序反了，那次回刷会带着上一次的 scraped=true 重建表，
// 于是「在途时表还是旧表」这句话就演示不出来了）。
ws.scraped = false
ws.generateNfo = true // switchSource('openlist') 把它关掉了
await tick(20) // 让这次回刷落地，别把它混进「在途」那一段
check('在途之前：表里是刮削前的文件名', ws.previewRows[0].new_filename === 'Show.S01E01.mkv', ws.previewRows[0].new_filename)
calls = []
hold = []
const inflight = ws.scrapeTitles()
await tick()
const inflightPayload = last('/rename/preview').body
check('在途：scraped 已被乐观置位为 true', ws.scraped === true, String(ws.scraped))
check('在途：scraping 为 true', ws.scraping === true, String(ws.scraping))
// 这就是用户看到的那个矛盾：载荷已带 TMDB，而表里仍是刮削前的文件名。
check('在途：载荷已带 tmdb_api_key', 'tmdb_api_key' in inflightPayload)
check('在途：表里仍是刮削前的文件名（屏幕上的表还没被换掉）',
  ws.previewRows[0].new_filename === 'Show.S01E01.mkv', ws.previewRows[0].new_filename)
check('在途：tmdbPendingScrape 为 true —— TMDB 列说「未刮削」而不是「未启用」',
  ws.tmdbPendingScrape === true, String(ws.tmdbPendingScrape))
check('在途：nfoNeedsScrape 为 true —— 左栏 NFO 提示不提前消失',
  ws.nfoNeedsScrape === true, String(ws.nfoNeedsScrape))
release()
await inflight
check('刮削落地后 tmdbPendingScrape 变 false', ws.tmdbPendingScrape === false)
check('刮削落地后 nfoNeedsScrape 变 false', ws.nfoNeedsScrape === false)
check('刮削落地后 scraping 复位', ws.scraping === false)
check('刮削落地后表换成带标题的新文件名',
  ws.previewRows[0].new_filename === 'Some Show - S01E01 - A Title.mkv', ws.previewRows[0].new_filename)

// --- 10. 刮削失败要回退置位（spec §17.3，I2(a) 的运行期证据）---
// buildPreview 的 catch 里有 console.error(e)（运维用）。401 是本节**故意**制造的，
// 两条堆栈会把真正的 FAIL 淹掉 —— 收掉。只收这一段的，其余照旧。
const realConsoleError = console.error
const quiet = async (fn) => {
  console.error = () => {}
  try { return await fn() } finally { console.error = realConsoleError }
}
failPreview = 'TMDB API Key 无效'
ws.scraped = false
await quiet(() => ws.scrapeTitles())
check('401 之后 scraped 回退为 false（否则 TMDB 列会一直说「未启用」）',
  ws.scraped === false, String(ws.scraped))
check('401 之后 scraping 复位', ws.scraping === false)
check('401 之后 tmdbPendingScrape 仍为 true —— 成因是 Key 无效，不是「未启用」',
  ws.tmdbPendingScrape === true, String(ws.tmdbPendingScrape))
await ws.executeAction(true)
check('401 之后的执行载荷回到 tmdb_enabled false（不再带着被拒的 Key 重试）',
  last('/rename/dry-run').body.tmdb_enabled === false &&
    !('tmdb_api_key' in last('/rename/dry-run').body),
  JSON.stringify(Object.keys(last('/rename/dry-run').body)))
// 已刮削过的源再刮失败时回退到 previous（true），而不是一律 false ——
// 否则一次网络抖动会把用户已经刮好的状态也抹掉。
ws.scraped = true
await quiet(() => ws.scrapeTitles())
check('已刮削的源再刮失败 → 保持 true（回退到 previous 而非硬编码 false）',
  ws.scraped === true, String(ws.scraped))
failPreview = null

// --- 11. clearAll ---
ws.scraped = true
ws.clearAll()
await tick(10)
ws.resolveConfirm(true)
await tick(10)
check('clearAll 后 scraped false', ws.scraped === false, String(ws.scraped))

// --- 12. 导出的名字都在（模板里按名字取用；少一个就是运行期 undefined）---
for (const n of ['scraped', 'scraping', 'tmdbDisabled', 'tmdbPendingScrape', 'nfoNeedsScrape', 'scrapeTitles']) {
  check(`导出 ${n}`, ws[n] !== undefined)
}

console.log(results.join('\n'))
const failed = results.filter(r => r.startsWith('FAIL')).length
console.log(failed ? `\n${failed} 项失败 / 共 ${results.length} 项` : `\n全部通过（${results.length} 项）`)
process.exit(failed ? 1 : 0)
