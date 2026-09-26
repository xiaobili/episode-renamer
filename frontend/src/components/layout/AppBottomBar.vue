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

    <!-- 刮削在途时这两个动作一并禁用（spec §17.4）。理由不是「怕并发」：
         `scraped` 在 await **之前**就置位，而屏幕上的表仍是刮削前那一张 ——
         放行执行就会写出**用户没见过的文件名**（载荷带上了 TMDB 标题，表里还是旧名），
         正是 §17.6 与 R29/R52/R54 一直在防的「预览与执行不一致」。
         禁用而非 loading：loading 属于发起的那个动作（刮削按钮在 FileTable 里），
         这两个按钮若一起转圈会让人以为它们也在跑。 -->
    <div class="flex shrink-0 items-center gap-2">
      <AppButton
        variant="secondary"
        :disabled="!selectedCount || scraping"
        @click="$emit('dry-run')"
      >
        试运行
      </AppButton>
      <AppButton
        variant="primary"
        :loading="executing"
        :disabled="!selectedCount || scraping"
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
  // 刮削在途（见模板里的注释）。默认 false：本组件在别处被单独使用时不该因此变灰。
  scraping: { type: Boolean, default: false },
})
defineEmits(['update:conflictStrategy', 'dry-run', 'execute'])
</script>
