<template>
  <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
    <div class="px-6 py-4 flex items-center justify-between flex-wrap gap-3">
      <div class="flex items-center gap-2 text-[13px] text-text-secondary">
        <span>冲突策略:</span>
        <select
          :value="conflictStrategy"
          @change="$emit('update:conflictStrategy', $event.target.value)"
          class="h-8 px-2.5 rounded-md border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        >
          <option label="跳过" value="skip" />
          <option label="中止" value="abort" />
          <option label="覆盖" value="overwrite" />
          <option label="自动编号" value="rename_dup" />
        </select>
      </div>
      <div class="flex items-center gap-3">
        <button
          class="h-10 px-5 bg-surface hover:bg-surface-muted border border-border-strong text-text-secondary hover:text-primary rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!selectedCount"
          @click="$emit('dry-run')"
        >
          <Play class="w-4 h-4" />
          试运行 (Dry Run)
        </button>
        <button
          class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!selectedCount"
          @click="$emit('execute')"
        >
          <Rocket class="w-4 h-4" />
          {{ executing ? '执行中...' : '执行重命名' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Play, Rocket } from 'lucide-vue-next'

defineProps({
  conflictStrategy: { type: String, default: 'skip' },
  selectedCount: { type: Number, default: 0 },
  executing: Boolean,
})
defineEmits(['update:conflictStrategy', 'dry-run', 'execute'])
</script>
