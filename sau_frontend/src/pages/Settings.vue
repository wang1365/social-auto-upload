<script setup lang="ts">
import { onBeforeRouteLeave } from "vue-router";
import { onMounted, ref, watch } from "vue";
import { Check, Upload, Delete } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { act, confirm } from "../state";
interface Settings {
  downloadProxy: string;
  youtubeCookieConfigured: boolean;
  youtubeCookieFileName: string;
  videoProcessing: Record<string, any>;
  defaultVideoProcessing: Record<string, any>;
  publishTopicPresets: Record<string, string[]>;
  tools: Record<string, boolean>;
}
const settings = ref<Settings>({
  downloadProxy: "",
  youtubeCookieConfigured: false,
  youtubeCookieFileName: "",
  videoProcessing: {},
  defaultVideoProcessing: {},
  publishTopicPresets: {},
  tools: {},
});
const loaded = ref(false);
const original = ref("");
const busy = ref(false);
const tab = ref("download");
const advanced = ref<string[]>([]);
const cookieInput = ref<HTMLInputElement>();
const presets = ref<{ name: string; tags: string }[]>([]);
const groups = [
  {
    key: "trimEnabled",
    label: "片头与片尾裁剪",
    hint: "从视频首尾随机裁剪指定时长",
    fields: [
      {
        key: "trimHeadMin",
        label: "片头最少",
        min: 0,
        max: 10,
        step: 0.1,
        unit: "秒",
      },
      {
        key: "trimHeadMax",
        label: "片头最多",
        min: 0,
        max: 10,
        step: 0.1,
        unit: "秒",
      },
      {
        key: "trimTailMin",
        label: "片尾最少",
        min: 0,
        max: 10,
        step: 0.1,
        unit: "秒",
      },
      {
        key: "trimTailMax",
        label: "片尾最多",
        min: 0,
        max: 10,
        step: 0.1,
        unit: "秒",
      },
    ],
  },
  {
    key: "speedEnabled",
    label: "轻微变速",
    hint: "在设定范围内调整播放速度",
    fields: [
      {
        key: "speedMin",
        label: "最慢",
        min: 0.5,
        max: 2,
        step: 0.01,
        unit: "倍",
      },
      {
        key: "speedMax",
        label: "最快",
        min: 0.5,
        max: 2,
        step: 0.01,
        unit: "倍",
      },
    ],
  },
  {
    key: "cropEnabled",
    label: "画面裁剪",
    hint: "按比例裁剪边缘画面",
    fields: [
      {
        key: "cropPercentMin",
        label: "最少",
        min: 0,
        max: 10,
        step: 0.1,
        unit: "%",
      },
      {
        key: "cropPercentMax",
        label: "最多",
        min: 0,
        max: 10,
        step: 0.1,
        unit: "%",
      },
    ],
  },
  {
    key: "pinkFilterEnabled",
    label: "粉色滤镜",
    hint: "轻微调整画面色调",
    fields: [
      {
        key: "pinkFilterStrength",
        label: "滤镜强度",
        min: 0,
        max: 1,
        step: 0.01,
        unit: "",
      },
    ],
  },
  {
    key: "frameDropEnabled",
    label: "随机抽帧",
    hint: "按设定强度抽取部分帧",
    fields: [
      {
        key: "frameDropStrength",
        label: "抽帧强度",
        min: 0,
        max: 0.2,
        step: 0.01,
        unit: "",
      },
    ],
  },
  {
    key: "edgeGuardEnabled",
    label: "边缘保护",
    hint: "保护画面边缘区域",
    fields: [
      {
        key: "edgeGuardPixels",
        label: "保护宽度",
        min: 0,
        max: 32,
        step: 1,
        unit: "像素",
      },
    ],
  },
];
function snapshot() {
  return JSON.stringify([
    settings.value.downloadProxy,
    settings.value.videoProcessing,
    presets.value,
  ]);
}
async function load() {
  const result = await api<Settings>("/settings");
  settings.value = result;
  loaded.value = true;
  presets.value = Object.entries(result.publishTopicPresets).map(
    ([name, tags]) => ({ name, tags: tags.join("，") }),
  );
  original.value = snapshot();
}
onMounted(() => act(load));
onBeforeRouteLeave(async () =>
  original.value !== snapshot()
    ? confirm("设置尚未保存，确定离开并放弃修改？", "未保存的修改")
    : true,
);
async function save() {
  if (!settings.value) return;
  const names = presets.value.map((p) => p.name.trim());
  if (names.some((n) => !n) || new Set(names).size !== names.length) {
    ElMessage.warning("模板名称不能为空或重复");
    return;
  }
  busy.value = true;
  await act(async () => {
    const body = {
      downloadProxy: settings.value!.downloadProxy,
      videoProcessing: settings.value!.videoProcessing,
      publishTopicPresets: Object.fromEntries(
        presets.value.map((p) => [
          p.name.trim(),
          p.tags
            .split(/[,，\n]/)
            .map((t) => t.trim().replace(/^#/, ""))
            .filter(Boolean),
        ]),
      ),
    };
    await api("/settings", { method: "PUT", body: JSON.stringify(body) });
    await load();
    ElMessage.success("设置已保存");
  });
  busy.value = false;
}
async function cookie(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file)
    await act(async () => {
      const form = new FormData();
      form.append("file", file);
      await api("/settings/youtube-cookie", { method: "POST", body: form });
      settings.value!.youtubeCookieConfigured = true;
      settings.value!.youtubeCookieFileName = file.name;
      ElMessage.success("登录凭据已导入");
    });
  if (cookieInput.value) cookieInput.value.value = "";
}
async function clearCookie() {
  if (await confirm("移除已保存的 YouTube 登录凭据？", "清除登录凭据"))
    await act(async () => {
      await api("/settings/youtube-cookie", { method: "DELETE" });
      settings.value!.youtubeCookieConfigured = false;
      settings.value!.youtubeCookieFileName = "";
    });
}
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">偏好设置</div>
      <h1>按您的习惯工作</h1>
      <p>调整下载、处理与常用话题，减少重复操作。</p>
    </div>
    <el-button type="primary" :icon="Check" :loading="busy" @click="save"
      >保存设置</el-button
    >
  </div>
  <div class="settings-layout">
    <nav class="settings-nav">
      <button
        v-for="item in [
          { key: 'download', label: '下载设置' },
          { key: 'processing', label: '视频处理' },
          { key: 'topics', label: '话题模板' },
        ]"
        :key="item.key"
        :class="{ active: tab === item.key }"
        @click="tab = item.key"
      >
        {{ item.label }}
      </button>
    </nav>
    <section v-if="loaded" class="panel settings-panel">
      <template v-if="tab === 'download'"
        ><div class="section-heading">
          <div>
            <h2>下载设置</h2>
            <span class="muted small">用于 YouTube 浏览、视频与字幕下载</span>
          </div>
        </div>
        <el-form label-position="top" class="settings-form"
          ><el-form-item label="YouTube 代理"
            ><el-input
              v-model="settings.downloadProxy"
              placeholder="例如：http://127.0.0.1:7890"
              clearable
            />
            <p class="field-hint">
              支持 HTTP、HTTPS 和 SOCKS5。仅用于 YouTube；抖音、小红书、快手和视频号始终直连。修改后请关闭并重新启动 YouTube 浏览器。
            </p></el-form-item
          ><el-form-item label="YouTube 登录凭据"
            ><div class="cookie-card">
              <span
                class="status-pill"
                :class="
                  settings.youtubeCookieConfigured ? 'succeeded' : 'cancelled'
                "
                ><i></i
                >{{
                  settings.youtubeCookieConfigured ? "已配置" : "未配置"
                }}</span
              >
              <p>导入 Netscape 格式的 Cookie 文件，用于需要登录的视频下载。</p>
              <el-button :icon="Upload" @click="cookieInput?.click()"
                >导入文件</el-button
              ><el-button
                v-if="settings.youtubeCookieConfigured"
                text
                type="danger"
                @click="clearCookie"
                >清除</el-button
              >
            </div></el-form-item
          ></el-form
        ><input
          ref="cookieInput"
          hidden
          type="file"
          accept=".txt"
          @change="cookie"
        />
        <div class="tools-status">
          <span>本机媒体工具</span
          ><span
            v-for="tool in ['ffmpeg', 'ffprobe']"
            :key="tool"
            :class="settings.tools[tool] ? 'success-text' : 'danger-text'"
            >{{ tool.toUpperCase() }} ·
            {{ settings.tools[tool] ? "可用" : "未安装" }}</span
          >
        </div></template
      >
      <template v-else-if="tab === 'processing'"
        ><div class="section-heading">
          <div>
            <h2>视频处理</h2>
            <span class="muted small">处理后生成新素材，保留原始视频</span>
          </div>
          <el-button
            size="small"
            text
            @click="
              confirm(
                '恢复默认视频处理参数？保存后生效。',
                '恢复默认设置',
              ).then((ok) => {
                if (ok && settings)
                  settings.videoProcessing = {
                    ...settings.defaultVideoProcessing,
                  };
              })
            "
            >恢复默认</el-button
          >
        </div>
        <div class="setting-switch">
          <div>
            <strong>下载后自动处理</strong>
            <p>下载完成后自动创建视频处理任务</p>
          </div>
          <el-switch v-model="settings.videoProcessing.autoProcess" />
        </div>
        <div class="setting-switch">
          <div>
            <strong>同时处理数量</strong>
            <p>数量越高，对电脑性能要求越高</p>
          </div>
          <el-input-number
            v-model="settings.videoProcessing.maxConcurrent"
            :min="1"
            :max="8"
            controls-position="right"
          />
        </div>
        <div class="setting-switch">
          <div>
            <strong>处理方式</strong>
            <p>显卡加速需要本机具备相应编码支持</p>
          </div>
          <el-select
            v-model="settings.videoProcessing.hardwareMode"
            style="width: 170px"
            ><el-option label="处理器（CPU）" value="cpu" /><el-option
              label="显卡加速（GPU）"
              value="gpu"
          /></el-select>
        </div>
        <el-collapse v-model="advanced" class="processing-collapse"
          ><el-collapse-item title="高级处理参数" name="advanced"
            ><div
              v-for="group in groups"
              :key="group.key"
              class="processing-group"
            >
              <div class="setting-switch">
                <div>
                  <strong>{{ group.label }}</strong>
                  <p>{{ group.hint }}</p>
                </div>
                <el-switch v-model="settings.videoProcessing[group.key]" />
              </div>
              <div
                v-if="settings.videoProcessing[group.key]"
                class="parameter-grid"
              >
                <label v-for="field in group.fields" :key="field.key"
                  ><span>{{ field.label }}</span
                  ><el-input-number
                    v-model="settings.videoProcessing[field.key]"
                    :min="field.min"
                    :max="field.max"
                    :step="field.step"
                    controls-position="right"
                  /><span>{{ field.unit }}</span></label
                >
              </div>
            </div>
            <div class="setting-switch">
              <div>
                <strong>扫光效果</strong>
                <p>为画面添加轻微扫光</p>
              </div>
              <el-switch
                v-model="settings.videoProcessing.lightSweep"
              /></div></el-collapse-item></el-collapse
      ></template>
      <template v-else
        ><div class="section-heading">
          <div>
            <h2>话题模板</h2>
            <span class="muted small">在发布中心快速填入一组常用话题</span>
          </div>
          <el-button size="small" @click="presets.push({ name: '', tags: '' })"
            >添加模板</el-button
          >
        </div>
        <div v-for="(preset, index) in presets" :key="index" class="preset-row">
          <el-input
            v-model="preset.name"
            placeholder="模板名称"
            aria-label="模板名称"
          /><el-input
            v-model="preset.tags"
            placeholder="话题之间用逗号分隔"
            aria-label="模板话题"
          /><el-button
            :icon="Delete"
            text
            type="danger"
            aria-label="删除模板"
            @click="presets.splice(index, 1)"
          />
        </div>
        <el-empty
          v-if="!presets.length"
          description="还没有话题模板"
          :image-size="60"
      /></template>
    </section>
    <el-skeleton v-else :rows="6" animated class="panel" />
  </div>
</template>
