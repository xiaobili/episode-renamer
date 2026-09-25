<template>
  <header
    class="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-surface px-4"
  >
    <div class="flex min-w-0 items-center gap-2.5">
      <BrandMark :size="28" class="text-accent" />
      <span class="truncate text-[14px] font-semibold text-ink">Episode Renamer</span>
    </div>

    <div
      v-if="showSourceSwitch"
      role="group"
      aria-label="文件来源"
      class="flex shrink-0 items-center gap-0.5 rounded-[8px] bg-sunken p-0.5"
    >
      <button
        v-for="src in SOURCES"
        :key="src.name"
        type="button"
        :aria-pressed="source === src.name"
        class="h-7 rounded-[6px] px-3 text-[12px] font-medium transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
        :class="source === src.name ? 'bg-accent-soft text-accent' : 'text-ink-2 hover:text-ink'"
        @click="$emit('update:source', src.name)"
      >
        {{ src.label }}
      </button>
    </div>

    <RouterLink
      :to="onSettings ? '/' : '/settings'"
      :aria-label="onSettings ? '返回工作区' : '设置'"
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
    >
      <ArrowLeft v-if="onSettings" class="h-4 w-4" />
      <SettingsIcon v-else class="h-4 w-4" />
    </RouterLink>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Settings as SettingsIcon } from 'lucide-vue-next'

import BrandMark from '../BrandMark.vue'

// 本地磁盘 / OpenList 两段。这里不再有 emoji —— 旧的源切换卡片上那对文件夹 /
// 云朵图标随它一起删除（spec §3.5 第 12 条）。
const SOURCES = [
  { name: 'local', label: '本地磁盘' },
  { name: 'openlist', label: 'OpenList' },
]

defineProps({
  source: { type: String, default: 'local' },
  showSourceSwitch: { type: Boolean, default: false },
})
defineEmits(['update:source'])

const route = useRoute()
const onSettings = computed(() => route.name === 'Settings')
</script>
