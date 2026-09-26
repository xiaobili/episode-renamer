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
assert('未刮削且 TMDB 开着 → 该说「未刮削」',
  tmdbPendingScrape({ scraped: false, tmdbDisabled: false }), true)
assert('已刮削 → 不说', tmdbPendingScrape({ scraped: true, tmdbDisabled: false }), false)
assert('设置页关着 → 不说（成因是那个开关，且它可行动）',
  tmdbPendingScrape({ scraped: false, tmdbDisabled: true }), false)

// --- nfoBlockedByScrape：NFO 会因为「本次没刮削」而写不出来吗 ---
assert('勾了 NFO + 未刮削 + TMDB 开着 → 是',
  nfoBlockedByScrape({ generateNfo: true, scraped: false, tmdbDisabled: false }), true)
assert('没勾 NFO → 否（那时 NFO 列说「未启用」才是对的成因）',
  nfoBlockedByScrape({ generateNfo: false, scraped: false, tmdbDisabled: false }), false)
assert('已刮削 → 否',
  nfoBlockedByScrape({ generateNfo: true, scraped: true, tmdbDisabled: false }), false)
assert('设置页关着 → 否（成因是那个开关）',
  nfoBlockedByScrape({ generateNfo: true, scraped: false, tmdbDisabled: true }), false)

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
