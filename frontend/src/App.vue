<template>
  <el-container class="app-container">
    <el-header class="app-header">
      <div class="header-left">
        <span class="logo">🎬</span>
        <h1 class="title">Episode Renamer</h1>
        <span class="subtitle">电视剧 / 番剧 自动化重命名</span>
      </div>
      <div class="header-right">
        <el-menu mode="horizontal" :default-active="route.path" router class="nav-menu">
          <el-menu-item index="/">
            <el-icon><FolderOpened /></el-icon>
            <span>重命名</span>
          </el-menu-item>
          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon>
            <span>设置</span>
          </el-menu-item>
        </el-menu>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<style>
html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f5f7fa;
}

.app-container {
  height: 100vh;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  font-size: 28px;
}

.title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #303133;
}

.subtitle {
  font-size: 13px;
  color: #909399;
  margin-left: 8px;
  padding-left: 12px;
  border-left: 1px solid #dcdfe6;
}

.header-right {
  display: flex;
  align-items: center;
}

.nav-menu {
  border-bottom: none !important;
}

.app-main {
  padding: 20px;
  overflow: auto;
  background: #f5f7fa;
}
</style>
