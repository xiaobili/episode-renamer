<template>
  <div class="settings-view">
    <el-card class="panel">
      <template #header><span>⚙️ 通用设置</span></template>
      <el-form :model="settings" label-width="180px" style="max-width: 600px">
        <el-form-item label="默认模板">
          <el-select v-model="settings.defaultTemplate" style="width: 320px">
            <el-option
              v-for="p in presets"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="集数补零位数">
          <el-input-number v-model="settings.episodePadDigits" :min="1" :max="4" />
        </el-form-item>
        <el-form-item label="季数补零位数">
          <el-input-number v-model="settings.seasonPadDigits" :min="1" :max="4" />
        </el-form-item>
        <el-form-item label="冲突默认策略">
          <el-select v-model="settings.conflictStrategy" style="width: 200px">
            <el-option label="跳过" value="skip" />
            <el-option label="中止" value="abort" />
            <el-option label="覆盖" value="overwrite" />
            <el-option label="自动编号" value="rename_dup" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="panel" style="margin-top: 16px">
      <template #header><span>☁️ OpenList 设置</span></template>
      <el-form label-width="180px" style="max-width: 600px">
        <el-form-item label="默认服务器地址">
          <el-input placeholder="http://localhost:5244" style="width: 320px" />
        </el-form-item>
        <el-form-item label="最大并发请求">
          <el-input-number :min="1" :max="10" :model-value="3" />
        </el-form-item>
        <el-form-item label="请求间隔 (秒)">
          <el-input-number :min="0.1" :max="5" :step="0.1" :model-value="0.5" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="panel" style="margin-top: 16px">
      <template #header><span>📝 说明</span></template>
      <div class="about-text">
        <p><strong>本地模式:</strong> 直接操作本机磁盘文件，支持撤销（通过 SQLite 日志）</p>
        <p><strong>OpenList 云盘模式:</strong> 通过 OpenList API 操作云盘文件，支持 115、阿里云盘、百度云盘等数十种云存储</p>
        <p><strong>Emby/Jellyfin 规范:</strong> 建议使用 "Emby 标准" 预设模板，格式为 <code>剧名 - SxxExx.mkv</code></p>
        <p><strong>番剧注意:</strong> 番剧通常没有季数，会使用默认季数 1；支持父目录智能推断</p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getPresets } from '../api/template'

const presets = ref([])
const settings = ref({
  defaultTemplate: 'emby_standard',
  episodePadDigits: 2,
  seasonPadDigits: 2,
  conflictStrategy: 'skip',
})

onMounted(async () => {
  const res = await getPresets()
  if (res.data?.data) presets.value = res.data.data
})
</script>

<style scoped>
.panel {
  border-radius: 8px;
}

.about-text {
  line-height: 1.8;
  color: #606266;
}

.about-text code {
  background: #f0f2f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}
</style>
