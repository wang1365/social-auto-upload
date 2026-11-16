import { reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  api,
  connection,
  post,
  type Account,
  type Material,
  type MaterialPage,
  type Task,
} from "./api";

export const state = reactive({
  accounts: [] as Account[],
  tasks: [] as Task[],
  materials: [] as Material[],
  materialTotal: 0,
  loaded: false,
});
export const drawerTask = ref<string | null>(null);
export const previewMaterial = ref<Material | null>(null);
export const platformNames: Record<number, string> = {
  1: "小红书",
  2: "视频号",
  3: "抖音",
  4: "快手",
};
export const platformLetters: Record<number, string> = {
  1: "红",
  2: "视",
  3: "抖",
  4: "快",
};
export const statusLabels: Record<string, string> = {
  queued: "等待执行",
  running: "进行中",
  succeeded: "已完成",
  failed: "失败",
  interrupted: "已中断",
  unknown: "结果待核实",
  cancelled: "已取消",
};
export const kindLabels: Record<string, string> = {
  publish: "发布",
  download: "下载",
  processing: "视频处理",
  login: "账号登录",
  check: "状态检查",
  preview: "视频预览",
};
export const isActive = (task: Task) =>
  ["queued", "running"].includes(task.status);
export const retryable = (task: Task) =>
  ["failed", "interrupted"].includes(task.status) &&
  !task.result.attempted &&
  !task.result.retry_status;
export const date = (value?: string | null) =>
  value
    ? new Date(
        value.includes("T") ? value : value.replace(" ", "T") + "Z",
      ).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";
export const duration = (value?: number | null) =>
  value
    ? `${Math.floor(value / 60)}:${Math.floor(value % 60)
        .toString()
        .padStart(2, "0")}`
    : "—";
export const titleOf = (material: Material) =>
  material.video_title_zh ||
  material.video_title ||
  material.filename.replace(/\.[^.]+$/, "");
export const sourceOf = (material: Material) =>
  material.material_type === "processed"
    ? "处理后素材"
    : material.source_type === "youtube"
      ? "YouTube"
      : "本地导入";

export async function act<T>(action: () => Promise<T>): Promise<T | undefined> {
  try {
    return await action();
  } catch (error) {
    ElMessage.error(
      error instanceof Error ? error.message : "操作失败，请重试",
    );
  }
}

export async function confirm(message: string, title = "请确认") {
  try {
    await ElMessageBox.confirm(message, title, {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    return true;
  } catch {
    return false;
  }
}

export async function refresh() {
  const [accounts, tasks, materials] = await Promise.all([
    api<Account[]>("/accounts"),
    api<Task[]>("/tasks?limit=500"),
    api<MaterialPage>("/materials?page_size=100"),
  ]);
  Object.assign(state, {
    accounts,
    tasks,
    materials: materials.items,
    materialTotal: materials.total,
    loaded: true,
  });
}

export async function retry(task: Task) {
  await act(async () => {
    const result = await post<{ id: string }>(`/tasks/${task.id}/retry`);
    drawerTask.value = result.id;
    await refresh();
  });
}

export const stoppingTasks = reactive(new Set<string>());
export async function cancelTask(task: Task) {
  if (stoppingTasks.has(task.id)) return;
  if (
    task.status === "running" &&
    !(await confirm(
      task.kind === "publish"
        ? "终止当前发布任务并停止上传？如果已提交到平台，仍需到平台核实结果。素材会保留。"
        : "终止当前任务？已保存的素材会保留。",
      "终止任务",
    ))
  )
    return;
  stoppingTasks.add(task.id);
  try {
    await act(async () => {
      await post(`/tasks/${task.id}/cancel`);
      await refresh();
    });
  } finally {
    stoppingTasks.delete(task.id);
  }
}

export async function accountLogin(account: Account, headed = false) {
  await act(async () => {
    const result = await post<{ id: string }>(`/accounts/${account.id}/login`, {
      headed,
    });
    drawerTask.value = result.id;
    await refresh();
  });
}

export function connectLive() {
  let stream: EventSource | null = null;
  let cursor = Number(sessionStorage.getItem("sau-event-cursor") || 0);
  let scheduled: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = setTimeout(() => {
      scheduled = null;
      refresh().catch(() => {});
    }, 800);
  };
  const open = () => {
    if (stopped) return;
    stream?.close();
    stream = new EventSource(`/api/v2/events?after=${cursor}`);
    stream.onopen = () => {
      connection.streaming = true;
      schedule();
    };
    stream.onerror = () => {
      connection.streaming = false;
    };
    stream.onmessage = (event) => {
      const value = JSON.parse(event.data);
      cursor = Number(event.lastEventId) || cursor;
      sessionStorage.setItem("sau-event-cursor", String(cursor));
      if (value.event !== "log") schedule();
    };
  };
  refresh()
    .then(open)
    .catch(() => {});
  const poll = setInterval(() => {
    if (!connection.streaming || !state.loaded) {
      refresh()
        .then(() => {
          if (!stream || stream.readyState === EventSource.CLOSED) open();
        })
        .catch(() => {});
    }
  }, 5000);
  return () => {
    stopped = true;
    stream?.close();
    clearInterval(poll);
    if (scheduled) clearTimeout(scheduled);
  };
}
