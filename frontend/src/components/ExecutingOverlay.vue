<template>
  <Transition name="modal">
    <div
      v-if="modelValue"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm"
    >
      <div class="bg-surface rounded-2xl shadow-2xl w-[340px] p-7 flex flex-col items-center gap-4">
        <div class="relative w-14 h-14">
          <div class="absolute inset-0 rounded-full border-4 border-primary/20" />
          <div class="absolute inset-0 rounded-full border-4 border-transparent border-t-primary animate-[spin_0.9s_linear_infinite]" />
          <Rocket class="absolute inset-0 m-auto w-6 h-6 text-primary animate-[bounce_1.4s_ease-in-out_infinite]" />
        </div>
        <div class="text-center">
          <div class="text-[15px] font-semibold text-text mb-1">{{ dryRun ? '试运行中...' : '正在执行重命名...' }}</div>
          <div class="text-[12px] text-text-muted">请稍候，操作进行中请勿关闭</div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { Rocket } from 'lucide-vue-next'

defineProps({
  modelValue: Boolean,
  dryRun: Boolean,
})
</script>

<style scoped>
.modal-enter-active {
  transition: opacity 0.2s ease-out;
}
.modal-enter-active > * {
  transition: opacity 0.2s ease-out, transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}
.modal-leave-active {
  transition: opacity 0.15s ease-in;
}
.modal-leave-active > * {
  transition: opacity 0.13s ease-in, transform 0.13s ease-in;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from > * {
  opacity: 0;
  transform: scale(0.94) translateY(8px);
}
.modal-leave-to > * {
  opacity: 0;
  transform: scale(0.96) translateY(-4px);
}
</style>
