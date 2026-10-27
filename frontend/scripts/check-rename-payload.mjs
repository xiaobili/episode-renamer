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
  fileId: 'f1',
  override: { title: '我的标题' },
  landed: { f1: '/media/绝命毒师/Season 02/绝命毒师 - S02E01.mkv' },
  openlistMaxConcurrent: 2,
  openlistRequestInterval: 0.5,
  path: '/media/绝命毒师/Season 02/',
  source: 'local',
  template: '{show} - S{season_padded}E{episode_padded}{extension}',
  folderTemplate: 'Season {season_padded}',
  // 与 generateNfo **取不同的值**（见下面「只关 TMDB」那一块）：三个布尔各是一个
  // 独立字段，只靠「取不同值」钉不住它们 —— 布尔只有两个值，三字段必有重复。
  // 故这里只负责让本字段与 generateNfo 分开，真正的鉴别力来自交叉钉住。
  createSeasonFolder: false,
  conflictStrategy: 'skip',
  overrides: { f1: { title: '我的标题' } },
  // 补零位数与 NFO 两项**必须取不同的值**。取同值时「互换实现里这两个字段」
  // 会让两条断言都拿到同一个数 → 双双通过，那对断言就成了零鉴别力的摆设。
  // 而互换的后果是真损失：补零位数互换会让每个文件按错的位数改名，NFO 两项
  // 互换会让用户勾了生成却不生成 —— 两处都静默。故 2/3 与 true/false 是
  // **有意的**，不要「顺手统一」成同值。
  episodePadDigits: 2,
  seasonPadDigits: 3,
  tmdb: { apiKey: 'THE-KEY', language: 'zh-CN', enabled: true },
  tmdbOverrides: { 绝命毒师: 1396 },
  scraped: true,
  generateNfo: true,
  nfoOverwrite: false,
  // STRM：模式取非默认值（默认是 remote_same），这样「漏发 strm_mode」不会被
  // 后端默认值掩盖成看起来正确的结果。
  strm: {
    mode: 'local',
    baseUrl: 'http://ol:5244',
    localRoot: '/m/strm',
    remoteRoot: '/strm',
  },
  strmScanRoot: '/media',
  generateStrm: true,
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
assert('create_season_folder 透传', on.create_season_folder, false)
assert('overrides 透传', on.overrides, { f1: { title: '我的标题' } })
assert('episode_pad_digits 透传', on.episode_pad_digits, 2)
assert('season_pad_digits 透传', on.season_pad_digits, 3)
assert('generate_nfo 透传', on.generate_nfo, true)
assert('nfo_overwrite 透传', on.nfo_overwrite, false)

// 三个布尔各是一个独立字段，**只靠「取不同值」钉不住**：布尔只有两个值，三个字段必有重复，
// 而重复的那一对互换后两条断言拿到同一个值 → 双双通过（本计划第三次栽在同一形态）。
// 故只动**一个**输入，断言另两个**不受影响** —— 互换实现会在这里红。
const tmdbOffPayload = buildRenamePayload({
  ...base, tmdb: { ...base.tmdb, enabled: false },
})
assert('只关 TMDB 时 tmdb_enabled 变 false', tmdbOffPayload.tmdb_enabled, false)
assert('只关 TMDB 时 generate_nfo 不受影响', tmdbOffPayload.generate_nfo, true)
assert('只关 TMDB 时 create_season_folder 不受影响', tmdbOffPayload.create_season_folder, false)

// --- 单文件模式：出 file_id 与 override（单数），不出 file_ids / overrides ---
// `fileIds: undefined` 是**必须的**：base 里的 fileIds 是给批量形态用的，直接
// `{ ...base, mode: 'execute' }` 会让它一并继承过去，撞上形状互斥校验而抛错。
// 于是「不带 fileIds 的 execute」与下面「带 fileIds 的 execute 必须抛错」成了
// 两条真正不同的路径 —— 删掉互斥校验时，红的正是后者。
{
  const one = buildRenamePayload({ ...base, mode: 'execute', fileIds: undefined })
  assert('execute 载荷带 file_id', one.file_id, 'f1')
  assertKey('execute 载荷不含 file_ids', one, 'file_ids', false)
  assert('execute 载荷带 override', one.override, { title: '我的标题' })
  assertKey('execute 载荷不含 overrides', one, 'overrides', false)
  assert('execute 载荷带 conflict_strategy', one.conflict_strategy, 'skip')
}

// --- 干跑仍是批量 ---
{
  const dry = buildRenamePayload({ ...base, mode: 'dry-run' })
  assert('dry-run 载荷带 file_ids', dry.file_ids, ['f1', 'f2'])
  assertKey('dry-run 载荷不含 file_id', dry, 'file_id', false)
  assert('dry-run 载荷带 overrides', dry.overrides, { f1: { title: '我的标题' } })
  assert('dry-run 载荷带 conflict_strategy', dry.conflict_strategy, 'skip')
}

// --- 收尾：批量 + landed，且**不带** conflict_strategy（它不做文件操作）---
{
  const fin = buildRenamePayload({ ...base, mode: 'finalize' })
  assert('finalize 载荷带 file_ids', fin.file_ids, ['f1', 'f2'])
  assert('finalize 载荷带 landed', fin.landed, base.landed)
  assertKey('finalize 载荷不含 conflict_strategy', fin, 'conflict_strategy', false)
}

// --- landed 是浅拷贝而非同一引用（改它不得污染调用方的对象）---
{
  const fin = buildRenamePayload({ ...base, mode: 'finalize' })
  assert('landed 是浅拷贝', fin.landed === base.landed, false)
}

// --- 预览仍是批量，且不带 conflict_strategy ---
{
  const pv = buildRenamePayload({ ...base, mode: 'preview' })
  assert('preview 载荷带 file_ids', pv.file_ids, ['f1', 'f2'])
  assertKey('preview 载荷不含 conflict_strategy', pv, 'conflict_strategy', false)
}

// --- OpenList 限流随请求下发（不下发 → 设置页那两项又是死的）---
{
  const one = buildRenamePayload({ ...base, mode: 'execute', fileIds: undefined })
  assert('下发 OpenList 并发', one.openlist_max_concurrent, 2)
  assert('下发 OpenList 间隔', one.openlist_request_interval, 0.5)
}

// --- STRM 配置随请求下发（漏发 → 后端按默认 remote_same + 空地址, 全程零报错）---
{
  const one = buildRenamePayload({ ...base, mode: 'execute', fileIds: undefined })
  assert('下发 generate_strm', one.generate_strm, true)
  assert('下发 strm_mode', one.strm_mode, 'local')
  assert('下发 strm_base_url', one.strm_base_url, 'http://ol:5244')
  assert('下发 strm_local_root', one.strm_local_root, '/m/strm')
  assert('下发 strm_remote_root', one.strm_remote_root, '/strm')
  assert('下发 strm_scan_root', one.strm_scan_root, '/media')

  const pv = buildRenamePayload({ ...base, mode: 'preview' })
  assert('预览也下发 strm_scan_root', pv.strm_scan_root, '/media')

  // 收尾不做文件操作, 不该带 strm 配置 —— 带了也不会被读, 但会让「哪个接口做什么」
  // 这件事在载荷层面变得含混。
  const finStr = buildRenamePayload({ ...base, mode: 'finalize' })
  assertKey('finalize 载荷不含 strm_mode', finStr, 'strm_mode', false)
  assertKey('finalize 载荷不含 strm_scan_root', finStr, 'strm_scan_root', false)
}

// --- 形状互斥：execute 传了 fileIds 必须抛错，而不是静默取其一 ---
{
  let threw = false
  try {
    buildRenamePayload({ ...base, mode: 'execute', fileIds: ['f1', 'f2'] })
  } catch {
    threw = true
  }
  assert('execute 模式传 fileIds 抛错', threw, true)
}

// --- 形状互斥：批量模式不传 fileIds 必须抛错 ---
{
  let threw = false
  try {
    buildRenamePayload({ ...base, mode: 'finalize', fileIds: undefined })
  } catch {
    threw = true
  }
  assert('finalize 模式缺 fileIds 抛错', threw, true)
}

// --- 剧集文件夹改名：一个布尔, 四种形态都要带 ---
//
// 漏发的后果不是「少一个字段」: 预览不显示目录计划、执行完却照 backend 的默认值
// （false）不动, 于是用户勾了、表里没说、目录也没改 —— 三处都静默。反过来,
// 四种形态里只要有一处没带, 就会出现「预览显示要改、执行时没改」（或相反）。
{
  for (const mode of ['preview', 'dry-run', 'finalize', 'folders']) {
    const body = buildRenamePayload({ ...base, mode, renameFolders: true })
    assert(`${mode} 载荷下发 rename_folders`, body.rename_folders, true)
  }
  const one = buildRenamePayload({ ...base, mode: 'execute', fileIds: undefined, renameFolders: true })
  assert('execute 载荷也带 rename_folders（形状统一）', one.rename_folders, true)
  // 未勾选时必须是**显式 false** 而不是缺失: 后端对缺失取默认 false, 行为一样,
  // 但「这个字段有没有被构造」正是上面那些断言唯一能观察到的东西。
  const off = buildRenamePayload({ ...base, mode: 'preview', renameFolders: false })
  assertKey('未勾选时 rename_folders 仍存在', off, 'rename_folders', true)
  assert('未勾选时为布尔 false', off.rename_folders, false)
}

// --- 改目录的载荷不带「只有文件操作才需要」的字段 ---
//
// 目录不覆盖、不自动编号, 也不写 strm。带上它们不只是冗余: 一份同时声明
// 「conflict_strategy: overwrite + generate_strm: true」的载荷会让后来者以为
// 改目录会覆盖同名目录、会写 strm。
{
  const body = buildRenamePayload({ ...base, mode: 'folders' })
  assert('folders 载荷带 file_ids', body.file_ids, ['f1', 'f2'])
  assert('folders 载荷带 overrides', body.overrides, { f1: { title: '我的标题' } })
  assertKey('folders 载荷不含 conflict_strategy', body, 'conflict_strategy', false)
  assertKey('folders 载荷不含 generate_strm', body, 'generate_strm', false)
  assertKey('folders 载荷不含 strm_mode', body, 'strm_mode', false)
  assertKey('folders 载荷不含 strm_scan_root', body, 'strm_scan_root', false)
  // 模板相关的字段**必须**带: 后端要靠它们推出「文件改名后的剧集根」,
  // 少了 create_season_folder 就会推出一个不同的目录层数。
  assert('folders 载荷带 template', body.template, base.template)
  assert('folders 载荷带 folder_template', body.folder_template, base.folderTemplate)
  assert('folders 载荷带 create_season_folder', body.create_season_folder, false)
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
