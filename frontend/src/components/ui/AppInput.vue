<template>
  <div class="flex flex-col gap-2">
    <label v-if="label" :for="inputId" class="text-[13px] font-medium text-ink-2">{{ label }}</label>
    <input
      :id="inputId"
      :type="type"
      :value="modelValue ?? ''"
      :placeholder="placeholder"
      :disabled="disabled"
      :min="min"
      :max="max"
      :step="step"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedById"
      class="h-9 w-full rounded-[8px] border border-border-control bg-surface px-3 text-[13px] text-ink transition-colors duration-150 outline-none placeholder:text-ink-3 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35 disabled:opacity-45 disabled:cursor-not-allowed"
      :class="[mono ? 'font-mono' : '', error ? 'border-danger' : '']"
      @input="onInput"
    />
    <p v-if="error" :id="`${inputId}-error`" class="text-[12px] text-danger">{{ error }}</p>
    <p v-else-if="hint" :id="`${inputId}-hint`" class="text-[12px] text-ink-3">{{ hint }}</p>
  </div>
</template>

<script setup>
import { computed, useId } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  type: { type: String, default: 'text' },
  mono: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
  min: { type: [String, Number], default: undefined },
  max: { type: [String, Number], default: undefined },
  step: { type: [String, Number], default: undefined },
  id: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const generatedId = useId()
const inputId = computed(() => props.id || `input-${generatedId}`)

const describedById = computed(() => {
  if (props.error) return `${inputId.value}-error`
  if (props.hint) return `${inputId.value}-hint`
  return undefined
})

function onInput(event) {
  const raw = event.target.value
  if (props.type !== 'number') {
    emit('update:modelValue', raw)
    return
  }
  // 清空数字框必须得到 null（= 用服务端默认值），不能是 0。
  // 若给 0，后端 PadConfig 会把它钳到 1，界面显示 0 而实际补零 1 位，两侧不一致。
  emit('update:modelValue', raw === '' ? null : Number(raw))
}
</script>
