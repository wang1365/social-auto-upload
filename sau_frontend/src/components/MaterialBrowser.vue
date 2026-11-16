<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { Search, VideoPlay } from "@element-plus/icons-vue";
import { api, media, type Material, type MaterialPage } from "../api";
import {
  act,
  date,
  duration,
  previewMaterial,
  sourceOf,
  state,
  titleOf,
} from "../state";
const selected = defineModel<Material[]>({ default: () => [] });
defineProps<{ compact?: boolean }>();
const items = ref<Material[]>([]);
const total = ref(0);
const page = ref(1);
const query = ref("");
const source = ref("");
const loading = ref(false);
const table = ref();
let generation = 0;
let debounce: ReturnType<typeof setTimeout> | null = null;
async function load() {
  const version = ++generation;
  loading.value = true;
  await act(async () => {
    const params = new URLSearchParams({
      q: query.value,
      source: source.value,
      page: String(page.value),
      page_size: "20",
    });
    const result = await api<MaterialPage>("/materials?" + params);
    if (generation !== version) return;
    items.value = result.items;
    total.value = result.total;
  });
  if (generation === version) loading.value = false;
}
function select(rows: Material[]) {
  const current = new Set(items.value.map((m) => m.id));
  const chosen = new Map(
    selected.value.filter((m) => !current.has(m.id)).map((m) => [m.id, m]),
  );
  rows.forEach((m) => chosen.set(m.id, m));
  selected.value = [...chosen.values()];
}
watch([query, source], () => {
  page.value = 1;
  if (debounce) clearTimeout(debounce);
  debounce = setTimeout(load, 250);
});
watch(page, load);
watch(() => state.materials, load);
watch(
  [items, selected],
  async () => {
    await nextTick();
    table.value?.clearSelection();
    items.value.forEach((m) => {
      if (selected.value.some((s) => s.id === m.id))
        table.value?.toggleRowSelection(m, true);
    });
  },
  { deep: false },
);
onMounted(load);
defineExpose({ load });
</script>

<template>
  <div class="material-browser">
    <div class="filter-bar">
      <el-input
        v-model="query"
        :prefix-icon="Search"
        clearable
        placeholder="搜索素材名称或标题"
        class="search-field"
        aria-label="搜索素材"
      /><el-select
        v-model="source"
        placeholder="全部来源"
        style="width: 150px"
        aria-label="筛选来源"
        ><el-option label="全部来源" value="" /><el-option
          label="本地导入"
          value="original" /><el-option
          label="YouTube"
          value="youtube" /><el-option
          label="处理后素材"
          value="processed" /></el-select
      ><span class="muted small filter-total">共 {{ total }} 条素材</span>
    </div>
    <el-table
      ref="table"
      v-loading="loading"
      :data="items"
      row-key="id"
      :max-height="compact ? 370 : undefined"
      @select="select"
      @select-all="select"
      @row-dblclick="(row: Material) => (previewMaterial = row)"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column label="素材" min-width="240"
        ><template #default="{ row }"
          ><div class="material-cell">
            <button
              class="video-thumb"
              aria-label="预览视频"
              @click="previewMaterial = row"
            >
              <img
                v-if="row.has_thumbnail"
                :src="media(row.id, 'thumbnail')"
                alt=""
              /><el-icon v-else><VideoPlay /></el-icon
              ><span v-if="row.duration">{{ duration(row.duration) }}</span>
            </button>
            <div class="material-name">
              <button
                class="text-link ellipsis"
                :title="titleOf(row)"
                @click="previewMaterial = row"
              >
                {{ titleOf(row) }}</button><span class="muted small ellipsis">{{
                row.filename
              }}</span>
            </div>
          </div></template
        ></el-table-column
      >
      <el-table-column label="来源" width="120"
        ><template #default="{ row }"
          ><span
            class="source-tag"
            :class="{ processed: row.material_type === 'processed' }"
            >{{ sourceOf(row) }}</span
          ></template
        ></el-table-column
      >
      <el-table-column v-if="!compact" label="分辨率 / 大小" width="150"
        ><template #default="{ row }"
          ><div class="small">{{ row.video_resolution || "—" }}</div>
          <div class="muted small">
            {{ row.filesize?.toFixed(1) || "0" }} MB
          </div></template
        ></el-table-column
      >
      <el-table-column v-if="!compact" label="添加时间" width="136"
        ><template #default="{ row }"
          ><span class="muted small">{{
            date(row.upload_time)
          }}</span></template
        ></el-table-column
      >
      <el-table-column
        v-if="$slots.actions"
        label="操作"
        width="140"
        fixed="right"
        ><template #default="{ row }"
          ><slot name="actions" :row="row" /></template
      ></el-table-column>
      <template #empty
        ><el-empty
          description="暂无素材，先导入视频或新建下载"
          :image-size="64"
      /></template>
    </el-table>
    <div v-if="total > 20" class="pagination">
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next"
      />
    </div>
  </div>
</template>
