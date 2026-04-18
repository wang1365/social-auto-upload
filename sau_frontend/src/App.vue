<template>
  <div id="app">
    <el-container>
      <el-aside :width="isCollapse ? '64px' : '220px'">
        <div class="sidebar">
          <div class="logo">
            <img v-show="isCollapse" src="/vite.svg" alt="Logo" class="logo-img">
            <h2 v-show="!isCollapse">Social Auto Upload</h2>
          </div>
          <el-menu
            :router="true"
            :default-active="activeMenu"
            :collapse="isCollapse"
            class="sidebar-menu"
            background-color="#001529"
            text-color="#fff"
            active-text-color="#409EFF"
          >
            <el-menu-item index="/">
              <el-icon><HomeFilled /></el-icon>
              <span>首页</span>
            </el-menu-item>
            <el-menu-item index="/account-management">
              <el-icon><User /></el-icon>
              <span>账号管理</span>
            </el-menu-item>
            <el-menu-item index="/material-management">
              <el-icon><Picture /></el-icon>
              <span>素材管理</span>
            </el-menu-item>
            <el-menu-item index="/download-center">
              <el-icon><Download /></el-icon>
              <span>素材下载</span>
            </el-menu-item>
            <el-menu-item index="/publish-center">
              <el-icon><Upload /></el-icon>
              <span>发布中心</span>
            </el-menu-item>
            <el-menu-item index="/system-settings">
              <el-icon><Setting /></el-icon>
              <span>系统配置</span>
            </el-menu-item>
            <el-menu-item index="/about">
              <el-icon><DataAnalysis /></el-icon>
              <span>关于</span>
            </el-menu-item>
          </el-menu>
        </div>
      </el-aside>
      <el-container>
        <el-header>
          <div class="header-content">
            <el-icon class="toggle-sidebar" @click="toggleSidebar"><Fold /></el-icon>
          </div>
        </el-header>
        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  DataAnalysis,
  Download,
  Fold,
  HomeFilled,
  Picture,
  Setting,
  Upload,
  User,
} from '@element-plus/icons-vue'

const route = useRoute()
const activeMenu = computed(() => route.path)
const isCollapse = ref(false)

const toggleSidebar = () => {
  isCollapse.value = !isCollapse.value
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

#app {
  min-height: 100vh;
}

.el-container {
  height: 100vh;
}

.el-aside {
  background-color: #001529;
  color: #fff;
  height: 100vh;
  overflow: hidden;
  transition: width 0.3s;
}

.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.logo {
  height: 60px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  background-color: #002140;
  overflow: hidden;
}

.logo-img {
  width: 32px;
  height: 32px;
  margin-right: 12px;
}

.logo h2 {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  margin: 0;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.el-header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  padding: 0;
  height: 60px;
}

.header-content {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 16px;
}

.toggle-sidebar {
  font-size: 20px;
  cursor: pointer;
  color: $text-regular;
}

.toggle-sidebar:hover {
  color: $primary-color;
}

.el-main {
  background-color: $bg-color-page;
  padding: 20px;
  overflow-y: auto;
}
</style>
