import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'episode-renamer:openlist'

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveToStorage(state) {
  try {
    const data = {
      serverUrl: state.serverUrl,
      username: state.username,
      mountPoints: state.mountPoints,
      selectedMount: state.selectedMount,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {}
}

function clearStorage() {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {}
}

export const useOpenListStore = defineStore('openlist', () => {
  const saved = loadFromStorage()

  const connected = ref(false)
  const serverUrl = ref(saved.serverUrl || '')
  const username = ref(saved.username || '')
  const mountPoints = ref(saved.mountPoints || [])
  const selectedMount = ref(saved.selectedMount || '')
  const writeAccess = ref(true)
  const loading = ref(false)

  watch(
    [serverUrl, username, mountPoints, selectedMount],
    () => {
      if (serverUrl.value) {
        saveToStorage({
          serverUrl: serverUrl.value,
          username: username.value,
          mountPoints: mountPoints.value,
          selectedMount: selectedMount.value,
        })
      }
    },
    { deep: true }
  )

  function setConnection(status, data = {}) {
    connected.value = status
    if (data.server_url !== undefined) serverUrl.value = data.server_url || ''
    if (data.username !== undefined) username.value = data.username || ''
    if (data.mount_points !== undefined) mountPoints.value = data.mount_points || []
    writeAccess.value = data.write_access ?? true
    if (mountPoints.value.length && !selectedMount.value) {
      selectedMount.value = mountPoints.value[0]
    }
    if (!mountPoints.value.includes(selectedMount.value) && mountPoints.value.length) {
      selectedMount.value = mountPoints.value[0]
    }
  }

  function disconnect() {
    connected.value = false
    mountPoints.value = []
    selectedMount.value = ''
    serverUrl.value = ''
    username.value = ''
    clearStorage()
  }

  return { connected, serverUrl, username, mountPoints, selectedMount, writeAccess, loading, setConnection, disconnect }
})
