import { aggregateBatch } from '../src/stores/renameAggregate.js'

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

// --- 计数用**后端给的字段**, 不按 status 重判 ---
// 故意喂一条自相矛盾的响应: status 说 skipped_conflict（按 status 重判会记 skipped）,
// 而后端给的计数说 failed。聚合必须采信后者。
// 改成按 result.status 归类 → 本断言红（skipped 变 1、failed 变 0）。
{
  const agg = aggregateBatch({
    items: [{
      executed: 0, skipped: 0, failed: 1,
      result: { status: 'skipped_conflict', error: '目标文件已存在，跳过' },
    }],
  })
  assert('计数采信后端字段（failed）', agg.failed, 1)
  assert('计数采信后端字段（skipped）', agg.skipped, 0)
  assert('计数采信后端字段（executed）', agg.executed, 0)
}

// --- 计数逐条求和 ---
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' } },
      { executed: 0, skipped: 1, failed: 0, result: { status: 'skipped_conflict' } },
      { executed: 0, skipped: 0, failed: 1, result: { status: 'failed' } },
    ],
  })
  assert('executed 求和', agg.executed, 1)
  assert('skipped 求和', agg.skipped, 1)
  assert('failed 求和', agg.failed, 1)
  assert('total == 条目数', agg.total, 3)
  assert('success == (failed === 0)', agg.success, false)
}

// --- finalize 的两项并入批次结果（丢掉 finalize 响应 → 本断言红）---
{
  const agg = aggregateBatch({
    items: [{ executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' },
              nfo_written: ['/m/Show - S01E01.nfo'] }],
    finalize: { nfo_written: ['/m/tvshow.nfo'], nfo_skipped: [{ path: '/m/season.nfo', reason: '已存在' }] },
  })
  assert('finalize 的写入并入', agg.nfo_written, ['/m/Show - S01E01.nfo', '/m/tvshow.nfo'])
  assert('finalize 的跳过并入', agg.nfo_skipped, [{ path: '/m/season.nfo', reason: '已存在' }])
}

// --- 各条 NFO 三项拼接 ---
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' },
        nfo_carried: ['/m/a.nfo'], nfo_skipped: [{ path: '/m/x.nfo', reason: '已存在' }] },
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' },
        nfo_carried: ['/m/b.nfo'] },
    ],
  })
  assert('nfo_carried 拼接', agg.nfo_carried, ['/m/a.nfo', '/m/b.nfo'])
  assert('nfo_skipped 拼接', agg.nfo_skipped, [{ path: '/m/x.nfo', reason: '已存在' }])
}

// --- errors 只收非空 error ---
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed', error: null } },
      { executed: 0, skipped: 0, failed: 1, result: { status: 'failed', error: '磁盘满了' } },
    ],
  })
  assert('errors 只收非空', agg.errors, ['磁盘满了'])
}

// --- 空批次不崩 ---
{
  const agg = aggregateBatch({ items: [] })
  assert('空批次 total 为 0', agg.total, 0)
  assert('空批次 success 为 true', agg.success, true)
}

// --- results 必须按输入顺序收齐 ---
// 少了这条, 删掉 `results.push(item.result)` **没有任何断言会红** —— 后果是
// ResultDialog 的明细表**静默消失**: 汇总数字还在, 每一行的详情没了。
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed', new_filename: 'a.mkv' } },
      { executed: 0, skipped: 1, failed: 0, result: { status: 'skipped_conflict', new_filename: 'b.mkv' } },
      { executed: 0, skipped: 0, failed: 1, result: { status: 'failed', new_filename: 'c.mkv' } },
    ],
  })
  assert('results 按输入顺序收齐', agg.results.map(r => r.new_filename), ['a.mkv', 'b.mkv', 'c.mkv'])
}

// --- 执行结果恒不是干跑 ---
{
  const agg = aggregateBatch({ items: [], nfoBlockedByScrape: true })
  assert('dry_run 恒为 false', agg.dry_run, false)
  assert('nfo_blocked_by_scrape 透传', agg.nfo_blocked_by_scrape, true)
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
