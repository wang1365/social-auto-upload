<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import {
  Promotion,
  FolderOpened,
  User,
  CircleCheck,
  ArrowRight,
  Plus,
  Download,
} from "@element-plus/icons-vue";
import { state, isActive, kindLabels, drawerTask } from "../state";
import TaskTable from "../components/TaskTable.vue";
const router = useRouter();
const relevant = computed(() =>
  state.tasks.filter((t) => !["preview", "check"].includes(t.kind)),
);
const active = computed(() => relevant.value.filter(isActive));
const attention = computed(() =>
  relevant.value.filter((t) =>
    ["failed", "interrupted", "unknown"].includes(t.status),
  ),
);
const completed = computed(() =>
  relevant.value.filter(
    (t) => t.kind === "publish" && t.status === "succeeded",
  ),
);
const valid = computed(
  () => state.accounts.filter((a) => a.status === 1).length,
);
const today = new Date().toLocaleDateString("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "long",
  day: "numeric",
  weekday: "long",
});
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">{{ today }}</div>
      <h1>今天，也让创作有条不紊</h1>
      <p>从一条视频开始，轻松管理您的内容分发。</p>
    </div>
    <el-button type="primary" :icon="Plus" @click="router.push('/publish')"
      >新建发布</el-button
    >
  </div>
  <div class="stats-grid">
    <div class="stat-card">
      <span class="stat-icon blue"
        ><el-icon><FolderOpened /></el-icon
      ></span>
      <div>
        <span>视频素材</span
        ><strong>{{ state.materialTotal }}<small>条</small></strong
        ><router-link to="/materials"
          >管理素材 <el-icon><ArrowRight /></el-icon
        ></router-link>
      </div>
    </div>
    <div class="stat-card">
      <span class="stat-icon green"
        ><el-icon><User /></el-icon
      ></span>
      <div>
        <span>可用账号</span
        ><strong
          >{{ valid }}<small>/ {{ state.accounts.length }} 个</small></strong
        ><router-link to="/accounts"
          >查看账号 <el-icon><ArrowRight /></el-icon
        ></router-link>
      </div>
    </div>
    <div class="stat-card">
      <span class="stat-icon violet"
        ><el-icon><Promotion /></el-icon
      ></span>
      <div>
        <span>进行中任务</span
        ><strong>{{ active.length }}<small>个</small></strong
        ><router-link to="/downloads"
          >查看进度 <el-icon><ArrowRight /></el-icon
        ></router-link>
      </div>
    </div>
    <div class="stat-card">
      <span class="stat-icon orange"
        ><el-icon><CircleCheck /></el-icon
      ></span>
      <div>
        <span>近期发布成功</span
        ><strong>{{ completed.length }}<small>条</small></strong
        ><router-link to="/publish"
          >发布记录 <el-icon><ArrowRight /></el-icon
        ></router-link>
      </div>
    </div>
  </div>
  <div class="dashboard-columns">
    <section class="panel quickstart">
      <div class="section-heading">
        <h2>开始一次内容分发</h2>
        <span class="muted small">三个步骤，完成准备</span>
      </div>
      <div class="quicksteps">
        <router-link to="/accounts"
          ><span class="quickstep-icon"><User /></span>
          <div>
            <strong>连接创作账号</strong><span>扫码添加各平台账号</span>
          </div>
          <span class="step-state" :class="{ done: valid }"
            >{{ valid ? "已就绪" : "去连接" }} →</span
          ></router-link
        ><router-link to="/materials"
          ><span class="quickstep-icon"><FolderOpened /></span>
          <div>
            <strong>准备视频素材</strong><span>本地导入，或下载后自动处理</span>
          </div>
          <span class="step-state" :class="{ done: state.materialTotal }"
            >{{ state.materialTotal ? "已就绪" : "去添加" }} →</span
          ></router-link
        ><router-link to="/publish"
          ><span class="quickstep-icon"><Promotion /></span>
          <div>
            <strong>编辑文案并发布</strong
            ><span>逐条编辑，一次提交多个账号</span>
          </div>
          <span class="step-state">去发布 →</span></router-link
        >
      </div>
    </section>
    <section class="panel attention-panel">
      <div class="section-heading">
        <h2>需要关注</h2>
        <span class="attention-count">{{
          attention.length + state.accounts.length - valid
        }}</span>
      </div>
      <template v-if="attention.length || state.accounts.length > valid"
        ><button
          v-if="state.accounts.length > valid"
          class="attention-item"
          @click="router.push('/accounts')"
        >
          <i class="status-dot warning"></i>
          <div>
            <strong>{{ state.accounts.length - valid }} 个账号需要登录</strong
            ><span>重新扫码后即可继续发布</span>
          </div>
          <el-icon><ArrowRight /></el-icon></button
        ><button
          v-for="task in attention.slice(0, 3)"
          :key="task.id"
          class="attention-item"
          @click="drawerTask = task.id"
        >
          <i class="status-dot warning"></i>
          <div>
            <strong class="ellipsis">{{ task.title }}</strong><span
              >{{ kindLabels[task.kind] }} ·
              {{
                task.status === "unknown"
                  ? "请到平台核实结果"
                  : "查看失败原因并处理"
              }}</span
            >
          </div>
          <el-icon><ArrowRight /></el-icon></button
      ></template>
      <div v-else class="all-clear">
        <el-icon><CircleCheck /></el-icon><strong>一切井然有序</strong
        ><span>暂无需要处理的事项</span>
      </div>
    </section>
  </div>
  <section class="panel recent-panel">
    <div class="section-heading">
      <h2>最近任务</h2>
      <router-link to="/publish" class="small">查看发布记录 →</router-link>
    </div>
    <TaskTable :tasks="relevant.slice(0, 6)" compact />
  </section>
</template>
