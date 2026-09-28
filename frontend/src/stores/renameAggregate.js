// 逐文件响应 + 收尾响应 → 一个与后端 BatchRenameResult **同形状**的对象。
//
// 同形状是硬要求: ResultDialog.vue 直接消费 BatchRenameResult 的字段, 不改它。
//
// 计数**直接用后端给的 executed/skipped/failed 字段求和**, 绝不按 result.status
// 重判 —— 重判会把 local_renamer.count_result 那套规则复制成第二份, 两份必然
// 漂移（spec R11）。判据见 scripts/check-rename-aggregate.mjs 的第一块。
//
// 零依赖纯函数: node 要能直接 import 它跑断言。

export function aggregateBatch({ items, finalize = null, nfoBlockedByScrape = false, source = 'local' }) {
  const results = []
  const errors = []
  const nfoWritten = []
  const nfoCarried = []
  const nfoSkipped = []
  let executed = 0
  let skipped = 0
  let failed = 0

  for (const item of items) {
    executed += item.executed || 0
    skipped += item.skipped || 0
    failed += item.failed || 0

    if (item.result) {
      results.push(item.result)
      if (item.result.error) errors.push(item.result.error)
    }
    if (item.nfo_written) nfoWritten.push(...item.nfo_written)
    if (item.nfo_carried) nfoCarried.push(...item.nfo_carried)
    if (item.nfo_skipped) nfoSkipped.push(...item.nfo_skipped)
  }

  if (finalize) {
    if (finalize.nfo_written) nfoWritten.push(...finalize.nfo_written)
    if (finalize.nfo_skipped) nfoSkipped.push(...finalize.nfo_skipped)
  }

  return {
    success: failed === 0,
    source,
    executed,
    skipped,
    failed,
    total: items.length,
    // 批次内冲突由后端报在 result 上, 这里没有额外的批次级冲突可报。
    conflicts: [],
    results,
    errors,
    nfo_written: nfoWritten,
    nfo_carried: nfoCarried,
    nfo_skipped: nfoSkipped,
    dry_run: false,
    nfo_blocked_by_scrape: nfoBlockedByScrape,
  }
}
