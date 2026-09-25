<template>
  <Transition name="modal">
    <div
      v-if="modelValue"
      class="fixed inset-0 flex items-center justify-center p-4"
      :class="[backdrop ? 'bg-black/40' : '', backdropBlur ? 'backdrop-blur-sm' : '']"
      :style="{ zIndex: zIndex }"
      @click.self="onOverlayClick"
    >
      <slot />
    </div>
  </Transition>
</template>

<script setup>
const props = defineProps({
  modelValue: Boolean,
  backdrop: { type: Boolean, default: true },
  backdropBlur: { type: Boolean, default: false },
  zIndex: { type: [Number, String], default: 50 },
  closeOnOverlay: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue', 'close'])

function onOverlayClick() {
  if (props.closeOnOverlay) {
    emit('update:modelValue', false)
    emit('close')
  }
}
</script>

<style>
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
