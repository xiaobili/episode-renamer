import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'

import './style.css'

import App from './App.vue'
import router from './router'
import { useSettingsStore } from './stores/settings'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 必须在 mount 之前：任何组件读到设置之前，持久化的值必须已经就位。
// 漏掉这一行不会报错，只会让所有设置静默回到默认值 —— 见 Review Focus 2。
useSettingsStore().load()

app.mount('#app')
