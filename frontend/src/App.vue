<template>
  <!-- 顶栏 / 路由内容两行骨架。grid-cols-1 与 HomeView 根上那一处同因同理：
       裸的 grid 只有一条隐式列，隐式列取 auto，auto 的下限是内容的 min-content ——
       极窄屏下顶栏（品牌名 nowrap + 分段控件）的 min-content 会超过视口，轨道随之
       撑宽、右侧被本层的 overflow-hidden 静默切掉。显式声明 minmax(0, 1fr) 把下限
       归零，轨道才能缩到视口以内；顶栏品牌名本就有 min-w-0 + truncate，收缩路径是
       现成的，所以允许收缩不会把裁切从轨道转移到内容上。 -->
  <div class="grid h-dvh grid-cols-1 grid-rows-[56px_1fr] overflow-hidden bg-canvas">
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
