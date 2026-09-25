<template>
  <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
    <div class="p-6">
      <template v-if="source === 'local'">
        <div class="flex items-center gap-3 flex-wrap">
          <div
            class="flex-1 min-w-[280px] h-10 px-3 rounded-lg border border-border bg-surface cursor-pointer hover:border-primary transition flex items-center gap-2"
            @click="$emit('browse-local')"
          >
            <Folder class="w-4 h-4 text-text-faint shrink-0" />
            <span
              v-if="localPath"
              class="text-[13px] text-text truncate flex-1 font-mono"
            >{{ localPath }}</span>
            <span v-else class="text-[13px] text-text-faint flex-1">点击浏览选择目录</span>
            <FolderSearch class="w-4 h-4 text-text-muted" />
          </div>
          <label class="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer select-none">
            <input :checked="recursive" @change="$emit('update:recursive', $event.target.checked)" type="checkbox" class="w-4 h-4 accent-primary rounded" />
            递归扫描
          </label>
          <label class="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer select-none">
            <input :checked="includeSubs" @change="$emit('update:includeSubs', $event.target.checked)" type="checkbox" class="w-4 h-4 accent-primary rounded" />
            包含字幕
          </label>
          <button
            class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="scanning || !localPath"
            @click="$emit('scan')"
          >
            <Search class="w-4 h-4" />
            {{ scanning ? '扫描中...' : '扫描' }}
          </button>
        </div>
      </template>

      <template v-else>
        <template v-if="!olStore.connected">
          <div class="flex items-center gap-3 flex-wrap">
            <div class="flex items-center gap-2">
              <span class="text-[13px] text-text-secondary">服务器</span>
              <input
                v-model="olForm.server_url"
                type="text"
                placeholder="http://localhost:5244"
                class="w-[220px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[13px] text-text-secondary">用户名</span>
              <input
                v-model="olForm.username"
                type="text"
                placeholder="admin"
                class="w-[140px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[13px] text-text-secondary">密码</span>
              <input
                v-model="olForm.password"
                type="password"
                placeholder="••••••"
                show-password
                class="w-[160px] h-10 px-3 rounded-lg border border-border bg-surface text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <button
              class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50"
              :disabled="olStore.loading"
              @click="$emit('login')"
            >
              <Zap class="w-4 h-4" />
              {{ olStore.loading ? '连接中...' : '连接' }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="flex items-center gap-3 flex-wrap">
            <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-success-light text-success text-[12px] font-medium">
              <CheckCircle2 class="w-3.5 h-3.5" />
              已连接: {{ olStore.serverUrl }}
            </div>

            <select
              :value="olStore.selectedMount"
              @change="$emit('mount-change', $event.target.value)"
              class="h-10 px-3 rounded-lg border border-border bg-surface text-[13px] text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            >
              <option v-for="m in olStore.mountPoints" :key="m" :value="m">{{ m }}</option>
            </select>

            <div
              class="flex-1 min-w-[280px] h-10 px-3 rounded-lg border border-border bg-surface cursor-pointer hover:border-primary transition flex items-center gap-2"
              @click="$emit('browse')"
            >
              <Folder class="w-4 h-4 text-text-faint shrink-0" />
              <span
                v-if="openlistBrowsePath"
                class="text-[13px] text-text truncate flex-1"
              >{{ openlistBrowsePath }}</span>
              <span v-else class="text-[13px] text-text-faint flex-1">点击浏览选择目录</span>
              <FolderSearch class="w-4 h-4 text-text-muted" />
            </div>

            <button
              class="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-lg text-[13px] font-medium flex items-center gap-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="scanning"
              @click="$emit('scan')"
            >
              <Search class="w-4 h-4" />
              {{ scanning ? '扫描中...' : '扫描' }}
            </button>
            <button
              class="h-10 px-4 bg-surface hover:bg-surface-muted border border-border-strong text-text-secondary hover:text-primary rounded-lg text-[13px] font-medium flex items-center gap-2 transition"
              @click="$emit('logout')"
            >
              <LogOut class="w-4 h-4" />
              断开
            </button>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup>
import { Folder, FolderSearch, Search, CheckCircle2, Zap, LogOut } from 'lucide-vue-next'

defineProps({
  source: { type: String, required: true },
  localPath: String,
  recursive: Boolean,
  includeSubs: Boolean,
  scanning: Boolean,
  openlistBrowsePath: String,
  olStore: { type: Object, required: true },
  olForm: { type: Object, required: true },
})
defineEmits([
  'update:localPath', 'update:recursive', 'update:includeSubs',
  'scan', 'login', 'logout', 'browse', 'mount-change', 'browse-local',
])
</script>
