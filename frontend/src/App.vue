<template>
  <div class="flex h-screen overflow-hidden">
    <aside class="w-60 shrink-0 bg-surface border-r border-border flex flex-col px-4 py-6">
      <div class="flex items-center gap-3 px-2 pb-5 border-b border-border mb-4">
        <BrandMark :size="40" class="text-accent" />
        <div>
          <div class="text-[15px] font-bold text-text -tracking-[0.01em]">Episode Renamer</div>
          <div class="text-xs text-text-muted mt-0.5">影视自动化重命名</div>
        </div>
      </div>

      <nav class="flex-1 flex flex-col gap-1">
        <div
          class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-medium cursor-pointer transition-all select-none"
          :class="route.path === '/'
            ? 'bg-primary-light text-primary font-semibold'
            : 'text-text-secondary hover:bg-surface-muted hover:text-text'"
          @click="$router.push('/')"
        >
          <FolderOpen class="w-4 h-4" />
          <span>重命名工作区</span>
        </div>
        <div
          class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-medium cursor-pointer transition-all select-none"
          :class="route.path === '/settings'
            ? 'bg-primary-light text-primary font-semibold'
            : 'text-text-secondary hover:bg-surface-muted hover:text-text'"
          @click="$router.push('/settings')"
        >
          <Settings class="w-4 h-4" />
          <span>设置</span>
        </div>
      </nav>

      <div class="pt-4 border-t border-border">
        <div class="text-xs text-text-faint px-2">v1.0.0</div>
      </div>
    </aside>

    <main class="flex-1 overflow-auto bg-bg">
      <div class="p-8 max-w-[1400px] mx-auto">
        <router-view v-slot="{ Component, route }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" :key="route.fullPath" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { FolderOpen, Settings } from 'lucide-vue-next'
import BrandMark from './components/BrandMark.vue'

const route = useRoute()
</script>

<style>
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
