<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto flex max-w-[680px] flex-col gap-4 p-6">
      <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
        <div class="px-6 py-4 border-b border-border flex items-center gap-2 font-semibold text-[14px] text-text">
          <Settings class="w-4 h-4 text-primary" />
          通用设置
        </div>
        <div class="p-6">
          <div class="flex flex-col gap-5">
            <div class="flex items-center gap-4">
              <label class="w-[140px] text-[13px] text-text-secondary shrink-0">默认模板</label>
              <select
                v-model="settings.defaultTemplate"
                class="h-9 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 w-[320px]"
              >
                <option value="">跟随系统</option>
                <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>
            <div class="flex items-center gap-4">
              <label class="w-[140px] text-[13px] text-text-secondary shrink-0">集数补零位数</label>
              <input
                v-model.number="settings.episodePadDigits"
                type="number" min="1" max="4"
                class="w-[120px] h-9 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="w-[140px] text-[13px] text-text-secondary shrink-0">季数补零位数</label>
              <input
                v-model.number="settings.seasonPadDigits"
                type="number" min="1" max="4"
                class="w-[120px] h-9 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="w-[140px] text-[13px] text-text-secondary shrink-0">冲突默认策略</label>
              <select
                v-model="settings.conflictStrategy"
                class="h-9 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 w-[200px]"
              >
                <option label="跳过" value="skip" />
                <option label="中止" value="abort" />
                <option label="覆盖" value="overwrite" />
                <option label="自动编号" value="rename_dup" />
              </select>
            </div>
          </div>
        </div>
      </div>

      <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
        <div class="px-6 py-4 border-b border-border flex items-center gap-2 font-semibold text-[14px] text-text">
          <Cloud class="w-4 h-4 text-primary" />
          OpenList 设置
        </div>
        <div class="p-6">
          <div class="flex flex-col gap-5">
            <div class="flex items-center gap-4">
              <label class="w-[140px] text-[13px] text-text-secondary shrink-0">默认服务器地址</label>
              <input
                v-model="settings.openlist.serverUrl"
                placeholder="http://localhost:5244"
                class="w-[320px] h-9 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="w-[140px] text-[13px] text-text-secondary shrink-0">最大并发请求</label>
              <input
                v-model.number="settings.openlist.concurrency"
                type="number" min="1" max="10"
                class="w-[120px] h-9 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="w-[140px] text-[13px] text-text-secondary shrink-0">请求间隔 (秒)</label>
              <input
                v-model.number="settings.openlist.requestInterval"
                type="number" min="0.1" max="5" step="0.1"
                class="w-[120px] h-9 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
        <div class="px-6 py-4 border-b border-border flex items-center gap-2 font-semibold text-[14px] text-text">
          <Info class="w-4 h-4 text-primary" />
          说明
        </div>
        <div class="p-6 text-[13px] text-text-secondary leading-[1.8] space-y-2">
          <p><strong class="text-text">本地模式:</strong> 直接操作本机磁盘文件，支持撤销（通过 SQLite 日志）</p>
          <p><strong class="text-text">OpenList 云盘模式:</strong> 通过 OpenList API 操作云盘文件，支持 115、阿里云盘、百度云盘等数十种云存储</p>
          <p><strong class="text-text">Emby/Jellyfin 规范:</strong> 建议使用 "Emby 标准" 预设模板，格式为 <code class="px-1.5 py-0.5 rounded bg-surface-muted text-text font-mono text-[12px]">剧名 - SxxExx.mkv</code></p>
          <p><strong class="text-text">番剧注意:</strong> 番剧通常没有季数，会使用默认季数 1；支持父目录智能推断</p>
        </div>
      </div>

      <div class="flex items-center justify-end gap-3 pt-2">
        <div
          v-if="savedFlash"
          class="text-[12px] text-success flex items-center gap-1.5 animate-[fadeOut_1.5s_ease_forwards]"
        >
          <CheckCircle2 class="w-4 h-4" />
          {{ savedFlash }}
        </div>
        <button
          class="h-10 px-5 bg-surface hover:bg-surface-muted border border-border-strong text-text-secondary hover:text-primary rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!dirty"
          @click="reset"
        >
          <RotateCcw class="w-4 h-4" />
          重置
        </button>
        <button
          class="h-10 px-6 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!dirty || saving"
          @click="save"
        >
          <Save class="w-4 h-4" />
          {{ saving ? '保存中...' : '保存设置' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { Settings, Cloud, Info, Save, RotateCcw, CheckCircle2 } from 'lucide-vue-next'
import { getPresets } from '../api/template'

const SETTINGS_KEY = 'episode-renamer:settings'

const defaultSettings = () => ({
  defaultTemplate: 'emby_standard',
  episodePadDigits: 2,
  seasonPadDigits: 2,
  conflictStrategy: 'skip',
  openlist: {
    serverUrl: '',
    concurrency: 3,
    requestInterval: 0.5,
  },
})

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (!raw) return defaultSettings()
    const data = JSON.parse(raw)
    const def = defaultSettings()
    return {
      ...def,
      ...data,
      openlist: { ...def.openlist, ...(data.openlist || {}) },
    }
  } catch {
    return defaultSettings()
  }
}

function saveSettings(data) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(data))
  } catch {}
}

const presets = ref([])
const original = reactive(loadSettings())
const settings = reactive(loadSettings())
const saving = ref(false)
const savedFlash = ref('')

const dirty = computed(() => JSON.stringify(settings) !== JSON.stringify(original))

async function save() {
  if (!dirty.value) return
  saving.value = true
  try {
    const snapshot = JSON.parse(JSON.stringify(settings))
    saveSettings(snapshot)
    Object.assign(original, snapshot)
    savedFlash.value = '设置已保存'
    setTimeout(() => { savedFlash.value = '' }, 1500)
  } finally {
    saving.value = false
  }
}

function reset() {
  Object.assign(settings, JSON.parse(JSON.stringify(original)))
}

onMounted(async () => {
  const res = await getPresets()
  if (res.data?.data) presets.value = res.data.data
})
</script>

<style scoped>
@keyframes fadeOut {
  0%   { opacity: 1; transform: translateY(0); }
  70%  { opacity: 1; }
  100% { opacity: 0; transform: translateY(-6px); }
}
</style>
