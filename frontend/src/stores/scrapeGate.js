// 「刮削」相关的判定集中在这里 —— 它们是**四处**界面共用的谓词：
// 预览表的 TMDB 列、NFO 列、左栏的 NFO 提示、结果对话框的 NFO 提示。
// 四处各写一份的后果不是重复，而是**成因说错**：未刮削时后端一律报 disabled，
// 于是四处都可能把「去点刮削标题」说成「去设置页打开 TMDB 开关」。
// 本仓库反复在修的就是这类「让用户去改一个没问题的东西」（spec §17.5）。
//
// 与 settingsSchema.js 同规格：纯函数 + node 断言（scripts/check-scrape-gate.mjs）。
// 本仓库刻意没有前端测试框架（spec §17.7），这是它认可的替代。
//
// 本模块**不得** import 任何东西 —— 否则 node 加载不了它，断言脚本就失效。

// 设置页显式关闭了 TMDB。判据是 `=== false` 而不是 `!enabled`：与后端
// resolve_tmdb_client 的 `enabled is False` 对齐 —— 未表态（undefined / 老客户端）
// 不等于关，否则一个被手工改坏的 localStorage 会让前端拒绝刮削，而同时发出去的
// tmdb_enabled 并没让后端禁用，两边不一致。
export function isTmdbDisabled(tmdb) {
  return tmdb?.enabled === false
}

// 预览表的 TMDB 列该说「未刮削」吗。
// 设置页关着时**不说** —— 那时「未启用」才是对的成因，且它可行动（去设置页打开）。
//
// 「在途的刮削视为尚未刮削」（`|| scraping`）：`scraped` 是在 await **之前**乐观置位的，
// 而在刮削返回之前，屏幕上那张表**确实**还是刮削前的那一张（后端报的仍是 disabled）。
// 此刻说「未启用」是误诊断 —— 把用户推去翻一个本来就开着的开关；说「未刮削」是实话。
export function tmdbPendingScrape({ scraped, tmdbDisabled, scraping }) {
  return (!scraped || scraping) && !tmdbDisabled
}

// NFO 会因为「本次没刮削」而写不出来吗。三个条件缺一不可：
//   · generateNfo   —— 没勾「生成 NFO」时 NFO 列本就说「未启用」，与刮削无关；
//   · !scraped      —— 已刮削就不是这个成因；
//   · !tmdbDisabled —— 设置页关着时成因是那个开关，不是「忘了点按钮」。
// `scraping` 的理由与上面完全相同：在途刮削时表还是旧表，成因是「还没刮完」。
// 注意 `|| scraping` 只写在 `!scraped` 那一边：设置页关着时**永远**不成立
// （刮削按钮本身就被 tmdbOff() 挡下，不会有在途刮削）。
export function nfoBlockedByScrape({ generateNfo, scraped, tmdbDisabled, scraping }) {
  return Boolean(generateNfo) && (!scraped || scraping) && !tmdbDisabled
}
