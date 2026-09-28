// 并发池的机械判据。零依赖，只用 node 内置模块（与其余 check-*.mjs 同规格）。
import { readFileSync } from 'node:fs'
import { runWithConcurrency, resolveConcurrency, sleep } from '../src/stores/renameRunner.js'

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

// --- 在途数不得超过 limit（把 limit 当摆设、一次全发 → 本断言红）---
{
  let active = 0
  let peak = 0
  const items = Array.from({ length: 10 }, (_, i) => i)
  await runWithConcurrency(items, 3, async () => {
    active += 1
    peak = Math.max(peak, active)
    await sleep(5)
    active -= 1
  })
  assert('在途数峰值 == limit', peak, 3)
}

// --- 结果按输入顺序（直接返回完成顺序 → 本断言红）---
{
  const items = [0, 1, 2, 3]
  const { results } = await runWithConcurrency(items, 4, async (n) => {
    await sleep((4 - n) * 10)   // 先发的更慢, 完成顺序与输入顺序相反
    return n * 10
  })
  assert('results 按输入顺序', results, [0, 10, 20, 30])
}

// --- 单个 worker 抛错不影响其余（Promise.all 直接 reject → 本断言红）---
{
  const { results, failures } = await runWithConcurrency([1, 2, 3], 3, async (n) => {
    if (n === 2) throw new Error('boom')
    return n
  })
  assert('失败不阻断其余（前）', results[0], 1)
  assert('失败不阻断其余（后）', results[2], 3)
  assert('失败的槽位为空', results[1], undefined)
  assert('失败记入 failures', failures.length, 1)
  assert('failures 带原始下标', failures[0].index, 1)
  assert('failures 带原始条目', failures[0].item, 2)
}

// --- onProgress 次数 == items.length（只在成功时调 → 本断言红）---
{
  let calls = 0
  await runWithConcurrency([1, 2, 3], 2, async () => { throw new Error('x') },
    { onProgress: () => { calls += 1 } })
  assert('onProgress 次数 == 条目数（含失败）', calls, 3)
}

// --- failures 必须按输入下标排序，而不是完成顺序 ---
// **这条断言需要两个以上的失败才可观测**: 只有一个失败时任何顺序都一样, 所以
// 原来那几条用例对 `failures.sort(...)` 这一行是失明的（实测: 删掉排序, 12 个
// 变异里只有它存活）。
{
  const { failures } = await runWithConcurrency([0, 1, 2, 3], 4, async (n) => {
    await sleep((4 - n) * 5)   // 下标小的先睡 → 完成顺序与输入顺序**相反**
    throw new Error('boom')
  })
  assert('failures 按输入下标排序', failures.map(f => f.index), [0, 1, 2, 3])
}

// --- limit 未传必须抛错，不得兜底（加默认值 → 本断言红）---
{
  let threw = false
  try {
    await runWithConcurrency([1], undefined, async () => 1)
  } catch {
    threw = true
  }
  assert('limit 未传时抛错而非兜底', threw, true)
}

// --- 批次内目标重名必须降级为串行（spec §10.1）---
{
  const base = { targets: ['/m/a.mkv', '/m/b.mkv'], localConcurrency: 4, openlistConcurrency: 2 }
  assert('无重名 + local → 用本地并发',
    resolveConcurrency({ ...base, source: 'local' }), 4)
  assert('无重名 + openlist → 用 OpenList 并发',
    resolveConcurrency({ ...base, source: 'openlist' }), 2)
  assert('有重名 → 降级为 1',
    resolveConcurrency({ ...base, source: 'local', targets: ['/m/a.mkv', '/m/a.mkv'] }), 1)
  assert('有重名时 openlist 也降级为 1',
    resolveConcurrency({ ...base, source: 'openlist', targets: ['/m/a.mkv', '/m/a.mkv'] }), 1)
}

// --- 死设置防复发：workspace.js 里的并发数必须来自 settingsStore ---
// 这条断言**只能在这里加**: 它检查的是 workspace.js 里那一行, 而那个文件到本任务
// 才被改。提前放进 Task 7 会让 Task 7–9 的 check-all 一直红 —— 一条恒红的判据
// 等于没有判据（没人会去看它为什么红）。
//
// **与计划里的写法有一处出入（有意的）**: 计划写的是直接拿
// `runWithConcurrency(` 的第二参去匹配 `settingsStore.*concurrency`，而本任务的
// 实现里第二参是局部变量 `limit`（settingsStore 是在上一步
// `resolveConcurrency({...})` 里读的）—— 那一版**永远为红**（实测捕获到 "limit"）。
// 恒红的判据等于没有判据，故改为检查「limit 从哪来」，分三条把同一件事钉住：
// 传进去的不得是字面量、它的声明处必须读 settingsStore 的并发设置、以及那个
// 设置的**判据输入**（预览行的 new_path）必须真的接上。
{
  const src = readFileSync(new URL('../src/stores/workspace.js', import.meta.url), 'utf8')

  // 1. 传给 runWithConcurrency 的是标识符，不是字面量
  //    （把 `items, limit,` 改成 `items, 4,` → 本断言红）
  const call = src.match(/runWithConcurrency\(\s*[^,]+,\s*([^,]+),/)
  const arg = call ? call[1].trim() : ''
  assert('传给 runWithConcurrency 的 limit 不是字面量',
    /^[A-Za-z_$][\w$]*$/.test(arg), true)

  // 2. 那个标识符的声明处读的是 settingsStore 的并发设置
  //    （把 `localConcurrency: settingsStore.localConcurrency` 改成 `localConcurrency: 4`
  //     → 本断言红）
  const decl = src.match(/const\s+limit\s*=\s*resolveConcurrency\(\{([\s\S]*?)\}\)/)
  const declArgs = decl ? decl[1] : ''
  assert('并发上限从 settingsStore 读（不是字面量）',
    /settingsStore\.\w*[Cc]oncurrency/.test(declArgs), true)

  // 3. 重名判据的**输入**必须真的接上：resolveConcurrency 读的是预览行的
  //    `new_path`，而它来自后端预览响应 —— 不把这一项抄进行构造里，每一行都是
  //    undefined，`new Set(targets).size !== targets.length` 恒真，并发上限永远
  //    降级为 1，上面两条断言**照样全绿**（它们只看 settingsStore 有没有被读）。
  //    删掉 workspace.js 里 `new_path: pv.new_path || '',` 那一行 → 本断言红。
  //    只扫 buildPreview 这一段（到下一个函数为止），避免在别处找到替身。
  const bpStart = src.indexOf('async function buildPreview')
  const bpEnd = src.indexOf('function updatePreview', bpStart)
  const bp = bpStart >= 0 && bpEnd > bpStart ? src.slice(bpStart, bpEnd) : ''
  assert('预览行带 new_path（并发降级判据的输入）',
    /new_path:\s*pv\.new_path/.test(bp), true)
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
