<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto flex max-w-[680px] flex-col gap-4 p-6">
      <AppPanel title="通用设置">
        <div class="flex flex-col gap-4">
          <AppSelect v-model="draft.defaultTemplateId" label="默认模板">
            <option value="">跟随系统</option>
            <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
          </AppSelect>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <AppInput
              v-model="draft.episodePadDigits"
              type="number"
              label="集数补零位数"
              :min="1"
              :max="6"
              :error="episodePadError"
              hint="1–6 位，即 {episode_padded} 的位数"
            />
            <AppInput
              v-model="draft.seasonPadDigits"
              type="number"
              label="季数补零位数"
              :min="1"
              :max="6"
              :error="seasonPadError"
              hint="1–6 位，即 {season_padded} 的位数"
            />
          </div>

          <AppSelect v-model="draft.conflictStrategy" label="冲突默认策略">
            <option label="跳过" value="skip" />
            <option label="中止" value="abort" />
            <option label="覆盖" value="overwrite" />
            <option label="自动编号" value="rename_dup" />
          </AppSelect>
        </div>
      </AppPanel>

      <AppPanel title="OpenList 设置">
        <div class="flex flex-col gap-4">
          <AppInput
            v-model="draft.openlist.serverUrl"
            label="默认服务器地址"
            placeholder="http://localhost:5244"
          />
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <AppInput
              v-model="draft.openlist.concurrency"
              type="number"
              label="最大并发请求"
              :min="1"
              :max="10"
            />
            <AppInput
              v-model="draft.openlist.requestInterval"
              type="number"
              label="请求间隔 (秒)"
              :min="0.1"
              :max="5"
              :step="0.1"
            />
          </div>

          <div
            class="flex items-start gap-2 rounded-[8px] bg-sunken px-3 py-2.5 text-[12px] text-ink-2"
          >
            <Info class="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <p>
              这两项当前由<strong class="text-ink">服务端</strong>的
              <code class="font-mono">openlist_max_concurrent</code> 与
              <code class="font-mono">openlist_request_interval</code> 决定。
              此处保存的值会被保留，但尚未下发到后端。
            </p>
          </div>
        </div>
      </AppPanel>

      <AppPanel title="说明">
        <div class="flex flex-col gap-2 text-[13px] leading-[1.8] text-ink-2">
          <p><strong class="text-ink">本地模式:</strong> 直接操作本机磁盘文件，支持撤销（通过 SQLite 日志）</p>
          <p><strong class="text-ink">OpenList 云盘模式:</strong> 通过 OpenList API 操作云盘文件，支持 115、阿里云盘、百度云盘等数十种云存储</p>
          <p>
            <strong class="text-ink">Emby/Jellyfin 规范:</strong> 建议使用 "Emby 标准" 预设模板，格式为
            <code class="rounded-[4px] bg-sunken px-1.5 py-0.5 font-mono text-[12px] text-ink">剧名 - SxxExx.mkv</code>
          </p>
          <p><strong class="text-ink">番剧注意:</strong> 番剧通常没有季数，会使用默认季数 1；支持父目录智能推断</p>
        </div>
      </AppPanel>

      <div v-if="!settingsStore.storageAvailable" class="text-[12px] text-warn">
        当前浏览器可能无法保存设置，改动可能只在本次会话内有效。
      </div>

      <div class="flex items-center justify-end gap-3">
        <span v-if="savedFlash" class="text-[12px] text-ink-2">{{ savedFlash }}</span>
        <AppButton variant="secondary" :disabled="!dirty" @click="reset">
          <RotateCcw class="h-4 w-4" aria-hidden="true" />
          重置
        </AppButton>
        <AppButton variant="primary" :disabled="!dirty" :loading="saving" @click="save">
          <Save class="h-4 w-4" aria-hidden="true" />
          {{ saving ? '保存中…' : '保存设置' }}
        </AppButton>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Info, RotateCcw, Save } from 'lucide-vue-next'

import { getPresets } from '../api/template'
import { useSettingsStore } from '../stores/settings'

import AppPanel from '../components/ui/AppPanel.vue'
import AppButton from '../components/ui/AppButton.vue'
import AppInput from '../components/ui/AppInput.vue'
import AppSelect from '../components/ui/AppSelect.vue'

const settingsStore = useSettingsStore()

const presets = ref([])
// 草稿语义：改动先落在 draft，点「保存设置」才写回 store 并落盘。
// 这样改坏了可以直接「重置」，也不会在没保存的情况下影响工作区（Review Focus 5）。
const draft = reactive(settingsStore.toObject())
const saving = ref(false)
const savedFlash = ref('')

const dirty = computed(() => JSON.stringify(draft) !== JSON.stringify(settingsStore.toObject()))

// 补零位数的越界提示（spec §10：表单错误内联于控件下方，不用 Toast）。
//
// 保存时 `settingsSchema.normalizeSettings` 会把越界值钳到 [1, 6]，与后端
// `PadConfig` 一致 —— 但**钳制是静默的**：用户输入 99、点保存、回来后看到 6，
// 中间没有任何解释。这个 error 就是把那次静默钳制说出来。
//
// 留空不算错误（视为「未设置」，回落默认值 2），所以空值返回空字符串。
function padRangeError(value) {
  if (value === null || value === undefined || value === '') return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return '请输入数字'
  if (n < 1 || n > 6) return '需在 1 到 6 之间，保存时会按就近边界处理'
  return ''
}

const episodePadError = computed(() => padRangeError(draft.episodePadDigits))
const seasonPadError = computed(() => padRangeError(draft.seasonPadDigits))

async function save() {
  if (!dirty.value) return
  saving.value = true
  try {
    // apply 是替换语义：必须传完整草稿，不能只传单个字段。
    settingsStore.apply(draft)
    settingsStore.save()
    Object.assign(draft, settingsStore.toObject())
    savedFlash.value = '设置已保存'
    setTimeout(() => { savedFlash.value = '' }, 1500)
  } finally {
    saving.value = false
  }
}

function reset() {
  Object.assign(draft, settingsStore.toObject())
}

onMounted(async () => {
  const res = await getPresets()
  if (res.data?.data) presets.value = res.data.data
})
</script>
