<template>
  <AppModal
    :model-value="modelValue"
    title="选择 TMDB 剧集"
    z-index="50"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="w-full max-w-[520px] overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 class="text-[14px] font-semibold text-ink">选择 TMDB 剧集</h2>
        <button
          type="button"
          aria-label="关闭"
          class="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
          @click="$emit('update:modelValue', false)"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div class="p-5">
        <form class="mb-4 flex items-end gap-2" @submit.prevent="$emit('search', query)">
          <AppInput
            v-model="query"
            label="剧名"
            :placeholder="row?.show_name || '输入剧名搜索'"
          />
          <AppButton variant="secondary" type="submit" :loading="loading">搜索</AppButton>
        </form>

        <div v-if="!results.length" class="py-12 text-center text-[13px] text-ink-3">
          {{ loading ? '搜索中…' : '没有结果。换个关键词，或确认 TMDB 已启用。' }}
        </div>

        <ul v-else class="flex max-h-[320px] flex-col gap-1 overflow-y-auto">
          <li v-for="item in results" :key="item.tv_id">
            <button
              type="button"
              class="w-full rounded-[8px] border border-line px-3 py-2 text-left transition-colors duration-150 hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
              @click="$emit('pick', item)"
            >
              <div class="text-[13px] font-medium text-ink">
                {{ item.name }}<span v-if="item.year" class="text-ink-3"> ({{ item.year }})</span>
              </div>
              <div
                v-if="item.original_name && item.original_name !== item.name"
                class="text-[11px] text-ink-3"
              >
                {{ item.original_name }}
              </div>
            </button>
          </li>
        </ul>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

import AppButton from './ui/AppButton.vue'
import AppInput from './ui/AppInput.vue'
import AppModal from './ui/AppModal.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  row: { type: Object, default: null },
  results: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
defineEmits(['update:modelValue', 'search', 'pick'])

const query = ref('')

// 每次打开都把搜索框重置成该行的剧名 —— 上一次残留的关键词会让用户
// 对着一个不属于当前行的搜索结果做选择。
watch(() => props.modelValue, (open) => {
  if (open) query.value = props.row?.show_name || ''
})
</script>
