<template>
  <div class="material-management">
    <div class="page-header">
      <h1>素材管理</h1>
      <p>管理本地素材文件，支持上传、预览、下载、删除和查看标题翻译。</p>
    </div>

    <div class="toolbar">
      <el-input
        v-model="searchKeyword"
        clearable
        placeholder="搜索文件名、原标题、中文标题、来源"
      />
      <div class="toolbar-actions">
        <el-button type="primary" @click="openUploadDialog">
          <el-icon><Upload /></el-icon>
          上传素材
        </el-button>
        <el-button :loading="isRefreshing" @click="fetchMaterials">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <div class="table-card">
      <el-table v-if="filteredMaterials.length" :data="filteredMaterials">
        <el-table-column prop="uuid" label="UUID" width="180" />
        <el-table-column prop="filename" label="文件名" min-width="240" show-overflow-tooltip />
        <el-table-column label="来源" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.source_type === 'youtube'" type="danger">YouTube</el-tag>
            <span v-else>本地上传</span>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="260">
          <template #default="{ row }">
            <div class="title-cell">
              <div class="title-primary">{{ row.video_title_zh || row.video_title || '-' }}</div>
              <div
                v-if="row.video_title && row.video_title_zh && row.video_title_zh !== row.video_title"
                class="title-secondary"
              >
                {{ row.video_title }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="filesize" label="大小" width="110">
          <template #default="{ row }">{{ row.filesize || 0 }} MB</template>
        </el-table-column>
        <el-table-column prop="upload_time" label="时间" width="180" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handlePreview(row)">预览</el-button>
            <el-button size="small" type="primary" @click="goToPublish(row)">发布</el-button>
            <el-button size="small" @click="downloadFile(row)">下载</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无素材数据" />
    </div>

    <el-dialog
      v-model="uploadDialogVisible"
      title="上传素材"
      width="640px"
      @close="resetUploadState"
    >
      <el-form label-width="90px">
        <el-form-item label="自定义文件名">
          <el-input
            v-model="customFilename"
            clearable
            placeholder="仅单文件上传时生效"
            :disabled="fileList.length > 1"
          />
        </el-form-item>
        <el-form-item label="选择文件">
          <el-upload
            drag
            multiple
            :auto-upload="false"
            :file-list="fileList"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
          >
            <el-icon class="upload-icon"><Upload /></el-icon>
            <div>拖拽文件到这里，或点击选择文件</div>
          </el-upload>
        </el-form-item>
      </el-form>

      <div v-if="fileList.length" class="upload-list">
        <div v-for="file in fileList" :key="file.uid" class="upload-item">
          <div class="upload-item-name">{{ file.name }}</div>
          <el-progress :percentage="uploadProgress[file.uid]?.percentage || 0">
            <span>{{ uploadProgress[file.uid]?.speed || '' }}</span>
          </el-progress>
        </div>
      </div>

      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="isUploading" @click="submitUpload">
          开始上传
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewDialogVisible" title="素材详情" width="760px">
      <div v-if="currentMaterial" class="preview-body">
        <div v-if="isVideoFile(currentMaterial.filename)" class="media-preview">
          <video controls :src="getPreviewUrl(currentMaterial.file_path)" />
        </div>
        <div v-else-if="isImageFile(currentMaterial.filename)" class="media-preview">
          <img :src="getPreviewUrl(currentMaterial.file_path)" alt="preview" />
        </div>

        <div class="meta-grid">
          <div><strong>文件名：</strong>{{ currentMaterial.filename }}</div>
          <div><strong>大小：</strong>{{ currentMaterial.filesize || 0 }} MB</div>
          <div><strong>来源：</strong>{{ currentMaterial.source_type || 'local' }}</div>
          <div><strong>时间：</strong>{{ currentMaterial.upload_time }}</div>
          <div v-if="currentMaterial.source_url" class="full-row">
            <strong>源链接：</strong>
            <el-link :href="currentMaterial.source_url" target="_blank" type="primary">
              {{ currentMaterial.source_url }}
            </el-link>
          </div>
          <div v-if="currentMaterial.video_title" class="full-row">
            <strong>原标题：</strong>{{ currentMaterial.video_title }}
          </div>
          <div v-if="currentMaterial.video_title_zh" class="full-row">
            <strong>中文标题：</strong>{{ currentMaterial.video_title_zh }}
          </div>
          <div v-if="currentMaterial.video_description" class="full-row description-block">
            <strong>简介：</strong>
            <div class="description-content">{{ currentMaterial.video_description }}</div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="previewDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="downloadFile(currentMaterial)">下载文件</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Upload } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { materialApi } from '@/api/material'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const router = useRouter()

const searchKeyword = ref('')
const isRefreshing = ref(false)
const isUploading = ref(false)
const uploadDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const fileList = ref([])
const customFilename = ref('')
const uploadProgress = ref({})
const currentMaterial = ref(null)

const filteredMaterials = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) return appStore.materials
  return appStore.materials.filter((material) => {
    const fields = [
      material.filename,
      material.video_title,
      material.video_title_zh,
      material.video_description,
      material.source_type,
      material.source_url,
    ]
    return fields.some((field) => (field || '').toLowerCase().includes(keyword))
  })
})

const fetchMaterials = async () => {
  isRefreshing.value = true
  try {
    const response = await materialApi.getAllMaterials()
    appStore.setMaterials(response.data || [])
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '获取素材列表失败')
  } finally {
    isRefreshing.value = false
  }
}

const openUploadDialog = () => {
  resetUploadState()
  uploadDialogVisible.value = true
}

const resetUploadState = () => {
  fileList.value = []
  customFilename.value = ''
  uploadProgress.value = {}
}

const handleFileChange = (file, uploadFileList) => {
  fileList.value = uploadFileList
  const nextProgress = {}
  uploadFileList.forEach((item) => {
    nextProgress[item.uid] = uploadProgress.value[item.uid] || { percentage: 0, speed: '' }
  })
  uploadProgress.value = nextProgress
}

const handleFileRemove = (file, uploadFileList) => {
  handleFileChange(file, uploadFileList)
}

const submitUpload = async () => {
  if (!fileList.value.length) {
    ElMessage.warning('请先选择文件')
    return
  }

  isUploading.value = true
  try {
    for (const file of fileList.value) {
      if (!file.raw) continue
      const formData = new FormData()
      formData.append('file', file.raw)
      if (fileList.value.length === 1 && customFilename.value.trim()) {
        formData.append('filename', customFilename.value.trim())
      }

      let lastLoaded = 0
      let lastTime = Date.now()
      await materialApi.uploadMaterial(formData, (progressEvent) => {
        const progressData = uploadProgress.value[file.uid]
        if (!progressData || !progressEvent.total) return
        progressData.percentage = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        const now = Date.now()
        const seconds = (now - lastTime) / 1000
        if (seconds >= 0.5) {
          const speed = (progressEvent.loaded - lastLoaded) / seconds
          progressData.speed =
            speed > 1024 * 1024
              ? `${(speed / 1024 / 1024).toFixed(2)} MB/s`
              : `${(speed / 1024).toFixed(2)} KB/s`
          lastLoaded = progressEvent.loaded
          lastTime = now
        }
      })
      uploadProgress.value[file.uid].speed = '完成'
    }
    ElMessage.success('上传完成')
    uploadDialogVisible.value = false
    await fetchMaterials()
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '上传失败')
  } finally {
    isUploading.value = false
  }
}

const handlePreview = (material) => {
  currentMaterial.value = material
  previewDialogVisible.value = true
}

const handleDelete = async (material) => {
  try {
    await ElMessageBox.confirm(`确认删除素材 ${material.filename} 吗？`, '提示', { type: 'warning' })
    await materialApi.deleteMaterial(material.id)
    appStore.removeMaterial(material.id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error === 'cancel' || error?.message === 'cancel') return
    console.error(error)
    ElMessage.error(error.message || '删除失败')
  }
}

const getPreviewUrl = (filePath) => materialApi.getMaterialPreviewUrl(filePath)

const downloadFile = (material) => {
  if (!material) return
  window.open(materialApi.downloadMaterial(material.file_path), '_blank')
}

const goToPublish = async (material) => {
  if (!material) return
  appStore.setPendingPublishMaterials([material])
  await router.push('/publish-center')
}

const isVideoFile = (filename) =>
  ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm'].some((ext) =>
    filename.toLowerCase().endsWith(ext)
  )

const isImageFile = (filename) =>
  ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'].some((ext) =>
    filename.toLowerCase().endsWith(ext)
  )

onMounted(() => {
  fetchMaterials()
})
</script>

<style lang="scss" scoped>
.material-management {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 24px;
}

.page-header p {
  margin: 0;
  color: #606266;
}

.toolbar,
.table-card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px;
}

.toolbar .el-input {
  max-width: 360px;
}

.toolbar-actions {
  display: flex;
  gap: 12px;
}

.table-card {
  padding: 20px;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.title-primary {
  color: #303133;
  line-height: 1.5;
}

.title-secondary {
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}

.upload-icon {
  font-size: 28px;
}

.upload-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-item {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.upload-item-name {
  margin-bottom: 8px;
  font-weight: 500;
}

.preview-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.media-preview {
  display: flex;
  justify-content: center;
}

.media-preview video,
.media-preview img {
  max-width: 100%;
  max-height: 420px;
  border-radius: 8px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 20px;
}

.full-row {
  grid-column: 1 / -1;
}

.description-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.description-content {
  white-space: pre-wrap;
  line-height: 1.6;
  padding: 12px;
  border-radius: 8px;
  background: #f7f8fa;
}

@media (max-width: 900px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar .el-input {
    max-width: none;
  }

  .toolbar-actions {
    flex-wrap: wrap;
  }

  .meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
