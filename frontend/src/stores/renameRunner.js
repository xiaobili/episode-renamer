// 并发池。零依赖纯函数 —— node 可以直接 import 它跑断言（本项目没有前端测试
// 设施, 见 settingsSchema.js 的头注释）。
//
// `limit` **必须由调用方传入**: 函数内不设默认值, 未传直接抛错。兜底会让
// 「调用点忘了传设置」静默退化成某个魔数, 而那正是本次要修的那类 bug ——
// 设置项在页面上可改、实际不生效（spec 事实 10）。

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// 在途上限怎么定。抽成纯函数是为了让「批次内目标重名 → 降级串行」这条规则
// 能被 node 判据钉住 —— 内联在 workspace.js 里就没有任何机械判据能发现它被删掉。
//
// 为什么重名必须降级: 后端 check_conflict 的第二参是空列表, duplicate_in_batch
// 分支从不触发, 所以并发下两个文件会双双通过存在性检查 → 双写同一个目标
// （overwrite 策略下是数据丢失）。见 spec §10.1。
export function resolveConcurrency({ source, targets, localConcurrency, openlistConcurrency }) {
  const hasDuplicateTarget = new Set(targets).size !== targets.length
  if (hasDuplicateTarget) return 1
  return source === 'openlist' ? openlistConcurrency : localConcurrency
}

export async function runWithConcurrency(items, limit, worker, { onProgress, intervalMs = 0 } = {}) {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error(`runWithConcurrency 需要正整数 limit，收到 ${limit}`)
  }

  const results = new Array(items.length)
  const failures = []
  let done = 0
  let next = 0

  async function runOne(index) {
    try {
      if (intervalMs > 0) await sleep(intervalMs)
      results[index] = await worker(items[index], index)
    } catch (error) {
      // 单个文件失败不得中断整批（spec §8「一律跑完」）。记下来, 让调用方汇总。
      failures.push({ index, item: items[index], error })
    } finally {
      done += 1
      // 失败也算「完成」—— 否则进度条永远走不到 100%。
      if (onProgress) onProgress(done, items.length)
    }
  }

  // 固定数量的「泵」, 每个循环取下一个下标 —— 这样在途数恒等于 min(limit, n),
  // 不需要维护队列。
  async function pump() {
    for (;;) {
      const index = next
      next += 1
      if (index >= items.length) return
      await runOne(index)
    }
  }

  const pumps = []
  for (let i = 0; i < Math.min(limit, items.length); i += 1) pumps.push(pump())
  await Promise.all(pumps)

  // failures 按完成顺序 push, 这里按下标排回来 —— 让调用方的报错顺序可预测。
  failures.sort((a, b) => a.index - b.index)
  return { results, failures }
}
