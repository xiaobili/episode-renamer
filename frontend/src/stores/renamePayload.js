// 预览 / 执行 / 干跑的请求载荷**只有这一处**构造。
//
// 为什么必须收敛到一处：这 16 个字段原先在 workspace.js 里有两份副本
// （buildPreview 一份、executeAction 一份），而「两处都要下发 TMDB 设置」
// 正是本功能设计里的头号风险（ledger R46）—— 漏一处会让预览显示标题、执行却
// 写出别的文件名，全程零报错（本仓库有前科）。两份副本还会各自漂移：新增字段时
// 漏改一处没有任何机械判据能发现（前端没有测试框架）。
//
// 与 settingsSchema.js 同规格：纯函数 + node 断言（scripts/check-rename-payload.mjs）。
// 本模块**不得** import 任何东西 —— 否则 node 加载不了它。
export function buildRenamePayload({
  // 'preview' 走 RenamePreviewRequest；'execute' 走 RenameExecuteRequest。
  // **干跑也用 'execute'** —— 它与真执行共用同一个请求模型，只是换个端点。
  mode,
  fileIds,
  // 批次路径。两种调用点各自算好传进来：预览用扫描到的首行、执行用选中的首行
  // （递归扫描下两者可能不同）。后端目前**不读** path（api/renamer.py 只用到
  // file_ids / source / conflict_strategy），故这里不做「改进」，逐字保留原行为。
  path,
  source,
  template,
  folderTemplate,
  createSeasonFolder,
  // 仅 mode === 'execute' 进入载荷：RenamePreviewRequest 没有这个字段。
  conflictStrategy,
  // 已收集好的逐行覆盖。**由调用方收集**：预览从全部预览行收集、执行只从选中行
  // 收集 —— 两者的行集合不同（首次预览时 previewRows 还是空的，而 file_ids 来自
  // filesStore.files），把它收进这里只会把这件事实藏起来。
  overrides,
  episodePadDigits,
  seasonPadDigits,
  tmdb,
  tmdbOverrides,
  // 本次扫描是否已刮削（spec §17）。
  scraped,
  generateNfo,
  nfoOverwrite,
}) {
  return {
    file_ids: fileIds,
    source,
    path,
    template,
    folder_template: folderTemplate,
    create_season_folder: createSeasonFolder,
    overrides,
    ...(mode === 'execute' ? { conflict_strategy: conflictStrategy } : {}),
    episode_pad_digits: episodePadDigits,
    season_pad_digits: seasonPadDigits,
    // 未刮削时**只发 tmdb_enabled: false**，且不发 Key / 语言 / 重选表。
    //
    // 「不查 TMDB」的唯一有效表达就是显式 false。另两种写法都是错的：
    //   · 省略字段 → 后端拿到 None → 回退到 .env 的 Key → **照样出网**；
    //   · 发空 Key '' → 后端按真值判断把 '' 当「未提供」→ 同样回退 .env → **照样出网**。
    // 这正是 R49-1 修过的形态（Docker 只配 .env 的部署会被它破坏），故由
    // check-rename-payload.mjs 的三条断言钉住，且那三种错误实现都必须被打红。
    //
    // 顺带：没要用的请求不该带上 Key，这是密钥卫生。
    ...(scraped
      ? {
          tmdb_api_key: tmdb.apiKey,
          tmdb_language: tmdb.language,
          tmdb_overrides: { ...tmdbOverrides },
          tmdb_enabled: tmdb.enabled,
        }
      : { tmdb_enabled: false }),
    generate_nfo: generateNfo,
    nfo_overwrite: nfoOverwrite,
  }
}
