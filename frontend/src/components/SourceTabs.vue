<template>
  <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
    <div class="flex border-b border-border bg-surface-muted">
      <button
        v-for="src in sources"
        :key="src.name"
        class="px-5 py-3 text-[13px] font-medium transition-all relative"
        :class="modelValue === src.name
          ? 'text-primary font-semibold bg-surface'
          : 'text-text-secondary hover:text-text'"
        @click="$emit('update:modelValue', src.name)"
      >
        <span class="mr-1.5">{{ src.icon }}</span>{{ src.label }}
        <span
          v-if="modelValue === src.name"
          class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
        />
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, required: true },
  sources: { type: Array, required: true },
})
defineEmits(['update:modelValue'])
</script>
