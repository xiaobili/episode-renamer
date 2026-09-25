<template>
  <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
    <div class="px-6 py-4 border-b border-border flex items-center justify-between">
      <div class="flex items-center gap-2 font-semibold text-[14px] text-text">
        <List class="w-4 h-4 text-primary" />
        文件列表
        <span v-if="filesStore.files.length" class="text-[12px] font-normal text-text-muted ml-2">
          共 {{ filesStore.files.length }} 个文件
          <span v-if="scannedInfo"> (视频 {{ scannedInfo.videos }} / 字幕 {{ scannedInfo.subtitles }})</span>
        </span>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="h-8 px-3 bg-surface hover:bg-surface-muted border border-border-strong text-text-secondary hover:text-primary rounded-md text-[12px] font-medium flex items-center gap-1.5 transition disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!filesStore.files.length"
          @click="$emit('preview-all')"
        >
          <Eye class="w-3.5 h-3.5" />
          预览
        </button>
        <button
          class="h-8 px-3 bg-error-light hover:bg-error hover:text-white border border-error text-error rounded-md text-[12px] font-medium flex items-center gap-1.5 transition disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!filesStore.files.length"
          @click="$emit('clear-all')"
        >
          <Trash2 class="w-3.5 h-3.5" />
          清空
        </button>
      </div>
    </div>

    <div class="relative">
      <div
        v-if="filesStore.scanning"
        class="absolute inset-0 bg-white/60 z-10 flex items-center justify-center"
      >
        <div class="text-text-muted text-[13px]">扫描中...</div>
      </div>
      <div class="overflow-auto" style="max-height: 480px">
        <table class="w-full text-[13px]">
          <thead class="bg-surface-muted sticky top-0 z-[1]">
            <tr class="text-text-secondary">
              <th class="w-12 px-4 py-3 text-left font-semibold">#</th>
              <th class="w-12 px-4 py-3 text-left font-semibold">
                <input
                  type="checkbox"
                  :checked="allSelected"
                  class="w-4 h-4 accent-primary rounded"
                  @change="$emit('toggle-all', $event.target.checked)"
                />
              </th>
              <th class="px-4 py-3 text-left font-semibold min-w-[220px]">原文件名</th>
              <th class="px-4 py-3 text-left font-semibold w-[160px]">解析剧名</th>
              <th class="px-4 py-3 text-left font-semibold w-[90px]">季</th>
              <th class="px-4 py-3 text-left font-semibold w-[90px]">集</th>
              <th class="px-4 py-3 text-left font-semibold w-[80px]">置信度</th>
              <th class="px-4 py-3 text-left font-semibold min-w-[220px]">新文件名</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="previewRows.length">
              <tr
                v-for="(row, idx) in previewRows"
                :key="row.id"
                class="border-t border-border hover:bg-primary-light/40 transition"
              >
                <td class="px-4 py-2.5 text-text-faint">{{ idx + 1 }}</td>
                <td class="px-4 py-2.5">
                  <input type="checkbox" :checked="row.selected" @change="$emit('select-row', { row, val: $event.target.checked })" class="w-4 h-4 accent-primary rounded" />
                </td>
                <td class="px-4 py-2.5">
                  <div class="text-text truncate max-w-[320px]">{{ row.filename }}</div>
                  <div class="text-[11px] text-text-faint truncate max-w-[320px]">{{ row.path }}</div>
                </td>
                <td class="px-4 py-2.5">
                  <input
                    :value="row.show_name"
                    @change="$emit('update-row', row)"
                    class="w-full h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </td>
                <td class="px-4 py-2.5">
                  <input
                    :value="row.season"
                    @change="$emit('update-row', row)"
                    type="number" min="1" max="30"
                    class="w-full h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </td>
                <td class="px-4 py-2.5">
                  <input
                    :value="row.episode"
                    @change="$emit('update-row', row)"
                    type="number" min="1" max="999"
                    class="w-full h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </td>
                <td class="px-4 py-2.5">
                  <span
                    class="inline-block px-2 py-0.5 rounded text-[11px] font-medium"
                    :class="row.needs_review
                      ? 'bg-warning-light text-warning'
                      : 'bg-success-light text-success'"
                  >{{ row.needs_review ? '⚠️ 待确认' : '✅ 已解析' }}</span>
                </td>
                <td class="px-4 py-2.5">
                  <div
                    class="truncate font-medium"
                    :class="row.new_filename && row.new_filename !== row.filename ? 'text-success' : 'text-text-muted'"
                  >
                    {{ row.new_filename || '(未解析)' }}
                  </div>
                </td>
              </tr>
            </template>
            <tr v-else>
              <td colspan="8" class="px-4 py-16 text-center">
                <div class="flex flex-col items-center gap-2 text-text-muted">
                  <FileQuestion class="w-10 h-10 text-text-faint" />
                  <div class="text-[13px]">扫描目录以加载文件</div>
                  <button
                    v-if="activeSource === 'local'"
                    class="mt-2 h-9 px-4 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium transition"
                    @click="$emit('quick-scan')"
                  >开始扫描</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { List, Eye, Trash2, FileQuestion } from 'lucide-vue-next'

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
