import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import { scanDirectory } from '../api/scanner'
import { previewRename, executeRename, dryRunRename } from '../api/renamer'
import { getPresets } from '../api/template'
import {
  openlistLogin,
  openlistLogout as apiLogout,
  openlistStatus as apiOlStatus,
} from '../api/openlist'

import { useFilesStore } from './files'
import { useTemplateStore } from './template'
import { useOpenListStore } from './openlist'

export const useWorkspaceStore = defineStore('workspace', () => {
  const filesStore = useFilesStore()
  const tplStore = useTemplateStore()
  const olStore = useOpenListStore()

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
    const res = await getPresets()
    if (res.data?.data) {
      tplStore.presets = res.data.data
      const def = tplStore.presets.find(p => p.id === tplStore.currentPresetId)
      if (def) tplStore.setPreset(def)
    }

    olForm.server_url = olStore.serverUrl || ''
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

  function onMountChange() {
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
    // 但这道防护是**防御性**的、代价极低，故保留：对话框常驻期间源仍可切换。
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
      const res = await previewRename({
        file_ids: ids,
        source: filesStore.source,
        path: filesStore.files[0].path.replace(filesStore.files[0].filename, ''),
        template: tplStore.currentTemplate,
        folder_template: tplStore.folderTemplate,
        create_season_folder: tplStore.createSeasonFolder,
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
    }
  }

  // 模板变更后立即重建预览。原来这个 watch 在 HomeView 的 setup 里，
  // 状态搬进 store 后它必须一起搬，否则改模板不再刷新「新文件名」列。
  watch(
    () => [tplStore.currentTemplate, tplStore.folderTemplate, tplStore.createSeasonFolder],
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
    doDryRun, doExecute, executeAction,
  }
})
