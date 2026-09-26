// 设置的默认值、归一化与读写。刻意零依赖：不 import vue / pinia / 任何东西，
// 这样 node 可以直接 import 它跑断言（本项目没有前端测试设施，见 spec §17 遗留 3）。

export const SETTINGS_KEY = 'episode-renamer:settings'

const CONFLICT_STRATEGIES = ['skip', 'abort', 'overwrite', 'rename_dup']

// [1,6] 的区间来自 spec 的补零位数设定，与后端 backend/app/core/template.py 的
// PAD_MIN / PAD_MAX 一致。后端在 PadConfig 构造时钳制，前端在这里钳制 —— 两道
// 防线各自独立，任一侧改了区间都必须同步另一侧，否则会出现「界面显示 0 而实际
// 补零 1 位」这类两侧不一致。
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

// 设置页的「默认服务器地址」要预填进 OpenList 登录表单。
// 优先级：设置页的值 > 上次实际使用的地址（olStore 的自有存储）> 空串。
// 设置页的值优先，因为它正是「默认」二字的所指 —— 它必须能被用户感知到
// 生效，否则就退回成本次修复前那种「写进 localStorage 却无人读」的死设置。
// 回落上次使用的地址只在设置页留空时发生，保留「换过一次服务器」的便利。
//
// 两个入参都做类型防御：调用方给的可能是被手工改坏的 localStorage 值，
// 非字符串（null / undefined / 对象）一律视为「未设置」，而不是被当成真值
// 拼进表单（那会让表单里出现 "[object Object]"）。
export function resolveOpenListServerUrl(settingsUrl, lastUsedUrl) {
  if (typeof settingsUrl === 'string' && settingsUrl) return settingsUrl
  if (typeof lastUsedUrl === 'string' && lastUsedUrl) return lastUsedUrl
  return ''
}
