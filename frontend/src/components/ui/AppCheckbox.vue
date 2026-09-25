<template>
  <label
    class="inline-flex items-center gap-2 select-none"
    :class="disabled ? 'cursor-not-allowed' : 'cursor-pointer'"
  >
    <span class="relative inline-flex h-4 w-4 shrink-0 items-center justify-center">
      <input
        type="checkbox"
        :checked="modelValue"
        :disabled="disabled"
        :aria-label="ariaLabel || undefined"
        class="peer h-4 w-4 appearance-none rounded-[4px] border border-border-control bg-surface transition-colors duration-150 outline-none checked:border-accent checked:bg-accent focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-45 disabled:cursor-not-allowed"
        @change="$emit('update:modelValue', $event.target.checked)"
      />
      <Check
        class="pointer-events-none absolute h-3 w-3 text-white opacity-0 peer-checked:opacity-100"
        aria-hidden="true"
      />
    </span>
    <span v-if="label || $slots.default" class="text-[13px] text-ink-2" :class="disabled ? 'opacity-45' : ''">
      <slot>{{ label }}</slot>
    </span>
  </label>
</template>

<script setup>
import { Check } from 'lucide-vue-next'

defineProps({
  modelValue: { type: Boolean, default: false },
  label: { type: String, default: '' },
  // 无可见 label 时的无障碍名（表格单元格等没空间放可见文字的场景）。
  ariaLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>
