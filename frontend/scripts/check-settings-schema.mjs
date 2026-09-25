import {
  SETTINGS_KEY,
  defaultSettings,
  normalizeSettings,
  readSettings,
  writeSettings,
} from '../src/stores/settingsSchema.js'

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

function fakeStorage(initial) {
  const data = { ...(initial || {}) }
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v) },
    removeItem: (k) => { delete data[k] },
  }
}

// --- 默认值 ---
assert('默认值的补零位数是 2', defaultSettings().episodePadDigits, 2)
assert('默认值的冲突策略是 skip', defaultSettings().conflictStrategy, 'skip')
assert('默认值与后端 config.py 一致（2 位）', defaultSettings().seasonPadDigits, 2)

// --- Review Focus 4：清空输入框（null）视为未设置，回落默认 ---
assert('null 补零位数回落默认 2', normalizeSettings({ episodePadDigits: null }).episodePadDigits, 2)
assert('空字符串补零位数回落默认 2', normalizeSettings({ episodePadDigits: '' }).episodePadDigits, 2)
assert('undefined 补零位数回落默认 2', normalizeSettings({}).episodePadDigits, 2)

// --- 0 / 负数 / 超大值钳制到 [1, 6]，与后端 PadConfig 一致 ---
assert('0 被钳到 1', normalizeSettings({ episodePadDigits: 0 }).episodePadDigits, 1)
assert('负数被钳到 1', normalizeSettings({ episodePadDigits: -5 }).episodePadDigits, 1)
assert('99 被钳到 6', normalizeSettings({ episodePadDigits: 99 }).episodePadDigits, 6)
assert('季数同样钳制', normalizeSettings({ seasonPadDigits: 99 }).seasonPadDigits, 6)
assert('小数被截断', normalizeSettings({ episodePadDigits: 3.9 }).episodePadDigits, 3)
assert('字符串数字被接受', normalizeSettings({ episodePadDigits: '4' }).episodePadDigits, 4)
assert('非数字字符串回落默认', normalizeSettings({ episodePadDigits: 'abc' }).episodePadDigits, 2)

// --- Review Focus 2：逐字段合并，残缺对象不能让字段变 undefined ---
const partial = normalizeSettings({ conflictStrategy: 'overwrite' })
assert('只给一个字段时补零位数仍是默认', partial.episodePadDigits, 2)
assert('只给一个字段时 openlist 仍是完整对象', partial.openlist, {
  serverUrl: '', concurrency: 3, requestInterval: 0.5,
})
assert('openlist 半残缺也能补全', normalizeSettings({ openlist: { concurrency: 5 } }).openlist, {
  serverUrl: '', concurrency: 5, requestInterval: 0.5,
})
assert('非法冲突策略回落默认', normalizeSettings({ conflictStrategy: 'nuke' }).conflictStrategy, 'skip')

// --- 旧字段名迁移（旧的 SettingsView 写的是 defaultTemplate） ---
assert('旧字段 defaultTemplate 被迁移', normalizeSettings({ defaultTemplate: 'plex' }).defaultTemplateId, 'plex')
assert('新字段优先于旧字段', normalizeSettings({ defaultTemplate: 'plex', defaultTemplateId: 'emby_standard' }).defaultTemplateId, 'emby_standard')
assert('两者都没有时用默认', normalizeSettings({}).defaultTemplateId, 'emby_standard')

// --- 完全非法输入 ---
assert('null 输入返回全默认', normalizeSettings(null), defaultSettings())
assert('字符串输入返回全默认', normalizeSettings('nonsense'), defaultSettings())
assert('数组输入返回全默认', normalizeSettings([1, 2, 3]), defaultSettings())

// --- Review Focus 3：localStorage 不可用（隐私模式） ---
assert('storage 为 null 时返回全默认', readSettings(null), defaultSettings())

// --- 读盘：键不存在 ---
assert('键不存在时返回全默认', readSettings(fakeStorage()), defaultSettings())

// --- 读盘：JSON 损坏 ---
assert('JSON 损坏时返回全默认', readSettings(fakeStorage({ [SETTINGS_KEY]: '{不好' })), defaultSettings())

// --- 读盘：正常往返 ---
const storage = fakeStorage()
writeSettings(storage, { ...defaultSettings(), episodePadDigits: 3, conflictStrategy: 'abort' })
assert('写盘后读回补零位数', readSettings(storage).episodePadDigits, 3)
assert('写盘后读回冲突策略', readSettings(storage).conflictStrategy, 'abort')

// --- 写盘失败不能抛（存储配额满 / 只读） ---
const throwingStorage = {
  getItem: () => null,
  setItem: () => { throw new Error('QuotaExceededError') },
}
writeSettings(throwingStorage, defaultSettings())
console.log('PASS 写盘抛异常时被吞掉，不冒泡')

// --- 读盘时 getItem 抛异常也要托住 ---
const throwingRead = {
  getItem: () => { throw new Error('SecurityError') },
  setItem: () => {},
}
assert('getItem 抛异常时返回全默认', readSettings(throwingRead), defaultSettings())

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
