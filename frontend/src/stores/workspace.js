import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import { scanDirectory } from '../api/scanner'
import { previewRename, executeRename, dryRunRename } from '../api/renamer'
import { searchTmdb } from '../api/tmdb'
import { getPresets } from '../api/template'
import {
  openlistLogin,
  openlistLogout as apiLogout,
  openlistStatus as apiOlStatus,
} from '../api/openlist'

import { useFilesStore } from './files'
import { useTemplateStore } from './template'
import { useOpenListStore } from './openlist'
import { useSettingsStore } from './settings'
import { resolveOpenListServerUrl } from './settingsSchema'

export const useWorkspaceStore = defineStore('workspace', () => {
  const filesStore = useFilesStore()
  const tplStore = useTemplateStore()
  const olStore = useOpenListStore()
  const settingsStore = useSettingsStore()

  const activeSource = ref('local')

  const sourceStates = reactive({
    local: { files: [], scanResult: null, previewRows: [], scannedInfo: null, path: '' },
    openlist: { files: [], scanResult: null, previewRows: [], scannedInfo: null, path: '' },
  })

  const recursive = ref(true)
  const includeSubs = ref(true)
  const scanning = ref(false)
  const executing = ref(false)
  const executeDryRun = ref(false)
  const conflictStrategy = ref('skip')
  const resultDialog = ref(false)
  const lastResult = ref(null)
  const olForm = reactive({ server_url: '', username: '', password: '' })

  // 剧名 -> tv_id。用户重选后写入, 随每次预览/执行下发。
  // 键用 show_name **原文**（预览行上那个），后端会做归一化后匹配 ——
  // 若这里用归一化形式，后端拿到后又归一化一次，两侧对不上就静默失效。
  const tmdbOverrides = reactive({})

  const tmdbDialog = reactive({
    open: false,
    row: null,
    query: '',
    results: [],
    loading: false,
  })

  const browse = reactive({
    open: false,
    source: 'local',
    initialPath: '',
    rootPath: '',
    disallowRoot: false,
  })

  const confirm = reactive({ open: false, message: '' })
  const toast = reactive({ show: false, type: 'info', msg: '' })

  let confirmResolver = null
  let toastTimer = null

  const path = computed({
    get: () => sourceStates[activeSource.value].path,
    set: (v) => { sourceStates[activeSource.value].path = v },
  })

  const previewRows = computed({
    get: () => sourceStates[activeSource.value].previewRows,
    set: (v) => { sourceStates[activeSource.value].previewRows = v },
  })

  const scannedInfo = computed({
    get: () => sourceStates[activeSource.value].scannedInfo,
    set: (v) => { sourceStates[activeSource.value].scannedInfo = v },
  })

  const allSelected = computed(() => {
    const selected = previewRows.value.filter(r => r.selected)
    return selected.length > 0 && selected.length === previewRows.value.length
  })

  const selectedCount = computed(() => previewRows.value.filter(r => r.selected).length)

  const totalCount = computed(() => previewRows.value.length)

  function showToast(msg, type = 'info') {
    toast.msg = msg
    toast.type = type
    toast.show = true
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { toast.show = false }, 2800)
  }

  async function initialize() {
    // 冲突策略：用设置页保存的默认值作初值。用户之后在底栏改的是本次会话的
    // 临时值，不回写设置（spec §12.2）。
    conflictStrategy.value = settingsStore.conflictStrategy

    const res = await getPresets()
    const presets = res.data?.data || []
    if (presets.length) {
      tplStore.presets = presets
      // 优先用设置页指定的默认模板；它失效时（预设被删或改名）退回模板 store
      // 自带的默认，而不是留下一个空的 currentTemplate。
      const wanted = settingsStore.defaultTemplateId
      const preset =
        presets.find(p => p.id === wanted) ||
        presets.find(p => p.id === tplStore.currentPresetId)
      if (preset) tplStore.setPreset(preset)
    }

    // 设置页的「默认服务器地址」在这里生效。修复前这一行只读 olStore.serverUrl
    // —— 那是另一个 localStorage 键（episode-renamer:openlist），而设置页写的是
    // openlist.serverUrl（episode-renamer:settings），两者从不相通，于是这项设置
    // 写进去就再没人读。优先级见 resolveOpenListServerUrl。
    olForm.server_url = resolveOpenListServerUrl(
      settingsStore.openlist.serverUrl,
      olStore.serverUrl,
    )
    olForm.username = olStore.username || ''

    const statusRes = await apiOlStatus()
    if (statusRes.data?.connected) {
      olStore.setConnection(true, statusRes.data)
    }
  }

  function switchSource(name) {
    if (name === activeSource.value) return
    const prev = activeSource.value
    sourceStates[prev].files = [...filesStore.files]
    sourceStates[prev].scanResult = filesStore.scanResult

    activeSource.value = name
    filesStore.source = name
    filesStore.setFiles(sourceStates[name].files)
    filesStore.scanResult = sourceStates[name].scanResult
    // previewRows / scannedInfo 不需要恢复：它们是 `path` 那样的可写 computed，
    // 直接读写 activeSource 对应那一份 sourceStates，切源后自动指向新源。

    if (name === 'openlist') {
      tplStore.createSeasonFolder = false
    }
  }

  async function doScan() {
    if (!path.value) {
      showToast('请输入目录路径', 'warning')
      return
    }
    scanning.value = true
    try {
      const res = await scanDirectory({
        source: 'local',
        path: path.value,
        recursive: recursive.value,
        include_subtitles: includeSubs.value,
      })
      const data = res.data
      filesStore.source = 'local'
      filesStore.setFiles(data.files || [])
      filesStore.scanResult = data
      scannedInfo.value = data
      showToast(`扫描完成，发现 ${data.total_files} 个文件`, 'success')
      await buildPreview()
    } catch (e) {
      showToast('扫描失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      scanning.value = false
    }
  }

  async function doOpenListLogin() {
    olStore.loading = true
    try {
      const res = await openlistLogin({
        server_url: olForm.server_url,
        username: olForm.username,
        password: olForm.password,
      })
      olStore.setConnection(true, res.data)
      showToast('连接成功', 'success')
    } catch (e) {
      showToast('连接失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      olStore.loading = false
    }
  }

  async function doOpenListLogout() {
    await apiLogout()
    olStore.disconnect()
    showToast('已断开', 'info')
  }

  async function doOpenListScan() {
    if (!path.value || path.value === olStore.selectedMount) {
      showToast('请浏览选择具体的子目录后再扫描', 'warning')
      openOpenListBrowseDialog()
      return
    }
    scanning.value = true
    try {
      const res = await scanDirectory({
        source: 'openlist',
        path: path.value,
        recursive: recursive.value,
        include_subtitles: includeSubs.value,
      })
      const data = res.data
      filesStore.source = 'openlist'
      filesStore.setFiles(data.files || [])
      filesStore.scanResult = data
      scannedInfo.value = data
      showToast(`扫描完成，发现 ${data.total_files} 个文件`, 'success')
      await buildPreview()
    } catch (e) {
      showToast('扫描失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      scanning.value = false
    }
  }

  function onMountChange(mount) {
    // 必须先落进 store：selectedMount 是「浏览」对话框的根路径，也是要持久化的值。
    // 只清 path 会让下拉框显示新挂载点、store 里还是旧的，浏览框就从错误的根下钻，
    // 且旧值会被写回 localStorage。
    olStore.selectedMount = mount
    path.value = ''
  }

  function openOpenListBrowseDialog() {
    const mount = olStore.selectedMount || ''
    browse.source = 'openlist'
    browse.initialPath = mount
    browse.rootPath = mount
    browse.disallowRoot = true
    browse.open = true
  }

  function openLocalBrowseDialog() {
    browse.source = 'local'
    browse.initialPath = path.value || ''
    browse.rootPath = ''
    browse.disallowRoot = false
    browse.open = true
  }

  function browseConfirm(pick) {
    if (!pick) return
    if (browse.source === 'openlist' && pick.path === olStore.selectedMount) {
      showToast('不能选择云盘根目录，请进入子文件夹后再选择', 'warning')
      return
    }
    // 写回 browse.source 那一份，而不是 path.value。顶栏的源切换让 activeSource
    // 可以在对话框打开期间改变：当初促成这道防护的是那个 180ms 的源切换离场过渡
    // —— 旧的 ScanPanel 在离场期间仍然可点，用户点它的「浏览」时 activeSource 已经
    // 翻到另一源了；path.value 会写到**当前**源上，于是本地绝对路径会落进 openlist
    // 的状态（反向同理）。离场过渡已随本次重构删除，这条路径不再那么容易被走到，
    // 但这道防护是**防御性**的、代价极低，故保留。
    sourceStates[browse.source].path = pick.path
    browse.open = false
  }

  function onPresetChange(value) {
    const preset = tplStore.presets.find(p => p.id === value)
    if (preset) tplStore.setPreset(preset)
    buildPreview()
  }

  function onTemplateEdit(value) {
    tplStore.setTemplate(value)
    buildPreview()
  }

  async function buildPreview() {
    if (!filesStore.files.length) {
      previewRows.value = []
      return
    }
    try {
      const ids = filesStore.files.map(f => f.id)
      // 逐行编辑必须随预览一起下发。行内那几个输入框（剧名/季/集/标题）改的只是
      // 前端这一行, 而「新文件名」列是**服务端**按模板渲染的 —— 不把 override 发上去,
      // 用户改完点「预览」看到的还是按原解析结果算出来的文件名, 改动一点作用都没有。
      // 构造方式与 executeAction 完全一致（含未编辑行得到空对象这件事:
      // 后端把空 dict 当作「没有 override」, 不会误当成「把这些字段清空」）。
      const overrides = {}
      previewRows.value.forEach(r => {
        if (r.override) overrides[r.id] = r.override
      })
      const res = await previewRename({
        file_ids: ids,
        source: filesStore.source,
        path: filesStore.files[0].path.replace(filesStore.files[0].filename, ''),
        template: tplStore.currentTemplate,
        folder_template: tplStore.folderTemplate,
        create_season_folder: tplStore.createSeasonFolder,
        overrides,
        episode_pad_digits: settingsStore.episodePadDigits,
        season_pad_digits: settingsStore.seasonPadDigits,
        tmdb_api_key: settingsStore.tmdb.apiKey,
        tmdb_language: settingsStore.tmdb.language,
        tmdb_enabled: settingsStore.tmdb.enabled,
        tmdb_overrides: { ...tmdbOverrides },
      })
      const previews = res.data.results || []
      previewRows.value = filesStore.files.map(f => {
        const pv = previews.find(p => p.original_path === f.path) || {}
        return {
          ...f,
          selected: true,
          show_name: pv.show_name || '',
          season: pv.season,
          episode: pv.episode,
          new_filename: pv.new_filename || '',
          needs_review: pv.needs_review || false,
          confidence: pv.confidence || 0,
          title: pv.title || '',
          tmdb_status: pv.tmdb_status || 'disabled',
          tmdb_match: pv.tmdb_match || null,
          override: {},
        }
      })
    } catch (e) {
      console.error(e)
    }
  }

  function updatePreview(row) {
    row.override = {
      show_name: row.show_name,
      season: row.season,
      episode: row.episode,
      // 空串必须传 null 而不是 ''：后端 apply_override 用 `is not None` 判断,
      // 传 '' 会把手动标题写成空串, 覆盖掉 TMDB 查到的标题。
      title: row.title ? row.title : null,
    }
  }

  function toggleAll(val) {
    previewRows.value.forEach(r => { r.selected = val })
  }

  async function previewAll() {
    await buildPreview()
    showToast('预览已刷新', 'success')
  }

  function clearAll() {
    askConfirm('确定清空文件列表？这将移除当前扫描到的所有文件。').then(ok => {
      if (!ok) return
      filesStore.clear()
      previewRows.value = []
      scannedInfo.value = null
      sourceStates[activeSource.value].files = []
      sourceStates[activeSource.value].scanResult = null
    })
  }

  function askConfirm(message) {
    confirm.message = message
    confirm.open = true
    return new Promise(resolve => { confirmResolver = resolve })
  }

  function resolveConfirm(ok) {
    confirm.open = false
    if (confirmResolver) {
      confirmResolver(ok)
      confirmResolver = null
    }
  }

  async function doDryRun() {
    await executeAction(true)
  }

  async function doExecute() {
    const ok = await askConfirm(`将对 ${selectedCount.value} 个文件执行重命名操作，确认继续？`)
    if (!ok) return
    await executeAction(false)
  }

  async function executeAction(dryRun = false) {
    const selected = previewRows.value.filter(r => r.selected)
    if (!selected.length) {
      showToast('请先选择文件', 'warning')
      return
    }

    executing.value = !dryRun
    executeDryRun.value = dryRun
    try {
      const overrides = {}
      selected.forEach(r => {
        if (r.override) overrides[r.id] = r.override
      })
      const ids = selected.map(r => r.id)
      const fn = dryRun ? dryRunRename : executeRename
      const res = await fn({
        file_ids: ids,
        source: filesStore.source,
        path: selected[0].path.replace(selected[0].filename, ''),
        template: tplStore.currentTemplate,
        folder_template: tplStore.folderTemplate,
        create_season_folder: tplStore.createSeasonFolder,
        conflict_strategy: conflictStrategy.value,
        overrides,
        episode_pad_digits: settingsStore.episodePadDigits,
        season_pad_digits: settingsStore.seasonPadDigits,
        tmdb_api_key: settingsStore.tmdb.apiKey,
        tmdb_language: settingsStore.tmdb.language,
        tmdb_enabled: settingsStore.tmdb.enabled,
        tmdb_overrides: { ...tmdbOverrides },
      })
      lastResult.value = res.data
      resultDialog.value = true
      if (!dryRun) {
        await buildPreview()
      }
    } catch (e) {
      showToast('操作失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      executing.value = false
      // 同时复位 executeDryRun：HomeView 用 `v-if="!executeDryRun"` 把遮罩整个卸掉，
      // 若它停留在 true，后续的执行会在「已打开」的状态下第一次挂载遮罩，而
      // <Transition> 在没有 appear 时不会为首挂播放进入过渡 —— spec §11 的
      // 「模态进出 200ms」就静默失效了。
      executeDryRun.value = false
    }
  }

  // 设置页那个「启用 TMDB 元数据」勾选框关掉之后, 这三个入口都不得再查 TMDB,
  // 也不得让用户以为一件不会发生的事发生了 —— 关着的时候 buildPreview /
  // executeAction 会把 tmdb_enabled: false 发下去, 后端对每行都返回 disabled,
  // 于是任何「重选」都会被静默丢弃。
  //
  // 判据与后端 build_tmdb_client 的 `enabled is False` 对齐（不是 `!enabled`）:
  // 只有**显式关闭**才算关, 未表态不等于关 —— 否则一个被手工改坏的 localStorage
  // 会让前端拒绝搜索, 而同时发出去的 tmdb_enabled 并没让后端禁用, 两边不一致。
  function tmdbOff() {
    return settingsStore.tmdb.enabled === false
  }

  const TMDB_OFF_TOAST = 'TMDB 元数据已关闭，请在设置中启用'

  function rematchShow(row) {
    // 关着的时候不打开一个注定查不出东西的搜索框 —— 打开它等于给用户一个
    // 必然失败的入口, 而失败原因(开关)在界面上完全看不见。
    if (tmdbOff()) {
      showToast(TMDB_OFF_TOAST, 'warning')
      return
    }
    tmdbDialog.row = row
    tmdbDialog.query = row.show_name || ''
    tmdbDialog.results = []
    tmdbDialog.open = true
    if (tmdbDialog.query) searchShow()
  }

  async function searchShow(query) {
    const q = (typeof query === 'string' ? query : tmdbDialog.query) || ''
    if (!q.trim()) return
    // 早退必须在 searchTmdb(...) 之前 —— 这里返回得比构造请求早一步,
    // 所以关掉开关后这条路径一个网络请求都不会发出去。
    if (tmdbOff()) {
      tmdbDialog.results = []
      showToast(TMDB_OFF_TOAST, 'warning')
      return
    }
    tmdbDialog.loading = true
    try {
      const res = await searchTmdb({
        q: q.trim(),
        apiKey: settingsStore.tmdb.apiKey,
        language: settingsStore.tmdb.language,
      })
      tmdbDialog.results = res.data?.data || []
    } catch (e) {
      showToast('搜索失败: ' + (e.response?.data?.detail || e.message), 'error')
      tmdbDialog.results = []
    } finally {
      tmdbDialog.loading = false
    }
  }

  async function pickShow(item) {
    if (!tmdbDialog.row) return
    // 对话框开着的期间用户可能去设置页把开关关了（rematchShow 的守卫只挡在
    // 打开那一刻）。此时选择会被后端丢弃, 所以既不能写入 tmdbOverrides
    // （重新打开开关后它会突然生效）, 更不能弹「已选用」骗用户。
    if (tmdbOff()) {
      tmdbDialog.open = false
      showToast(TMDB_OFF_TOAST, 'warning')
      return
    }
    const showName = tmdbDialog.row.show_name
    if (showName) tmdbOverrides[showName] = item.tv_id
    tmdbDialog.open = false
    await buildPreview()
    showToast(`已选用 ${item.name}${item.year ? ` (${item.year})` : ''}`, 'success')
  }

  // 模板或补零位数变更后立即重建预览。原来这个 watch 在 HomeView 的 setup 里，
  // 状态搬进 store 后它必须一起搬，否则改模板不再刷新「新文件名」列。
  //
  // 补零位数两项是修复「设置不生效」时补上的：它们与模板同为渲染的输入，
  // 漏掉它们会让用户保存设置后回到工作区**仍看到旧位数** —— 与修复前那种
  // 「设置不生效」的观感一模一样，而 spec §15.3 要求的是「预览列立即显示」。
  //
  // TMDB 三项同因：它们也是渲染的输入（决定标题列与 TMDB 列的内容），
  // 而且三者都真的随请求下发了。语言从 zh-CN 改成 ja-JP 却不回刷，用户回到
  // 工作区看到的仍是旧语种的标题 —— 与「设置不生效」是同一个观感。
  // 设置 store 只在点「保存设置」时写入（草稿语义，见 SettingsView），所以
  // 把这些放进依赖数组不会让未保存的草稿影响工作区（Review Focus 5）。
  watch(
    () => [
      tplStore.currentTemplate, tplStore.folderTemplate, tplStore.createSeasonFolder,
      settingsStore.episodePadDigits, settingsStore.seasonPadDigits,
      settingsStore.tmdb.apiKey, settingsStore.tmdb.language, settingsStore.tmdb.enabled,
    ],
    () => { if (filesStore.files.length) buildPreview() },
    { deep: true },
  )

  return {
    activeSource, sourceStates,
    recursive, includeSubs, scanning, executing, executeDryRun,
    conflictStrategy, resultDialog, lastResult, olForm,
    browse, confirm, toast,
    path, previewRows, scannedInfo, allSelected, selectedCount, totalCount,
    initialize, switchSource,
    doScan, doOpenListScan, doOpenListLogin, doOpenListLogout, onMountChange,
    openOpenListBrowseDialog, openLocalBrowseDialog, browseConfirm,
    onPresetChange, onTemplateEdit,
    buildPreview, previewAll, updatePreview, toggleAll, clearAll,
    askConfirm, resolveConfirm, showToast,
    tmdbOverrides, tmdbDialog, rematchShow, searchShow, pickShow,
    doDryRun, doExecute, executeAction,
  }
})
