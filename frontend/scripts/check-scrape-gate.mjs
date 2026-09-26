import {
  isTmdbDisabled,
  tmdbPendingScrape,
  nfoBlockedByScrape,
} from '../src/stores/scrapeGate.js'

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

// --- isTmdbDisabled：只有显式 false 才算关（与后端 enabled is False 对齐）---
assert('enabled=false 算关闭', isTmdbDisabled({ enabled: false }), true)
assert('enabled=true 不算关闭', isTmdbDisabled({ enabled: true }), false)
assert('enabled 缺失（未表态）不算关闭', isTmdbDisabled({}), false)
assert('tmdb 整个缺失不算关闭', isTmdbDisabled(undefined), false)

// --- tmdbPendingScrape：预览表 TMDB 列该说「未刮削」吗 ---
// 每一次调用都**显式**传 `scraping`：省略它时 `(!scraped || undefined)` 会漏出
// undefined 而不是布尔，断言比的是 JSON，undefined 与 false 都不相等 —— 传全了才谈得上鉴别力。
assert('未刮削且 TMDB 开着 → 该说「未刮削」',
  tmdbPendingScrape({ scraped: false, tmdbDisabled: false, scraping: false }), true)
assert('已刮削（已停下）→ 不说',
  tmdbPendingScrape({ scraped: true, tmdbDisabled: false, scraping: false }), false)
assert('设置页关着 → 不说（成因是那个开关，且它可行动）',
  tmdbPendingScrape({ scraped: false, tmdbDisabled: true, scraping: false }), false)

// --- 在途刮削视为「未刮削」（spec §17.3）---
// 这一组是**新增项**的鉴别力所在：`scraped` 在 await 之前就乐观置位，而屏幕上那张表
// 还是刮削前的那一张 —— 此刻若不看 `scraping`，TMDB 列会渲染成「未启用」，把用户
// 推去翻一个本来就开着的开关（spec §17.5 要防的正是这种误诊断）。
// 删掉谓词里的 `|| scraping` 时，第一条立刻红（true → false）。
assert('在途刮削（scraped 已乐观置位）→ 仍该说「未刮削」',
  tmdbPendingScrape({ scraped: true, tmdbDisabled: false, scraping: true }), true)
assert('在途刮削且设置页关着 → 仍然不说（开关可行动这一事实不受在途影响）',
  tmdbPendingScrape({ scraped: false, tmdbDisabled: true, scraping: true }), false)

// --- nfoBlockedByScrape：NFO 会因为「本次没刮削」而写不出来吗 ---
assert('勾了 NFO + 未刮削 + TMDB 开着 → 是',
  nfoBlockedByScrape({ generateNfo: true, scraped: false, tmdbDisabled: false, scraping: false }), true)
assert('没勾 NFO → 否（那时 NFO 列说「未启用」才是对的成因）',
  nfoBlockedByScrape({ generateNfo: false, scraped: false, tmdbDisabled: false, scraping: false }), false)
assert('已刮削（已停下）→ 否',
  nfoBlockedByScrape({ generateNfo: true, scraped: true, tmdbDisabled: false, scraping: false }), false)
assert('设置页关着 → 否（成因是那个开关）',
  nfoBlockedByScrape({ generateNfo: true, scraped: false, tmdbDisabled: true, scraping: false }), false)
// 左栏的 NFO 提示与 NFO 列共用这个谓词：在途刮削时它也**必须**继续显示
// （「NFO 需要 TMDB 元数据，未刮削则不会写出」），否则同一次刮削里提示会在
// 结果出来之前先消失，而表还是旧表。删掉 `|| scraping` 时这条红。
assert('勾了 NFO + 在途刮削 → 是（提示不能提前消失）',
  nfoBlockedByScrape({ generateNfo: true, scraped: true, tmdbDisabled: false, scraping: true }), true)
assert('在途刮削且设置页关着 → 否（成因是那个开关）',
  nfoBlockedByScrape({ generateNfo: true, scraped: true, tmdbDisabled: true, scraping: true }), false)

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
