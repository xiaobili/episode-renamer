<template>
  <div class="grid h-dvh grid-rows-[56px_1fr] overflow-hidden bg-canvas">
    <AppTopBar
      :source="ws.activeSource"
      :show-source-switch="route.name === 'Home'"
      @update:source="ws.switchSource($event)"
    />

    <!-- min-h-0 是整条链的第一环：少了它，路由内容会把 grid 行撑破，
         整页开始滚动，底栏被推出视口。 -->
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
