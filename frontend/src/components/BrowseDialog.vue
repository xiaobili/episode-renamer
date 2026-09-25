<template>
  <AppModal :model-value="modelValue" @update:model-value="$emit('update:modelValue')" z-index="50">
    <div class="bg-surface rounded-xl shadow-2xl w-full max-w-[520px] overflow-hidden">
      <div class="px-6 py-4 border-b border-border flex items-center justify-between">
        <div class="font-semibold text-[15px] text-text">选择目录</div>
        <button class="text-text-faint hover:text-text transition" @click="$emit('update:modelValue', false)">
          <X class="w-5 h-5" />
        </button>
      </div>
      <div class="p-6">
        <div class="flex items-center gap-2 mb-4 pb-3 border-b border-border">
          <button
            class="h-8 px-3 rounded-md bg-surface-muted hover:bg-border text-[12px] text-text-secondary hover:text-text transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
            :disabled="!currentPath || currentPath === rootPath"
            @click="goParent"
          >
            <ChevronLeft class="w-4 h-4" />上级
          </button>
          <div class="flex-1 flex items-center gap-1 text-[12px] text-text-muted overflow-hidden">
            <template v-for="(seg, idx) in breadcrumbs" :key="idx">
              <span
                class="cursor-pointer hover:text-primary transition truncate"
                @click="navigate(seg.path)"
              >{{ seg.name }}</span>
              <ChevronRight v-if="idx < breadcrumbs.length - 1" class="w-3 h-3 shrink-0 text-text-faint" />
            </template>
          </div>
        </div>

        <div class="flex items-center gap-2 mb-3 px-1 text-[12px]">
          <span class="text-text-muted">当前目录:</span>
          <span class="font-mono text-text truncate">{{ currentPath }}</span>
          <span
            v-if="!selected"
            class="px-1.5 py-0.5 rounded bg-primary-light text-primary text-[10px] font-medium"
          >点击确定将选择此目录</span>
          <span
            v-else
            class="px-1.5 py-0.5 rounded bg-primary text-white text-[10px] font-medium"
          >已选中子目录: {{ selected.name }}</span>
        </div>

        <div v-if="loading" class="py-12 text-center text-text-muted text-[13px]">加载中...</div>
        <div v-else-if="!dirs.length" class="py-12 text-center text-text-muted text-[13px]">此目录无子目录</div>
        <div v-else class="max-h-[280px] overflow-auto">
          <div
            v-for="d in dirs"
            :key="d.path"
            class="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg cursor-pointer transition-all"
            :class="selected?.path === d.path
              ? 'bg-primary-light text-primary'
              : 'hover:bg-surface-muted text-text'"
            @click="selected = d"
            @dblclick="navigate(d.path)"
          >
            <Folder class="w-[18px] h-[18px] shrink-0" :class="selected?.path === d.path ? 'text-primary' : 'text-text-faint'" />
            <span class="text-[14px] font-medium truncate">{{ d.name }}</span>
          </div>
        </div>
      </div>
      <div class="px-6 py-3 border-t border-border flex justify-end gap-2">
        <button
          class="h-9 px-4 bg-surface-muted hover:bg-border rounded-lg text-[13px] font-medium transition"
          @click="$emit('update:modelValue', false)"
        >取消</button>
        <button
          class="h-9 px-4 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="confirmDisabled"
          @click="confirm"
        >确定选择</button>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { X, ChevronLeft, ChevronRight, Folder } from 'lucide-vue-next'
import AppModal from './ui/AppModal.vue'
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

async function load(path) {
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
}

function navigate(path) {
  if (!path || path === currentPath.value) return
  selected.value = null
  load(path)
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
