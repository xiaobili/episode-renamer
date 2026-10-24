// BrowseDialog 目录列表的本地过滤 —— 零依赖纯函数，node 可直接加载跑断言。
//
// 为什么单独成文件：对话框里「键盘走到哪一项」的判据全挂在**过滤后的列表**上
// （下钻取 dirs[index]、↑/↓ 的边界、焦点交接的下标），一旦过滤与列表不是同一个
// 来源，那些下标会集体错位。把过滤摘出来，才能用断言把这条不变量钉住。

/** 归一化：去首尾空白，NFKC 全角转半角（全角输入法打出的字母/数字/空格要能命中），小写。 */
export function normalizeQuery(q) {
  return String(q ?? '').trim().normalize('NFKC').toLowerCase()
}

/**
 * 按名称做子串匹配（不区分大小写）。空查询原样返回**同一个数组的副本语义**：
 * 返回 `dirs` 本身而不是空数组，保证「没在搜」与「搜了但什么都没匹配上」
 * 在调用点可以区分（前者不能显示「无匹配」，否则一打开对话框就会说没有子目录）。
 *
 * @param {Array<{name: string}>} dirs
 * @param {string} query
 * @returns {Array} 过滤后的新数组
 */
export function filterDirs(dirs, query) {
  const list = Array.isArray(dirs) ? dirs : []
  const q = normalizeQuery(query)
  if (!q) return list.slice()
  return list.filter((d) => normalizeQuery(d?.name).includes(q))
}
