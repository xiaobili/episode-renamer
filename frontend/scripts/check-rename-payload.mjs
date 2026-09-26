import { buildRenamePayload } from '../src/stores/renamePayload.js'

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

// 键存在性单独断言：assert 比的是值，比不出「字段该不该出现」
// （字段缺失与值为 undefined 在 JSON 里同样看不见）。
function assertKey(label, obj, key, present) {
  const ok = Object.prototype.hasOwnProperty.call(obj, key) === present
  if (!ok) {
    failed += 1
    console.log('FAIL', label, '得到', Object.prototype.hasOwnProperty.call(obj, key) ? '有' : '无',
      '期望', present ? '有' : '无')
  } else {
    console.log('PASS', label)
  }
}

const base = {
  mode: 'preview',
  fileIds: ['f1', 'f2'],
  path: '/media/绝命毒师/Season 02/',
  source: 'local',
  template: '{show} - S{season_padded}E{episode_padded}{extension}',
  folderTemplate: 'Season {season_padded}',
  createSeasonFolder: true,
  conflictStrategy: 'skip',
  overrides: { f1: { title: '我的标题' } },
  episodePadDigits: 2,
  seasonPadDigits: 2,
  tmdb: { apiKey: 'THE-KEY', language: 'zh-CN', enabled: true },
  tmdbOverrides: { 绝命毒师: 1396 },
  scraped: true,
  generateNfo: false,
  nfoOverwrite: false,
}

// --- 未刮削：唯一的正确表达是显式 tmdb_enabled: false（spec §17.2）---
const off = buildRenamePayload({ ...base, scraped: false })
assert('未刮削时 tmdb_enabled 严格为布尔 false', off.tmdb_enabled, false)
assertKey('未刮削时载荷不含 tmdb_api_key', off, 'tmdb_api_key', false)
assertKey('未刮削时载荷不含 tmdb_language', off, 'tmdb_language', false)
assertKey('未刮削时载荷不含 tmdb_overrides', off, 'tmdb_overrides', false)

// --- 已刮削：四项都在，且取设置值 ---
const on = buildRenamePayload({ ...base, scraped: true })
assert('已刮削时带上 Key', on.tmdb_api_key, 'THE-KEY')
assert('已刮削时带上语言', on.tmdb_language, 'zh-CN')
assert('已刮削时带上重选表', on.tmdb_overrides, { 绝命毒师: 1396 })
assert('已刮削时 tmdb_enabled 取设置值', on.tmdb_enabled, true)
assert('重选表是浅拷贝而非同一引用', on.tmdb_overrides === base.tmdbOverrides, false)

// --- 设置页关着：即使已刮削也照实下发 false（前端不替后端决定）---
assert('设置页关闭时 tmdb_enabled 为 false',
  buildRenamePayload({ ...base, tmdb: { apiKey: '', language: 'zh-CN', enabled: false } }).tmdb_enabled,
  false)

// --- 两种模式共用的字段一个都不能少（两份副本漂移就是在这里被抓住的）---
assert('file_ids 原样透传', on.file_ids, ['f1', 'f2'])
assert('source 透传', on.source, 'local')
assert('path 透传', on.path, '/media/绝命毒师/Season 02/')
assert('template 透传', on.template, base.template)
assert('folder_template 透传', on.folder_template, 'Season {season_padded}')
assert('create_season_folder 透传', on.create_season_folder, true)
assert('overrides 透传', on.overrides, { f1: { title: '我的标题' } })
assert('episode_pad_digits 透传', on.episode_pad_digits, 2)
assert('season_pad_digits 透传', on.season_pad_digits, 2)
assert('generate_nfo 透传', on.generate_nfo, false)
assert('nfo_overwrite 透传', on.nfo_overwrite, false)

// --- conflict_strategy 只属于 execute（RenamePreviewRequest 没有这个字段）---
assertKey('preview 载荷不含 conflict_strategy', off, 'conflict_strategy', false)
assert('execute 载荷带 conflict_strategy',
  buildRenamePayload({ ...base, mode: 'execute' }).conflict_strategy, 'skip')

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
