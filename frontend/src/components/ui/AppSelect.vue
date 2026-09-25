<template>
  <div class="flex flex-col gap-2">
    <label v-if="label" :for="selectId" class="text-[13px] font-medium text-ink-2">{{ label }}</label>
    <div class="relative">
      <select
        :id="selectId"
        :value="modelValue"
        :disabled="disabled"
        class="h-9 w-full appearance-none rounded-[8px] border border-border-control bg-surface pl-3 pr-8 text-[13px] text-ink transition-colors duration-150 outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35 disabled:opacity-45 disabled:cursor-not-allowed"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <slot />
      </select>
      <ChevronDown
        class="pointer-events-none absolute top-1/2 right-2.5 h-4 w-4 -translate-y-1/2 text-ink-3"
        aria-hidden="true"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, useId } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  id: { type: String, default: '' },
})
defineEmits(['update:modelValue'])

const generatedId = useId()
const selectId = computed(() => props.id || `select-${generatedId}`)
</script>
