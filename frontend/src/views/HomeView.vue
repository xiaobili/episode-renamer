<template>
  <div class="home-view">
    <el-row :gutter="16">
      <el-col :span="24">
        <el-card class="panel">
          <el-tabs v-model="activeSource" @tab-change="onSourceChange">
            <el-tab-pane label="📁 本地磁盘" name="local" />
            <el-tab-pane label="☁️ OpenList 云盘" name="openlist" />
          </el-tabs>

          <template v-if="activeSource === 'local'">
            <div class="path-row">
              <el-input
                v-model="localPath"
                placeholder="输入要扫描的目录路径，如 /home/user/Movies"
                clearable
                style="flex: 1"
              >
                <template #prefix>
                  <el-icon><Folder /></el-icon>
                </template>
              </el-input>
              <el-checkbox v-model="recursive" label="递归扫描" />
              <el-checkbox v-model="includeSubs" label="包含字幕" />
              <el-button type="primary" :loading="scanning" @click="doScan">
                <el-icon><Search /></el-icon>扫描
              </el-button>
            </div>
          </template>

          <template v-else>
            <div class="path-row">
              <template v-if="!olStore.connected">
                <el-form :inline="true" style="width: 100%">
                  <el-form-item label="服务器">
                    <el-input v-model="olForm.server_url" placeholder="http://localhost:5244" style="width: 220px" />
                  </el-form-item>
                  <el-form-item label="用户名">
                    <el-input v-model="olForm.username" placeholder="admin" style="width: 120px" />
                  </el-form-item>
                  <el-form-item label="密码">
                    <el-input v-model="olForm.password" type="password" placeholder="••••••" show-password style="width: 140px" />
                  </el-form-item>
                  <el-form-item>
                    <el-button :loading="olStore.loading" type="primary" @click="doOpenListLogin">
                      <el-icon><Connection /></el-icon>连接
                    </el-button>
                  </el-form-item>
                </el-form>
              </template>
              <template v-else>
                <el-tag type="success" effect="light" style="margin-right: 12px">
                  <el-icon><CircleCheck /></el-icon>已连接: {{ olStore.serverUrl }}
                </el-tag>
                <el-select v-model="olStore.selectedMount" style="width: 160px; margin-right: 8px" @change="onMountChange">
                  <el-option
                    v-for="m in olStore.mountPoints"
                    :key="m"
                    :label="m"
                    :value="m"
                  />
                </el-select>
                <el-input
                  v-model="openlistBrowsePath"
                  placeholder="点击浏览选择目录"
                  readonly
                  style="flex: 1; margin-right: 8px; cursor: pointer"
                  @click="openBrowseDialog"
                >
                  <template #prefix>
                    <el-icon><Folder /></el-icon>
                  </template>
                  <template #suffix>
                    <el-icon style="cursor: pointer" @click="openBrowseDialog"><FolderOpened /></el-icon>
                  </template>
                </el-input>
                <el-button :loading="scanning" type="primary" @click="doOpenListScan">
                  <el-icon><Search /></el-icon>扫描
                </el-button>
                <el-button @click="doOpenListLogout">
                  <el-icon><SwitchButton /></el-icon>断开
                </el-button>
              </template>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="24">
        <el-card class="panel">
          <template #header>
            <div class="panel-header">
              <span>📝 重命名模板</span>
            </div>
          </template>
          <div class="template-row">
            <el-select v-model="tplStore.currentPresetId" placeholder="选择预设模板" style="width: 240px" @change="onPresetChange">
              <el-option
                v-for="p in tplStore.presets"
                :key="p.id"
                :label="p.name"
                :value="p.id"
              />
            </el-select>
            <el-input
              v-model="tplStore.currentTemplate"
              placeholder="自定义模板"
              @input="onTemplateEdit"
            />
            <el-checkbox v-model="tplStore.createSeasonFolder" label="创建季文件夹" />
            <el-input
              v-if="tplStore.createSeasonFolder"
              v-model="tplStore.folderTemplate"
              placeholder="季文件夹模板，如 Season {season_padded}"
              style="width: 240px"
            />
          </div>
          <div class="template-hint">
            <span>可用变量: </span>
            <el-tag size="small" v-for="v in templateVars" :key="v" style="margin-right: 4px">{{ v }}</el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="24">
        <el-card class="panel">
          <template #header>
            <div class="panel-header">
              <span>📋 文件列表</span>
              <div class="header-actions">
                <span v-if="filesStore.files.length" class="stats">
                  共 {{ filesStore.files.length }} 个文件
                  <span v-if="scannedInfo">
                    (视频 {{ scannedInfo.videos }} / 字幕 {{ scannedInfo.subtitles }})
                  </span>
                </span>
                <el-button size="small" @click="previewAll" :disabled="!filesStore.files.length">
                  <el-icon><View /></el-icon>预览
                </el-button>
                <el-button size="small" type="danger" plain @click="clearAll" :disabled="!filesStore.files.length">
                  <el-icon><Delete /></el-icon>清空
                </el-button>
              </div>
            </div>
          </template>

          <el-table
            v-loading="filesStore.scanning"
            :data="previewRows"
            border
            stripe
            style="width: 100%"
            height="480"
            max-height="600"
          >
            <el-table-column width="50" type="index" label="#" />
            <el-table-column width="60">
              <template #header>
                <el-checkbox :model-value="allSelected" @change="toggleAll" />
              </template>
              <template #default="{ row }">
                <el-checkbox v-model="row.selected" />
              </template>
            </el-table-column>
            <el-table-column label="原文件名" min-width="240" show-overflow-tooltip>
              <template #default="{ row }">
                <div>{{ row.filename }}</div>
                <div class="path-sub">{{ row.path }}</div>
              </template>
            </el-table-column>
            <el-table-column label="解析剧名" width="180">
              <template #default="{ row }">
                <el-input
                  size="small"
                  v-model="row.show_name"
                  @change="updatePreview(row)"
                />
              </template>
            </el-table-column>
            <el-table-column label="季" width="80">
              <template #default="{ row }">
                <el-input-number
                  size="small"
                  v-model="row.season"
                  :min="1"
                  :max="30"
                  controls-position="right"
                  @change="updatePreview(row)"
                />
              </template>
            </el-table-column>
            <el-table-column label="集" width="80">
              <template #default="{ row }">
                <el-input-number
                  size="small"
                  v-model="row.episode"
                  :min="1"
                  :max="999"
                  controls-position="right"
                  @change="updatePreview(row)"
                />
              </template>
            </el-table-column>
            <el-table-column label="置信度" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.needs_review" type="warning" size="small">⚠️</el-tag>
                <el-tag v-else type="success" size="small">✅</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="新文件名" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">
                <div :class="{ 'new-name-diff': row.new_filename !== row.filename }">
                  {{ row.new_filename || '(未解析)' }}
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="!filesStore.files.length" class="empty-state">
            <el-empty description="扫描目录以加载文件">
              <el-button v-if="activeSource === 'local'" type="primary" @click="doScan">开始扫描</el-button>
            </el-empty>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="24">
        <el-card class="panel">
          <div class="action-bar">
            <span class="hint">
              冲突策略:
              <el-select v-model="conflictStrategy" size="small" style="width: 100px; margin-left: 4px">
                <el-option label="跳过" value="skip" />
                <el-option label="中止" value="abort" />
                <el-option label="覆盖" value="overwrite" />
                <el-option label="自动编号" value="rename_dup" />
              </el-select>
            </span>
            <div class="actions">
              <el-button :disabled="!selectedCount" @click="doDryRun">
                <el-icon><Document /></el-icon>试运行 (Dry Run)
              </el-button>
              <el-button type="primary" :disabled="!selectedCount" :loading="executing" @click="doExecute">
                <el-icon><Promotion /></el-icon>执行重命名
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="resultDialog" title="重命名结果" width="600px">
      <div v-if="lastResult">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="数据源">{{ lastResult.source }}</el-descriptions-item>
          <el-descriptions-item label="成功">{{ lastResult.executed }}</el-descriptions-item>
          <el-descriptions-item label="跳过">{{ lastResult.skipped }}</el-descriptions-item>
          <el-descriptions-item label="失败">{{ lastResult.failed }}</el-descriptions-item>
        </el-descriptions>
        <el-table v-if="lastResult.results?.length" :data="lastResult.results" border stripe size="small" style="margin-top: 12px">
          <el-table-column prop="original_filename" label="原文件名" show-overflow-tooltip />
          <el-table-column prop="new_filename" label="新文件名" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="resultDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="browseDialog" title="选择目录" width="520px">
      <div class="browse-nav">
        <el-button size="small" :disabled="!browseCurrent || browseCurrent === browseRoot" @click="browseTo(browseParent)">
          <el-icon><Back /></el-icon>上级
        </el-button>
        <el-breadcrumb separator="/" style="flex: 1; margin-left: 12px">
          <el-breadcrumb-item
            v-for="(seg, idx) in browseBreadcrumbs"
            :key="idx"
            @click="browseTo(seg.path)"
          >{{ seg.name }}</el-breadcrumb-item>
        </el-breadcrumb>
      </div>
      <div v-loading="browseLoading" class="browse-list">
        <div
          v-for="d in browseDirs"
          :key="d.path"
          class="browse-item"
          @dblclick="browseTo(d.path)"
          @click="browsePick(d)"
          :class="{ active: browseSelected?.path === d.path }"
        >
          <el-icon class="browse-icon"><Folder /></el-icon>
          <span class="browse-name">{{ d.name }}</span>
        </div>
        <el-empty v-if="!browseLoading && !browseDirs.length" description="此目录无子目录" />
      </div>
      <template #footer>
        <el-button @click="browseDialog = false">取消</el-button>
        <el-button :disabled="!browseSelected" @click="browseConfirm">确定选择</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder, FolderOpened, Search, View, Delete, Connection, CircleCheck, SwitchButton, Document, Promotion, Back } from '@element-plus/icons-vue'

import { useFilesStore } from '../stores/files'
import { useTemplateStore } from '../stores/template'
import { useOpenListStore } from '../stores/openlist'

import { scanDirectory, getCachedFiles } from '../api/scanner'
import { previewRename, executeRename, dryRunRename } from '../api/renamer'
import { getPresets } from '../api/template'
import { openlistLogin, openlistLogout as apiLogout, openlistStatus as apiOlStatus, openlistBrowse } from '../api/openlist'

const filesStore = useFilesStore()
const tplStore = useTemplateStore()
const olStore = useOpenListStore()

const activeSource = ref('local')
const localPath = ref('')
const openlistBrowsePath = ref('')
const recursive = ref(true)
const includeSubs = ref(true)
const scanning = ref(false)
const executing = ref(false)
const conflictStrategy = ref('skip')
const scannedInfo = ref(null)
const resultDialog = ref(false)
const lastResult = ref(null)

const browseDialog = ref(false)
const browseLoading = ref(false)
const browseCurrent = ref('')
const browseParent = ref('')
const browseRoot = ref('')
const browseDirs = ref([])
const browseSelected = ref(null)

const olForm = reactive({ server_url: '', username: '', password: '' })

const templateVars = ['{show}', '{season}', '{season_padded}', '{episode}', '{episode_padded}', '{extension}', '{quality}', '{source}', '{sub_lang}']

const previewRows = ref([])

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

function onSourceChange() {
  filesStore.clear()
  previewRows.value = []
  scannedInfo.value = null
}

async function doScan() {
  if (!localPath.value) {
    ElMessage.warning('请输入目录路径')
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
    ElMessage.success(`扫描完成，发现 ${data.total_files} 个文件`)
    await buildPreview()
  } catch (e) {
    ElMessage.error('扫描失败')
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
    ElMessage.success('连接成功')
  } catch (e) {
    ElMessage.error('连接失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    olStore.loading = false
  }
}

async function doOpenListLogout() {
  await apiLogout()
  olStore.disconnect()
  ElMessage.success('已断开')
}

async function doOpenListScan() {
  const fullPath = openlistBrowsePath.value || olStore.selectedMount || ''
  if (!fullPath) {
    ElMessage.warning('请选择挂载点或浏览选择目录')
    return
  }
  scanning.value = true
  try {
    const res = await scanDirectory({
      source: 'openlist',
      path: fullPath,
      recursive: recursive.value,
      include_subtitles: includeSubs.value,
    })
    const data = res.data
    filesStore.source = 'openlist'
    filesStore.setFiles(data.files || [])
    filesStore.scanResult = data
    scannedInfo.value = data
    ElMessage.success(`扫描完成，发现 ${data.total_files} 个文件`)
    await buildPreview()
  } catch (e) {
    ElMessage.error('扫描失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    scanning.value = false
  }
}

function onPresetChange() {
  const preset = tplStore.presets.find(p => p.id === tplStore.currentPresetId)
  if (preset) tplStore.setPreset(preset)
  buildPreview()
}

function onTemplateEdit() {
  tplStore.currentPresetId = ''
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
  ElMessage.success('预览已刷新')
}

function clearAll() {
  ElMessageBox.confirm('确定清空文件列表？', '提示', {
    type: 'warning',
  }).then(async () => {
    filesStore.clear()
    previewRows.value = []
    scannedInfo.value = null
  }).catch(() => {})
}

async function doDryRun() {
  await executeAction(true)
}

async function doExecute() {
  ElMessageBox.confirm(
    `将对 ${selectedCount.value} 个文件执行重命名操作，确认继续？`,
    '确认执行',
    { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' }
  ).then(() => executeAction(false)).catch(() => {})
}

async function executeAction(dryRun = false) {
  const selected = previewRows.value.filter(r => r.selected)
  if (!selected.length) {
    ElMessage.warning('请先选择文件')
    return
  }

  executing.value = true
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
    ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    executing.value = false
  }
}

watch(
  () => [tplStore.currentTemplate, tplStore.folderTemplate, tplStore.createSeasonFolder],
  () => { if (filesStore.files.length) buildPreview() },
  { deep: true }
)

const browseBreadcrumbs = computed(() => {
  const root = browseRoot.value
  const cur = browseCurrent.value
  const segs = [{ name: root || '/', path: root || '/' }]
  if (cur && cur !== root) {
    const rel = cur.startsWith(root) ? cur.slice(root.length) : cur
    rel.split('/').filter(Boolean).forEach((part, i, arr) => {
      segs.push({
        name: part,
        path: root + '/' + arr.slice(0, i + 1).join('/'),
      })
    })
  }
  return segs
})

function onMountChange() {
  openlistBrowsePath.value = ''
}

function openBrowseDialog() {
  const mount = olStore.selectedMount || ''
  browseRoot.value = mount
  browseParent.value = mount
  browseCurrent.value = mount
  browseSelected.value = null
  browseDirs.value = []
  browseDialog.value = true
  browseLoad(mount)
}

async function browseLoad(path) {
  browseLoading.value = true
  try {
    const res = await openlistBrowse(path)
    const data = res.data
    browseDirs.value = data.dirs || []
    browseParent.value = data.parent
    browseCurrent.value = data.path
  } catch (e) {
    ElMessage.error('加载目录失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    browseLoading.value = false
  }
}

function browsePick(d) {
  browseSelected.value = d
}

function browseTo(path) {
  if (!path || path === browseCurrent.value) return
  browseLoad(path)
}

function browseConfirm() {
  const pick = browseSelected.value
  if (!pick) return
  openlistBrowsePath.value = pick.path
  browseDialog.value = false
}
</script>

<style scoped>
.panel {
  border-radius: 8px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stats {
  font-size: 13px;
  color: #909399;
  margin-right: 12px;
}

.path-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.template-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.template-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}

.path-sub {
  font-size: 11px;
  color: #c0c4cc;
}

.new-name-diff {
  color: #67c23a;
  font-weight: 500;
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hint {
  font-size: 13px;
  color: #606266;
}

.actions {
  display: flex;
  gap: 12px;
}

.empty-state {
  padding: 20px 0;
}

.browse-nav {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.browse-list {
  min-height: 260px;
  max-height: 360px;
  overflow-y: auto;
}

.browse-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.browse-item:hover {
  background: #f5f7fa;
}

.browse-item.active {
  background: #ecf5ff;
  color: #409eff;
}

.browse-icon {
  font-size: 18px;
  margin-right: 10px;
  color: #e6a23c;
}

.browse-item.active .browse-icon {
  color: #409eff;
}

.browse-name {
  font-size: 14px;
}
</style>
