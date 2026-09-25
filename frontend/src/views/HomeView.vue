<template>
  <div class="flex flex-col gap-4">
    <Transition name="source-fade" mode="out-in">
    <div :key="ws.activeSource" class="flex flex-col gap-4">

      <ScanPanel
        :source="ws.activeSource"
        :local-path="ws.path"
        :recursive="ws.recursive"
        :include-subs="ws.includeSubs"
        :scanning="ws.scanning"
        :openlist-browse-path="ws.path"
        :ol-store="olStore"
        :ol-form="ws.olForm"
        @update:local-path="ws.path = $event"
        @update:recursive="ws.recursive = $event"
        @update:include-subs="ws.includeSubs = $event"
        @scan="ws.activeSource === 'local' ? ws.doScan() : ws.doOpenListScan()"
        @login="ws.doOpenListLogin"
        @logout="ws.doOpenListLogout"
        @browse="ws.openOpenListBrowseDialog"
        @browse-local="ws.openLocalBrowseDialog"
        @mount-change="ws.onMountChange"
      />

      <TemplateConfig
        :tpl-store="tplStore"
        :source="ws.activeSource"
        @preset-change="ws.onPresetChange"
        @template-edit="ws.onTemplateEdit"
        @update:createSeasonFolder="v => tplStore.createSeasonFolder = v"
        @update:folderTemplate="v => tplStore.folderTemplate = v"
      />

      <FileTable
        :files-store="filesStore"
        :preview-rows="ws.previewRows"
        :scanned-info="ws.scannedInfo"
        :all-selected="ws.allSelected"
        :active-source="ws.activeSource"
        @preview-all="ws.previewAll"
        @clear-all="ws.clearAll"
        @toggle-all="ws.toggleAll"
        @select-row="({ row, val }) => row.selected = val"
        @update-row="ws.updatePreview"
        @quick-scan="ws.doScan"
      />

    </div>
    </Transition>

    <ActionBar
      :conflict-strategy="ws.conflictStrategy"
      :selected-count="ws.selectedCount"
      :executing="ws.executing"
      @update:conflict-strategy="ws.conflictStrategy = $event"
      @dry-run="ws.doDryRun"
      @execute="ws.doExecute"
    />

    <ConfirmDialog
      v-model="ws.confirm.open"
      :message="ws.confirm.message"
      @ok="ws.resolveConfirm(true)"
      @cancel="ws.resolveConfirm(false)"
    />

    <ExecutingOverlay v-if="!ws.executeDryRun" v-model="ws.executing" :dry-run="ws.executeDryRun" />

    <ResultDialog v-model="ws.resultDialog" :result="ws.lastResult" />

    <BrowseDialog
      v-model="ws.browse.open"
      :source="ws.browse.source"
      :initial-path="ws.browse.initialPath"
      :root-path="ws.browse.rootPath"
      :disallow-root="ws.browse.disallowRoot"
      @confirm="ws.browseConfirm"
      @error="(m) => ws.showToast(m, 'error')"
    />

    <Toast :show="ws.toast.show" :type="ws.toast.type" :msg="ws.toast.msg" />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'

import { useFilesStore } from '../stores/files'
import { useTemplateStore } from '../stores/template'
import { useOpenListStore } from '../stores/openlist'
import { useWorkspaceStore } from '../stores/workspace'

import ScanPanel from '../components/ScanPanel.vue'
import TemplateConfig from '../components/TemplateConfig.vue'
import FileTable from '../components/FileTable.vue'
import ActionBar from '../components/ActionBar.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ExecutingOverlay from '../components/ExecutingOverlay.vue'
import ResultDialog from '../components/ResultDialog.vue'
import BrowseDialog from '../components/BrowseDialog.vue'
import Toast from '../components/Toast.vue'

const ws = useWorkspaceStore()

// 这三个 store 实例**必须保留**：模板里仍要把它们当 prop 传给本期尚未改造
// 的子组件（FileTable 的 :files-store、TemplateConfig 的 :tpl-store、
// ScanPanel 的 :ol-store）。漏掉任何一个，对应的 prop 会收到 undefined。
// filesStore 会一直留到第四期 FileTable 彻底改用 workspace store 之后。
const filesStore = useFilesStore()
const tplStore = useTemplateStore()
const olStore = useOpenListStore()

// 旧的源切换卡片留下的数据源列表（含 emoji）。那张卡片已在 Task 2 被顶栏的
// segmented control 取代并删除，这个数组因此失去了唯一的消费者；它的清理留给
// Task 3 ——那时旧卡片栈整体重构，本文件的其他旧结构也一并消失。本任务不制造
// 这份死代码，所以不动它。
const sources = [
  { name: 'local', label: '本地磁盘', icon: '📁' },
  { name: 'openlist', label: 'OpenList 云盘', icon: '☁️' },
]

onMounted(() => { ws.initialize() })

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
