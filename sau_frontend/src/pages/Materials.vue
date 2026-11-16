<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { Upload, Promotion, FolderOpened } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import MaterialBrowser from "../components/MaterialBrowser.vue";
import { api, post, upload, type Material } from "../api";
import { act, confirm, drawerTask, refresh } from "../state";
const router = useRouter();
const selected = ref<Material[]>([]);
const input = ref<HTMLInputElement>();
const busy = ref(false);
const percent = ref(0);
const dragging = ref(false);
const browser = ref<InstanceType<typeof MaterialBrowser>>();
async function importFiles(files: File[]) {
  if (!files.length || busy.value) return;
  busy.value = true;
  percent.value = 0;
  await act(async () => {
    const result = await upload(files, (value) => (percent.value = value));
    ElMessage.success(`已导入 ${result.length} 条素材`);
    await refresh();
    await browser.value?.load();
  });
  busy.value = false;
  if (input.value) input.value.value = "";
}
async function remove(rows: Material[]) {
  if (
    !(await confirm(
      `将删除 ${rows.length} 条素材及其本地视频、字幕文件，此操作无法撤销。`,
      "删除素材",
    ))
  )
    return;
  await act(async () => {
    const failed: string[] = [];
    for (const row of rows) {
      try {
        await api(`/materials/${row.id}`, { method: "DELETE" });
      } catch (error) {
        failed.push(`${row.filename}：${(error as Error).message}`);
      }
    }
    selected.value = [];
    await refresh();
    await browser.value?.load();
    if (failed.length) throw new Error(failed.join("；"));
    ElMessage.success("素材已删除");
  });
}
function publish(rows: Material[]) {
  sessionStorage.setItem(
    "sau-publish-selection",
    JSON.stringify(rows.map((m) => m.id)),
  );
  router.push("/publish");
}
async function process(row: Material) {
  await act(async () => {
    const result = await post<{ id: string }>("/processing", {
      material_id: row.id,
    });
    drawerTask.value = result.id;
    await refresh();
  });
}
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">素材管理</div>
      <h1>素材库</h1>
      <p>集中管理视频，从素材到发布更顺手。</p>
    </div>
    <el-button
      type="primary"
      :icon="Upload"
      :loading="busy"
      @click="input?.click()"
      >导入视频</el-button
    >
  </div>
  <input
    ref="input"
    type="file"
    multiple
    accept=".mp4,.mov,.mkv,.avi,.m4v,.webm,.flv,.wmv"
    hidden
    @change="
      importFiles(Array.from(($event.target as HTMLInputElement).files || []))
    "
  />
  <div
    class="drop-strip"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="
      dragging = false;
      importFiles(Array.from($event.dataTransfer?.files || []));
    "
  >
    <el-icon><FolderOpened /></el-icon
    ><span
      >将视频拖到这里，或
      <button class="text-link" @click="input?.click()">
        选择本地文件
      </button></span
    ><span class="muted small">支持 MP4、MOV、MKV 等常用格式</span>
  </div>
  <el-progress
    v-if="busy"
    :percentage="percent"
    :format="(value: number) => (value === 100 ? '正在整理素材…' : value + '%')"
    class="import-progress"
  />
  <section class="panel">
    <div v-if="selected.length" class="selection-bar">
      <span
        >已选 <strong>{{ selected.length }}</strong> 条素材</span
      >
      <div>
        <el-button
          :icon="Promotion"
          size="small"
          type="primary"
          @click="publish(selected)"
          >去发布</el-button
        ><el-button size="small" type="danger" plain @click="remove(selected)"
          >删除素材</el-button
        ><el-button size="small" text @click="selected = []"
          >取消选择</el-button
        >
      </div>
    </div>
    <MaterialBrowser ref="browser" v-model="selected"
      ><template #actions="{ row }"
        ><el-button link type="primary" @click="publish([row])">发布</el-button
        ><el-dropdown
          trigger="click"
          @command="
            (command: string) =>
              command === 'process'
                ? process(row)
                : command === 'delete'
                  ? remove([row])
                  : act(() => post(`/materials/${row.id}/reveal`))
          "
          ><el-button link>更多</el-button
          ><template #dropdown
            ><el-dropdown-menu
              ><el-dropdown-item command="process">处理视频</el-dropdown-item
              ><el-dropdown-item command="reveal"
                >打开所在文件夹</el-dropdown-item
              ><el-dropdown-item command="delete" divided
                >删除素材</el-dropdown-item
              ></el-dropdown-menu
            ></template
          ></el-dropdown
        ></template
      ></MaterialBrowser
    >
  </section>
</template>
