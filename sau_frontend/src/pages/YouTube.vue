<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  ArrowLeft,
  ArrowRight,
  Refresh,
  Search,
  VideoPlay,
  Download,
  Promotion,
  Monitor,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { api, post, type BrowserState, type BrowserAction } from "../api";
import { act, drawerTask, platformNames, refresh, state } from "../state";

const browser = ref<BrowserState | null>(null);
const address = ref("");
const starting = ref(false),
  submitting = ref(false),
  dialog = ref(false);
const problem = ref("");
const surface = ref<HTMLElement | null>(null);
const remoteInput = ref<HTMLTextAreaElement | null>(null);
const image = ref("");
const selected = ref({ url: "", title: "" });
const title = ref(""),
  description = ref(""),
  tags = ref("");
const accountIds = ref<number[]>([]),
  subtitles = ref(true);
const requestKey = ref(crypto.randomUUID());
const validAccounts = computed(() =>
  state.accounts.filter((a) => a.status === 1),
);
const related = computed(() =>
  state.tasks.filter(
    (t) => t.kind === "download" && Array.isArray(t.payload.publish_jobs),
  ),
);
let stopped = false;
let timer: ReturnType<typeof setTimeout> | undefined;
let pending = 0;
let actions = Promise.resolve();

function apply(value: BrowserState) {
  browser.value = value;
  if (value.image) image.value = value.image;
  problem.value = value.message;
}
async function poll() {
  try {
    if (!document.hidden && !pending && !starting.value)
      apply(await api<BrowserState>("/youtube/browser"));
  } catch (error) {
    problem.value =
      error instanceof Error ? error.message : "浏览连接中断，请重试";
  } finally {
    if (!stopped) timer = setTimeout(poll, 1000);
  }
}
onMounted(poll);
onUnmounted(() => {
  stopped = true;
  clearTimeout(timer);
});

async function start() {
  starting.value = true;
  await act(async () => {
    apply(await post<BrowserState>("/youtube/browser/start"));
  });
  starting.value = false;
}
function command(action: BrowserAction) {
  pending++;
  actions = actions
    .then(async () => {
      if (stopped) return;
      try {
        apply(await post<BrowserState>("/youtube/browser/action", action));
      } catch (error) {
        problem.value = error instanceof Error ? error.message : "页面操作失败";
      }
    })
    .finally(() => {
      pending--;
    });
}
function navigate() {
  if (address.value.trim()) command({ kind: "navigate", text: address.value });
}
function point(event: MouseEvent) {
  const bounds = surface.value!.getBoundingClientRect();
  return {
    x: Math.max(
      0,
      Math.min(1280, ((event.clientX - bounds.left) * 1280) / bounds.width),
    ),
    y: Math.max(
      0,
      Math.min(800, ((event.clientY - bounds.top) * 800) / bounds.height),
    ),
  };
}
function click(event: MouseEvent) {
  remoteInput.value?.focus({ preventScroll: true });
  command({
    kind: "click",
    ...point(event),
    clicks: event.detail >= 2 ? 2 : 1,
  });
}
function wheel(event: WheelEvent) {
  command({
    kind: "scroll",
    ...point(event),
    dx: Math.max(-5000, Math.min(5000, event.deltaX)),
    dy: Math.max(-5000, Math.min(5000, event.deltaY)),
  });
}
function key(event: KeyboardEvent) {
  if (
    event.isComposing ||
    ["Shift", "Control", "Alt", "Meta"].includes(event.key)
  )
    return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v")
    return;
  event.preventDefault();
  if (
    event.key.length === 1 &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.altKey
  )
    command({ kind: "text", text: event.key });
  else {
    const modifiers = [
      event.ctrlKey ? "Control" : "",
      event.metaKey ? "Meta" : "",
      event.altKey ? "Alt" : "",
      event.shiftKey ? "Shift" : "",
    ].filter(Boolean);
    command({ kind: "key", text: [...modifiers, event.key].join("+") });
  }
}
function paste(event: ClipboardEvent) {
  const text = event.clipboardData?.getData("text/plain");
  if (text) command({ kind: "text", text: text.slice(0, 4000) });
}
function composed(event: CompositionEvent) {
  if (event.data) command({ kind: "text", text: event.data });
  if (remoteInput.value) remoteInput.value.value = "";
}
function compose() {
  if (!browser.value?.video_url) return;
  selected.value = { url: browser.value.video_url, title: browser.value.title };
  title.value = selected.value.title.slice(0, 200);
  description.value = "";
  tags.value = "";
  accountIds.value = accountIds.value.filter((id) =>
    validAccounts.value.some((a) => a.id === id),
  );
  requestKey.value = crypto.randomUUID();
  dialog.value = true;
}
async function download(alsoPublish: boolean) {
  if (submitting.value) return;
  const videoUrl = alsoPublish ? selected.value.url : browser.value?.video_url;
  if (!videoUrl) return;
  if (alsoPublish && (!accountIds.value.length || !title.value.trim())) {
    ElMessage.warning("请填写标题并选择至少一个已登录账号");
    return;
  }
  submitting.value = true;
  await act(async () => {
    const result = await post<{ id: string }>("/youtube/downloads", {
      url: videoUrl,
      subtitles: subtitles.value,
      request_key: requestKey.value,
      title: alsoPublish ? title.value : "",
      description: alsoPublish ? description.value : "",
      tags: alsoPublish
        ? tags.value
            .split(/[,，\n]/)
            .map((t) => t.trim())
            .filter(Boolean)
        : [],
      account_ids: alsoPublish ? accountIds.value : [],
    });
    dialog.value = false;
    requestKey.value = crypto.randomUUID();
    ElMessage.success(
      alsoPublish
        ? "下载任务已创建，成功后自动分发到所选账号"
        : "下载任务已创建",
    );
    drawerTask.value = result.id;
    await refresh();
  });
  submitting.value = false;
}
async function closeBrowser() {
  starting.value = true;
  await act(async () => {
    await api("/youtube/browser", { method: "DELETE" });
    browser.value = null;
    image.value = "";
  });
  starting.value = false;
}
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">发现与分发</div>
      <h1>YouTube 浏览</h1>
      <p>浏览完整站点，选中当前视频，一次下载，分发到多个平台。</p>
    </div>
    <router-link to="/downloads">查看下载任务 →</router-link>
  </div>
  <section class="panel youtube-workspace">
    <div class="youtube-toolbar">
      <el-button-group
        ><el-button
          :icon="ArrowLeft"
          aria-label="后退"
          :disabled="!browser?.active"
          @click="command({ kind: 'back' })" /><el-button
          :icon="ArrowRight"
          aria-label="前进"
          :disabled="!browser?.active"
          @click="command({ kind: 'forward' })" /><el-button
          :icon="Refresh"
          aria-label="刷新网页"
          :disabled="!browser?.active"
          @click="command({ kind: 'reload' })"
      /></el-button-group>
      <el-input
        v-model="address"
        aria-label="YouTube 地址或关键词"
        placeholder="搜索 YouTube 或粘贴视频、频道链接"
        :disabled="!browser?.active"
        clearable
        @keyup.enter="navigate"
        ><template #prefix
          ><el-icon><Search /></el-icon></template
      ></el-input>
      <el-button :disabled="!browser?.active" @click="navigate">前往</el-button>
      <el-button
        :icon="Monitor"
        :disabled="!browser?.active"
        @click="command({ kind: 'show' })"
        >独立窗口播放</el-button
      >
    </div>
    <div v-if="browser?.active" class="youtube-location">
      <span class="youtube-dot"></span><span>{{ browser.url }}</span
      ><el-button link @click="closeBrowser">关闭浏览</el-button>
    </div>
    <el-alert
      v-if="problem"
      :title="problem"
      type="warning"
      show-icon
      :closable="false"
    />
    <div v-if="!browser?.active" class="youtube-welcome">
      <span class="youtube-logo"
        ><el-icon><VideoPlay /></el-icon
      ></span>
      <h2>在这里打开完整 YouTube</h2>
      <p>搜索、浏览频道、点击视频，登录状态保存在本机。</p>
      <el-button
        type="primary"
        :loading="starting"
        :icon="VideoPlay"
        @click="start"
        >启动 YouTube 浏览器</el-button
      >
      <router-link to="/settings" class="small"
        >网络无法连接？检查下载代理设置</router-link
      >
    </div>
    <div
      v-else
      ref="surface"
      class="youtube-surface"
      role="application"
      aria-label="YouTube 完整网页，可点击、滚动、键盘输入或粘贴"
      @click="click"
      @wheel.prevent="wheel"
    >
      <img
        v-if="image"
        :src="image"
        alt="YouTube 浏览器网页"
        draggable="false"
      />
      <div v-else class="youtube-loading">正在加载网页…</div>
      <textarea
        ref="remoteInput"
        class="youtube-input"
        aria-label="YouTube 网页键盘输入"
        autocomplete="off"
        @keydown="key"
        @paste.prevent="paste"
        @compositionend="composed"
        @click.stop
      ></textarea>
    </div>
    <div class="youtube-current">
      <div>
        <strong>{{
          browser?.video_url
            ? browser.title || "当前视频"
            : "打开一条视频，即可下载或发布"
        }}</strong>
        <p class="muted small">
          {{
            browser?.video_url ||
            "可以在网页内搜索和点击，也可以在上方输入链接。"
          }}
        </p>
      </div>
      <el-checkbox v-model="subtitles">下载可用字幕</el-checkbox>
      <el-button
        :icon="Download"
        :disabled="!browser?.video_url"
        :loading="submitting"
        @click="download(false)"
        >下载当前视频</el-button
      >
      <el-button
        type="primary"
        :icon="Promotion"
        :disabled="!browser?.video_url"
        @click="compose"
        >下载并发布</el-button
      >
    </div>
  </section>
  <p class="muted small youtube-footnote">
    网页交互保留在系统内；需要视频声音时，点击“独立窗口播放”。下载使用设置中的代理与
    YouTube 登录凭据。
  </p>
  <section v-if="related.length" class="panel youtube-recent">
    <div class="section-heading">
      <h2>最近下载与分发</h2>
      <router-link to="/publish">查看发布进度 →</router-link>
    </div>
    <button
      v-for="task in related.slice(0, 5)"
      :key="task.id"
      class="youtube-task"
      @click="drawerTask = task.id"
    >
      <span class="ellipsis">{{ task.payload.url }}</span
      ><span>{{ task.phase }} →</span>
    </button>
  </section>
  <el-dialog
    v-model="dialog"
    title="下载并发布到多个平台"
    width="660px"
    :close-on-click-modal="false"
  >
    <div class="info-box">
      {{ selected.title }}<br /><span class="small">{{ selected.url }}</span>
    </div>
    <el-form label-position="top" class="youtube-publish-form">
      <el-form-item label="发布标题" required
        ><el-input v-model="title" maxlength="200" show-word-limit
      /></el-form-item>
      <el-form-item label="正文描述"
        ><el-input
          v-model="description"
          type="textarea"
          :rows="3"
          maxlength="5000"
          placeholder="可修改为适合目标平台的文案；视频号不单独提交正文"
      /></el-form-item>
      <el-form-item label="话题"
        ><el-input v-model="tags" placeholder="多个话题用逗号分隔"
      /></el-form-item>
      <el-form-item label="发布账号" required
        ><el-checkbox-group v-model="accountIds" class="youtube-accounts"
          ><el-checkbox
            v-for="account in state.accounts"
            :key="account.id"
            :value="account.id"
            :disabled="account.status !== 1"
            >{{ platformNames[account.type] }} · {{ account.userName
            }}{{ account.status !== 1 ? "（需登录）" : "" }}</el-checkbox
          ></el-checkbox-group
        >
        <p v-if="!state.accounts.length" class="muted">
          请先在账号管理中添加并登录账号。
        </p></el-form-item
      >
    </el-form>
    <div class="info-box">
      将下载 1 条视频，成功后立即创建
      {{
        accountIds.length
      }}
      条发布任务。下载失败不会发布；离开页面后任务继续执行。
    </div>
    <template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button
        type="primary"
        :disabled="!accountIds.length || !title.trim()"
        :loading="submitting"
        @click="download(true)"
        >确认下载并发布</el-button
      ></template
    >
  </el-dialog>
</template>

<style scoped>
.youtube-workspace {
  overflow: hidden;
}
.youtube-toolbar {
  display: flex;
  gap: 10px;
  padding: 14px;
  border-bottom: 1px solid #edf0f5;
}
.youtube-toolbar .el-input {
  flex: 1;
  min-width: 180px;
}
.youtube-location {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  height: 38px;
  color: #7d8799;
  font-size: 12px;
}
.youtube-location > span:nth-child(2) {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.youtube-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #e34c4c;
}
.youtube-welcome {
  min-height: 470px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  background: linear-gradient(145deg, #fff, #f7f9fd);
}
.youtube-welcome h2 {
  font-size: 22px;
}
.youtube-welcome p {
  color: #8792a5;
}
.youtube-logo {
  display: grid;
  place-items: center;
  width: 76px;
  height: 58px;
  background: #ff0033;
  border-radius: 18px;
  color: white;
  font-size: 42px;
}
.youtube-surface {
  position: relative;
  width: 100%;
  aspect-ratio: 8/5;
  background: #fff;
  overflow: hidden;
  outline-offset: -3px;
}
.youtube-surface img {
  display: block;
  width: 100%;
  height: 100%;
  user-select: none;
}
.youtube-loading {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8792a5;
}
.youtube-input {
  position: absolute;
  left: 2px;
  top: 2px;
  width: 1px;
  height: 1px;
  padding: 0;
  border: 0;
  opacity: 0;
  resize: none;
}
.youtube-current {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px;
  border-top: 1px solid #edf0f5;
}
.youtube-current > div {
  flex: 1;
  min-width: 0;
}
.youtube-current strong {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.youtube-current p {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 4px;
}
.youtube-footnote {
  margin: 12px 0 20px;
}
.youtube-publish-form {
  margin-top: 20px;
}
.youtube-accounts {
  display: flex;
  flex-direction: column;
}
.youtube-recent {
  margin-top: 18px;
}
.youtube-task {
  border: 0;
  border-top: 1px solid #edf0f5;
  background: transparent;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 16px 20px;
  text-align: left;
  color: #55647a;
}
.youtube-task:hover {
  background: #f8faff;
}
@media (max-width: 1100px) {
  .youtube-toolbar {
    flex-wrap: wrap;
  }
  .youtube-toolbar .el-input {
    order: 2;
    flex-basis: 70%;
  }
  .youtube-current {
    flex-wrap: wrap;
  }
  .youtube-current > div {
    flex-basis: 100%;
  }
}
</style>
