import { readFileSync } from 'node:fs'

let failed = 0
function assert(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) { failed += 1; console.log('FAIL', label, '得到', JSON.stringify(actual), '期望', JSON.stringify(expected)) }
  else { console.log('PASS', label) }
}

// **先剥掉注释再匹配**: 否则把一处调用注释掉, 文本断言照样绿 —— 那是最廉价的一种
// 「判据恒真」。与 check-workspace-gating.mjs 里那批源码级断言同一考虑。
const raw = readFileSync(new URL('../src/stores/workspace.js', import.meta.url), 'utf8')
const src = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')

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

// --- 另外两条（实现期追加，理由随附）---
// 这两条在「上面七条全绿」时仍能各自打红一个真实变异, 故留下:
//   · `limit 不是字面量` 打红「调用点第二参改成 4」—— 那正是 Step 5b 点名要实测的
//     变异, 而 Step 5b 那三条查的是 resolveConcurrency 的实参、不是 runWithConcurrency
//     的第二参, 所以它抓不到;
//   · `预览行带 new_path` 打红「删掉行构造里那句」—— 与 Step 3b 是同一个死设置缺口
//     的第二道防线。
//
// **与计划给的正则有一处出入（有意的）**: 计划写的是
//   /runWithConcurrency\([\s\S]{0,120}?\n\s*limit,/
// 它要求 `limit,` 出现在**另一行**上, 而计划 Step 3 的代码是 `items, limit,` 同一行
// —— 实测该正则对计划的代码返回 false, 即断言**恒红**。改为捕获第二参并断言它是
// **标识符**（不是数字字面量），这正是这条断言要说的那件事, 且实测能红。
assert('limit 不是字面量（第二参不是数字）',
  /runWithConcurrency\(\s*[^,]+,\s*([A-Za-z_$][\w$]*)\s*,/.test(src), true)
assert('预览行带 new_path',
  /new_path:\s*pv\.new_path/.test(src), true)

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
