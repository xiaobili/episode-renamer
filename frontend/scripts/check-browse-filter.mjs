// BrowseDialog 目录搜索框的判据。
//
// 为什么需要它：搜索框会改变「列表里有几项、第几项是哪个目录」，而对话框里所有
// 键盘定位（↓/↑ 的边界、ArrowRight 下钻取 dirs[index]、下钻后焦点交接的下标）
// 都建立在「可见列表」上。过滤一旦与列表脱节，这些下标会集体错位 —— 按 ↓ 选中
// 隔壁目录、按 → 进入一个用户没看见的目录，全都不会报错。
//
// 用法：cd frontend && node scripts/check-browse-filter.mjs
// 退出码非 0 表示有断言失败。

import { filterDirs, normalizeQuery } from '../src/components/browseFilter.js'

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

const DIRS = [
  { name: '藏锋', path: '/m/藏锋' },
  { name: '长安二十四计', path: '/m/长安二十四计' },
  { name: '陈情令', path: '/m/陈情令' },
  { name: '成何体统', path: '/m/成何体统' },
  { name: '春色寄情人', path: '/m/春色寄情人' },
  { name: 'The Last of Us', path: '/m/The Last of Us' },
  { name: 'the office', path: '/m/the office' },
  { name: 'S01 Backup', path: '/m/S01 Backup' },
]

// --- 空查询原样放行 ---
// 写成「空查询返回 []」的实现会让对话框一打开就说「无匹配」，
// 或者更糟：列表整片消失但 loading 为假 —— 用户以为目录是空的。
{
  assert('空串放行全部', filterDirs(DIRS, '').length, DIRS.length)
  assert('空串保持原序', filterDirs(DIRS, '').map((d) => d.name), DIRS.map((d) => d.name))
  assert('纯空白视为空查询', filterDirs(DIRS, '   ').length, DIRS.length)
  assert('undefined 视为空查询', filterDirs(DIRS, undefined).length, DIRS.length)
}

// --- 子串命中，保持原序 ---
{
  assert('中文子串命中', filterDirs(DIRS, '情').map((d) => d.name), ['陈情令', '春色寄情人'])
  // 多条命中必须按**原列表顺序**返回（不是按相关度重排），否则键盘下标与
  // 用户眼睛看到的顺序会对不上。
  assert('命中多条时保持原序', filterDirs(DIRS, 'e').map((d) => d.name),
    ['The Last of Us', 'the office'])
  // 名字中间的空白必须保留：写成「按空白切词」的实现会把 "S01 Backup" 拆开，
  // 于是 "s01b" 也会命中 —— 见下面那条。
  assert('命中单条', filterDirs(DIRS, 'backup').map((d) => d.name), ['S01 Backup'])
}

// --- 大小写不敏感（两个方向都要） ---
// 只做 toLowerCase(query) 而忘了 name 的实现能过其中一条、过不了另一条。
{
  assert('大写查询命中大写名', filterDirs(DIRS, 'LAST').map((d) => d.name), ['The Last of Us'])
  assert('小写查询命中混合大小写名', filterDirs(DIRS, 'office').map((d) => d.name), ['the office'])
  assert('小写查询命中首字母大写名', filterDirs(DIRS, 'the').length, 2)
}

// --- 全角输入（中文输入法下按 Shift 没切回来很常见） ---
// 不归一化 NFKC 的实现会在这里返回 0 条 —— 用户看到「无匹配」，
// 却怎么也不明白名字明明在眼前。
{
  assert('全角字符命中半角名', filterDirs(DIRS, 'ｏｆｆｉｃｅ').map((d) => d.name), ['the office'])
  assert('全角数字命中', filterDirs([{ name: 'S01' }], 'ｓ０１').length, 1)
}

// --- 首尾空白不参与匹配 ---
{
  assert('首尾空白被裁掉', filterDirs(DIRS, '  陈情令  ').map((d) => d.name), ['陈情令'])
  // 名字中间的空白必须保留：写成「按空白切词」的实现会把 "S01 Backup" 拆开，
  // 于是 "s01b" 也会命中 —— 见下一条。
  assert('名字中间的空格参与匹配', filterDirs(DIRS, 's01 b').length, 1)
  assert('不按空白切词', filterDirs(DIRS, 's01b').length, 0)
}

// --- 无匹配返回空数组，而不是回退成全量 ---
// 回退会让用户在「搜一个不存在的名字」时看到全部目录，误以为全都匹配了。
{
  assert('无匹配返回空', filterDirs(DIRS, 'zzz'), [])
  assert('空输入返回空', filterDirs([], 'x'), [])
  assert('null 输入不崩', filterDirs(null, 'x'), [])
}

// --- 不得改动入参（对话框的 dirs 是响应式数组，就地排序/删除会污染缓存） ---
{
  const input = DIRS.slice()
  const out = filterDirs(input, '')
  out.push({ name: '外部追加' })
  assert('返回值不是入参本身', out === input, false)
  assert('入参长度未被污染', input.length, DIRS.length)
}

// --- normalizeQuery 是唯一口径 ---
// filterDirs 若绕开它自写一套，上面全角/空白那几条会红；这里再直接钉一次，
// 免得将来有人只改 normalizeQuery 而误以为 filterDirs 跟着变。
{
  assert('normalizeQuery 全角+空白+大小写', normalizeQuery('  ＴＨＥ  '), 'the')
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
