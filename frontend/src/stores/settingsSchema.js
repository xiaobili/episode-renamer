// 设置的默认值、归一化与读写。刻意零依赖：不 import vue / pinia / 任何东西，
// 这样 node 可以直接 import 它跑断言（本项目没有前端测试设施，见 spec §17 遗留 3）。

export const SETTINGS_KEY = 'episode-renamer:settings'

const CONFLICT_STRATEGIES = ['skip', 'abort', 'overwrite', 'rename_dup']

// 与后端 app/core/template.py 的 PAD_MIN / PAD_MAX 一致。
// 两侧区间不同会让「界面显示 0 而实际补零 1 位」这种不一致出现。
const PAD_MIN = 1
const PAD_MAX = 6

export function defaultSettings() {
  return {
    defaultTemplateId: 'emby_standard',
    episodePadDigits: 2,
    seasonPadDigits: 2,
    conflictStrategy: 'skip',
    openlist: {
      serverUrl: '',
      concurrency: 3,
      requestInterval: 0.5,
    },
  }
}

function clampNumber(value, min, max, fallback, integer = false) {
  // null / undefined / '' 视为「未设置」，回落默认值。
  // AppInput 在 type="number" 下清空输入框会 emit null —— 若把它当 0，
  // 后端会钳到 1，界面却显示 0，两侧不一致。
  if (value === null || value === undefined || value === '') return fallback
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  const truncated = integer ? Math.trunc(n) : n
  return Math.min(max, Math.max(min, truncated))
}

function asString(value, fallback) {
  return typeof value === 'string' ? value : fallback
}

export function normalizeSettings(raw) {
  const def = defaultSettings()
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return def

  const openlist = (raw.openlist && typeof raw.openlist === 'object' && !Array.isArray(raw.openlist))
    ? raw.openlist
    : {}

  // defaultTemplate 是第一版的字段名。这里读一次做迁移，否则升级后
  // 用户已保存的默认模板会被静默丢掉、退回 emby_standard。
  const templateId = typeof raw.defaultTemplateId === 'string'
    ? raw.defaultTemplateId
    : (typeof raw.defaultTemplate === 'string' ? raw.defaultTemplate : def.defaultTemplateId)

  return {
    defaultTemplateId: templateId,
    episodePadDigits: clampNumber(raw.episodePadDigits, PAD_MIN, PAD_MAX, def.episodePadDigits, true),
    seasonPadDigits: clampNumber(raw.seasonPadDigits, PAD_MIN, PAD_MAX, def.seasonPadDigits, true),
    conflictStrategy: CONFLICT_STRATEGIES.includes(raw.conflictStrategy)
      ? raw.conflictStrategy
      : def.conflictStrategy,
    openlist: {
      serverUrl: asString(openlist.serverUrl, def.openlist.serverUrl),
      concurrency: clampNumber(openlist.concurrency, 1, 10, def.openlist.concurrency, true),
      requestInterval: clampNumber(openlist.requestInterval, 0.1, 5, def.openlist.requestInterval),
    },
  }
}

export function readSettings(storage) {
  // storage 为 null（隐私模式 / 存储被禁用）时退化为纯内存态，不阻塞启动。
  if (!storage) return defaultSettings()
  try {
    const raw = storage.getItem(SETTINGS_KEY)
    if (!raw) return defaultSettings()
    return normalizeSettings(JSON.parse(raw))
  } catch {
    // JSON 损坏、getItem 抛异常（SecurityError）都走这里
    return defaultSettings()
  }
}

export function writeSettings(storage, data) {
  if (!storage) return
  try {
    storage.setItem(SETTINGS_KEY, JSON.stringify(data))
  } catch {
    // 配额满 / 只读存储。设置不持久化不应让保存按钮崩掉。
  }
}
