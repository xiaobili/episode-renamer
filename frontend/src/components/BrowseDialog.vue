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
            ref="parentButtonRef"
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
        <!-- 无匹配与「此目录无子目录」必须分开说：前者是搜索词的问题（还留在
             当前目录），后者是目录真的空。合成一句会让用户以为目录没内容。 -->
        <div v-else-if="!filteredDirs.length" class="py-12 text-center text-[13px] text-ink-3">
          没有匹配「{{ query.trim() }}」的子目录
        </div>
        <div
          v-else
          id="browse-dir-list"
          ref="listRef"
          role="listbox"
          aria-label="子目录"
          class="max-h-[280px] overflow-auto"
          @keydown="onListKeydown"
        >
          <button
            v-for="d in filteredDirs"
            :key="d.path"
            type="button"
            role="option"
            :aria-selected="selected?.path === d.path"
            class="flex w-full items-center gap-2.5 rounded-[8px] px-3.5 py-2.5 text-left transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
            :class="selected?.path === d.path
              ? 'bg-accent-soft text-accent'
              : 'text-ink hover:bg-sunken'"
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

        <!-- 搜索框放在列表与按钮栏之间的留白里：贴在列表下沿（手指/视线不离开
             列表），又不会被列表的 280px 滚动区吃进去 —— 目录再多，搜索框也永远
             在同一个位置。目录少时它会留在原位（不浮动到底部），避免位置随内容跳。 -->
        <div class="mt-3 flex items-center gap-2">
          <div class="relative min-w-0 flex-1">
            <Search
              class="pointer-events-none absolute left-2.5 top-1/2 h-[15px] w-[15px] -translate-y-1/2 text-ink-3"
              aria-hidden="true"
            />
            <input
              ref="searchInputRef"
              v-model="query"
              type="text"
              role="searchbox"
              aria-label="搜索当前目录"
              aria-controls="browse-dir-list"
              :aria-describedby="searchStatus ? 'browse-search-status' : undefined"
              placeholder="搜索当前目录…"
              class="h-8 w-full rounded-[8px] border border-border-control bg-surface pl-8 pr-8 text-[13px] text-ink transition-colors duration-150 outline-none placeholder:text-ink-3 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/35"
              @input="onQueryInput"
              @keydown="onSearchKeydown"
            />
            <button
              v-if="query"
              type="button"
              aria-label="清空搜索"
              class="absolute right-1 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-[6px] text-ink-3 transition-colors duration-150 hover:bg-sunken hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
              @click="clearQuery"
            >
              <X class="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
          <span
            v-if="query.trim() && !loading && dirs.length"
            class="shrink-0 text-[12px] tabular-nums text-ink-3"
          >
            {{ filteredDirs.length }} / {{ dirs.length }}
          </span>
        </div>
        <!-- 结果数播报给读屏：列表是靠 v-for 静默换的，没有 live region 的话
             读屏用户完全不知道过滤后还剩几条。sr-only 不影响视觉。 -->
        <p id="browse-search-status" class="sr-only" aria-live="polite">{{ searchStatus }}</p>
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
import { ChevronRight, Folder, Search, X } from 'lucide-vue-next'

import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'
import AppBadge from './ui/AppBadge.vue'
import { browseLocalDirectory } from '../api/scanner'
import { openlistBrowse } from '../api/openlist'
import { filterDirs } from './browseFilter'

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
// 搜索词只过滤**已列出的**当前目录内容，不发任何请求 —— 目录动辄几十上百个，
// 本地过滤是即时的；一次网络往返既慢又会在输入过程中闪「加载中」。
const query = ref('')

const listRef = ref(null)
const searchInputRef = ref(null)
// 焦点交接的兜底目标（见 focusListIndex）：走进没有子目录的目录之后，
// 往上走是自然的下一步。
const parentButtonRef = ref(null)

const rootPath = computed(() => props.rootPath || '')

// 列表渲染、键盘下标、下钻取路径**全部**走这一个数组（见 onListKeydown）。
// 任何一处退回 dirs.value，都会让列表与下标错位。
const filteredDirs = computed(() => filterDirs(dirs.value, query.value))

const searchStatus = computed(() => {
  if (!query.value.trim() || loading.value || !dirs.value.length) return ''
  return filteredDirs.value.length
    ? `找到 ${filteredDirs.value.length} 个子目录`
    : '没有匹配的子目录'
})

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
    // items 由 v-for="d in filteredDirs" 渲染，与 filteredDirs 同序，可以按下标取路径
    if (current < 0) return
    const target = filteredDirs.value[current]
    if (!target) return
    // 下钻会把整列换掉（loading 期间列表卸载），所以焦点不能停在原地 ——
    // 由 load() 在新目录渲染好后做交接：成功给新列表第一项，
    // 失败还给这一项（restoreIndex），别把用户从他按下的目录挪开。
    navigate(target.path, { focusFirst: true, restoreIndex: current })
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

// 搜索框里的键盘：
//   ↓        —— 把焦点交给列表第一项（否则用户敲完搜索词还得按一堆 Tab）
//   ↑        —— 交给列表最后一项（从底部往上看，是往回翻的手感）
//   Enter    —— 恰好只剩一条匹配时直接选中它；否则把焦点交给列表，
//               由列表里的 Enter 走 confirm。不做「Enter 直接进目录」：
//               进目录会把用户打进搜索框的词连同整个列表一起换掉，
//               一次误按就丢了上下文。
//   Esc      —— 非空时先清空搜索词，而不是关掉对话框：蒙对的清空是
//               可撤销的，蒙错的关窗不可撤销（对话框是唯一入口）。
//               清空后再次 Esc 交给 AppModal 的全局处理器关窗。
function onSearchKeydown(event) {
  if (event.key === 'Escape') {
    if (!query.value) return
    event.preventDefault()
    event.stopPropagation()
    clearQuery()
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    if (filteredDirs.value.length === 1) {
      selected.value = filteredDirs.value[0]
      return
    }
    if (filteredDirs.value.length) focusListIndex(0)
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    if (!filteredDirs.value.length) return
    event.preventDefault()
    focusListIndex(event.key === 'ArrowDown' ? 0 : filteredDirs.value.length - 1)
  }
}

// 搜索框自己吃掉这次输入时不希望发生的事：v-model 已经更新，这里只需要把
// 「过滤后选中项被藏起来」处理掉 —— 选中别的目录后再输入搜索词，
// 底部徽章会说「已选中: X」，而 X 已经不在列表里了，用户看不到自己选了什么。
function onQueryInput() {
  if (selected.value && !filteredDirs.value.some((d) => d.path === selected.value.path)) {
    selected.value = null
  }
}

function clearQuery() {
  query.value = ''
  searchInputRef.value?.focus()
}

async function load(path, { focusFirst = false, restoreIndex = 0 } = {}) {
  loading.value = true
  let loaded = false
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
    // 进了另一个目录就丢掉搜索词：上一步是为「上一个目录」打的字，
    // 留在框里会让新目录一进来就是空的（或只剩一条），用户会以为目录没内容。
    // 放在 load 里而不是 navigate 里，键盘下钻、双击、面包屑、上级四条路径全覆盖。
    query.value = ''
    loaded = true
  } catch (e) {
    emit('error', '加载目录失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
  // 键盘下钻后的焦点交接（见 onListKeydown）。必须等 nextTick ——
  // loading 翻回 false 的同一拍列表才重新挂载。
  if (focusFirst) {
    await nextTick()
    focusListIndex(loaded ? 0 : restoreIndex)
  }
}

// 把焦点交给列表里的第 idx 项。拿不到列表或该项时退回「上级」按钮 ——
// 下钻进一个空目录会走模板里「此目录无子目录」那一支，listRef 是 null；
// 旧实现此时什么都不做，焦点便落到 body 上，而 aria-modal 的对话框还开着，
// 读屏的虚拟光标于是停在背景页。最低要求是焦点留在对话框内，
// 「上级」既是已有的控件、也是走进死路后的自然下一步。
function focusListIndex(idx) {
  const items = listRef.value ? Array.from(listRef.value.querySelectorAll('button')) : []
  ;(items[idx] || items[0] || parentButtonRef.value?.$el)?.focus()
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
    // 打开时清空上一次的搜索词。放在这里而不是 load 里，是因为重新打开同一个
    // 目录时 path 没变、加载分支照跑，但语义上「这是一次新的选择」。
    query.value = ''
    load(init)
  }
})
</script>
