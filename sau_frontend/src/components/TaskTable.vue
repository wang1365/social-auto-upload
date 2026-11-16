<script setup lang="ts">
import { computed, ref } from "vue";
import type { Task } from "../api";
import { api, post } from "../api";
import {
  act,
  confirm,
  date,
  drawerTask,
  isActive,
  kindLabels,
  refresh,
  retry,
  retryable,
  statusLabels,
  platformNames,
} from "../state";
const props = defineProps<{ tasks: Task[]; compact?: boolean }>();
const filter = ref("all");
const visible = computed(() =>
  props.tasks.filter(
    (t) =>
      filter.value === "all" ||
      (filter.value === "active"
        ? isActive(t)
        : filter.value === "attention"
          ? ["failed", "interrupted", "unknown"].includes(t.status)
          : t.status === filter.value),
  ),
);
async function remove(task: Task) {
  if (
    await confirm(
      "只删除这条任务记录，已生成的素材和平台内容会保留。",
      "删除记录",
    )
  )
    await act(async () => {
      await api(`/tasks/${task.id}`, { method: "DELETE" });
      await refresh();
    });
}
async function cancel(task: Task) {
  await act(async () => {
    await post(`/tasks/${task.id}/cancel`);
    await refresh();
  });
}
</script>

<template>
  <div v-if="!compact" class="table-tabs">
    <button
      v-for="tab in [
        { id: 'all', name: '全部任务' },
        { id: 'active', name: '进行中' },
        { id: 'succeeded', name: '已完成' },
        { id: 'attention', name: '需要关注' },
      ]"
      :key="tab.id"
      :class="{ active: filter === tab.id }"
      @click="filter = tab.id"
    >
      {{ tab.name }}
    </button>
  </div>
  <el-table
    :data="visible"
    row-key="id"
    class="task-table"
    empty-text="暂无任务记录"
    @row-dblclick="(row: Task) => (drawerTask = row.id)"
  >
    <el-table-column label="任务内容" min-width="220"
      ><template #default="{ row }"
        ><button class="text-link task-title" @click="drawerTask = row.id">
          {{ row.title }}
        </button>
        <div class="muted small task-subtitle">
          {{ kindLabels[row.kind]
          }}<template v-if="row.payload.account_name">
            · {{ platformNames[row.payload.platform] }} /
            {{ row.payload.account_name }}</template
          >
        </div></template
      ></el-table-column
    >
    <el-table-column label="状态" width="132"
      ><template #default="{ row }"
        ><span class="status-pill" :class="row.status"
          ><i></i>{{ statusLabels[row.status] }}</span
        ></template
      ></el-table-column
    >
    <el-table-column v-if="!compact" label="当前进度" min-width="180"
      ><template #default="{ row }"
        ><div class="small ellipsis">{{ row.phase }}</div>
        <el-progress
          v-if="row.status === 'running' && row.progress !== null"
          :percentage="Math.min(100, Math.max(0, row.progress))"
          :stroke-width="4"
          :show-text="false" /></template
    ></el-table-column>
    <el-table-column label="创建时间" width="136"
      ><template #default="{ row }"
        ><span class="muted small">{{ date(row.created_at) }}</span></template
      ></el-table-column
    >
    <el-table-column label="操作" :width="compact ? 72 : 176" fixed="right"
      ><template #default="{ row }"
        ><div class="row-actions">
          <el-button link type="primary" @click="drawerTask = row.id"
            >详情</el-button
          ><el-button
            v-if="!compact && retryable(row)"
            link
            type="primary"
            @click="retry(row)"
            >重试</el-button
          ><el-button
            v-if="!compact && row.status === 'queued'"
            link
            @click="cancel(row)"
            >取消</el-button
          ><el-button
            v-if="!compact && !isActive(row)"
            link
            type="danger"
            @click="remove(row)"
            >删除</el-button
          >
        </div></template
      ></el-table-column
    >
  </el-table>
</template>
