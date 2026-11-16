<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  Plus,
  VideoPlay,
  Promotion,
  ArrowRight,
  Delete,
  Select,
  Edit,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import {
  api,
  media,
  post,
  type Batch,
  type Material,
  type PublishItem,
} from "../api";
import {
  act,
  confirm,
  platformLetters,
  platformNames,
  previewMaterial,
  refresh,
  state,
  titleOf,
} from "../state";
import { emptyDraft, fillItems, restoreDraft } from "../draft";
import MaterialBrowser from "../components/MaterialBrowser.vue";
import TaskTable from "../components/TaskTable.vue";

const draft = ref(restoreDraft(localStorage.getItem("sau-publish-draft-v2")));
const materials = ref<Material[]>([]);
const picker = ref(false);
const picked = ref<Material[]>([]);
const current = ref<number | null>(null);
const activeTab = ref("compose");
const platform = ref(0);
const busy = ref(false);
const initializing = ref(true);
const bulkDialog = ref(false);
const bulkTitle = ref(""),
  bulkDescription = ref(""),
  bulkTags = ref("");
const fillTitle = ref(false),
  fillDescription = ref(true),
  fillTags = ref(true);
const previewFailed = ref(false);
const currentMaterial = computed(() =>
  materials.value.find((m) => m.id === current.value),
);
const currentItem = computed(() =>
  draft.value.items.find((m) => m.material_id === current.value),
);
const accounts = computed(() =>
  state.accounts.filter((a) => !platform.value || a.type === platform.value),
);
const selectedAccounts = computed(() =>
  state.accounts.filter((a) => draft.value.account_ids.includes(a.id)),
);
const publishTasks = computed(() =>
  state.tasks.filter((t) => t.kind === "publish"),
);
const expected = computed(
  () => draft.value.items.length * selectedAccounts.value.length,
);
const canSubmit = computed(
  () =>
    !initializing.value &&
    expected.value > 0 &&
    draft.value.items.every((i) => i.title.trim()) &&
    selectedAccounts.value.every((a) => a.status === 1),
);
const onlyTencent = computed(
  () =>
    selectedAccounts.value.length > 0 &&
    selectedAccounts.value.every((a) => a.type === 2),
);
const includesTencent = computed(() =>
  selectedAccounts.value.some((a) => a.type === 2),
);
const templateOptions = ref<Record<string, string[]>>({});
const selectionTemplate = ref("");
let previousContent = JSON.stringify([
  draft.value.items,
  draft.value.account_ids,
]);

watch(
  draft,
  (value) => {
    const content = JSON.stringify([value.items, value.account_ids]);
    if (content !== previousContent) {
      previousContent = content;
      value.request_key = crypto.randomUUID();
    }
    if (!initializing.value) {
      localStorage.setItem("sau-publish-draft-v2", JSON.stringify(value));
    }
  },
  { deep: true },
);
watch(current, () => (previewFailed.value = false));
onMounted(async () => {
  await act(async () => {
    if (!state.loaded) await refresh();
    draft.value.account_ids = draft.value.account_ids.filter((id) =>
      state.accounts.some((a) => a.id === id),
    );
    const fromLibrary = JSON.parse(
      sessionStorage.getItem("sau-publish-selection") || "[]",
    ) as number[];
    sessionStorage.removeItem("sau-publish-selection");
    const ids = [
      ...new Set([
        ...draft.value.items.map((i) => i.material_id),
        ...fromLibrary,
      ]),
    ];
    const results = await Promise.all(
      ids.map((id) => api<Material>(`/materials/${id}`).catch(() => null)),
    );
    materials.value = results.filter((m): m is Material => m !== null);
    const available = new Set(materials.value.map((m) => m.id));
    draft.value.items = draft.value.items.filter((i) =>
      available.has(i.material_id),
    );
    materials.value.forEach((m) => {
      if (!draft.value.items.some((i) => i.material_id === m.id))
        draft.value.items.push(makeItem(m));
    });
    if (results.some((r) => !r))
      ElMessage.warning("部分草稿素材已不存在，已从列表中移除");
    current.value = materials.value[0]?.id || null;
    const settings = await api<{
      publishTopicPresets: Record<string, string[]>;
    }>("/settings");
    templateOptions.value = settings.publishTopicPresets;
  });
  initializing.value = false;
});

function makeItem(m: Material): PublishItem {
  return {
    material_id: m.id,
    title: titleOf(m),
    description: m.video_description || "",
    tags: [],
  };
}
function openPicker() {
  picked.value = [...materials.value];
  picker.value = true;
}
function applySelection() {
  const existing = new Map(draft.value.items.map((i) => [i.material_id, i]));
  materials.value = [...picked.value];
  draft.value.items = picked.value.map(
    (m) => existing.get(m.id) || makeItem(m),
  );
  if (!materials.value.some((m) => m.id === current.value))
    current.value = materials.value[0]?.id || null;
  picker.value = false;
}
function remove(id: number) {
  materials.value = materials.value.filter((m) => m.id !== id);
  draft.value.items = draft.value.items.filter((i) => i.material_id !== id);
  if (current.value === id) current.value = materials.value[0]?.id || null;
}
function selectAccounts() {
  const valid = accounts.value.filter((a) => a.status === 1).map((a) => a.id);
  const allSelected = valid.every((id) => draft.value.account_ids.includes(id));
  draft.value.account_ids = allSelected
    ? draft.value.account_ids.filter((id) => !valid.includes(id))
    : [...new Set([...draft.value.account_ids, ...valid])];
}
function toggleAccount(id: number, valid: boolean) {
  if (!valid) return;
  draft.value.account_ids = draft.value.account_ids.includes(id)
    ? draft.value.account_ids.filter((value) => value !== id)
    : [...draft.value.account_ids, id];
}
function bulkFill() {
  const values: Partial<PublishItem> = {};
  if (fillTitle.value) values.title = bulkTitle.value;
  if (fillDescription.value) values.description = bulkDescription.value;
  if (fillTags.value)
    values.tags = bulkTags.value
      .split(/[,，\n]/)
      .map((t) => t.trim().replace(/^#/, ""))
      .filter(Boolean);
  draft.value.items = fillItems(draft.value.items, values);
  bulkDialog.value = false;
  ElMessage.success("已填充到所有选中素材，您仍可逐条修改");
}
async function submit() {
  if (!canSubmit.value || busy.value) return;
  if (
    !(await confirm(
      `即将将 ${draft.value.items.length} 条视频发布到 ${selectedAccounts.value.length} 个账号，共 ${expected.value} 条发布任务。请确认文案和账号无误。`,
      "确认立即发布",
    ))
  )
    return;
  busy.value = true;
  await act(async () => {
    const batch = await post<Batch>("/publish-batches", draft.value);
    ElMessage.success(`已提交 ${batch.tasks.length} 条发布任务`);
    draft.value = emptyDraft();
    materials.value = [];
    current.value = null;
    localStorage.removeItem("sau-publish-draft-v2");
    activeTab.value = "history";
    await refresh();
  });
  busy.value = false;
}
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">内容发布</div>
      <h1>发布中心</h1>
      <p>选好视频与账号，让每条内容有序发布。</p>
    </div>
    <span v-if="activeTab === 'compose'" class="draft-hint"
      ><el-icon><Select /></el-icon>草稿自动保存于本机</span
    >
  </div>
  <div class="page-tabs">
    <button
      :class="{ active: activeTab === 'compose' }"
      @click="activeTab = 'compose'"
    >
      新建发布</button
    ><button
      :class="{ active: activeTab === 'history' }"
      @click="activeTab = 'history'"
    >
      发布记录<span v-if="publishTasks.length" class="tab-count">{{
        publishTasks.length
      }}</span>
    </button>
  </div>
  <section v-if="activeTab === 'history'" class="panel">
    <TaskTable :tasks="publishTasks" />
  </section>
  <div v-else class="publish-layout">
    <div class="publish-editor" :inert="busy">
      <section class="panel compose-panel">
        <div class="section-heading">
          <div>
            <span class="step-number">1</span>
            <h2>选择素材</h2>
            <span class="muted small">{{
              materials.length
                ? `已选 ${materials.length} 条视频`
                : "选择需要发布的视频"
            }}</span>
          </div>
          <el-button size="small" :icon="Plus" @click="openPicker"
            >选择素材</el-button
          >
        </div>
        <div v-if="!materials.length" class="compose-empty" @click="openPicker">
          <el-icon><VideoPlay /></el-icon>
          <div>
            <strong>从素材库选择视频</strong
            ><span>支持一次选择多条视频，逐条编辑发布文案</span>
          </div>
          <el-icon><ArrowRight /></el-icon>
        </div>
        <div v-else class="selected-materials">
          <div
            v-for="(m, index) in materials"
            :key="m.id"
            class="selected-material"
            :class="{ active: current === m.id }"
            @click="current = m.id"
          >
            <span class="material-index">{{
              String(index + 1).padStart(2, "0")
            }}</span>
            <div class="video-thumb mini">
              <img
                v-if="m.has_thumbnail"
                :src="media(m.id, 'thumbnail')"
                alt=""
              /><el-icon v-else><VideoPlay /></el-icon>
            </div>
            <div class="material-name">
              <strong class="ellipsis">{{
                draft.items.find((i) => i.material_id === m.id)?.title ||
                "未填写标题"
              }}</strong><span class="muted small ellipsis">{{
                m.filename
              }}</span>
            </div>
            <button
              class="icon-button"
              aria-label="移除此素材"
              @click.stop="remove(m.id)"
            >
              <el-icon><Delete /></el-icon>
            </button>
          </div>
        </div>
      </section>
      <section class="panel compose-panel">
        <div class="section-heading">
          <div>
            <span class="step-number">2</span>
            <h2>选择账号</h2>
            <span class="muted small"
              >已选 {{ selectedAccounts.length }} 个</span
            >
          </div>
          <el-button
            v-if="accounts.some((a) => a.status === 1)"
            size="small"
            text
            type="primary"
            @click="selectAccounts"
            >全选可用账号</el-button
          >
        </div>
        <div class="platform-filters">
          <button :class="{ active: platform === 0 }" @click="platform = 0">
            全部平台</button
          ><button
            v-for="(name, id) in platformNames"
            :key="id"
            :class="{ active: platform === Number(id) }"
            @click="platform = Number(id)"
          >
            {{ name }}
          </button>
        </div>
        <el-checkbox-group
          v-if="accounts.length"
          v-model="draft.account_ids"
          class="account-options"
          ><div
            v-for="a in accounts"
            :key="a.id"
            class="account-option"
            @click="toggleAccount(a.id, a.status === 1)"
            :class="{
              chosen: draft.account_ids.includes(a.id),
              invalid: a.status !== 1,
            }"
          >
            <el-checkbox
              :value="a.id"
              :disabled="a.status !== 1"
              :aria-label="a.userName"
              @click.stop
            /><span class="platform-avatar" :class="'platform-' + a.type">{{
              platformLetters[a.type]
            }}</span
            ><span class="account-option-name"
              ><strong>{{ a.userName }}</strong
              ><small
                >{{ platformNames[a.type]
                }}<span v-if="a.status !== 1" class="danger-text">
                  · 登录已失效</span
                ></small
              ></span
            >
          </div></el-checkbox-group
        >
        <div v-else class="inline-empty">
          暂无{{ platform ? platformNames[platform] : "" }}账号，<router-link
            to="/accounts"
            >去添加账号</router-link
          >
        </div>
        <div
          v-if="selectedAccounts.some((a) => a.status !== 1)"
          class="inline-warning"
        >
          所选账号有登录失效项，请取消选择或到账号管理重新登录。
        </div>
      </section>
      <section class="panel compose-panel">
        <div class="section-heading">
          <div>
            <span class="step-number">3</span>
            <h2>编辑文案</h2>
            <span v-if="materials.length > 1" class="muted small"
              >点击上方素材切换编辑</span
            >
          </div>
          <el-button
            size="small"
            :icon="Edit"
            :disabled="!materials.length"
            @click="bulkDialog = true"
            >批量填充</el-button
          >
        </div>
        <el-form v-if="currentItem" label-position="top" class="copy-form"
          ><el-form-item label="发布标题" required
            ><el-input
              v-model="currentItem.title"
              maxlength="200"
              show-word-limit
              placeholder="为这条视频写一个标题" /></el-form-item
          ><el-form-item v-if="!onlyTencent" label="正文描述"
            ><el-input
              v-model="currentItem.description"
              type="textarea"
              :rows="3"
              maxlength="5000"
              placeholder="补充视频介绍，可不填写"
          /></el-form-item>
          <p v-if="includesTencent" class="muted small field-note">
            视频号使用标题与话题，不单独提交正文描述。
          </p>
          <el-form-item label="话题"
            ><div class="tags-row">
              <el-select
                v-model="currentItem.tags"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="输入话题后按回车，可添加多个"
                ><el-option
                  v-for="tag in currentItem.tags"
                  :key="tag"
                  :label="tag"
                  :value="tag" /></el-select
              ><el-select
                v-model="selectionTemplate"
                placeholder="使用话题模板"
                clearable
                @change="
                  (value: string) => {
                    if (value && currentItem)
                      currentItem.tags = [...templateOptions[value]];
                  }
                "
                ><el-option
                  v-for="(_, name) in templateOptions"
                  :key="name"
                  :value="name"
                  :label="name"
              /></el-select></div></el-form-item
        ></el-form>
        <div v-else class="inline-empty">
          选择素材后，在这里编辑标题、正文与话题。
        </div>
      </section>
    </div>
    <aside class="publish-preview">
      <section class="panel preview-panel">
        <div class="section-heading">
          <h2>视频预览</h2>
          <span class="muted small">{{
            materials.length
              ? `${materials.findIndex((m) => m.id === current) + 1} / ${materials.length}`
              : "未选择"
          }}</span>
        </div>
        <div class="preview-stage">
          <video
            v-if="currentMaterial"
            :key="currentMaterial.id"
            :src="media(currentMaterial.id)"
            controls
            preload="metadata"
            @error="previewFailed = true"
          />
          <div v-else class="preview-placeholder">
            <el-icon><VideoPlay /></el-icon><span>选中视频后在此预览</span>
          </div>
        </div>
        <div v-if="previewFailed" class="preview-fallback">
          <span>当前格式暂无法播放</span
          ><el-button
            size="small"
            text
            type="primary"
            @click="previewMaterial = currentMaterial || null"
            >兼容预览</el-button
          >
        </div>
        <div class="preview-copy">
          <strong>{{ currentItem?.title || "视频标题" }}</strong>
          <p>{{ currentItem?.description || "填写文案后将在这里预览" }}</p>
          <span class="tag-text">{{
            currentItem?.tags.map((t) => "#" + t).join(" ")
          }}</span>
        </div>
      </section>
      <section class="panel summary-panel">
        <h2>发布摘要</h2>
        <dl>
          <dt>发布方式</dt>
          <dd>立即发布</dd>
          <dt>视频素材</dt>
          <dd>{{ materials.length }} 条</dd>
          <dt>目标账号</dt>
          <dd>{{ selectedAccounts.length }} 个</dd>
          <dt>预计发布</dt>
          <dd>
            <strong class="primary-text">{{ expected }} 条</strong>
          </dd>
        </dl>
        <div class="summary-note">
          每条视频会分别发布到所有选中账号，结果可在发布记录中查看。
        </div>
      </section>
    </aside>
    <div class="publish-footer">
      <div>
        <strong>{{ expected }} 条发布任务</strong
        ><span class="muted small"
          >{{ materials.length }} 条视频 ·
          {{ selectedAccounts.length }} 个账号</span
        >
      </div>
      <div>
        <el-button
          text
          :disabled="!materials.length"
          @click="
            confirm('清空尚未提交的素材、文案和账号选择？', '清空草稿').then(
              (ok) => {
                if (ok) {
                  draft = emptyDraft();
                  materials = [];
                  current = null;
                }
              },
            )
          "
          >清空草稿</el-button
        ><el-button
          type="primary"
          size="large"
          :icon="Promotion"
          :disabled="!canSubmit"
          :loading="busy"
          @click="submit"
          >开始发布</el-button
        >
      </div>
    </div>
  </div>
  <el-dialog
    v-model="picker"
    title="选择视频素材"
    width="min(900px, 94vw)"
    destroy-on-close
    ><MaterialBrowser v-model="picked" compact /><template #footer
      ><span class="dialog-selection">已选 {{ picked.length }} 条</span
      ><el-button @click="picker = false">取消</el-button
      ><el-button type="primary" @click="applySelection"
        >确定选择</el-button
      ></template
    ></el-dialog
  >
  <el-dialog v-model="bulkDialog" title="批量填充文案" width="520px"
    ><p class="muted small">
      仅勾选的字段会覆盖所有选中素材，未勾选的内容保持不变。
    </p>
    <el-form label-position="top"
      ><el-form-item
        ><el-checkbox v-model="fillTitle">统一标题</el-checkbox
        ><el-input
          v-if="fillTitle"
          v-model="bulkTitle"
          placeholder="所有视频使用此标题" /></el-form-item
      ><el-form-item
        ><el-checkbox v-model="fillDescription">填充正文</el-checkbox
        ><el-input
          v-if="fillDescription"
          v-model="bulkDescription"
          type="textarea"
          :rows="3"
          placeholder="留空将清空已有正文" /></el-form-item
      ><el-form-item
        ><el-checkbox v-model="fillTags">填充话题</el-checkbox
        ><el-input
          v-if="fillTags"
          v-model="bulkTags"
          placeholder="多个话题用中文或英文逗号分隔" /></el-form-item></el-form
    ><template #footer
      ><el-button @click="bulkDialog = false">取消</el-button
      ><el-button type="primary" @click="bulkFill"
        >应用到 {{ materials.length }} 条素材</el-button
      ></template
    ></el-dialog
  >
</template>
