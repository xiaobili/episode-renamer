import { readFileSync } from 'node:fs'

let failed = 0
function assert(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) { failed += 1; console.log('FAIL', label, '得到', JSON.stringify(actual), '期望', JSON.stringify(expected)) }
  else { console.log('PASS', label) }
}

const src = readFileSync(new URL('../src/stores/workspace.js', import.meta.url), 'utf8')

// --- 执行载荷是**单数**形态 ---
// 改回 `mode: 'execute'` + fileIds 会让互斥校验抛错，整条执行路径被 catch 吞成 toast。
assert('执行载荷用 mode: execute 且传 fileId（单数）',
  /mode:\s*'execute',\s*fileId:/.test(src), true)
assert('执行载荷不传 fileIds',
  /mode:\s*'execute'[\s\S]{0,200}?fileIds:/.test(src), false)

// --- 干跑走它自己的 mode ---
assert('干跑用 mode: dry-run', /mode:\s*'dry-run'/.test(src), true)

// --- 逐文件并发 ---
assert('用 runWithConcurrency 驱动', /runWithConcurrency\(/.test(src), true)

// --- 失败条目必须补记录：Array.from 而非 map（map 跳过空洞）---
// 删掉这处的 Array.from 换回 map，整批结果会在部分失败时全部消失。
assert('失败条目用 Array.from 补记录（map 会跳过空洞）',
  /const settled = Array.from\(results,/.test(src), true)

// --- 收尾必须在 buildPreview **之前** ---
// buildPreview 会重扫并刷新后端的文件缓存，之后 finalize 就重建不出同一批 plan。
{
  const fin = src.indexOf('finalizeRename(')
  const preview = src.indexOf('await buildPreview()', fin)
  assert('finalizeRename 在 executeAction 里被调用', fin > -1, true)
  assert('finalizeRename 出现在 buildPreview 之前', fin > -1 && preview > fin, true)
}

// --- 聚合 ---
assert('用 aggregateBatch 聚合结果', /aggregateBatch\(/.test(src), true)

// ---------------------------------------------------------------------------
// 以下两条**超出计划的七条**，是本任务在执行路径上另补的防复发判据。
// 两条各自钉住一个「删掉/改坏之后上面七条照样全绿」的缺口，理由写在各自头上。
// ---------------------------------------------------------------------------

// --- 并发上限不得是字面量：传进 runWithConcurrency 的必须是那个算出来的标识符 ---
// 缺口: 上面「用 runWithConcurrency 驱动」只看函数被调用过；把第二参改成字面量
// `4`（`const limit = resolveConcurrency({...})` 原样留着）时七条**全绿**，而设置
// 又一次变成摆设。这正是本功能要修的那类 bug（spec 事实 10），故单列一条。
{
  const call = src.match(/runWithConcurrency\(\s*[^,]+,\s*([^,]+),/)
  const arg = call ? call[1].trim() : ''
  assert('传给 runWithConcurrency 的 limit 不是字面量',
    /^[A-Za-z_$][\w$]*$/.test(arg), true)
}

// --- 重名判据的**输入**必须真的接上：预览行的 new_path ---
// 缺口: resolveConcurrency 读的是预览行的 `new_path`，而它来自后端预览响应 ——
// 行构造里不抄这一项，每一行都是 undefined，`new Set(targets).size !== targets.length`
// 恒真，并发上限永远降级为 1，而上面所有断言**照样全绿**（它们只看 settingsStore
// 有没有被读、runWithConcurrency 有没有被调）。实测: 删掉那一行，在途峰值 1 而设置是 4。
// 只扫 buildPreview 那一段（到下一个函数为止），避免在别处找到替身。
{
  const bpStart = src.indexOf('async function buildPreview')
  const bpEnd = src.indexOf('function updatePreview', bpStart)
  const bp = bpStart >= 0 && bpEnd > bpStart ? src.slice(bpStart, bpEnd) : ''
  assert('预览行带 new_path（并发降级判据的输入）',
    /new_path:\s*pv\.new_path/.test(bp), true)
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
