<template>
  <div class="flex flex-col gap-4">
    <SourceTabs v-model="activeSource" :sources="sources" />

    <Transition name="source-fade" mode="out-in">
    <div :key="activeSource" class="flex flex-col gap-4">

      <ScanPanel
        :source="activeSource"
        :local-path="localPath"
        :recursive="recursive"
        :include-subs="includeSubs"
        :scanning="scanning"
        :openlist-browse-path="openlistBrowsePath"
        :ol-store="olStore"
        :ol-form="olForm"
        @update:local-path="localPath = $event"
        @update:recursive="recursive = $event"
        @update:include-subs="includeSubs = $event"
        @scan="activeSource === 'local' ? doScan() : doOpenListScan()"
        @login="doOpenListLogin"
        @logout="doOpenListLogout"
        @browse="openOpenListBrowseDialog"
        @browse-local="openLocalBrowseDialog"
        @mount-change="onMountChange"
      />

      <TemplateConfig
        :tpl-store="tplStore"
        :source="activeSource"
        @preset-change="onPresetChange"
        @template-edit="onTemplateEdit"
        @update:createSeasonFolder="v => tplStore.createSeasonFolder = v"
        @update:folderTemplate="v => tplStore.folderTemplate = v"
      />

      <FileTable
        :files-store="filesStore"
        :preview-rows="previewRows"
        :scanned-info="scannedInfo"
        :all-selected="allSelected"
        :active-source="activeSource"
        @preview-all="previewAll"
        @clear-all="clearAll"
        @toggle-all="toggleAll"
        @select-row="({ row, val }) => row.selected = val"
        @update-row="updatePreview"
        @quick-scan="doScan"
      />

    </div>
    </Transition>

    <ActionBar
      :conflict-strategy="conflictStrategy"
      :selected-count="selectedCount"
      :executing="executing"
      @update:conflict-strategy="conflictStrategy = $event"
      @dry-run="doDryRun"
      @execute="doExecute"
    />

    <ConfirmDialog
      v-model="confirmDialog"
      :message="confirmMessage"
      @ok="onConfirmOk"
      @cancel="onConfirmCancel"
    />

    <ExecutingOverlay v-if="!executeDryRun" v-model="executing" :dry-run="executeDryRun" />

    <ResultDialog v-model="resultDialog" :result="lastResult" />

    <BrowseDialog
      v-model="browseDialog"
      :source="browseSource"
      :initial-path="browseInitialPath"
      :root-path="browseRootPath"
      :disallow-root="browseDisallowRoot"
      @confirm="browseConfirm"
      @error="(m) => showToast(m, 'error')"
    />

    <Toast :show="toast.show" :type="toast.type" :msg="toast.msg" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'

import { useFilesStore } from '../stores/files'
import { useTemplateStore } from '../stores/template'
import { useOpenListStore } from '../stores/openlist'

import { scanDirectory } from '../api/scanner'
import { previewRename, executeRename, dryRunRename } from '../api/renamer'
import { getPresets } from '../api/template'
import { openlistLogin, openlistLogout as apiLogout, openlistStatus as apiOlStatus } from '../api/openlist'

import SourceTabs from '../components/SourceTabs.vue'
import ScanPanel from '../components/ScanPanel.vue'
import TemplateConfig from '../components/TemplateConfig.vue'
import FileTable from '../components/FileTable.vue'
import ActionBar from '../components/ActionBar.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ExecutingOverlay from '../components/ExecutingOverlay.vue'
import ResultDialog from '../components/ResultDialog.vue'
import BrowseDialog from '../components/BrowseDialog.vue'
import Toast from '../components/Toast.vue'

const sources = [
  { name: 'local', label: '本地磁盘', icon: '📁' },
  { name: 'openlist', label: 'OpenList 云盘', icon: '☁️' },
]

const toast = reactive({ show: false, type: 'info', msg: '' })
let toastTimer = null
function showToast(msg, type = 'info') {
  toast.msg = msg
  toast.type = type
  toast.show = true
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.show = false }, 2800)
}

const filesStore = useFilesStore()
const tplStore = useTemplateStore()
const olStore = useOpenListStore()

const activeSource = ref('local')

const sourceStates = reactive({
  local: {
    files: [],
    scanResult: null,
    previewRows: [],
    scannedInfo: null,
    path: '',
  },
  openlist: {
    files: [],
    scanResult: null,
    previewRows: [],
    scannedInfo: null,
    path: '',
  },
})

const localPath = computed({
  get: () => sourceStates.local.path,
  set: (v) => { sourceStates.local.path = v },
})
const openlistBrowsePath = computed({
  get: () => sourceStates.openlist.path,
  set: (v) => { sourceStates.openlist.path = v },
})
const previewRows = computed({
  get: () => sourceStates[activeSource.value].previewRows,
  set: (v) => { sourceStates[activeSource.value].previewRows = v },
})
const scannedInfo = computed({
  get: () => sourceStates[activeSource.value].scannedInfo,
  set: (v) => { sourceStates[activeSource.value].scannedInfo = v },
})

const recursive = ref(true)
const includeSubs = ref(true)
const scanning = ref(false)
const executing = ref(false)
const executeDryRun = ref(false)
const confirmDialog = ref(false)
const confirmMessage = ref('')
let confirmResolver = null
const conflictStrategy = ref('skip')
const resultDialog = ref(false)
const lastResult = ref(null)

const browseDialog = ref(false)
const browseSource = ref('local')
const browseInitialPath = ref('')
const browseRootPath = ref('')
const browseDisallowRoot = ref(false)

const olForm = reactive({ server_url: '', username: '', password: '' })

const allSelected = computed(() => {
  const selected = previewRows.value.filter(r => r.selected)
  return selected.length > 0 && selected.length === previewRows.value.length
})

const selectedCount = computed(() => {
  return previewRows.value.filter(r => r.selected).length
})

onMounted(async () => {
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
})

function switchSource(name) {
  if (name === activeSource.value) return
  activeSource.value = name
  filesStore.clear()
  previewRows.value = []
  scannedInfo.value = null
  if (name === 'openlist') {
    tplStore.createSeasonFolder = false
  }
}

async function doScan() {
  if (!localPath.value) {
    showToast('请输入目录路径', 'warning')
    return
  }
  scanning.value = true
  try {
    const res = await scanDirectory({
      source: 'local',
      path: localPath.value,
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
    const data = res.data
    olStore.setConnection(true, data)
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
  if (!openlistBrowsePath.value || openlistBrowsePath.value === olStore.selectedMount) {
    showToast('请浏览选择具体的子目录后再扫描', 'warning')
    openOpenListBrowseDialog()
    return
  }
  scanning.value = true
  try {
    const res = await scanDirectory({
      source: 'openlist',
      path: openlistBrowsePath.value,
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
  openlistBrowsePath.value = ''
}

function openOpenListBrowseDialog() {
  const mount = olStore.selectedMount || ''
  browseSource.value = 'openlist'
  browseInitialPath.value = mount
  browseRootPath.value = mount
  browseDisallowRoot.value = true
  browseDialog.value = true
}

function openLocalBrowseDialog() {
  browseSource.value = 'local'
  browseInitialPath.value = localPath.value || ''
  browseRootPath.value = ''
  browseDisallowRoot.value = false
  browseDialog.value = true
}

function browseConfirm(pick) {
  if (!pick) return
  if (browseSource.value === 'openlist') {
    if (pick.path === olStore.selectedMount) {
      showToast('不能选择云盘根目录，请进入子文件夹后再选择', 'warning')
      return
    }
    openlistBrowsePath.value = pick.path
  } else {
    localPath.value = pick.path
  }
  browseDialog.value = false
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
  showConfirm('确定清空文件列表？这将移除当前扫描到的所有文件。').then(ok => {
    if (ok) {
      filesStore.clear()
      previewRows.value = []
      scannedInfo.value = null
      sourceStates[activeSource.value].files = []
      sourceStates[activeSource.value].scanResult = null
    }
  })
}

async function showConfirm(message) {
  confirmMessage.value = message
  confirmDialog.value = true
  return new Promise(resolve => {
    confirmResolver = resolve
  })
}

function onConfirmOk() {
  confirmDialog.value = false
  if (confirmResolver) {
    confirmResolver(true)
    confirmResolver = null
  }
}

function onConfirmCancel() {
  confirmDialog.value = false
  if (confirmResolver) {
    confirmResolver(false)
    confirmResolver = null
  }
}

async function doDryRun() {
  await executeAction(true)
}

async function doExecute() {
  const ok = await showConfirm(`将对 ${selectedCount.value} 个文件执行重命名操作，确认继续？`)
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

watch(
  () => activeSource.value,
  (name, prev) => {
    if (prev) {
      sourceStates[prev].files = [...filesStore.files]
      sourceStates[prev].scanResult = filesStore.scanResult
    }
    filesStore.source = name
    filesStore.setFiles(sourceStates[name].files)
    filesStore.scanResult = sourceStates[name].scanResult
    if (name === 'openlist') {
      tplStore.createSeasonFolder = false
    }
  }
)

watch(
  () => [tplStore.currentTemplate, tplStore.folderTemplate, tplStore.createSeasonFolder],
  () => { if (filesStore.files.length) buildPreview() },
  { deep: true }
)
</script>

<style scoped>
.source-fade-enter-active {
  transition: opacity 0.22s ease-out, transform 0.22s ease-out;
}
.source-fade-leave-active {
  transition: opacity 0.18s ease-in, transform 0.18s ease-in;
}
.source-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.source-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
