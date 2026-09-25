<template>
  <span
    class="inline-flex items-center gap-1 whitespace-nowrap rounded-[8px] px-2 py-0.5 text-[12px] font-medium"
    :class="TONE_CLASSES[tone]"
  >
    <slot name="icon" />
    <slot />
  </span>
</template>

<script setup>
// 状态表达的统一入口。全站只有这四种 tone，不允许在调用处临时拼颜色。
//
// 「成功」故意没有自己的 tone：强调色占用了绿系，绿色不再表达成功
// （spec §5.2）。「已解析」用 neutral + 对勾图标，「待确认」用 warn。
const TONE_CLASSES = {
  neutral: 'bg-sunken text-ink-2',
  accent: 'bg-accent-soft text-accent',
  warn: 'bg-warn-soft text-warn',
  danger: 'bg-danger-soft text-danger',
}

defineProps({
  tone: {
    type: String,
    default: 'neutral',
    validator: (v) => ['neutral', 'accent', 'warn', 'danger'].includes(v),
  },
})
</script>
