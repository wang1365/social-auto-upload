<script setup lang="ts">
import { computed, ref } from "vue";
import { Plus, Download, VideoPlay } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { post } from "../api";
import {
  act,
  date,
  drawerTask,
  previewMaterial,
  refresh,
  state,
  titleOf,
} from "../state";
import TaskTable from "../components/TaskTable.vue";
const dialog = ref(false),
  url = ref(""),
  subtitles = ref(true),
  busy = ref(false);
const tasks = computed(() =>
  state.tasks.filter((t) => ["download", "processing"].includes(t.kind)),
);
const history = computed(() => {
  const known = new Set(state.tasks.map((t) => Number(t.result.materialId)));
  return state.materials.filter(
    (m) => m.source_type === "youtube" && !known.has(m.id),
  );
});
async function submit() {
  if (!url.value.trim()) {
    ElMessage.warning("请先输入视频链接");
    return;
  }
  busy.value = true;
  await act(async () => {
    const result = await post<{ id: string }>("/downloads", {
      url: url.value,
      subtitles: subtitles.value,
    });
    dialog.value = false;
    url.value = "";
    drawerTask.value = result.id;
    await refresh();
  });
  busy.value = false;
}
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">下载与处理</div>
      <h1>下载中心</h1>
      <p>下载、字幕与视频处理，进度尽在掌握。</p>
    </div>
    <el-button type="primary" :icon="Plus" @click="dialog = true"
      >新建下载</el-button
    >
  </div>
  <div class="info-strip">
    <el-icon><Download /></el-icon
    ><span>支持单条 YouTube 视频下载，完成后自动进入素材库。</span
    ><router-link to="/settings">下载与处理设置 →</router-link>
  </div>
  <section class="panel"><TaskTable :tasks="tasks" /></section>
  <section v-if="history.length" class="panel history-panel">
    <div class="section-heading">
      <div>
        <h2>历史下载素材</h2>
        <span class="muted small">来自已有素材记录，无历史运行日志</span>
      </div>
      <router-link to="/materials" class="small">查看全部素材 →</router-link>
    </div>
    <el-table :data="history"
      ><el-table-column label="视频" min-width="280"
        ><template #default="{ row }"
          ><button class="text-link" @click="previewMaterial = row">
            {{ titleOf(row) }}
          </button></template
        ></el-table-column
      ><el-table-column label="下载时间" width="150"
        ><template #default="{ row }">{{
          date(row.upload_time)
        }}</template></el-table-column
      ><el-table-column label="操作" width="100"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="previewMaterial = row"
            >预览</el-button
          ></template
        ></el-table-column
      ></el-table
    >
  </section>
  <el-dialog v-model="dialog" title="新建视频下载" width="540px"
    ><el-form label-position="top" @submit.prevent="submit"
      ><el-form-item label="视频链接" required
        ><el-input
          v-model="url"
          placeholder="粘贴 YouTube 单条视频链接"
          clearable
          @keyup.enter="submit" /></el-form-item
      ><el-form-item
        ><el-checkbox v-model="subtitles"
          >同时下载可用字幕</el-checkbox
        ></el-form-item
      >
      <div class="info-box">
        下载使用设置中的代理与登录凭据。若已启用自动处理，下载后会继续生成处理版本。
      </div></el-form
    ><template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="submit"
        >开始下载</el-button
      ></template
    ></el-dialog
  >
</template>
