import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useTemplateStore = defineStore('template', () => {
  const presets = ref([])
  const currentPresetId = ref('emby_standard')
  const currentTemplate = ref('{show} - S{season_padded}E{episode_padded}{extension}')
  const folderTemplate = ref('Season {season_padded}')
  const createSeasonFolder = ref(true)

  const currentPreset = computed(() => {
    return presets.value.find(p => p.id === currentPresetId.value)
  })

  function setPreset(preset) {
    currentPresetId.value = preset.id
    currentTemplate.value = preset.template
    folderTemplate.value = preset.folder_template || ''
  }

  function setTemplate(tpl) {
    currentTemplate.value = tpl
    currentPresetId.value = ''
  }

  return { presets, currentPresetId, currentTemplate, folderTemplate, createSeasonFolder, currentPreset, setPreset, setTemplate }
})
