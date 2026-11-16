<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { api, type Task, type TaskEvent, type Material } from "../api";
import {
  act,
  accountLogin,
  date,
  drawerTask,
  isActive,
  kindLabels,
  platformNames,
  previewMaterial,
  cancelTask,
  stoppingTasks,
  retry,
  retryable,
  state,
  statusLabels,
} from "../state";
const task = ref<Task | null>(null);
const logs = ref<TaskEvent[]>([]);
const subtitle = ref("");
const detailsOpen = ref(false);
const account = computed(() =>
  state.accounts.find((a) => a.id === task.value?.account_id),
);
const child = computed(() =>
  state.tasks.find(
    (t) => t.parent_id === task.value?.id && t.kind === "processing",
  ),
);
const publishChildren = computed(() =>
  state.tasks.filter(
    (t) => t.parent_id === task.value?.id && t.kind === "publish",
  ),
);
let timer: ReturnType<typeof setInterval> | null = null;
let generation = 0;
let logCursor = 0;
async function load(id: string, version: number) {
  const [item, events] = await Promise.all([
    api<Task>(`/tasks/${id}`),
    api<TaskEvent[]>(`/tasks/${id}/logs?after=${logCursor}`),
  ]);
  if (version !== generation) return;
  task.value = item;
  if (events.length) logCursor = events[events.length - 1].id;
  const existing = new Set(logs.value.map((event) => event.id));
  logs.value = [
    ...logs.value,
    ...events.filter((e) => e.event === "log" && !existing.has(e.id)),
  ].slice(-1000);
}
watch(drawerTask, (id) => {
  generation++;
  logCursor = 0;
  task.value = null;
  logs.value = [];
  subtitle.value = "";
  detailsOpen.value = false;
  if (timer) clearInterval(timer);
  if (id) {
    const version = generation;
    act(() => load(id, version));
    timer = setInterval(() => {
      if (drawerTask.value === id) load(id, version).catch(() => {});
    }, 2000);
  }
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
async function preview(id: number) {
  await act(async () => {
    previewMaterial.value = await api<Material>(`/materials/${id}`);
  });
}
async function showSubtitle(id: number) {
  await act(async () => {
    subtitle.value =
      (await api<{ text: string }>(`/materials/${id}/subtitle`)).text ||
      "此素材没有字幕";
  });
}
async function cancel() {
  if (task.value) {
    const id = task.value.id;
    await cancelTask(task.value);
    await act(() => load(id, generation));
  }
}
</script>

<template>
  <el-drawer
    :model-value="!!drawerTask"
    title="任务详情"
    size="560px"
    destroy-on-close
    @close="drawerTask = null"
  >
    <div v-if="task" class="task-detail">
      <div class="detail-heading">
        <span class="eyebrow">{{ kindLabels[task.kind] }}</span>
        <h2>{{ task.title }}</h2>
        <span class="status-pill" :class="task.status"
          ><i></i>{{ statusLabels[task.status] }}</span
        >
      </div>
      <div class="detail-progress">
        <strong>{{ task.phase }}</strong><el-progress
          v-if="task.progress !== null"
          :percentage="Math.min(100, Math.max(0, task.progress))"
          :stroke-width="6"
        />
        <p v-if="isActive(task)" class="muted small">
          您可以离开此页面，任务会在后台继续。
        </p>
      </div>
      <div
        v-if="task.kind === 'login' && task.result.qrcode && isActive(task)"
        class="qr-panel"
      >
        <img :src="String(task.result.qrcode)" alt="账号登录二维码" />
        <p>
          打开{{ account ? platformNames[account.type] : "对应平台" }}
          App，扫码登录
        </p>
        <span class="muted small"
          >请在手机上确认登录，二维码更新后会自动刷新。</span
        >
      </div>
      <el-alert
        v-if="task.status === 'unknown'"
        type="warning"
        title="请先到对应平台核实结果，避免重复发布。"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="task.result.retry_status"
        type="info"
        :title="
          task.result.retry_status === 'succeeded'
            ? '此任务的后续重试已成功。'
            : '此任务的后续重试结果待核实，请先到平台确认。'
        "
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="task.error"
        :title="task.error"
        type="error"
        :closable="false"
        show-icon
      />
      <dl class="detail-meta">
        <dt>创建时间</dt>
        <dd>{{ date(task.created_at) }}</dd>
        <dt>更新时间</dt>
        <dd>{{ date(task.updated_at) }}</dd>
        <template v-if="account"
          ><dt>关联账号</dt>
          <dd>
            {{ platformNames[account.type] }} / {{ account.userName }}
          </dd></template
        >
      </dl>
      <div class="detail-actions">
        <el-button v-if="retryable(task)" type="primary" @click="retry(task)"
          >重新尝试</el-button
        ><el-button v-if="task.status === 'queued'" @click="cancel"
          >取消等待</el-button
        ><el-button
          v-if="task.status === 'running'"
          type="danger"
          :loading="stoppingTasks.has(task.id)"
          @click="cancel"
          >终止任务</el-button
        ><el-button
          v-if="task.kind === 'login' && !isActive(task) && account"
          @click="accountLogin(account, true)"
          >打开浏览器登录</el-button
        ><el-button
          v-if="task.result.materialId"
          @click="preview(Number(task.result.materialId))"
          >查看原视频</el-button
        ><el-button
          v-if="
            task.result.processedMaterialId || child?.result.processedMaterialId
          "
          @click="
            preview(
              Number(
                task.result.processedMaterialId ||
                  child?.result.processedMaterialId,
              ),
            )
          "
          >查看处理结果</el-button
        ><el-button
          v-if="task.result.materialId"
          @click="showSubtitle(Number(task.result.materialId))"
          >查看字幕</el-button
        >
      </div>
      <div v-if="child" class="info-box">
        <span>后续视频处理</span
        ><button class="text-link" @click="drawerTask = child.id">
          {{ statusLabels[child.status] }} · {{ child.phase }} →
        </button>
      </div>
      <div v-if="publishChildren.length" class="info-box">
        <strong>后续发布任务（{{ publishChildren.length }}）</strong>
        <p v-for="job in publishChildren" :key="job.id">
          <button class="text-link" @click="drawerTask = job.id">
            {{ platformNames[Number(job.payload.platform)] }} ·
            {{ job.payload.account_name }} · {{ statusLabels[job.status] }} →
          </button>
        </p>
      </div>
      <pre v-if="subtitle" class="subtitle-content">{{ subtitle }}</pre>
      <el-collapse
        ><el-collapse-item title="运行日志" name="logs"
          ><div class="log-list">
            <p v-for="event in logs" :key="event.id">
              <time>{{ date(event.created_at) }}</time>{{ event.data.message }}
            </p>
            <el-empty
              v-if="!logs.length"
              description="暂时没有日志"
              :image-size="48"
            /></div></el-collapse-item
      ></el-collapse>
      <button
        v-if="task.detail"
        class="text-link muted small"
        @click="detailsOpen = !detailsOpen"
      >
        {{ detailsOpen ? "收起技术详情" : "展开技术详情" }}
      </button>
      <pre v-if="detailsOpen" class="technical-detail">{{ task.detail }}</pre>
    </div>
    <el-skeleton v-else :rows="6" animated />
  </el-drawer>
</template>
