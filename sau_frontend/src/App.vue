<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import {
  House,
  Promotion,
  FolderOpened,
  Download,
  VideoPlay,
  User,
  Setting,
  ArrowRight,
  Monitor,
  Connection,
} from "@element-plus/icons-vue";
import { connectLive, state, isActive } from "./state";
import { connection } from "./api";
import TaskDrawer from "./components/TaskDrawer.vue";
import VideoPreview from "./components/VideoPreview.vue";

const route = useRoute();
const links = [
  { path: "/", label: "工作台", icon: House },
  { path: "/publish", label: "发布中心", icon: Promotion },
  { path: "/materials", label: "素材库", icon: FolderOpened },
  { path: "/youtube", label: "YouTube 浏览", icon: VideoPlay },
  { path: "/downloads", label: "下载中心", icon: Download },
  { path: "/accounts", label: "账号管理", icon: User },
  { path: "/settings", label: "设置", icon: Setting },
];
const activeCount = computed(
  () => state.tasks.filter((t) => isActive(t) && t.kind !== "preview").length,
);
let disconnect = () => {};
onMounted(() => {
  disconnect = connectLive();
});
onUnmounted(() => disconnect());
</script>

<template>
  <el-config-provider>
    <div
      class="app-shell"
      :class="{ 'youtube-route': route.path === '/youtube' }"
    >
      <aside class="sidebar">
        <router-link to="/" class="brand"
          ><span class="brand-mark"><i></i><i></i><i></i></span
          ><span class="brand-name">拾光分发<small>SHIGUANG</small></span
          ><span class="version">2.0</span></router-link
        >
        <div class="nav-label">内容管理</div>
        <nav aria-label="主导航">
          <router-link
            v-for="link in links"
            :key="link.path"
            :to="link.path"
            class="nav-item"
            :class="{ selected: route.path === link.path }"
            ><el-icon><component :is="link.icon" /></el-icon
            ><span>{{ link.label }}</span
            ><span
              v-if="link.path === '/downloads' && activeCount"
              class="nav-count"
              >{{ activeCount }}</span
            ></router-link
          >
        </nav>
        <div class="sidebar-bottom">
          <el-icon><Monitor /></el-icon>
          <div>
            <strong>本机工作空间</strong><span>文件与账号保存在此电脑</span>
          </div>
        </div>
      </aside>
      <div class="main-shell">
        <header class="topbar">
          <span>我的工作空间</span
          ><el-icon class="crumb-arrow"><ArrowRight /></el-icon
          ><strong>{{ route.name }}</strong>
          <div class="topbar-right">
            <span class="connection"
              ><i :class="{ offline: !connection.online }"></i
              >{{ connection.online ? "本机服务已连接" : "连接已断开" }}</span
            ><span class="topbar-divider"></span
            ><el-icon><Connection /></el-icon><span>本地模式</span>
          </div>
        </header>
        <el-alert
          v-if="!connection.online"
          :title="connection.error"
          type="error"
          :closable="false"
          show-icon
          class="offline-banner"
        />
        <main class="page-content"><router-view /></main>
      </div>
    </div>
    <TaskDrawer />
    <VideoPreview />
  </el-config-provider>
</template>
