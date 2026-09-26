<template>
  <AppModal
    :model-value="modelValue"
    title="选择目录"
    z-index="50"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="w-full max-w-[520px] overflow-hidden rounded-[12px] bg-surface shadow-overlay">
      <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 class="text-[14px] font-semibold text-ink">选择目录</h2>
        <button
          type="button"
          aria-label="关闭"
          class="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-2 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:outline-none"
          @click="$emit('update:modelValue', false)"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div class="p-5">
        <div class="mb-4 flex items-center gap-2 border-b border-line pb-3">
          <AppButton
            size="sm"
            variant="secondary"
            :disabled="!currentPath || currentPath === rootPath"
            @click="goParent"
          >
            上级
          </AppButton>
          <div class="flex min-w-0 flex-1 items-center gap-1 overflow-hidden text-[12px] text-ink-3">
            <template v-for="(seg, idx) in breadcrumbs" :key="idx">
              <button
                type="button"
                class="truncate rounded-[4px] transition-colors duration-150 hover:text-accent focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
                @click="navigate(seg.path)"
              >{{ seg.name }}</button>
              <ChevronRight v-if="idx < breadcrumbs.length - 1" class="h-3 w-3 shrink-0 text-ink-3" aria-hidden="true" />
            </template>
          </div>
        </div>

        <div class="mb-3 flex min-w-0 items-center gap-2 px-1 text-[12px]">
          <span class="shrink-0 text-ink-3">当前目录:</span>
          <span class="truncate text-ink">{{ currentPath }}</span>
          <AppBadge v-if="!selected" tone="accent">确定将选择此目录</AppBadge>
          <AppBadge v-else tone="neutral">已选中: {{ selected.name }}</AppBadge>
        </div>

        <div v-if="loading" class="py-12 text-center text-[13px] text-ink-3">加载中…</div>
        <div v-else-if="!dirs.length" class="py-12 text-center text-[13px] text-ink-3">此目录无子目录</div>
        <div
          v-else
          ref="listRef"
          class="max-h-[280px] overflow-auto"
          @keydown="onListKeydown"
        >
          <button
            v-for="d in dirs"
            :key="d.path"
            type="button"
            class="flex w-full items-center gap-2.5 rounded-[8px] px-3.5 py-2.5 text-left transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
            :class="selected?.path === d.path
              ? 'bg-accent-soft text-accent'
              : 'text-ink hover:bg-sunken'"
            :aria-pressed="selected?.path === d.path"
            @click="selected = d"
            @dblclick="navigate(d.path)"
          >
            <Folder
              class="h-[18px] w-[18px] shrink-0"
              :class="selected?.path === d.path ? 'text-accent' : 'text-ink-3'"
              aria-hidden="true"
            />
            <span class="truncate text-[14px] font-medium">{{ d.name }}</span>
          </button>
        </div>
      </div>

      <div class="flex justify-end gap-2 border-t border-line px-5 py-3">
        <AppButton variant="secondary" @click="$emit('update:modelValue', false)">取消</AppButton>
        <AppButton variant="primary" :disabled="confirmDisabled" @click="confirm">确定选择</AppButton>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ChevronRight, Folder, X } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'
import AppBadge from './ui/AppBadge.vue'
import { browseLocalDirectory } from '../api/scanner'
import { openlistBrowse } from '../api/openlist'

const props = defineProps({
  modelValue: Boolean,
  source: { type: String, default: 'local' },
  initialPath: String,
  rootPath: String,
  disallowRoot: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'confirm', 'error'])

const loading = ref(false)
const dirs = ref([])
const currentPath = ref('')
const parentPath = ref('')
const selected = ref(null)

const listRef = ref(null)

const rootPath = computed(() => props.rootPath || '')

const confirmDisabled = computed(() => {
  if (!currentPath.value) return true
  if (props.disallowRoot && currentPath.value === rootPath.value) return true
  return false
})

function currentPathBasename() {
  const p = currentPath.value
  if (!p) return ''
  const sep = p.includes('\\') && !p.includes('/') ? '\\' : '/'
  if (p === sep) return sep
  return p.replace(/[\\/]+$/, '').split(sep).pop() || p
}

const breadcrumbs = computed(() => {
  const root = rootPath.value
  const cur = currentPath.value
  if (!cur) return []
  const sep = cur.includes('\\') && !cur.includes('/') ? '\\' : '/'
  const parts = cur.split(sep).filter(Boolean)
  const segs = []
  let acc = sep === '/' ? '/' : ''
  for (const p of parts) {
    acc = acc ? acc + sep + p : (sep === '/' ? '/' + p : p)
    segs.push({ name: p, path: acc })
  }
  if (sep === '/' && cur.startsWith('/')) {
    segs.unshift({ name: '/', path: '/' })
  }
  let rootIdx = -1
  if (root) {
    rootIdx = segs.findIndex(s => s.path === root)
  }
  return rootIdx >= 0 ? segs.slice(rootIdx) : segs
})

// 目录项是 <button>，天然可 Tab 聚焦并可用 Enter / Space 激活 ——
// 激活即「选中」（click），这是这一列的主用法。
// 这里再补上方向键与 Home / End，让长目录不必按很多次 Tab
// （spec §8.3：BrowseDialog「补 aria 与键盘导航」）。
// ArrowRight 是「下钻」，对应鼠标的双击。双击（@dblclick）只有鼠标能触发，
// 少了这个键，键盘用户能选中目录却进不去子目录，而面包屑只能往上。
function onListKeydown(event) {
  const KEYS = ['ArrowDown', 'ArrowUp', 'Home', 'End', 'ArrowRight']
  if (!KEYS.includes(event.key)) return
  const items = Array.from(listRef.value?.querySelectorAll('button') || [])
  if (!items.length) return
  event.preventDefault()
  const current = items.indexOf(document.activeElement)
  if (event.key === 'ArrowRight') {
    // items 由 v-for="d in dirs" 渲染，与 dirs 同序，可以按下标取路径
    if (current < 0) return
    const target = dirs.value[current]
    if (!target) return
    // 下钻会把整列换掉（loading 期间列表卸载），所以焦点不能停在原地 ——
    // 让 load() 在新目录渲染好后把焦点交给它的第一项。
    navigate(target.path, { focusFirst: true })
    return
  }
  let next
  if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = items.length - 1
  else if (current === -1) next = 0
  else next = event.key === 'ArrowDown'
    ? Math.min(items.length - 1, current + 1)
    : Math.max(0, current - 1)
  items[next].focus()
}

async function load(path, { focusFirst = false } = {}) {
  loading.value = true
  try {
    let res
    if (props.source === 'openlist') {
      res = await openlistBrowse(path)
    } else {
      res = await browseLocalDirectory(path)
    }
    const data = res.data
    dirs.value = data.dirs || []
    parentPath.value = data.parent
    currentPath.value = data.path
  } catch (e) {
    emit('error', '加载目录失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
  // 键盘下钻后把焦点交还给新列表的第一项（见 onListKeydown）。
  // 必须等 nextTick —— loading 翻回 false 的同一拍列表才重新挂载。
  // 新目录没有子项时 listRef 为 null（模板走「此目录无子目录」那一支），
  // 此时不夺焦：模态陷阱会把下一次 Tab 收回对话框内。
  if (focusFirst) {
    await nextTick()
    listRef.value?.querySelector('button')?.focus()
  }
}

function navigate(path, opts) {
  if (!path || path === currentPath.value) return
  selected.value = null
  load(path, opts)
}

function goParent() {
  if (!parentPath.value || parentPath.value === currentPath.value) return
  navigate(parentPath.value)
}

function confirm() {
  const pick = selected.value || { path: currentPath.value, name: currentPathBasename() }
  if (props.disallowRoot && pick.path === rootPath.value) {
    emit('error', '不能选择根目录，请进入子文件夹后再选择')
    return
  }
  emit('confirm', pick)
}

watch(() => props.modelValue, (v) => {
  if (v) {
    const init = props.initialPath || props.rootPath || (props.source === 'local' ? '' : '/')
    selected.value = null
    load(init)
  }
})
</script>
