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
// 同一个 onKeydown 被注册两次（capture / 冒泡），靠这个开关分辨当前是哪一拍。
// 用「标志位 + try/finally」而不是两个函数：两拍的 Escape 分支必须引用**同一段**
// 代码，拆成两份迟早会改漏一处。顺便也不依赖事件对象（原生事件不允许挂自定义字段）。
let capturePass = false

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
    // Escape 分两拍：先让模态**内部**的控件有机会消费它（例如 BrowseDialog 的
    // 搜索框「有搜索词时先清空」），再决定关窗。
    //
    // 不能靠内部控件 stopPropagation 来解决：本监听器挂在 document 的 **capture**
    // 阶段，它比目标元素上的任何冒泡监听器都先跑，阻止已经来不及（实测：监听
    // 顺序恒为 doc-capture → target → 冒泡）。所以捕获阶段这一拍主动让开，
    // 只要焦点在面板内就交给下面那个**冒泡**监听器。
    //
    // 判断「焦点在面板内」是必须的：焦点不在面板里时（例如刚打开、或焦点掉到
    // body）若也让开，就没人再处理 Escape，对话框会关不掉。
    if (capturePass && panelRef.value && panelRef.value.contains(document.activeElement)) return

    // 冒泡拍发现控件已经 preventDefault（它消费了这次 Escape），本层不再关窗。
    if (event.defaultPrevented) return
    event.preventDefault()
    close()
    return
  }

  // Tab 之外的键不管。下面这段（焦点陷阱）只走捕获阶段，与 Escape 无关。
  if (!capturePass || event.key !== 'Tab' || !panelRef.value) return

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

function onCaptureKeydown(event) {
  capturePass = true
  try {
    onKeydown(event)
  } finally {
    capturePass = false
  }
}

function onBubbleKeydown(event) {
  capturePass = false
  onKeydown(event)
}

function onOpen() {
  triggerEl = document.activeElement instanceof HTMLElement ? document.activeElement : null
  lockScroll()
  // capture 一拍管焦点陷阱 + 让位；冒泡一拍只负责 Escape 关窗。
  document.addEventListener('keydown', onCaptureKeydown, true)
  document.addEventListener('keydown', onBubbleKeydown)
  nextTick(() => {
    const nodes = focusableNodes()
    if (nodes.length) nodes[0].focus()
    else panelRef.value?.focus()
  })
}

function onClose() {
  document.removeEventListener('keydown', onCaptureKeydown, true)
  document.removeEventListener('keydown', onBubbleKeydown)
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
  document.removeEventListener('keydown', onCaptureKeydown, true)
  document.removeEventListener('keydown', onBubbleKeydown)
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
