<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    class="shrink-0"
  >
    <rect width="24" height="24" rx="6" fill="currentColor" />
    <g
      class="text-white"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M7.5 12h7.5" />
      <path d="M12.5 9.25 15.25 12l-2.75 2.75" />
    </g>
  </svg>
</template>

<script setup>
// 品牌标记：圆角方框 + 内部向右箭头（重命名 = 从「原名」指向「新名」）。
// 单色几何，靠 currentColor 上色；<g class="text-white"> 只改变箭头自身的
// currentColor，方框仍取外层颜色。
defineProps({
  size: { type: Number, default: 28 },
})
</script>
