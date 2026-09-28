// 并发池的机械判据。零依赖，只用 node 内置模块（与其余 check-*.mjs 同规格）。
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

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
