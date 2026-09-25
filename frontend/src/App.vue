<template>
  <div class="grid h-dvh grid-rows-[56px_1fr] overflow-hidden bg-canvas">
    <AppTopBar
      :source="ws.activeSource"
      :show-source-switch="route.name === 'Home'"
      @update:source="ws.switchSource($event)"
    />

    <!-- 整条滚动链的第一环：这个容器必须允许自己被压缩到比内容更矮。少了它，
         路由内容会把这一行撑破，超出的下半部分被裁掉且无法滚动到 —— 内容静默
         丢失，比出现滚动条更糟（外壳整体不滚动，所以不会有页面滚动条兜底）。 -->
    <div class="min-h-0 overflow-hidden">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'

import AppTopBar from './components/layout/AppTopBar.vue'
import { useWorkspaceStore } from './stores/workspace'

const route = useRoute()
const ws = useWorkspaceStore()
</script>
