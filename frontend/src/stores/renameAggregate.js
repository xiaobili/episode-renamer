// 逐文件响应 + 收尾响应 → 一个与后端 BatchRenameResult **同形状**的对象。
//
// 同形状是硬要求: ResultDialog.vue 直接消费 BatchRenameResult 的字段, 不改它。
//
// 计数**直接用后端给的 executed/skipped/failed 字段求和**, 绝不按 result.status
// 重判 —— 重判会把 local_renamer.count_result 那套规则复制成第二份, 两份必然
// 漂移（spec R11）。判据见 scripts/check-rename-aggregate.mjs 的第一块。
//
// 零依赖纯函数: node 要能直接 import 它跑断言。

export function aggregateBatch({
  items, finalize = null, folders = null, nfoBlockedByScrape = false, source = 'local',
}) {
  const results = []
  const errors = []
  const nfoWritten = []
  const nfoCarried = []
  const nfoSkipped = []
  const strmWritten = []
  const strmSkipped = []
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
    // STRM 只来自逐文件响应（收尾不写 strm）, 所以这里没有 finalize 分支。
    if (item.strm_written) strmWritten.push(...item.strm_written)
    if (item.strm_skipped) strmSkipped.push(...item.strm_skipped)
  }

  // 收尾响应只并这两项, **不并 nfo_carried**: 携带既有 NFO 是**每文件**的事
  // （跟着那个视频一起搬走）, 由 /rename/execute 报在单文件响应上; 收尾响应里
  // 根本没有这个字段。这不是「别的字段都并了、唯独漏一个」, 别顺手补上。
  if (finalize) {
    if (finalize.nfo_written) nfoWritten.push(...finalize.nfo_written)
    if (finalize.nfo_skipped) nfoSkipped.push(...finalize.nfo_skipped)
  }

  // 剧集文件夹改名是**发生在途中的第四个动作**（execute → finalize → folders）,
  // 既不属于逐文件响应, 也不属于 finalize。它的计数是「部剧」而不是「个文件」,
  // 所以不参与 executed / skipped / failed —— 把 1 个目录算成 1 个失败会误导用户
  // 以为有某一集没改名。
  const foldersRenamed = folders?.renamed || []
  const foldersSkipped = folders?.skipped || []

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
    strm_written: strmWritten,
    strm_skipped: strmSkipped,
    folders_renamed: foldersRenamed,
    folders_skipped: foldersSkipped,
    dry_run: false,
    nfo_blocked_by_scrape: nfoBlockedByScrape,
  }
}
