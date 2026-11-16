<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { media, post } from "../api";
import { act, drawerTask, previewMaterial, titleOf } from "../state";
const compatible = ref(false);
const failed = ref(false);
const busy = ref(false);
const source = computed(() =>
  previewMaterial.value
    ? media(previewMaterial.value.id) +
      (compatible.value ? "?compatible=true" : "")
    : "",
);
watch(previewMaterial, () => {
  compatible.value = false;
  failed.value = false;
});
async function transcode() {
  if (!previewMaterial.value) return;
  busy.value = true;
  await act(async () => {
    const result = await post<{ id: string }>(
      `/materials/${previewMaterial.value!.id}/preview`,
    );
    drawerTask.value = result.id;
    previewMaterial.value = null;
  });
  busy.value = false;
}
</script>

<template>
  <el-dialog
    :model-value="!!previewMaterial"
    :title="previewMaterial ? titleOf(previewMaterial) : '视频预览'"
    width="min(880px, 90vw)"
    destroy-on-close
    @close="previewMaterial = null"
  >
    <video
      v-if="previewMaterial"
      :key="source"
      :src="source"
      controls
      autoplay
      class="dialog-video"
      @error="failed = true"
      @loadeddata="failed = false"
    ></video>
    <div class="preview-toolbar">
      <span class="muted small">{{
        failed ? "浏览器无法播放此视频，可尝试兼容预览。" : "原视频仅在本机读取"
      }}</span>
      <div>
        <el-button v-if="!compatible" size="small" @click="compatible = true"
          >使用兼容预览</el-button
        ><el-button
          v-if="failed"
          size="small"
          :loading="busy"
          @click="transcode"
          >生成兼容预览</el-button
        >
      </div>
    </div>
  </el-dialog>
</template>
