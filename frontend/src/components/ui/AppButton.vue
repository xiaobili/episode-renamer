<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading ? 'true' : undefined"
    class="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[8px] font-medium transition-colors duration-150 select-none active:scale-[.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-45 disabled:cursor-not-allowed"
    :class="[VARIANT_CLASSES[variant], SIZE_CLASSES[size], block ? 'w-full' : '']"
  >
    <Loader2 v-if="loading" class="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
    <slot />
  </button>
</template>

<script setup>
import { Loader2 } from 'lucide-vue-next'

const VARIANT_CLASSES = {
  primary: 'bg-accent text-white hover:bg-accent-hover',
  secondary: 'border border-line-strong bg-surface text-ink-2 hover:bg-sunken hover:text-ink',
  danger: 'bg-danger text-white hover:bg-danger-hover',
  ghost: 'text-ink-2 hover:bg-sunken hover:text-ink',
}

const SIZE_CLASSES = {
  sm: 'h-8 px-3 text-[12px]',
  md: 'h-9 px-4 text-[13px]',
}

defineProps({
  variant: {
    type: String,
    default: 'secondary',
    validator: (v) => ['primary', 'secondary', 'danger', 'ghost'].includes(v),
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md'].includes(v),
  },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
  block: { type: Boolean, default: false },
})
</script>
