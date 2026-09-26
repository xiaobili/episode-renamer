<template>
  <Transition name="overlay">
    <div
      v-if="modelValue"
      ref="overlayRef"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-ink/50"
      tabindex="-1"
      @keydown.tab.prevent
    >
      <div
        role="status"
        aria-live="polite"
        class="flex w-[320px] flex-col items-center gap-3 rounded-[12px] bg-surface p-6 shadow-overlay"
      >
        <Loader2 class="h-6 w-6 animate-spin text-accent" aria-hidden="true" />
        <div class="text-center">
          <div class="text-[14px] font-semibold text-ink">
            {{ dryRun ? '试运行中…' : '正在执行重命名…' }}
          </div>
          <div class="mt-1 text-[12px] text-ink-2">请稍候，操作进行中请勿关闭</div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { Loader2 } from 'lucide-vue-next'

const props = defineProps({
  modelValue: Boolean,
  dryRun: Boolean,
})

// 唯一的进度指示：一个旋转的 Loader2。删掉了原来的三层动画堆叠
// （静态圆环 + 旋转圆环 + 弹跳火箭）—— 三者不传达任何额外信息
// （spec §11）。animate-spin 与 AppButton 的 loading 态用的是同一个图标，
// 全站「正在处理」只有一个视觉语汇。
const overlayRef = ref(null)

// 遮罩打开时把焦点收进来，配合 @keydown.tab.prevent 让键盘也无法
// 操作背后的界面 —— 破坏性操作需要明确阻断（spec §10）。
// 没有用 AppModal：AppModal 支持 Esc 关闭，而这里**不能**被关闭。
//
// 两条路径分开处理，各自都落在「元素确定已在 DOM 里」的时刻：
//  · 组件在遮罩已打开的状态下挂载 —— HomeView 的 v-if 会在试运行期间卸载它，
//    执行时再挂载，那一刻 modelValue 已经是 true；onMounted 在元素插入之后跑
//  · 组件已挂载、modelValue 随后翻成 true —— flush: 'post' 让回调等到 DOM 更新之后
// 注意 watch 不能只靠 immediate 覆盖第一种情形：Vue 对带回调的 watch 会
// 同步直调 job、绕过 scheduler，flush: 'post' 对那一次不生效。
watch(
  () => props.modelValue,
  (v) => {
    if (v) overlayRef.value?.focus()
  },
  { flush: 'post' },
)

onMounted(() => {
  if (props.modelValue) overlayRef.value?.focus()
})
</script>

<style scoped>
/* 遮罩进出 200ms（spec §11 的动效表；modal 与阻断式遮罩同一行）。 */
.overlay-enter-active {
  transition: opacity 0.2s ease-out;
}
.overlay-leave-active {
  transition: opacity 0.2s ease-in;
}
.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}
</style>
