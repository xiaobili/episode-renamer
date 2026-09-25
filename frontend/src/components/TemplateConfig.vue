<template>
  <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
    <div class="px-6 py-4 border-b border-border flex items-center justify-between">
      <div class="flex items-center gap-2 font-semibold text-[14px] text-text">
        <FileText class="w-4 h-4 text-primary" />
        重命名模板
      </div>
    </div>
    <div class="p-6">
      <div class="flex items-center gap-3 flex-wrap">
        <select
          :value="tplStore.currentPresetId"
          @change="$emit('preset-change', $event.target.value)"
          class="h-10 px-3 rounded-lg border border-border bg-surface text-[13px] text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 w-[220px]"
        >
          <option value="">选择预设模板</option>
          <option v-for="p in tplStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>

      <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-[12px] text-text-muted">文件模板</label>
          <input
            ref="tplInputRef"
            :value="tplStore.currentTemplate"
            @input="$emit('template-edit', $event.target.value)"
            placeholder="如 {show} - S{season_padded}E{episode_padded}{extension}"
            class="h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 font-mono"
          />
        </div>
        <div class="flex flex-col gap-1.5">
          <div class="flex items-center gap-2">
            <label
              class="flex items-center gap-1.5 text-[12px] select-none transition"
              :class="source === 'openlist'
                ? 'text-text-faint cursor-not-allowed'
                : 'text-text-secondary cursor-pointer'"
              :title="source === 'openlist' ? 'OpenList 暂不支持自动创建季文件夹' : ''"
            >
              <input
                type="checkbox"
                :checked="tplStore.createSeasonFolder"
                :disabled="source === 'openlist'"
                @change="$emit('update:createSeasonFolder', $event.target.checked)"
                class="w-3.5 h-3.5 accent-primary rounded disabled:opacity-40 disabled:cursor-not-allowed"
              />
              创建季文件夹
            </label>
          </div>
          <input
            :disabled="!tplStore.createSeasonFolder || source === 'openlist'"
            :value="tplStore.folderTemplate"
            @input="$emit('update:folderTemplate', $event.target.value)"
            placeholder="季文件夹模板，如 Season {season_padded}"
            class="h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 font-mono disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>
      </div>

      <div class="mt-5">
        <div class="flex items-center gap-1.5 text-[12px] text-text-muted mb-2">
          <Info class="w-3.5 h-3.5" />
          可用变量（点击可插入到模板中）
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          <button
            v-for="v in VARIABLE_DEFS"
            :key="v.tag"
            type="button"
            @click="insertVariable(v.tag)"
            class="group flex flex-col items-start gap-0.5 px-3 py-2 rounded-lg border border-border bg-surface-muted hover:bg-primary-light hover:border-primary transition-all text-left"
          >
            <span class="font-mono text-[12px] font-semibold text-primary">{{ v.tag }}</span>
            <span class="text-[11px] text-text-muted group-hover:text-text-secondary leading-tight">{{ v.desc }}</span>
            <span class="text-[10px] text-text-faint font-mono truncate max-w-full">例: {{ v.example }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { FileText, Info } from 'lucide-vue-next'

const VARIABLE_DEFS = [
  { tag: '{show}', desc: '剧名（自动从路径/文件名解析）', example: '绝命毒师' },
  { tag: '{show_clean}', desc: '剧名（已清洗，去除特殊字符）', example: '绝命毒师' },
  { tag: '{season}', desc: '季数（阿拉伯数字）', example: '1' },
  { tag: '{season_padded}', desc: '季数（补零，默认2位）', example: '01' },
  { tag: '{episode}', desc: '集数（阿拉伯数字）', example: '5' },
  { tag: '{episode_padded}', desc: '集数（补零，默认2位）', example: '05' },
  { tag: '{title}', desc: '集标题（部分资源可解析）', example: 'PILOT' },
  { tag: '{quality}', desc: '画质标记', example: '1080p WEB-DL' },
  { tag: '{source}', desc: '来源标记', example: 'WEB-DL AMZN' },
  { tag: '{extension}', desc: '文件扩展名', example: '.mkv' },
  { tag: '{sub_lang}', desc: '字幕语言标记', example: 'CHS' },
]

const props = defineProps({
  tplStore: { type: Object, required: true },
  source: { type: String, required: true },
})
defineEmits([
  'preset-change', 'template-edit',
  'update:createSeasonFolder', 'update:folderTemplate',
])

const tplInputRef = ref(null)

function insertVariable(tag) {
  const input = tplInputRef.value
  if (!input) return
  const current = props.tplStore.currentTemplate || ''
  const start = input.selectionStart ?? current.length
  const end = input.selectionEnd ?? current.length
  const next = current.slice(0, start) + tag + current.slice(end)
  props.tplStore.currentTemplate = next
  input.focus()
  const pos = start + tag.length
  requestAnimationFrame(() => {
    input.setSelectionRange(pos, pos)
  })
}
</script>
