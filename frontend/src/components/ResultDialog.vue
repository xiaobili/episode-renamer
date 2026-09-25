<template>
  <AppModal :model-value="modelValue" @update:model-value="$emit('update:modelValue')" z-index="50">
    <div class="bg-surface rounded-xl shadow-2xl w-full max-w-[700px] max-h-[85vh] overflow-hidden">
      <div class="px-6 py-4 border-b border-border flex items-center justify-between">
        <div class="font-semibold text-[15px] text-text">重命名结果</div>
        <button class="text-text-faint hover:text-text transition" @click="$emit('update:modelValue', false)">
          <X class="w-5 h-5" />
        </button>
      </div>
      <div class="p-6 overflow-auto max-h-[calc(85vh-130px)]">
        <template v-if="result">
          <div class="grid grid-cols-4 gap-4 mb-4">
            <div class="text-center p-3 rounded-lg bg-surface-muted">
              <div class="text-[11px] text-text-muted">数据源</div>
              <div class="text-sm font-semibold mt-1">{{ result.source }}</div>
            </div>
            <div class="text-center p-3 rounded-lg bg-success-light">
              <div class="text-[11px] text-success">成功</div>
              <div class="text-sm font-bold mt-1 text-success">{{ result.executed }}</div>
            </div>
            <div class="text-center p-3 rounded-lg bg-surface-muted">
              <div class="text-[11px] text-text-muted">跳过</div>
              <div class="text-sm font-bold mt-1 text-text-secondary">{{ result.skipped }}</div>
            </div>
            <div class="text-center p-3 rounded-lg" :class="result.failed ? 'bg-error-light' : 'bg-surface-muted'">
              <div class="text-[11px]" :class="result.failed ? 'text-error' : 'text-text-muted'">失败</div>
              <div class="text-sm font-bold mt-1" :class="result.failed ? 'text-error' : 'text-text-secondary'">{{ result.failed }}</div>
            </div>
          </div>
          <table v-if="result.results?.length" class="w-full text-[12px]">
            <thead class="bg-surface-muted">
              <tr class="text-text-secondary">
                <th class="px-3 py-2 text-left font-semibold">原文件名</th>
                <th class="px-3 py-2 text-left font-semibold">新文件名</th>
                <th class="px-3 py-2 text-left font-semibold w-[80px]">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in result.results" :key="i" class="border-t border-border">
                <td class="px-3 py-2 text-text truncate max-w-[200px]">{{ r.original_filename }}</td>
                <td class="px-3 py-2 text-text truncate max-w-[200px]">{{ r.new_filename }}</td>
                <td class="px-3 py-2">
                  <span
                    class="inline-block px-2 py-0.5 rounded text-[11px] font-medium"
                    :class="r.success ? 'bg-success-light text-success' : 'bg-error-light text-error'"
                  >{{ r.status }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
      <div class="px-6 py-3 border-t border-border flex justify-end">
        <button
          class="h-9 px-4 bg-surface-muted hover:bg-border rounded-lg text-[13px] font-medium transition"
          @click="$emit('update:modelValue', false)"
        >关闭</button>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { X } from 'lucide-vue-next'
import AppModal from './ui/AppModal.vue'

defineProps({
  modelValue: Boolean,
  result: { type: Object, default: null },
})
defineEmits(['update:modelValue'])
</script>
