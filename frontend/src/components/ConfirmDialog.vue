<template>
  <AppModal :model-value="modelValue" @update:model-value="$emit('update:modelValue')" z-index="55">
    <div class="bg-surface rounded-xl shadow-2xl w-full max-w-[420px] overflow-hidden">
      <div class="px-6 py-5 flex items-start gap-4">
        <div class="w-10 h-10 rounded-full bg-warning-light flex items-center justify-center shrink-0">
          <AlertTriangle class="w-5 h-5 text-warning" />
        </div>
        <div class="flex-1">
          <div class="font-semibold text-[15px] text-text mb-1">确认执行</div>
          <div class="text-[13px] text-text-secondary leading-relaxed">{{ message }}</div>
        </div>
      </div>
      <div class="px-6 py-3 border-t border-border bg-surface-muted flex justify-end gap-2">
        <button
          class="h-9 px-4 bg-surface hover:bg-border border border-border-strong rounded-lg text-[13px] font-medium text-text-secondary hover:text-text transition"
          @click="$emit('cancel')"
        >取消</button>
        <button
          class="h-9 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium transition"
          @click="$emit('ok')"
        >确定</button>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { AlertTriangle } from 'lucide-vue-next'
import AppModal from './ui/AppModal.vue'

defineProps({
  modelValue: Boolean,
  message: { type: String, default: '' },
})
defineEmits(['update:modelValue', 'ok', 'cancel'])
</script>
