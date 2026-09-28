// 「执行循环」的**运行期**判据。
//
// 为什么必须有它：本任务的两个 bug（`settled` 用 `map` 跳过空洞、预览行缺
// `new_path`）都是**运行期探针**挖出来的，而当时那批源码级断言**全绿**。
// check-execute-loop.mjs 那类文本断言看的是「文件里有没有这段字」，看不出
// 「参数顺序反了」「失败记录取的是 selected[0] 而不是 selected[i]」「landed 赋的是
// 空串」这类**语义**错误 —— 它们改完文本照样在。只有真跑一遍才现形。
//
// 技术照搬 check-workspace-gating.mjs（那门技术在仓库里本来就有，不是新发明）：
//   · 自注册一个「补 .js」的 ESM loader —— 仓库源码用打包器风格的无扩展名相对导入；
//   · 桩掉 localStorage / window（settings store 建在它们之上）；
//   · 装一个 axios adapter，截获载荷并按开关模拟后端行为；
//   · 加载**真实的** workspace store，驱动它跑一次 executeAction(false)。
//
// 陷阱（审查者已为此付过一个周期）：adapter 对非 2xx 必须**显式 reject**。
// `validateStatus` 不作用于 adapter 的返回值 —— 直接 resolve `{ status: 500 }`
// 会被 axios 当成**成功**，于是「失败不吞整批」这条用例永远不会红。
//
// 运行：node scripts/check-execute-behaviour.mjs

import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { registerHooks } from 'node:module'

if (typeof registerHooks !== 'function') {
  // 静默跳过是最坏的选择（那又是一条「永远不会失败的检查」）—— 明确非零退出。
  console.error('需要 node >= 22.15（module.registerHooks）。')
  process.exit(2)
}
registerHooks({
  resolve(specifier, context, nextResolve) {
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
const { useSettingsStore } = await import(new URL('src/stores/settings.js', FE).href)

const results = []
function check(name, cond, extra = '') {
  results.push(`${cond ? 'PASS' : 'FAIL'} ${name}${cond ? '' : '  <<< ' + extra}`)
}
const tick = (ms = 0) => new Promise(r => setTimeout(r, ms))

// ---------------------------------------------------------------------------
// 夹具：4 个文件。f2 回 500（失败），f3 报 skipped_conflict（未落地，不进 landed），
// f1 / f4 正常改名。四个目标名互不相同 —— 否则 resolveConcurrency 会（正确地）
// 降级为串行，并发那条断言就测不到东西了。
// ---------------------------------------------------------------------------
const FILES = [
  { id: 'f1', path: '/m/S/Show.S01E01.mkv', filename: 'Show.S01E01.mkv' },
  { id: 'f2', path: '/m/S/Show.S01E02.mkv', filename: 'Show.S01E02.mkv' },
  { id: 'f3', path: '/m/S/Show.S01E03.mkv', filename: 'Show.S01E03.mkv' },
  { id: 'f4', path: '/m/S/Show.S01E04.mkv', filename: 'Show.S01E04.mkv' },
]
const byId = id => FILES.find(f => f.id === id)
const newPathOf = f => `/m/S/Show - ${f.filename.slice(5, 11)}.mkv`   // S01E01 → 各不同
const GROUP_NFO = '/m/S/Show/tvshow.nfo'

let calls = []
let inFlight = 0
let peak = 0
let failExecuteIds = new Set()
let failFinalize = false

const reply = (config, data) => ({ data, status: 200, statusText: 'OK', headers: {}, config })
const reject = (config, status, detail) => {
  const err = new Error(`Request failed with status code ${status}`)
  err.response = { status, data: { detail }, headers: {}, config }
  return err
}

request.defaults.adapter = async (config) => {
  const body = config.data ? JSON.parse(config.data) : null
  calls.push({ url: config.url, body })

  if (config.url === '/scan') {
    return reply(config, { files: FILES, total_files: FILES.length })
  }

  if (config.url === '/rename/preview') {
    return reply(config, {
      results: FILES.map(f => ({
        original_path: f.path,
        original_filename: f.filename,
        new_path: newPathOf(f),
        new_filename: newPathOf(f).split('/').pop(),
        show_name: 'Show', season: 1, episode: Number(f.filename.slice(5, 7)),
        tmdb_status: 'disabled', title: '',
      })),
    })
  }

  if (config.url === '/rename/execute') {
    // 在途峰值：进 adapter 就 +1，出就 -1 —— 这就是「同时有几个请求在路上」。
    inFlight += 1
    peak = Math.max(peak, inFlight)
    await tick(25)
    inFlight -= 1

    if (failExecuteIds.has(body.file_id)) throw reject(config, 500, '磁盘炸了')

    const f = byId(body.file_id)
    // f3 走「目标已存在，跳过」：状态不在后端 _NO_LANDING_STATUSES 之外 → 不算落地。
    const skipped = body.file_id === 'f3'
    const landed = !skipped
    return reply(config, {
      success: landed,
      source: 'local',
      file_id: body.file_id,
      result: {
        id: f.id,
        original_path: f.path,
        new_path: landed ? newPathOf(f) : f.path,
        original_filename: f.filename,
        new_filename: landed ? newPathOf(f).split('/').pop() : f.filename,
        success: landed,
        status: landed ? 'renamed' : 'skipped_conflict',
        error: null,
      },
      executed: landed ? 1 : 0,
      skipped: landed ? 0 : 1,
      failed: 0,
      nfo_written: [], nfo_carried: [], nfo_skipped: [],
    })
  }

  if (config.url === '/rename/finalize') {
    if (failFinalize) throw reject(config, 500, '收尾炸了')
    // 带一条组级 NFO —— 结果对话框要能把它并进来，才谈得上「收尾真的接了」。
    return reply(config, { nfo_written: [{ path: GROUP_NFO, scope: 'tvshow' }], nfo_skipped: [] })
  }

  return reply(config, {})
}

setActivePinia(createPinia())
const ws = useWorkspaceStore()
const st = useSettingsStore()

const executes = () => calls.filter(c => c.url === '/rename/execute')
const finalizes = () => calls.filter(c => c.url === '/rename/finalize')

// ---------------------------------------------------------------------------
// 场景 A：4 个文件、其中一个 500 —— 断言 1~4
// ---------------------------------------------------------------------------
st.localConcurrency = 2          // 断言 4 的前提：设置是 2，而不是默认的 4
ws.path = '/m/S'
ws.generateNfo = true            // 收尾（finalize）只在勾了 NFO 时才走
await ws.doScan()
await tick(30)                   // 让设置变更引发的自动回刷落地，别混进下面的计数
calls = []
peak = 0
failExecuteIds = new Set(['f2'])
await ws.executeAction(false)

// --- 1. 逐文件请求：N 个文件 N 次 /rename/execute，每次带**单数** file_id ---
check('4 个文件发出 4 次 /rename/execute', executes().length === 4, String(executes().length))
check('每次执行都带单数 file_id',
  executes().every(c => typeof c.body.file_id === 'string' && c.body.file_id) &&
    executes().map(c => c.body.file_id).join(',') === 'f1,f2,f3,f4',
  JSON.stringify(executes().map(c => c.body.file_id)))
// `every` 对空数组恒真 —— 前面那条计数断言已经挡住「一个请求都没发」的情形，
// 这里再显式要求非空，免得这条自身在空集上恒绿。
check('每次执行都不带 fileIds（批量形态）',
  executes().length > 0 && executes().every(c => !('file_ids' in c.body)),
  JSON.stringify(executes().map(c => Object.keys(c.body).filter(k => k === 'file_ids'))))

// --- 2. 部分失败不吞整批 ---
check('部分失败时结果仍然产出（对话框打开）', ws.resultDialog === true)
check('失败计 1、执行计 2、跳过计 1',
  ws.lastResult?.failed === 1 && ws.lastResult?.executed === 2 && ws.lastResult?.skipped === 1,
  `failed=${ws.lastResult?.failed} executed=${ws.lastResult?.executed} skipped=${ws.lastResult?.skipped}`)
check('结果里仍列出全部 4 个文件', ws.lastResult?.results?.length === 4,
  String(ws.lastResult?.results?.length))
check('失败那一行报的是**它自己**的文件名',
  ws.lastResult?.results?.find(r => r.status === 'failed')?.original_filename === 'Show.S01E02.mkv',
  JSON.stringify(ws.lastResult?.results?.find(r => r.status === 'failed')?.original_filename))

// --- 3. 收尾在全部执行之后，且 landed 恰好是落地文件的真实落点 ---
check('收尾只发一次', finalizes().length === 1, String(finalizes().length))
check('收尾排在所有执行之后',
  calls.findIndex(c => c.url === '/rename/finalize') >
    calls.map(c => c.url).lastIndexOf('/rename/execute'))
check('landed 恰好是落地文件的真实落点（f1/f4，不含失败的 f2 与跳过的 f3）',
  JSON.stringify(finalizes()[0]?.body?.landed) ===
    JSON.stringify({ f1: newPathOf(byId('f1')), f4: newPathOf(byId('f4')) }),
  JSON.stringify(finalizes()[0]?.body?.landed))
check('收尾的 file_ids 是全部选中文件',
  JSON.stringify(finalizes()[0]?.body?.file_ids) === JSON.stringify(['f1', 'f2', 'f3', 'f4']),
  JSON.stringify(finalizes()[0]?.body?.file_ids))
check('组级 NFO 并入结果（收尾真的接了）',
  (ws.lastResult?.nfo_written || []).some(n => n.path === GROUP_NFO),
  JSON.stringify(ws.lastResult?.nfo_written))

// --- 4. 并发遵守设置 ---
// 断言 == 2 而不是计划里的 <= 2：`<= 2` 对「永远降级为串行」（峰值 1）**照样为真**，
// 而那正是本任务修掉的那个死设置 bug —— 一条被它放过的判据等于没钉住。
check('在途峰值 == localConcurrency（2）',
  peak === 2, `peak=${peak} localConcurrency=${st.localConcurrency}`)

// ---------------------------------------------------------------------------
// 场景 B：收尾回 500 —— 断言 5（F1：收尾失败不得吞掉整批结果）
// ---------------------------------------------------------------------------
failFinalize = true
await ws.doScan()
await tick(30)
calls = []
// **必须清掉上一场景留下的结果与对话框状态**：否则「收尾失败时结果对话框仍然打开」
// 会因为 A 场景把它置成了 true 而**恒真** —— 一条被自己上一段喂绿的判据。
ws.resultDialog = false
ws.lastResult = null
await ws.executeAction(false)

check('收尾失败时结果对话框仍然打开', ws.resultDialog === true)
check('收尾失败时改名结果完好（2 执行 / 1 失败 / 1 跳过）',
  ws.lastResult?.executed === 2 && ws.lastResult?.failed === 1 && ws.lastResult?.skipped === 1,
  `executed=${ws.lastResult?.executed} failed=${ws.lastResult?.failed} skipped=${ws.lastResult?.skipped}`)
check('收尾失败时降级为「没有组级 NFO」',
  (ws.lastResult?.nfo_written || []).length === 0,
  JSON.stringify(ws.lastResult?.nfo_written))
check('收尾失败时如实告知是哪一步没做成（不是「操作失败」）',
  ws.toast.type === 'warning' && ws.toast.msg.startsWith('重命名已完成，但剧集级 NFO 未写出'),
  `${ws.toast.type} / ${ws.toast.msg}`)
check('收尾失败时 executing 已复位', ws.executing === false && ws.executeDryRun === false)

console.log(results.join('\n'))
const failed = results.filter(r => r.startsWith('FAIL')).length
console.log(failed ? `\n${failed} 项失败 / 共 ${results.length} 项` : `\n全部通过（${results.length} 项）`)
process.exit(failed ? 1 : 0)
