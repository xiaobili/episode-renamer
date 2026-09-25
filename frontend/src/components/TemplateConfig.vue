<template>
  <div class="flex flex-col gap-3">
    <AppSelect
      :model-value="tplStore.currentPresetId"
      label="预设模板"
      @update:model-value="$emit('preset-change', $event)"
    >
      <option value="">选择预设模板</option>
      <option v-for="p in tplStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
    </AppSelect>

    <AppInput
      ref="tplInputRef"
      :model-value="tplStore.currentTemplate"
      label="文件模板"
      mono
      placeholder="如 {show} - S{season_padded}E{episode_padded}{extension}"
      @update:model-value="$emit('template-edit', $event)"
    />

    <div class="flex flex-col gap-3">
      <AppCheckbox
        :model-value="tplStore.createSeasonFolder"
        :disabled="source === 'openlist'"
        :label="source === 'openlist' ? '创建季文件夹（OpenList 暂不支持）' : '创建季文件夹'"
        @update:model-value="$emit('update:createSeasonFolder', $event)"
      />
      <AppInput
        :model-value="tplStore.folderTemplate"
        :disabled="!tplStore.createSeasonFolder || source === 'openlist'"
        label="季文件夹模板"
        mono
        placeholder="如 Season {season_padded}"
        @update:model-value="$emit('update:folderTemplate', $event)"
      />
    </div>

    <div class="flex flex-col gap-2">
      <div class="flex items-center gap-1.5 text-[12px] text-ink-3">
        <Info class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        可用变量（点击插入）
      </div>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="v in VARIABLE_DEFS"
          :key="v.tag"
          type="button"
          :title="v.desc"
          class="rounded-[8px] border border-line bg-surface px-2 py-1 font-mono text-[12px] text-accent transition-colors duration-150 hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
          @click="insertVariable(v.tag)"
        >
          {{ v.tag }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Info } from 'lucide-vue-next'

import AppSelect from './ui/AppSelect.vue'
import AppInput from './ui/AppInput.vue'
import AppCheckbox from './ui/AppCheckbox.vue'

const VARIABLE_DEFS = [
  { tag: '{show}', desc: '剧名（自动从路径/文件名解析）', example: '绝命毒师' },
  { tag: '{show_clean}', desc: '剧名（已清洗，去除特殊字符）', example: '绝命毒师' },
  { tag: '{season}', desc: '季数（阿拉伯数字）', example: '1' },
  { tag: '{season_padded}', desc: '季数（补零）', example: '01' },
  { tag: '{episode}', desc: '集数（阿拉伯数字）', example: '5' },
  { tag: '{episode_padded}', desc: '集数（补零）', example: '05' },
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
  // tplInputRef 指向 AppInput 的**组件实例**（AppInput 未设 inheritAttrs: false，
  // 且根是单个 <div>），所以要走 $el 再查内部的原生 input。
  // 原生 <input> 换成本组件后，这里是唯一会静默失效的地方：路径写错时
  // 下面的 !input 早退，点击变量 chip 毫无反应且 Console 无报错。
  const wrapper = tplInputRef.value
  const input = wrapper?.$el?.querySelector('input')
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
