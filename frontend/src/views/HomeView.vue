<template>
  <!-- 两行骨架：第一行是「左栏 + 工作区」，第二行是常驻底栏。根自身也是滚动链上
       的一环 —— 它必须限制自身高度，否则中段的内容会把行撑破，底栏被推出视口。
       中段自己不再滚动：左栏滚自己，工作区里的表滚自己（见下面各自的 overflow）。
       对话框与提示条全部挪到网格之外，网格里只留两个子项，不会产生隐式空行。 -->
  <div class="grid h-full min-h-0 grid-rows-[1fr_56px] overflow-hidden">
    <!-- 窄屏是一行「可展开的左栏条带 + 其下的工作区」，两行高度由内容决定，
         所以用 flex-col；lg 起才是严格的两列等高分栏。 -->
    <div class="flex min-h-0 flex-col overflow-hidden lg:grid lg:grid-cols-[280px_1fr]">
      <AppLeftRail>
        <template #source>
          <SourceConfigPanel
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
        </template>

        <template #template>
          <TemplateConfig
            :tpl-store="tplStore"
            :source="ws.activeSource"
            @preset-change="ws.onPresetChange"
            @template-edit="ws.onTemplateEdit"
            @update:createSeasonFolder="v => tplStore.createSeasonFolder = v"
            @update:folderTemplate="v => tplStore.folderTemplate = v"
          />
        </template>
      </AppLeftRail>

      <!-- 工作区自身不滚动：底色是 surface，与 canvas 的左栏形成明度差（spec §5.4），
           露出的边界就是工作区的边缘。Table 撑满这里剩下的高度、并在自己内部滚动，
           所以本层只负责给出高度与底色，不再需要「整块工作区可滚」那种兜底。 -->
      <main class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface">
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
      </main>
    </div>

    <AppBottomBar
      :conflict-strategy="ws.conflictStrategy"
      :selected-count="ws.selectedCount"
      :total-count="ws.totalCount"
      :executing="ws.executing"
      @update:conflict-strategy="ws.conflictStrategy = $event"
      @dry-run="ws.doDryRun"
      @execute="ws.doExecute"
    />
  </div>

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
</template>

<script setup>
import { onMounted } from 'vue'

import { useFilesStore } from '../stores/files'
import { useTemplateStore } from '../stores/template'
import { useOpenListStore } from '../stores/openlist'
import { useWorkspaceStore } from '../stores/workspace'

import SourceConfigPanel from '../components/SourceConfigPanel.vue'
import TemplateConfig from '../components/TemplateConfig.vue'
import FileTable from '../components/FileTable.vue'
import AppBottomBar from '../components/layout/AppBottomBar.vue'
import AppLeftRail from '../components/layout/AppLeftRail.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ExecutingOverlay from '../components/ExecutingOverlay.vue'
import ResultDialog from '../components/ResultDialog.vue'
import BrowseDialog from '../components/BrowseDialog.vue'
import Toast from '../components/Toast.vue'

const ws = useWorkspaceStore()

// 这三个 store 实例**必须保留**：模板里仍要把它们当 prop 传给本期尚未改造
// 的子组件（FileTable 的 :files-store、TemplateConfig 的 :tpl-store、
// SourceConfigPanel 的 :ol-store）。漏掉任何一个，对应的 prop 会收到 undefined。
// filesStore 会一直留到第四期 FileTable 彻底改用 workspace store 之后。
const filesStore = useFilesStore()
const tplStore = useTemplateStore()
const olStore = useOpenListStore()

onMounted(() => { ws.initialize() })
</script>
