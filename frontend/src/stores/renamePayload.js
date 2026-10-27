// 预览 / 干跑 / 执行 / 收尾的请求载荷**只有这一处**构造。
//
// 为什么必须收敛到一处：这些字段原先在 workspace.js 里有两份副本
// （buildPreview 一份、executeAction 一份），而「两处都要下发 TMDB 设置」
// 正是本功能设计里的头号风险（ledger R46）—— 漏一处会让预览显示标题、执行却
// 写出别的文件名，全程零报错（本仓库有前科）。两份副本还会各自漂移：新增字段时
// 漏改一处没有任何机械判据能发现（前端没有测试框架）。
//
// 与 settingsSchema.js 同规格：纯函数 + node 断言（scripts/check-rename-payload.mjs）。
// 本模块**不得** import 任何东西 —— 否则 node 加载不了它。
// 四种形态:
//   preview   —— 批量计划（RenamePreviewRequest）
//   dry-run   —— 批量计划 + 冲突策略（RenameDryRunRequest）。**干跑仍是批量**:
//                它是纯计划操作, 不写盘, 没有进度可言。
//   execute   —— **单个文件**（RenameExecuteRequest）。file_id / override 用单数。
//   finalize  —— 批量收尾（RenameFinalizeRequest）, 额外带 landed 真实落点。
//   folders   —— 批量改剧集目录名（RenameFoldersRequest）。**不带** conflict_strategy
//                与 strm 字段: 目录不覆盖、不自动编号, 也不写任何元数据。三个布尔
//                （NFO / STRM / 文件夹）各管一件事, 混进同一份载荷会让「勾了没生效」
//                又变成一处静默的分叉。
export function buildRenamePayload({
  mode,
  // execute 用单数 fileId / override；preview / dry-run / finalize 用批量。
  fileId,
  fileIds,
  override,
  // 已收集好的逐行覆盖。**由调用方收集**：预览从全部预览行收集、执行只从选中行
  // 收集 —— 两者的行集合不同（首次预览时 previewRows 还是空的，而 file_ids 来自
  // filesStore.files），把它收进这里只会把这件事实藏起来。
  overrides,
  // finalize 专用：file_id → 真实落点。
  landed,
  // 批次路径。两种调用点各自算好传进来：预览用扫描到的首行、执行用选中的首行
  // （递归扫描下两者可能不同）。后端目前**不读** path（api/renamer.py 只用到
  // file_ids / source / conflict_strategy），故这里不做「改进」，逐字保留原行为。
  path,
  source,
  template,
  folderTemplate,
  createSeasonFolder,
  // 仅 mode === 'execute' / 'dry-run' 进入载荷：RenamePreviewRequest 没有这个字段。
  conflictStrategy,
  episodePadDigits,
  seasonPadDigits,
  tmdb,
  tmdbOverrides,
  // 本次扫描是否已刮削（spec §17）。
  scraped,
  generateNfo,
  nfoOverwrite,
  // STRM。`strm` = 模式 / 对外地址 / 本地根目录（设置页）+ **远端自定义目录**
  // （工作区左栏，由 workspace 的 strmOptions 补进来 —— 它随任务变, 不在设置里）;
  // `strmScanRoot` 是**用户实际扫描的目录** —— 镜像结构的根。不能用 `path` 代替:
  // 那是首行文件所在目录, 递归扫描时它不是扫描根。
  strm = {},
  strmScanRoot,
  generateStrm,
  // 设置页的 OpenList 限流。只随**真会做文件操作**的形态下发（execute / dry-run）:
  // 预览是纯计划、收尾只写 NFO, 后端那两个模型也不读它们（见 api/renamer.py）。
  openlistMaxConcurrent,
  openlistRequestInterval,
  // 本次是否连剧集目录一起改名（`剧名 (年份) [tmdbid-x]`）。批次级动作, 但不影响
  // 载荷形状 —— 四种形态都带这一个布尔, 少了它就等于「预览不显示、执行却改了」。
  renameFolders,
}) {
  // 形状互斥**必须显式校验**: 传错形状时静默取其一, 会得到「预览 2 个文件、
  // 执行 0 个」这种零报错的错行为（本仓库有前科）。
  if (mode === 'execute') {
    if (!fileId) throw new Error('buildRenamePayload: execute 模式必须传 fileId')
    if (Array.isArray(fileIds) && fileIds.length) {
      throw new Error('buildRenamePayload: execute 模式不得传 fileIds')
    }
  } else if (mode === 'preview' || mode === 'dry-run' || mode === 'finalize' || mode === 'folders') {
    if (!Array.isArray(fileIds)) {
      throw new Error(`buildRenamePayload: ${mode} 模式必须传 fileIds`)
    }
  } else {
    throw new Error(`buildRenamePayload: 未知 mode ${mode}`)
  }
  if (mode === 'finalize' && (!landed || typeof landed !== 'object')) {
    throw new Error('buildRenamePayload: finalize 模式必须传 landed')
  }

  const common = {
    source,
    path,
    template,
    folder_template: folderTemplate,
    create_season_folder: createSeasonFolder,
    episode_pad_digits: episodePadDigits,
    season_pad_digits: seasonPadDigits,
    // 未刮削时**只发 tmdb_enabled: false**，且不发 Key / 语言 / 重选表。
    // 详见下面的长注释, 三条错误实现都由本文件的判据钉住。
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
    // 剧集文件夹改名。**放在 common**: 预览/干跑读它决定报不报计划, execute 虽然
    // 不看（逐文件接口无权代表整批改目录）, 但少了它就会出现「预览里没有目录列、
    // 执行完目录却被改了」—— 那正是本仓库最忌讳的那类分叉。
    rename_folders: !!renameFolders,
  }

  // STRM 的落点配置。**不并进 common**: 收尾（finalize）不做文件操作, 带上它
  // 会让载荷暗示一个不存在的副作用（后端也不读）。
  const strmFields = {
    generate_strm: generateStrm,
    strm_mode: strm.mode,
    strm_base_url: strm.baseUrl,
    strm_local_root: strm.localRoot,
    strm_remote_root: strm.remoteRoot,
    strm_scan_root: strmScanRoot,
  }

  if (mode === 'execute') {
    return {
      file_id: fileId,
      override: override ?? null,
      ...common,
      ...strmFields,
      conflict_strategy: conflictStrategy,
      openlist_max_concurrent: openlistMaxConcurrent,
      openlist_request_interval: openlistRequestInterval,
    }
  }

  if (mode === 'finalize') {
    // finalize 不做文件操作, 故**不带** conflict_strategy（后端模型也没有它）。
    return { file_ids: fileIds, overrides, landed: { ...landed }, ...common }
  }

  if (mode === 'folders') {
    // 改目录名：不带 conflict_strategy（目录不覆盖、不自动编号）、不带 strm 字段
    // （它不写文件）, 也不带 openlist 限流 —— 这批请求只有「一部剧一次 rename」。
    return { file_ids: fileIds, overrides, ...common }
  }

  if (mode === 'dry-run') {
    return {
      file_ids: fileIds,
      overrides,
      ...common,
      ...strmFields,
      conflict_strategy: conflictStrategy,
      openlist_max_concurrent: openlistMaxConcurrent,
      openlist_request_interval: openlistRequestInterval,
    }
  }

  return { file_ids: fileIds, overrides, ...common, ...strmFields }
}
