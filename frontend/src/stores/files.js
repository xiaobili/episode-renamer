import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useFilesStore = defineStore('files', () => {
  const files = ref([])
  const loading = ref(false)
  const source = ref('local')
  const scanResult = ref(null)

  function setFiles(list) {
    files.value = list
  }

  function updateFile(id, patch) {
    const f = files.value.find(x => x.id === id)
    if (f) Object.assign(f, patch)
  }

  function getFileById(id) {
    return files.value.find(x => x.id === id)
  }

  function clear() {
    files.value = []
    scanResult.value = null
  }

  return { files, loading, source, scanResult, setFiles, updateFile, getFileById, clear }
})
