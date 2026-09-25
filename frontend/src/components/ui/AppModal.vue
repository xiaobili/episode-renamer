<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="modelValue"
        class="fixed inset-0 flex items-center justify-center bg-ink/40 p-4"
        :style="{ zIndex }"
        @click="onOverlayClick"
      >
        <div
          ref="panelRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="title ? titleId : undefined"
          tabindex="-1"
          class="flex w-full justify-center outline-none"
        >
          <h2 v-if="title" :id="titleId" class="sr-only">{{ title }}</h2>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  zIndex: { type: [Number, String], default: 50 },
  closeOnOverlay: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const panelRef = ref(null)
const titleId = `modal-title-${useId()}`

let triggerEl = null
let prevOverflow = ''
let prevPaddingRight = ''

function focusableNodes() {
  if (!panelRef.value) return []
  // getClientRects().length === 0 的元素（display:none / 未布局）不可聚焦，
  // 必须排除，否则陷阱会把焦点扔到一个收不到的节点上，Tab 看起来「卡死」。
  return Array.from(panelRef.value.querySelectorAll(FOCUSABLE)).filter(
    (el) => el.getClientRects().length > 0,
  )
}

function lockScroll() {
  const gap = window.innerWidth - document.documentElement.clientWidth
  prevOverflow = document.body.style.overflow
  prevPaddingRight = document.body.style.paddingRight
  document.body.style.overflow = 'hidden'
  // 补上滚动条宽度，否则锁定瞬间整页会横向跳一下
  if (gap > 0) document.body.style.paddingRight = `${gap}px`
}

function unlockScroll() {
  document.body.style.overflow = prevOverflow
  document.body.style.paddingRight = prevPaddingRight
}

function close() {
  emit('update:modelValue', false)
}

function onOverlayClick(event) {
  if (!props.closeOnOverlay) return
  // 面板外层是 w-full 的居中容器，点卡片左右两侧的空白命中的是「面板本身」
  // 而不是遮罩。这两种位置都应当视为「点了外部」，所以不能简单用 @click.self。
  if (panelRef.value && event.target !== panelRef.value && panelRef.value.contains(event.target)) {
    return
  }
  close()
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab' || !panelRef.value) return

  const nodes = focusableNodes()
  if (nodes.length === 0) {
    // 模态内一个可聚焦元素都没有（例如纯提示框）时，把焦点钉在面板上，
    // 不让它漏到背后的页面。
    event.preventDefault()
    panelRef.value.focus()
    return
  }

  const first = nodes[0]
  const last = nodes[nodes.length - 1]
  const active = document.activeElement
  const inside = panelRef.value.contains(active)

  if (event.shiftKey && (active === first || !inside)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !inside)) {
    event.preventDefault()
    first.focus()
  }
}

function onOpen() {
  triggerEl = document.activeElement instanceof HTMLElement ? document.activeElement : null
  lockScroll()
  document.addEventListener('keydown', onKeydown, true)
  nextTick(() => {
    const nodes = focusableNodes()
    if (nodes.length) nodes[0].focus()
    else panelRef.value?.focus()
  })
}

function onClose() {
  document.removeEventListener('keydown', onKeydown, true)
  unlockScroll()
  // 触发元素可能在模态打开期间被 v-if 卸载（FileTable 的「清空」就是这种情况），
  // 所以必须先确认它还在文档里。
  if (triggerEl && document.contains(triggerEl)) triggerEl.focus()
  triggerEl = null
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) onOpen()
    else onClose()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown, true)
  if (props.modelValue) unlockScroll()
})
</script>

<style>
/* 模态进出 200ms —— spec §11 的动效表。进出**都用 200ms**：旧文件里离场是
   150/130ms、进场是 200ms，既是本文件内部的不一致，也不符合 §11 的「模态进出
   200ms」。不要因为「收起可以更快」而改回去 —— 那属于该表未列出的动效。
   只做透明度与极小的位移，
   意图是「让用户看清层级来自哪里」，不做弹跳。 */
.modal-enter-active {
  transition: opacity 0.2s ease-out;
}
.modal-enter-active > * {
  transition: opacity 0.2s ease-out, transform 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.modal-leave-active {
  transition: opacity 0.2s ease-in;
}
.modal-leave-active > * {
  transition: opacity 0.2s ease-in, transform 0.2s ease-in;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from > * {
  opacity: 0;
  transform: scale(0.96) translateY(6px);
}
.modal-leave-to > * {
  opacity: 0;
  transform: scale(0.98) translateY(-3px);
}
</style>
