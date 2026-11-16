<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import { BrowserMedia } from "../browser-media";
import {
  ArrowLeft,
  ArrowRight,
  Refresh,
  Search,
  VideoPlay,
  Download,
  Promotion,
  Monitor,
  FullScreen,
  Close,
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
const video = ref<HTMLVideoElement | null>(null);
const workspace = ref<HTMLElement | null>(null);
const immersive = ref(false);
const mediaStatus = ref("正在连接音视频…");
const muted = ref(false);
const connecting = ref(false);
let media: BrowserMedia | null = null;
let mediaRevision = -1;
let observer: ResizeObserver | undefined;
let resizeTimer: ReturnType<typeof setTimeout> | undefined;

async function connectMedia() {
  if (connecting.value || !browser.value?.active) return;
  connecting.value = true;
  media?.close();
  media = new BrowserMedia();
  const current = media;
  mediaRevision = browser.value.revision;
  mediaStatus.value = "正在连接音视频…";
  await nextTick();
  try {
    await resize();
    if (stopped || !video.value) return;
    await current.connect(video.value, (value) => {
      mediaStatus.value = value;
      muted.value = video.value?.muted ?? false;
    });
    if (!video.value.muted) command({ kind: "unmute" });
  } catch (error) {
    current.close();
    mediaStatus.value =
      error instanceof Error ? error.message : "播放连接失败，请重连";
  } finally {
    connecting.value = false;
  }
}
async function sound() {
  if (!video.value) return;
  video.value.muted = !video.value.muted;
  muted.value = video.value.muted;
  try {
    await video.value.play();
  } catch {
    mediaStatus.value = "请点击开启声音";
  }
  if (!muted.value) command({ kind: "unmute" });
}
async function resize() {
  if (!surface.value || !browser.value?.active) return;
  const bounds = surface.value.getBoundingClientRect();
  const width = Math.max(640, Math.min(2560, Math.round(bounds.width)));
  const height = Math.max(360, Math.min(1440, Math.round(bounds.height)));
  if (width !== browser.value.width || height !== browser.value.height)
    apply(
      await post<BrowserState>("/youtube/browser/action", {
        kind: "resize",
        width,
        height,
      }),
    );
}
async function fullscreen() {
  await act(async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await workspace.value?.requestFullscreen();
  });
}
function escape(event: KeyboardEvent) {
  if (event.key === "Escape") immersive.value = false;
}
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
  if (!value.active) releaseMedia();
  problem.value = value.message;
}
async function poll() {
  try {
    if (!document.hidden && !pending && !starting.value) {
      apply(await api<BrowserState>("/youtube/browser"));
      if (
        browser.value?.active &&
        (!media || mediaRevision !== browser.value.revision)
      )
        void connectMedia();
    }
  } catch (error) {
    problem.value =
      error instanceof Error ? error.message : "浏览连接中断，请重试";
  } finally {
    if (!stopped) timer = setTimeout(poll, 2500);
  }
}
onMounted(() => {
  void poll();
  document.addEventListener("keydown", escape);
  window.addEventListener("pagehide", releaseMedia);
  observer = new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => void resize().catch(() => {}), 200);
  });
  if (workspace.value) observer.observe(workspace.value);
});
function releaseMedia() {
  media?.close();
  media = null;
}
onUnmounted(() => {
  stopped = true;
  clearTimeout(timer);
  clearTimeout(resizeTimer);
  observer?.disconnect();
  releaseMedia();
  document.removeEventListener("keydown", escape);
  window.removeEventListener("pagehide", releaseMedia);
});

async function start() {
  starting.value = true;
  await act(async () => {
    apply(await post<BrowserState>("/youtube/browser/start"));
    void connectMedia();
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
      Math.min(
        browser.value!.width,
        ((event.clientX - bounds.left) * browser.value!.width) / bounds.width,
      ),
    ),
    y: Math.max(
      0,
      Math.min(
        browser.value!.height,
        ((event.clientY - bounds.top) * browser.value!.height) / bounds.height,
      ),
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
  if (event.key === "Escape") {
    immersive.value = false;
    return;
  }
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
async function compose() {
  if (!browser.value?.video_url) return;
  if (document.fullscreenElement) await document.exitFullscreen();
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
  if (document.fullscreenElement) await document.exitFullscreen();
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
  releaseMedia();
  starting.value = true;
  await act(async () => {
    await api("/youtube/browser", { method: "DELETE" });
    browser.value = null;
  });
  starting.value = false;
}
</script>

<template>
  <section
    ref="workspace"
    class="panel youtube-workspace"
    :class="{ immersive }"
  >
    <h1 class="sr-only">YouTube 浏览</h1>
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
        title="独立窗口播放"
        aria-label="独立窗口播放"
        @click="
          releaseMedia();
          command({ kind: 'show' });
        "
      />
      <el-button :disabled="!browser?.active" @click="sound">{{
        muted ? "开启声音" : "静音"
      }}</el-button>
      <el-button @click="immersive = !immersive">{{
        immersive ? "退出沉浸" : "沉浸"
      }}</el-button>
      <el-button
        :icon="FullScreen"
        aria-label="全屏"
        title="全屏 / Esc 退出"
        @click="fullscreen"
      />
      <el-button
        :icon="Close"
        aria-label="关闭浏览"
        title="关闭浏览"
        :disabled="!browser?.active"
        @click="closeBrowser"
      />
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
      <p>启动时自动加载设置中已保存的 YouTube Cookie，登录状态保存在本机。</p>
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
      <video
        ref="video"
        class="youtube-video"
        aria-label="YouTube 浏览器网页"
        autoplay
        playsinline
        @volumechange="muted = video?.muted ?? false"
      />
      <div
        v-if="mediaStatus !== '实时播放' && mediaStatus !== '点击开启声音'"
        class="youtube-stream-status"
        @click.stop
      >
        <span>{{ mediaStatus }}</span><el-button
          size="small"
          :loading="connecting"
          @click="connectMedia"
          >重连播放</el-button
        >
      </div>
      <button v-if="muted" class="youtube-audio-prompt" @click.stop="sound">
        开启声音
      </button>
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
  <details v-if="related.length" class="panel youtube-recent">
    <summary>最近下载与分发（{{ related.length }}）</summary>
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
      <span class="ellipsis">{{ task.payload.url }}</span><span
        >{{ task.phase }} →</span
      >
    </button>
  </details>
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
      {{ accountIds.length }}
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
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}
.youtube-workspace {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 24px);
  min-height: 480px;
  overflow: hidden;
}
.youtube-workspace.immersive {
  position: fixed;
  inset: 0;
  z-index: 2000;
  height: 100dvh;
  border-radius: 0;
  border: 0;
}
.youtube-workspace:fullscreen {
  height: 100dvh;
  width: 100vw;
  background: #fff;
}
.youtube-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border-bottom: 1px solid #edf0f5;
  flex-shrink: 0;
}
.youtube-toolbar .el-input {
  flex: 1;
  min-width: 100px;
}
.youtube-toolbar .el-button + .el-button {
  margin-left: 0;
}
.youtube-toolbar > .el-button {
  padding: 8px;
}
.youtube-toolbar .el-button-group {
  display: flex;
  flex-shrink: 0;
}
.youtube-toolbar .el-button-group .el-button {
  padding: 8px;
}
.youtube-welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  background: linear-gradient(145deg, #fff, #f7f9fd);
  padding: 20px;
  text-align: center;
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
  flex: 1;
  min-height: 0;
  background: #111;
  overflow: hidden;
  outline-offset: -3px;
}
.youtube-video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: fill;
  user-select: none;
}
.youtube-stream-status {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 12px;
  align-items: center;
  background: #fffef0ee;
  color: #544b30;
  padding: 8px 12px;
  border-radius: 8px;
  max-width: 90%;
  font-size: 12px;
}
.youtube-audio-prompt {
  position: absolute;
  bottom: 20px;
  right: 20px;
  border: 0;
  border-radius: 8px;
  padding: 10px 16px;
  background: #fff;
  color: #354f77;
  cursor: pointer;
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
  padding: 8px 12px;
  border-top: 1px solid #edf0f5;
  flex-shrink: 0;
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
  font-size: 13px;
}
.youtube-publish-form {
  margin-top: 20px;
}
.youtube-accounts {
  display: flex;
  flex-direction: column;
}
.youtube-recent {
  margin-top: 12px;
}
.youtube-recent summary {
  padding: 12px 20px;
  cursor: pointer;
  font-size: 13px;
  color: #55647a;
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
@media (max-width: 800px) {
  .youtube-toolbar {
    flex-wrap: wrap;
  }
  .youtube-toolbar .el-input {
    min-width: 150px;
  }
  .youtube-current {
    flex-wrap: wrap;
    gap: 6px;
  }
  .youtube-current > div {
    flex-basis: 100%;
  }
}
</style>
