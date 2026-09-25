<template>
  <AppModal
    :model-value="modelValue"
    title="确认执行"
    z-index="55"
    @update:model-value="onModalUpdate"
  >
    <div class="w-full max-w-[420px] overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex items-start gap-3.5 px-5 py-5">
        <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-warn-soft">
          <AlertTriangle class="h-4.5 w-4.5 text-warn" aria-hidden="true" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="text-[13px] leading-relaxed text-ink-2">{{ message }}</p>
        </div>
      </div>
      <div class="flex justify-end gap-2 border-t border-line bg-sunken px-5 py-3">
        <AppButton variant="secondary" @click="$emit('cancel')">取消</AppButton>
        <AppButton variant="primary" @click="$emit('ok')">确定</AppButton>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { AlertTriangle } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'

defineProps({
  modelValue: Boolean,
  message: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'ok', 'cancel'])

// AppModal 在 Esc / 点遮罩时会 emit(false)。那不是「确认」，必须让上层拿到 cancel，
// 否则 askConfirm() 的 promise 永远不 resolve，调用方的 .then() 静默不执行。
function onModalUpdate(value) {
  emit('update:modelValue', value)
  if (!value) emit('cancel')
}
</script>
