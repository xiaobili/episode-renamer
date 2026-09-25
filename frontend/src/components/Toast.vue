<template>
  <Transition name="toast">
    <div
      v-if="show"
      :role="isAlert ? 'alert' : 'status'"
      :aria-live="isAlert ? 'assertive' : 'polite'"
      class="fixed top-4 right-4 z-[100] flex items-center gap-2 rounded-[8px] border px-3.5 py-2.5 text-[13px] font-medium shadow-overlay"
      :class="TONE_CLASSES[type] || TONE_CLASSES.info"
    >
      <AlertTriangle v-if="type === 'error' || type === 'warning'" class="h-4 w-4 shrink-0" aria-hidden="true" />
      <Check v-else class="h-4 w-4 shrink-0" aria-hidden="true" />
      <span class="max-w-[320px]">{{ msg }}</span>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { AlertTriangle, Check } from 'lucide-vue-next'

// 成功不再是绿色（spec §5.2：颜色只承担「强调」与「告警」两种职责）。
//
// 这不违反 toast 的最佳实践 —— 通行做法是「严重度要靠颜色、图标、文案三者中
// 至少两个来区分，不能只靠颜色」（WCAG 1.4.1 Use of Color）。这里的分配是：
//   · 图标：warning/error 用警告三角，success/info 用对勾 —— 有区分
//   · 文案：四种类型的文案本身不同 —— 有区分
//   · 底色：只有**需要用户注意**的 warning / error 上色 —— 这恰恰是最佳实践
//     里颜色的正确用途：把有限的色彩预算花在需要打断用户的地方。
// success 与 info 都是非可操作的确认，靠图标 + 文案足矣；给它们再上一次色
// 只会稀释 warning / error 的视觉优先级，并且会和作为强调色的深青绿打架。
const TONE_CLASSES = {
  success: 'border-line bg-surface text-ink-2',
  info: 'border-line bg-surface text-ink-2',
  warning: 'border-warn bg-warn-soft text-warn',
  error: 'border-danger bg-danger-soft text-danger',
}

const props = defineProps({
  show: Boolean,
  type: { type: String, default: 'info' },
  msg: { type: String, default: '' },
})

const isAlert = computed(() => props.type === 'error')
</script>

<style scoped>
/* Toast 进出 200ms（spec §11 的动效表）。 */
.toast-enter-active {
  transition: opacity 0.2s ease-out, transform 0.2s ease-out;
}
.toast-leave-active {
  transition: opacity 0.18s ease-in, transform 0.18s ease-in;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(12px);
}
</style>
