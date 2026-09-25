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
        <AppButton
          size="sm"
          variant="secondary"
          :disabled="!filesStore.files.length"
          @click="$emit('preview-all')"
        >
          预览
        </AppButton>
        <AppButton
          size="sm"
          variant="danger"
          :disabled="!filesStore.files.length"
          @click="$emit('clear-all')"
        >
          清空
        </AppButton>
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
              <AppCheckbox
                :model-value="allSelected"
                aria-label="全选"
                @update:model-value="$emit('toggle-all', $event)"
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
                <AppCheckbox
                  :model-value="row.selected"
                  :aria-label="`选择 ${row.filename}`"
                  @update:model-value="$emit('select-row', { row, val: $event })"
                />
              </td>
              <td class="px-4 py-2.5">
                <div class="max-w-[320px] truncate text-ink">{{ row.filename }}</div>
                <div class="max-w-[320px] truncate text-[11px] text-ink-3">{{ row.path }}</div>
              </td>
              <td class="hidden px-4 py-2.5 md:table-cell">
                <AppInput
                  v-model="row.show_name"
                  size="sm"
                  aria-label="解析剧名"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppInput
                  v-model.number="row.season"
                  size="sm"
                  type="number"
                  :min="1"
                  :max="30"
                  aria-label="季"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppInput
                  v-model.number="row.episode"
                  size="sm"
                  type="number"
                  :min="1"
                  :max="999"
                  aria-label="集"
                  @update:model-value="$emit('update-row', row)"
                />
              </td>
              <td class="px-4 py-2.5">
                <AppBadge :tone="row.needs_review ? 'warn' : 'neutral'">
                  <template #icon>
                    <AlertTriangle v-if="row.needs_review" class="h-3.5 w-3.5" aria-hidden="true" />
                    <Check v-else class="h-3.5 w-3.5" aria-hidden="true" />
                  </template>
                  {{ row.needs_review ? '待确认' : '已解析' }}
                </AppBadge>
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
                <AppButton
                  v-if="activeSource === 'local'"
                  variant="primary"
                  class="mt-2"
                  @click="$emit('quick-scan')"
                >
                  开始扫描
                </AppButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { AlertTriangle, Check, FileQuestion } from 'lucide-vue-next'

import AppBadge from './ui/AppBadge.vue'
import AppButton from './ui/AppButton.vue'
import AppCheckbox from './ui/AppCheckbox.vue'
import AppInput from './ui/AppInput.vue'

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
