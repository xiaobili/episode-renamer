<template>
  <Transition name="toast">
    <div
      v-if="show"
      class="fixed top-6 right-6 z-[100] flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg text-[13px] font-medium"
      :class="{
        'bg-success-light text-success': type === 'success',
        'bg-error-light text-error': type === 'error',
        'bg-warning-light text-warning': type === 'warning',
        'bg-primary-light text-primary': type === 'info',
      }"
    >
      <CheckCircle2 v-if="type === 'success'" class="w-4 h-4" />
      <XCircle v-else-if="type === 'error'" class="w-4 h-4" />
      <AlertTriangle v-else-if="type === 'warning'" class="w-4 h-4" />
      <Info v-else class="w-4 h-4" />
      {{ msg }}
    </div>
  </Transition>
</template>

<script setup>
import { CheckCircle2, XCircle, AlertTriangle, Info } from 'lucide-vue-next'

defineProps({
  show: Boolean,
  type: { type: String, default: 'info' },
  msg: { type: String, default: '' },
})
</script>

<style scoped>
.toast-enter-active {
  animation: toastIn 0.25s ease-out;
}
.toast-leave-active {
  animation: toastOut 0.18s ease-in forwards;
}
@keyframes toastIn {
  from { transform: translateX(120%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
@keyframes toastOut {
  from { transform: translateX(0); opacity: 1; }
  to { transform: translateX(120%); opacity: 0; }
}
</style>
