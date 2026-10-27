// 设置的默认值、归一化与读写。刻意零依赖：不 import vue / pinia / 任何东西，
// 这样 node 可以直接 import 它跑断言（本项目没有前端测试设施，见 spec §17 遗留 3）。

export const SETTINGS_KEY = 'episode-renamer:settings'

const CONFLICT_STRATEGIES = ['skip', 'abort', 'overwrite', 'rename_dup']

// STRM 的三种落点。与后端 models/strm.py 的 Literal 逐字一致 —— 两边各写一份
// 是必要的（一个跑在浏览器、一个跑在服务端), 但取值集合必须相同: 前端多一个值
// 会让保存成功、执行时 422, 少一个则用户选不到。
const STRM_MODES = ['local', 'remote_custom', 'remote_same']

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
    // 本地源的并发在途上限。**默认 4**：本地是磁盘操作，瓶颈在 IO 而不在服务端；
    // OpenList 默认 2 是因为它每次请求都要出网打远端 API。
    localConcurrency: 4,
    // TMDB 未配置时 enabled 仍为 true —— 后端在 api_key 为空时自行降级为 disabled。
    // 前端把「未配置」与「已禁用」当成两件事，用户才知道该去填 Key 还是该去打开开关。
    tmdb: {
      apiKey: '',
      language: 'zh-CN',
      enabled: true,
    },
    openlist: {
      serverUrl: '',
      // 默认 2（spec §7.1）。它是**下发到后端**的 —— OpenListClient 用它构造并发
      // 限流器, 见 backend/app/core/openlist_client.py。
      concurrency: 2,
      requestInterval: 0.5,
    },
    // STRM 的**长期**部分住设置页: 输出模式（我的库怎么组织）与对外地址
    // （反代域名, 一年改一次）。两个根目录中, 本地根目录也在这里;
    // 远端自定义目录**不在这里** —— 它每次任务都可能不同（扫 A 库写 A 目录,
    // 扫 B 库写 B 目录），故住在工作区左栏, 见 workspace 的 strmRemoteRoot。
    strm: {
      // remote_same 是最不需要额外配置的模式（落点由视频位置决定）。
      mode: 'remote_same',
      // 留空 = 用 OpenList 服务器地址。反代/容器内网地址不一致时才需要填。
      baseUrl: '',
      localRoot: '',
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

  const tmdb = (raw.tmdb && typeof raw.tmdb === 'object' && !Array.isArray(raw.tmdb))
    ? raw.tmdb
    : {}

  const strm = (raw.strm && typeof raw.strm === 'object' && !Array.isArray(raw.strm))
    ? raw.strm
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
    localConcurrency: clampNumber(
      raw.localConcurrency, 1, 10, def.localConcurrency, true
    ),
    tmdb: {
      // Key 从网页复制常带尾部空白或换行。不 trim 的话用户看到的是「API Key 无效」，
      // 却查不出原因。Key 本身不含空白字符，trim 是无损的。
      apiKey: asString(tmdb.apiKey, def.tmdb.apiKey).trim(),
      // 只有「非空字符串」才算有效语言。空串与纯空白都回落到默认，
      // 否则会把空语言下发给 TMDB，拿到的是原语言数据而用户以为设置了中文。
      language: (typeof tmdb.language === 'string' && tmdb.language.trim())
        ? tmdb.language.trim()
        : def.tmdb.language,
      enabled: typeof tmdb.enabled === 'boolean' ? tmdb.enabled : def.tmdb.enabled,
    },
    openlist: {
      serverUrl: asString(openlist.serverUrl, def.openlist.serverUrl),
      concurrency: clampNumber(openlist.concurrency, 1, 10, def.openlist.concurrency, true),
      requestInterval: clampNumber(openlist.requestInterval, 0.1, 5, def.openlist.requestInterval),
    },
    strm: {
      // 非法 mode 回落默认：一个拼错的值不该让每次预览都拿到 422。
      mode: STRM_MODES.includes(strm.mode) ? strm.mode : def.strm.mode,
      // 路径与地址都 trim：从文件管理器复制的路径常带首尾空白, 而空格开头的
      // 本地路径会被当成相对路径, 落点静默跑到进程的工作目录下。
      baseUrl: asString(strm.baseUrl, def.strm.baseUrl).trim(),
      localRoot: asString(strm.localRoot, def.strm.localRoot).trim(),
      // remoteRoot 刻意不在这里: 它是每次任务的工作参数, 存在 workspace 的
      // 独立 localStorage 键里（episode-renamer:strm-root）。留在设置里会和
      // 设置页的草稿语义打架 —— 左栏改了值, 设置页那份旧草稿一保存就把它盖回
      // 去, 而那个字段在界面上根本看不见。
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
