<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface">
    <div class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-3">
      <div class="flex min-w-0 items-center gap-2 text-[14px] font-semibold text-ink">
        <span class="truncate">文件列表</span>
        <span v-if="filesStore.files.length" class="truncate text-[12px] font-normal text-ink-3">
          共 {{ filesStore.files.length }} 个文件
          <span v-if="scannedInfo"> (视频 {{ scannedInfo.videos }} / 字幕 {{ scannedInfo.subtitles }})</span>
        </span>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <button
          class="h-8 rounded-[8px] border border-line-strong bg-surface px-3 text-[12px] font-medium text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none disabled:opacity-45 disabled:cursor-not-allowed"
          :disabled="!filesStore.files.length"
          @click="$emit('preview-all')"
        >
          预览
        </button>
        <button
          class="h-8 rounded-[8px] border border-danger bg-surface px-3 text-[12px] font-medium text-danger transition-colors duration-150 hover:bg-danger-soft focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none disabled:opacity-45 disabled:cursor-not-allowed"
          :disabled="!filesStore.files.length"
          @click="$emit('clear-all')"
        >
          清空
        </button>
      </div>
    </div>

    <!-- 滚动容器。flex-1 + min-h-0 让它吃掉父容器剩余高度并在内部滚动，
         而不是把页面撑高（spec §7.2）。 -->
    <div class="min-h-0 flex-1 overflow-auto">
      <table class="w-full min-w-[560px] text-[13px]">
        <thead class="sticky top-0 z-[1] bg-sunken">
          <tr class="text-ink-2">
            <th class="hidden w-12 px-4 py-3 text-left font-semibold sm:table-cell">#</th>
            <th class="w-12 px-4 py-3 text-left font-semibold">
              <input
                type="checkbox"
                :checked="allSelected"
                aria-label="全选"
                class="h-4 w-4 accent-accent"
                @change="$emit('toggle-all', $event.target.checked)"
              />
            </th>
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[220px]">原文件名</th>
            <th class="hidden w-[160px] px-4 py-3 text-left font-semibold md:table-cell">解析剧名</th>
            <th class="w-[72px] px-4 py-3 text-left font-semibold md:w-[80px]">季</th>
            <th class="w-[72px] px-4 py-3 text-left font-semibold md:w-[80px]">集</th>
            <th class="w-[80px] px-4 py-3 text-left font-semibold md:w-[96px]">状态</th>
            <th class="min-w-[140px] px-4 py-3 text-left font-semibold md:min-w-[220px]">新文件名</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="previewRows.length">
            <tr
              v-for="(row, idx) in previewRows"
              :key="row.id"
              class="border-t border-line transition-colors duration-150 hover:bg-sunken/60"
            >
              <td class="hidden px-4 py-2.5 text-ink-3 tabular-nums sm:table-cell">{{ idx + 1 }}</td>
              <td class="px-4 py-2.5">
                <input
                  type="checkbox"
                  :checked="row.selected"
                  :aria-label="`选择 ${row.filename}`"
                  class="h-4 w-4 accent-accent"
                  @change="$emit('select-row', { row, val: $event.target.checked })"
                />
              </td>
              <td class="px-4 py-2.5">
                <div class="max-w-[320px] truncate text-ink">{{ row.filename }}</div>
                <div class="max-w-[320px] truncate text-[11px] text-ink-3">{{ row.path }}</div>
              </td>
              <td class="hidden px-4 py-2.5 md:table-cell">
                <input
                  v-model="row.show_name"
                  aria-label="解析剧名"
                  @change="$emit('update-row', row)"
                  class="h-8 w-full rounded-[8px] border border-border-control bg-surface px-2.5 text-[13px] text-ink transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35"
                />
              </td>
              <td class="px-4 py-2.5">
                <input
                  v-model.number="row.season"
                  type="number" min="1" max="30"
                  aria-label="季"
                  @change="$emit('update-row', row)"
                  class="h-8 w-full rounded-[8px] border border-border-control bg-surface px-2.5 text-[13px] text-ink tabular-nums transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35"
                />
              </td>
              <td class="px-4 py-2.5">
                <input
                  v-model.number="row.episode"
                  type="number" min="1" max="999"
                  aria-label="集"
                  @change="$emit('update-row', row)"
                  class="h-8 w-full rounded-[8px] border border-border-control bg-surface px-2.5 text-[13px] text-ink tabular-nums transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35"
                />
              </td>
              <td class="px-4 py-2.5">
                <span
                  class="inline-flex items-center gap-1 whitespace-nowrap rounded-[8px] px-2 py-0.5 text-[12px] font-medium"
                  :class="row.needs_review ? 'bg-warn-soft text-warn' : 'bg-sunken text-ink-2'"
                >
                  {{ row.needs_review ? '待确认' : '已解析' }}
                </span>
              </td>
              <td class="px-4 py-2.5">
                <div class="truncate font-medium text-ink" :class="row.new_filename ? '' : 'text-ink-3'">
                  {{ row.new_filename || '(未解析)' }}
                </div>
              </td>
            </tr>
          </template>
          <tr v-else>
            <td colspan="8" class="px-4 py-16 text-center">
              <div class="flex flex-col items-center gap-2 text-ink-2">
                <FileQuestion class="h-10 w-10 text-ink-3" aria-hidden="true" />
                <div class="text-[13px]">扫描目录以加载文件</div>
                <button
                  v-if="activeSource === 'local'"
                  class="mt-2 h-9 rounded-[8px] bg-accent px-4 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
                  @click="$emit('quick-scan')"
                >开始扫描</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { FileQuestion } from 'lucide-vue-next'

defineProps({
  filesStore: { type: Object, required: true },
  previewRows: { type: Array, default: () => [] },
  scannedInfo: Object,
  allSelected: Boolean,
  activeSource: String,
})
defineEmits([
  'preview-all', 'clear-all', 'toggle-all', 'select-row', 'update-row', 'quick-scan',
])
</script>
