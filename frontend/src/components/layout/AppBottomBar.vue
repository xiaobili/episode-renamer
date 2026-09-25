<template>
  <footer
    class="flex h-14 shrink-0 items-center justify-between gap-3 border-t border-line bg-surface px-4"
  >
    <div class="flex min-w-0 items-center gap-3">
      <AppSelect
        :model-value="conflictStrategy"
        aria-label="冲突策略"
        class="w-[132px]"
        @update:model-value="$emit('update:conflictStrategy', $event)"
      >
        <option label="跳过" value="skip" />
        <option label="中止" value="abort" />
        <option label="覆盖" value="overwrite" />
        <option label="自动编号" value="rename_dup" />
      </AppSelect>

      <span class="hidden truncate text-[13px] text-ink-2 sm:inline">
        已选 <span class="tabular-nums text-ink">{{ selectedCount }}</span>
        / <span class="tabular-nums">{{ totalCount }}</span>
      </span>
    </div>

    <div class="flex shrink-0 items-center gap-2">
      <AppButton variant="secondary" :disabled="!selectedCount" @click="$emit('dry-run')">
        试运行
      </AppButton>
      <AppButton
        variant="primary"
        :loading="executing"
        :disabled="!selectedCount"
        @click="$emit('execute')"
      >
        <span class="sm:hidden">{{ executing ? '执行中…' : '执行' }}</span>
        <span class="hidden sm:inline">{{ executing ? '执行中…' : '执行重命名' }}</span>
      </AppButton>
    </div>
  </footer>
</template>

<script setup>
import AppButton from '../ui/AppButton.vue'
import AppSelect from '../ui/AppSelect.vue'

defineProps({
  conflictStrategy: { type: String, default: 'skip' },
  selectedCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
  executing: { type: Boolean, default: false },
})
defineEmits(['update:conflictStrategy', 'dry-run', 'execute'])
</script>
