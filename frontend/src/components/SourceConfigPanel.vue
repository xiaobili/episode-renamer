<template>
  <div class="flex flex-col gap-2.5">
    <template v-if="source === 'local'">
      <div class="flex items-end gap-2">
        <AppInput
          :model-value="localPath"
          label="目录路径"
          placeholder="点击右侧浏览，或直接输入"
          class="min-w-0 flex-1"
          @update:model-value="$emit('update:localPath', $event)"
        />
        <AppButton variant="secondary" @click="$emit('browse-local')">浏览</AppButton>
      </div>

      <AppCheckbox
        :model-value="recursive"
        label="递归扫描"
        @update:model-value="$emit('update:recursive', $event)"
      />
      <AppCheckbox
        :model-value="includeSubs"
        label="包含字幕"
        @update:model-value="$emit('update:includeSubs', $event)"
      />

      <!-- 刮削在途时扫描一并禁用（spec §17.4）。这是一场**镜像竞态**：刮削在途时
           发起扫描，两个请求都在飞，若刮削的响应后到，它会用「带标题的表」覆盖
           「扫描的表」，而此刻 `scraped` 已被乐观置位、扫描又有把 scraped 重置为
           false 的职责 —— 两边拉锯的结果同样是「预览与执行不一致」（表里是新名，
           载荷按 scraped 走另一条路）。 -->
      <AppButton
        variant="primary"
        block
        :loading="scanning"
        :disabled="!localPath || scraping"
        @click="$emit('scan')"
      >
        {{ scanning ? '扫描中…' : '扫描' }}
      </AppButton>
    </template>

    <template v-else>
      <template v-if="!olStore.connected">
        <AppInput
          v-model="olForm.server_url"
          label="服务器"
          placeholder="http://localhost:5244"
        />
        <AppInput v-model="olForm.username" label="用户名" placeholder="admin" />
        <AppInput
          v-model="olForm.password"
          label="密码"
          type="password"
          placeholder="••••••"
        />
        <AppButton
          variant="primary"
          block
          :loading="olStore.loading"
          @click="$emit('login')"
        >
          {{ olStore.loading ? '连接中…' : '连接' }}
        </AppButton>
      </template>

      <template v-else>
        <div class="flex items-center gap-1.5 text-[12px] font-medium text-ink-2">
          <CheckCircle2 class="h-3.5 w-3.5 text-accent" aria-hidden="true" />
          <span class="truncate">已连接: {{ olStore.serverUrl }}</span>
        </div>

        <AppSelect
          label="挂载点"
          :model-value="olStore.selectedMount"
          @update:model-value="$emit('mount-change', $event)"
        >
          <option v-for="m in olStore.mountPoints" :key="m" :value="m">{{ m }}</option>
        </AppSelect>

        <div class="flex items-end gap-2">
          <AppInput
            :model-value="openlistBrowsePath"
            label="目录路径"
            placeholder="点击右侧浏览选择"
            class="min-w-0 flex-1"
            @update:model-value="$emit('update:localPath', $event)"
          />
          <AppButton variant="secondary" @click="$emit('browse')">浏览</AppButton>
        </div>

        <AppButton
          variant="primary"
          block
          :loading="scanning"
          :disabled="!openlistBrowsePath || scraping"
          @click="$emit('scan')"
        >
          {{ scanning ? '扫描中…' : '扫描' }}
        </AppButton>
        <AppButton variant="ghost" block @click="$emit('logout')">断开连接</AppButton>
      </template>
    </template>
  </div>
</template>

<script setup>
import { CheckCircle2 } from 'lucide-vue-next'

import AppButton from './ui/AppButton.vue'
import AppSelect from './ui/AppSelect.vue'
import AppInput from './ui/AppInput.vue'
import AppCheckbox from './ui/AppCheckbox.vue'

defineProps({
  source: { type: String, required: true },
  localPath: { type: String, default: '' },
  recursive: { type: Boolean, default: true },
  includeSubs: { type: Boolean, default: true },
  scanning: { type: Boolean, default: false },
  // 刮削在途（见模板里扫描按钮上的注释）。默认 false 而非 required：本组件在
  // 没有 workspace store 的上下文里（如单独预览）也该能渲染。
  scraping: { type: Boolean, default: false },
  openlistBrowsePath: { type: String, default: '' },
  olStore: { type: Object, required: true },
  olForm: { type: Object, required: true },
})
defineEmits([
  'update:localPath', 'update:recursive', 'update:includeSubs',
  'scan', 'login', 'logout', 'browse', 'mount-change', 'browse-local',
])
</script>
