<template>
  <AppModal
    :model-value="modelValue"
    title="重命名结果"
    z-index="50"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="flex max-h-[85vh] w-full max-w-[700px] flex-col overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 class="text-[14px] font-semibold text-ink">重命名结果</h2>
        <button
          type="button"
          aria-label="关闭"
          class="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
          @click="$emit('update:modelValue', false)"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-5">
        <template v-if="result">
          <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">数据源</div>
              <div class="mt-1 text-[13px] font-semibold text-ink">{{ result.source }}</div>
            </div>
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">成功</div>
              <div class="mt-1 text-[13px] font-semibold tabular-nums text-ink">{{ result.executed }}</div>
            </div>
            <div class="rounded-[8px] bg-sunken p-3 text-center">
              <div class="text-[11px] text-ink-3">跳过</div>
              <div class="mt-1 text-[13px] font-semibold tabular-nums text-ink">{{ result.skipped }}</div>
            </div>
            <div
              class="rounded-[8px] p-3 text-center"
              :class="result.failed ? 'bg-danger-soft' : 'bg-sunken'"
            >
              <div class="text-[11px]" :class="result.failed ? 'text-danger' : 'text-ink-3'">失败</div>
              <div
                class="mt-1 text-[13px] font-semibold tabular-nums"
                :class="result.failed ? 'text-danger' : 'text-ink'"
              >{{ result.failed }}</div>
            </div>
          </div>

          <table v-if="result.results?.length" class="w-full text-[12px]">
            <thead class="bg-sunken">
              <tr class="text-ink-2">
                <th class="px-3 py-2 text-left font-semibold">原文件名</th>
                <th class="px-3 py-2 text-left font-semibold">新文件名</th>
                <th class="w-[100px] px-3 py-2 text-left font-semibold">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in result.results" :key="i" class="border-t border-line">
                <td class="max-w-[220px] truncate px-3 py-2 text-ink">{{ r.original_filename }}</td>
                <td class="max-w-[220px] truncate px-3 py-2 text-ink">{{ r.new_filename }}</td>
                <td class="px-3 py-2">
                  <AppBadge :tone="r.success ? 'neutral' : 'danger'">
                    <template #icon>
                      <AlertTriangle v-if="!r.success" class="h-3.5 w-3.5" aria-hidden="true" />
                      <Check v-else class="h-3.5 w-3.5" aria-hidden="true" />
                    </template>
                    {{ r.status }}
                  </AppBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>

      <div class="flex shrink-0 justify-end border-t border-line px-5 py-3">
        <AppButton variant="secondary" @click="$emit('update:modelValue', false)">关闭</AppButton>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { AlertTriangle, Check, X } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'
import AppBadge from './ui/AppBadge.vue'

defineProps({
  modelValue: Boolean,
  result: { type: Object, default: null },
})
defineEmits(['update:modelValue'])
</script>
