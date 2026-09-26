import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'

import {
  defaultSettings,
  normalizeSettings,
  readSettings,
  writeSettings,
} from './settingsSchema'

function safeStorage() {
  // 隐私模式 / 禁用站点数据时，访问 localStorage 会抛 SecurityError。
  // 探测一次，失败就返回 null（纯内存态），绝不让它阻塞应用启动。
  try {
    const probe = '__episode_renamer_probe__'
    window.localStorage.setItem(probe, '1')
    window.localStorage.removeItem(probe)
    return window.localStorage
  } catch {
    return null
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const storage = safeStorage()
  const storageAvailable = ref(storage !== null)
  const initial = defaultSettings()

  // 初值用默认值，真正的读盘在 load() 里 —— 由 main.js 在挂载前调用。
  // 这样「什么时候读盘」是显式的，而不是藏在 store 创建的副作用里。
  const defaultTemplateId = ref(initial.defaultTemplateId)
  const episodePadDigits = ref(initial.episodePadDigits)
  const seasonPadDigits = ref(initial.seasonPadDigits)
  const conflictStrategy = ref(initial.conflictStrategy)
  const openlist = reactive({ ...initial.openlist })
  const tmdb = reactive({ ...initial.tmdb })

  function apply(data) {
    const next = normalizeSettings(data)
    defaultTemplateId.value = next.defaultTemplateId
    episodePadDigits.value = next.episodePadDigits
    seasonPadDigits.value = next.seasonPadDigits
    conflictStrategy.value = next.conflictStrategy
    tmdb.apiKey = next.tmdb.apiKey
    tmdb.language = next.tmdb.language
    tmdb.enabled = next.tmdb.enabled
    openlist.serverUrl = next.openlist.serverUrl
    openlist.concurrency = next.openlist.concurrency
    openlist.requestInterval = next.openlist.requestInterval
  }

  function toObject() {
    return {
      defaultTemplateId: defaultTemplateId.value,
      episodePadDigits: episodePadDigits.value,
      seasonPadDigits: seasonPadDigits.value,
      conflictStrategy: conflictStrategy.value,
      tmdb: { ...tmdb },
      openlist: { ...openlist },
    }
  }

  function load() {
    apply(readSettings(storage))
  }

  function save() {
    writeSettings(storage, toObject())
  }

  return {
    defaultTemplateId, episodePadDigits, seasonPadDigits, conflictStrategy, tmdb, openlist,
    storageAvailable,
    load, save, apply, toObject,
  }
})
