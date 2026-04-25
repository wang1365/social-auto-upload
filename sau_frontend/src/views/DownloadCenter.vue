<template>
  <div class="download-center">
    <div class="page-header">
      <div>
        <h1>素材下载</h1>
        <p>管理 YouTube 下载任务，查看进度、元数据、原始标题和中文标题。</p>
      </div>
      <div class="header-actions">
        <el-button
          type="danger"
          plain
          :disabled="!selectedDeletableTasks.length"
          @click="handleBatchDelete"
        >
          批量删除
        </el-button>
        <el-button :loading="loading" @click="fetchTasks(true)">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          新建下载
        </el-button>
      </div>
    </div>

    <div class="toolbar-card">
      <el-input
        v-model="searchKeyword"
        clearable
        placeholder="搜索任务 ID、标题、中文标题、链接、文件名"
      />
      <el-radio-group v-model="statusFilter">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button label="pending">等待中</el-radio-button>
        <el-radio-button label="downloading">下载中</el-radio-button>
        <el-radio-button label="success">已完成</el-radio-button>
        <el-radio-button label="failed">失败</el-radio-button>
      </el-radio-group>
    </div>

    <div class="table-card">
      <el-table
        v-if="filteredTasks.length"
        :data="filteredTasks"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="52" :selectable="isTaskDeletable" />
        <el-table-column prop="taskId" label="任务 ID" min-width="220" show-overflow-tooltip />
        <el-table-column label="标题" min-width="260">
          <template #default="{ row }">
            <div class="title-cell">
              <div class="title-primary">{{ row.videoTitleZh || row.videoTitle || '-' }}</div>
              <div
                v-if="row.videoTitle && row.videoTitleZh && row.videoTitleZh !== row.videoTitle"
                class="title-secondary"
              >
                {{ row.videoTitle }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="视频 URL" min-width="320">
          <template #default="{ row }">
            <div class="url-cell">
              <el-link
                v-if="row.sourceUrl"
                :href="row.sourceUrl"
                target="_blank"
                type="primary"
                class="url-link"
              >
                {{ row.sourceUrl }}
              </el-link>
              <span v-else>-</span>
              <el-button
                v-if="row.sourceUrl"
                text
                type="primary"
                @click="copyText(row.sourceUrl, '视频链接已复制')"
              >
                复制
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="280">
          <template #default="{ row }">
            <div class="progress-cell">
              <el-progress
                :percentage="normalizedProgress(row)"
                :status="row.status === 'failed' ? 'exception' : undefined"
                :stroke-width="10"
              />
              <div class="progress-meta">
                <span>{{ row.progressText || '-' }}</span>
                <span v-if="row.speedText">{{ row.speedText }}</span>
                <span v-if="row.etaText">ETA {{ row.etaText }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="filename" label="本地文件" min-width="220" show-overflow-tooltip />
        <el-table-column prop="updatedAt" label="更新时间" width="180" />
        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openTaskDetail(row)">详情</el-button>
            <el-button
              size="small"
              type="primary"
              :disabled="!row.sourceUrl && !row.filePath"
              @click="openTaskDetail(row, true)"
            >
              播放
            </el-button>
            <el-button
              v-if="row.status === 'success' && row.materialId"
              size="small"
              type="success"
              @click="goToPublish(row)"
            >
              发布
            </el-button>
            <el-button
              size="small"
              type="warning"
              v-if="row.sourceUrl"
              @click="retryDownload(row)"
            >
              重新下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无下载任务" />
    </div>

    <el-dialog
      v-model="createDialogVisible"
      title="新建 YouTube 下载"
      width="640px"
      @close="resetCreateForm"
    >
      <el-form label-width="90px">
        <el-form-item label="视频链接">
          <el-input
            v-model="createForm.url"
            clearable
            placeholder="请输入单个 YouTube 视频链接"
          />
        </el-form-item>
        <el-form-item label="字幕">
          <el-switch
            v-model="createForm.downloadSubtitles"
            inline-prompt
            active-text="开"
            inactive-text="关"
          />
        </el-form-item>
      </el-form>

      <el-alert
        title="下载会自动提取元数据，并将标题翻译为中文后保存。"
        type="info"
        :closable="false"
        show-icon
      />

      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createDownloadTask">
          开始下载
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="detailVisible"
      title="下载详情"
      width="95%"
      top="5vh"
      class="download-detail-dialog"
      destroy-on-close
    >
      <template v-if="selectedTask">
        <div class="detail-dialog-layout">
          <aside class="detail-info-pane">
        <div class="detail-section">
          <div class="detail-grid">
            <div><strong>任务 ID：</strong>{{ selectedTask.taskId }}</div>
            <div><strong>状态：</strong>{{ statusLabel(selectedTask.status) }}</div>
            <div><strong>创建时间：</strong>{{ selectedTask.createdAt || '-' }}</div>
            <div><strong>更新时间：</strong>{{ selectedTask.updatedAt || '-' }}</div>
            <div><strong>阶段：</strong>{{ phaseLabel(selectedTask.phase) }}</div>
            <div><strong>进度：</strong>{{ normalizedProgress(selectedTask) }}%</div>
            <div class="full-row"><strong>原标题：</strong>{{ selectedTask.videoTitle || '-' }}</div>
            <div class="full-row"><strong>中文标题：</strong>{{ selectedTask.videoTitleZh || '-' }}</div>
            <div class="full-row"><strong>视频 ID：</strong>{{ selectedTask.videoId || '-' }}</div>
            <div class="full-row detail-url-row">
              <strong>链接：</strong>
              <div class="detail-url-actions">
                <el-link
                  v-if="selectedTask.sourceUrl"
                  :href="selectedTask.sourceUrl"
                  target="_blank"
                  type="primary"
                >
                  {{ selectedTask.sourceUrl }}
                </el-link>
                <span v-else>-</span>
                <el-button
                  v-if="selectedTask.sourceUrl"
                  text
                  type="primary"
                  @click="copyText(selectedTask.sourceUrl, '视频链接已复制')"
                >
                  复制链接
                </el-button>
              </div>
            </div>
            <div class="full-row"><strong>本地文件：</strong>{{ selectedTask.filename || '-' }}</div>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-title">视频详情</div>
          <div class="metadata-card">
            <div><strong>原标题：</strong>{{ selectedTask.videoTitle || '-' }}</div>
            <div><strong>中文标题：</strong>{{ selectedTask.videoTitleZh || '-' }}</div>
            <div class="metadata-description">
              <strong>内容描述：</strong>
              <div class="description-box">{{ selectedTask.videoDescription || '-' }}</div>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-title">实时进度</div>
          <el-progress
            :percentage="normalizedProgress(selectedTask)"
            :status="selectedTask.status === 'failed' ? 'exception' : undefined"
          />
          <div class="progress-panel">
            <div><strong>状态说明：</strong>{{ selectedTask.progressText || '-' }}</div>
            <div><strong>下载速度：</strong>{{ selectedTask.speedText || '-' }}</div>
            <div><strong>剩余时间：</strong>{{ selectedTask.etaText || '-' }}</div>
            <div>
              <strong>已下载 / 总大小：</strong>
              {{ formatBytes(selectedTask.downloadedBytes) }} / {{ formatBytes(selectedTask.totalBytes) }}
            </div>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-title">视频处理</div>
          <div class="processing-card">
            <el-tag :type="processingTagType(selectedTask.processingStatus)">
              {{ processingLabel(selectedTask.processingStatus) }}
            </el-tag>
            <span>{{ selectedTask.processingProgressText || '等待下载完成后自动处理' }}</span>
            <el-progress
              v-if="selectedTask.processingStatus"
              :percentage="normalizedProcessingProgress(selectedTask)"
              :status="selectedTask.processingStatus === 'failed' ? 'exception' : undefined"
            />
            <div v-if="selectedTask.processingErrorMessage" class="error-summary">
              {{ selectedTask.processingErrorMessage }}
            </div>
            <div v-if="selectedTask.processedFilePath" class="detail-actions">
              <el-button type="primary" @click="activePlaybackTab = 'processed'">播放处理后视频</el-button>
              <el-button type="success" @click="goToProcessedPublish(selectedTask)">发布处理后视频</el-button>
            </div>
          </div>
        </div>

          </aside>
          <main class="detail-preview-pane">
            <div class="preview-grid">
              <section class="preview-panel">
                <div class="preview-title">源视频</div>
              <iframe
                v-if="youtubeEmbedUrl"
                class="source-player"
                :src="youtubeEmbedUrl"
                title="YouTube Source Player"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                referrerpolicy="strict-origin-when-cross-origin"
                allowfullscreen
              />
              <el-empty v-else description="当前无可播放源视频" />
              </section>
              <section class="preview-panel">
                <div class="preview-title">已下载视频</div>
              <video
                v-if="selectedTask.filePath && isVideoFile(selectedTask.filename || selectedTask.filePath)"
                controls
                class="video-player"
                :src="materialApi.getMaterialPreviewUrl(selectedTask.filePath)"
              />
              <el-empty v-else description="当前无已下载视频文件" />
              </section>
              <section class="preview-panel">
                <div class="preview-title">处理后视频</div>
              <video
                v-if="selectedTask.processedFilePath"
                controls
                class="video-player"
                :src="materialApi.getMaterialPreviewUrl(selectedTask.processedFilePath)"
              />
              <el-empty v-else description="当前没有处理后视频" />
              </section>
            </div>

            <div class="detail-section subtitle-section">
              <div class="section-title">字幕</div>
              <div v-if="selectedTask.subtitleText" class="subtitle-box">{{ selectedTask.subtitleText }}</div>
              <el-empty v-else description="当前任务无可展示字幕" />
              <div class="detail-actions">
                <el-button
                  v-if="selectedTask.subtitleText"
                  text
                  type="primary"
                  @click="copyText(selectedTask.subtitleText, '字幕已复制')"
                >
                  复制字幕
                </el-button>
                <el-button
                  v-if="selectedTask.subtitleFilePath"
                  text
                  type="primary"
                  @click="downloadSubtitle(selectedTask.subtitleFilePath)"
                >
                  下载字幕文件
                </el-button>
              </div>
            </div>
          </main>

        <div v-if="selectedTask.errorMessage" class="detail-section error-panel">
          <div class="section-title">失败信息</div>
          <div class="error-summary">{{ selectedTask.errorMessage }}</div>
          <el-input
            v-if="selectedTask.errorDetail"
            :model-value="selectedTask.errorDetail"
            type="textarea"
            :rows="8"
            readonly
          />
          <div class="detail-actions">
            <el-button
              v-if="selectedTask.errorDetail"
              text
              type="primary"
              @click="copyText(selectedTask.errorDetail, '详细错误信息已复制')"
            >
              复制详细信息
            </el-button>
            <el-button
              v-if="selectedTask.sourceUrl"
              type="warning"
              @click="retryDownload(selectedTask)"
            >
              重新下载
            </el-button>
          </div>
        </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { downloadApi } from '@/api/download'
import { materialApi } from '@/api/material'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const router = useRouter()
const loading = ref(false)
const creating = ref(false)
const createDialogVisible = ref(false)
const detailVisible = ref(false)
const searchKeyword = ref('')
const statusFilter = ref('all')
const tasks = ref([])
const selectedTask = ref(null)
const createForm = ref({ url: '', downloadSubtitles: false })
const activePlaybackTab = ref('source')
const latestMaterialSignature = ref('')
const selectedDeletableTasks = ref([])
let pollTimer = null

const filteredTasks = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return tasks.value.filter((task) => {
    const matchStatus = statusFilter.value === 'all' || task.status === statusFilter.value
    if (!matchStatus) return false
    if (!keyword) return true
    const fields = [
      task.taskId,
      task.videoTitle,
      task.videoTitleZh,
      task.videoDescription,
      task.videoId,
      task.sourceUrl,
      task.filename,
      task.progressText,
    ]
    return fields.some((field) => (field || '').toLowerCase().includes(keyword))
  })
})

const hasActiveTasks = computed(() =>
  tasks.value.some((task) =>
    task.status === 'pending' ||
    task.status === 'downloading' ||
    task.processingStatus === 'pending' ||
    task.processingStatus === 'processing'
  )
)

const youtubeEmbedUrl = computed(() => {
  const videoId = selectedTask.value?.videoId
  if (!videoId) return ''
  return `https://www.youtube.com/embed/${encodeURIComponent(videoId)}`
})

watch(
  () => selectedTask.value,
  (task) => {
    if (task?.filePath) {
      activePlaybackTab.value = 'local'
      return
    }
    if (task?.sourceUrl) {
      activePlaybackTab.value = 'source'
    }
  }
)

const statusLabel = (status) => {
  if (status === 'pending') return '等待中'
  if (status === 'downloading') return '下载中'
  if (status === 'success') return '已完成'
  if (status === 'failed') return '失败'
  return status || '-'
}

const phaseLabel = (phase) => {
  if (phase === 'pending') return '等待调度'
  if (phase === 'metadata') return '提取元数据'
  if (phase === 'download') return '下载文件'
  if (phase === 'processing') return '合并与落盘'
  if (phase === 'completed') return '完成'
  if (phase === 'failed') return '失败'
  return phase || '-'
}

const statusTagType = (status) => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'downloading') return 'warning'
  return 'info'
}

const normalizedProgress = (task) => {
  if (!task) return 0
  if (typeof task.progressPercent === 'number') {
    return Math.max(0, Math.min(100, Math.round(task.progressPercent)))
  }
  if (task.status === 'success') return 100
  return 0
}

const normalizedProcessingProgress = (task) => {
  if (!task) return 0
  if (typeof task.processingProgressPercent === 'number') {
    return Math.max(0, Math.min(100, Math.round(task.processingProgressPercent)))
  }
  if (task.processingStatus === 'success' || task.processingStatus === 'failed') return 100
  return 0
}

const processingLabel = (status) => {
  if (status === 'pending') return '等待处理'
  if (status === 'processing') return '处理中'
  if (status === 'success') return '处理完成'
  if (status === 'failed') return '处理失败'
  return '未开始'
}

const processingTagType = (status) => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'processing') return 'warning'
  return 'info'
}

const formatBytes = (value) => {
  if (typeof value !== 'number' || Number.isNaN(value) || value < 0) return '-'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(2)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const copyText = async (value, successMessage) => {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success(successMessage)
  } catch (error) {
    console.error(error)
    ElMessage.error('复制失败')
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

const buildMaterialSignature = (taskList) =>
  taskList
    .filter((task) => task.status === 'success' && task.materialId)
    .map((task) => `${task.materialId}:${task.processedMaterialId || ''}:${task.updatedAt || ''}`)
    .sort()
    .join('|')

const syncMaterials = async () => {
  const response = await materialApi.getAllMaterials()
  appStore.setMaterials(response.data || [])
}

const isTaskDeletable = (task) => task?.status === 'success' && Boolean(task?.materialId)

const handleSelectionChange = (selection) => {
  selectedDeletableTasks.value = selection.filter(isTaskDeletable)
}

const schedulePolling = () => {
  stopPolling()
  if (!hasActiveTasks.value) return
  pollTimer = setTimeout(() => {
    fetchTasks(false)
  }, 1500)
}

const fetchTasks = async (showMessage = false) => {
  loading.value = true
  try {
    const response = await downloadApi.listYoutubeTasks()
    tasks.value = response.data || []
    const materialSignature = buildMaterialSignature(tasks.value)
    if (materialSignature !== latestMaterialSignature.value) {
      latestMaterialSignature.value = materialSignature
      await syncMaterials()
    }
    if (selectedTask.value) {
      const current = tasks.value.find((item) => item.taskId === selectedTask.value.taskId)
      if (current) {
        selectedTask.value = {
          ...current,
          subtitleText: current.subtitleText || selectedTask.value.subtitleText || '',
        }
      } else {
        selectedTask.value = null
        detailVisible.value = false
      }
    }
    if (showMessage) ElMessage.success('下载列表已刷新')
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '获取下载列表失败')
  } finally {
    loading.value = false
    schedulePolling()
  }
}

const goToPublish = async (task) => {
  if (!task?.materialId) {
    ElMessage.warning('当前任务还没有生成可发布素材')
    return
  }

  let material = appStore.materials.find((item) => item.id === task.materialId)
  if (!material) {
    await syncMaterials()
    material = appStore.materials.find((item) => item.id === task.materialId)
  }
  if (!material) {
    ElMessage.error('未找到对应素材，请先刷新列表后重试')
    return
  }

  appStore.setPendingPublishMaterials([material])
  await router.push('/publish-center')
}

const goToProcessedPublish = async (task) => {
  if (!task?.processedMaterialId) {
    ElMessage.warning('当前任务还没有生成处理后素材')
    return
  }
  let material = appStore.materials.find((item) => item.id === task.processedMaterialId)
  if (!material) {
    await syncMaterials()
    material = appStore.materials.find((item) => item.id === task.processedMaterialId)
  }
  if (!material) {
    ElMessage.error('未找到处理后素材，请先刷新列表后重试')
    return
  }
  appStore.setPendingPublishMaterials([material])
  await router.push('/publish-center')
}

const handleBatchDelete = async () => {
  const ids = selectedDeletableTasks.value
    .map((task) => Number(task.materialId))
    .filter((id) => Number.isInteger(id) && id > 0)
  if (!ids.length) {
    ElMessage.warning('请先选择已下载完成的素材任务')
    return
  }

  try {
    await ElMessageBox.confirm(`确认批量删除已选中的 ${ids.length} 个下载素材吗？`, '提示', {
      type: 'warning',
    })
    await materialApi.deleteMaterials(ids)
    await syncMaterials()
    await fetchTasks()
    selectedDeletableTasks.value = []
    ElMessage.success('批量删除成功')
  } catch (error) {
    if (error === 'cancel' || error?.message === 'cancel') return
    console.error(error)
    ElMessage.error(error.message || '批量删除失败')
  }
}

const openCreateDialog = () => {
  resetCreateForm()
  createDialogVisible.value = true
}

const resetCreateForm = () => {
  createForm.value = { url: '', downloadSubtitles: true }
}

const createDownloadTask = async () => {
  const url = createForm.value.url.trim()
  if (!url) {
    ElMessage.warning('请输入 YouTube 视频链接')
    return
  }
  creating.value = true
  try {
    const response = await downloadApi.createYoutubeDownloadTask(
      url,
      createForm.value.downloadSubtitles !== false
    )
    createDialogVisible.value = false
    await fetchTasks()
    const createdTask = await downloadApi.getYoutubeTask(response.data.taskId)
    selectedTask.value = createdTask.data
    detailVisible.value = true
    ElMessage.success('下载任务已创建')
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '创建下载任务失败')
  } finally {
    creating.value = false
  }
}

const retryDownload = async (task) => {
  if (!task.sourceUrl) {
    ElMessage.warning('没有视频链接，无法重新下载')
    return
  }
  creating.value = true
  try {
    const response = await downloadApi.createYoutubeDownloadTask(
      task.sourceUrl,
      task.downloadSubtitles !== false
    )
    await fetchTasks()
    const createdTask = await downloadApi.getYoutubeTask(response.data.taskId)
    selectedTask.value = createdTask.data
    detailVisible.value = true
    ElMessage.success('重新下载任务已创建')
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '创建重新下载任务失败')
  } finally {
    creating.value = false
  }
}

const openTaskDetail = async (task, focusPlayer = false) => {
  try {
    const response = await downloadApi.getYoutubeTask(task.taskId)
    selectedTask.value = response.data
    detailVisible.value = true
    if (focusPlayer) {
      if (response.data.filePath) {
        activePlaybackTab.value = 'local'
      } else if (response.data.sourceUrl) {
        activePlaybackTab.value = 'source'
      }
    }
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '获取下载详情失败')
  }
}

const isVideoFile = (filename) =>
  ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm'].some((ext) =>
    (filename || '').toLowerCase().endsWith(ext)
  )

const downloadSubtitle = (subtitlePath) => {
  if (!subtitlePath) return
  window.open(materialApi.downloadMaterial(subtitlePath), '_blank')
}

onMounted(() => {
  fetchTasks()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.download-center {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header,
.toolbar-card,
.table-card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
}

.page-header h1 {
  margin: 0 0 6px;
  font-size: 24px;
}

.page-header p {
  margin: 0;
  color: #606266;
}

.header-actions,
.detail-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
}

.toolbar-card .el-input {
  max-width: 420px;
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

.url-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.url-link {
  flex: 1;
  min-width: 0;
}

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #606266;
}

.detail-section {
  margin-bottom: 24px;
}

.download-detail-dialog :deep(.el-dialog__body) {
  max-height: 78vh;
  overflow: hidden;
}

.detail-dialog-layout {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(0, 3fr);
  gap: 20px;
  height: 78vh;
  min-height: 0;
}

.detail-info-pane,
.detail-preview-pane {
  min-height: 0;
  overflow: auto;
}

.detail-info-pane {
  padding-right: 4px;
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}

.preview-panel {
  min-width: 0;
  overflow: hidden;
}

.preview-title {
  margin-bottom: 10px;
  font-weight: 600;
  color: #303133;
}

.section-title {
  margin-bottom: 12px;
  font-weight: 600;
  color: #303133;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 20px;
}

.full-row {
  grid-column: 1 / -1;
}

.detail-url-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.detail-url-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
  flex-wrap: wrap;
}

.metadata-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  background: #f7f8fa;
}

.metadata-description {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.description-box {
  min-height: 80px;
  padding: 12px;
  white-space: pre-wrap;
  line-height: 1.6;
  border-radius: 8px;
  background: #fff;
}

.subtitle-box {
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  line-height: 1.6;
  padding: 12px;
  border-radius: 8px;
  background: #f7f8fa;
  border: 1px solid #ebeef5;
}

.progress-panel {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 20px;
}

.processing-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  background: #f7f8fa;
}

.source-player {
  width: 100%;
  height: 58vh;
  max-height: 58vh;
  border: 0;
  border-radius: 8px;
  background: #000;
}

.video-player {
  display: block;
  width: calc(100% + 12px);
  max-width: none;
  height: 58vh;
  max-height: 58vh;
  margin: 0 -6px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  object-fit: cover;
}

.error-panel {
  padding: 16px;
  border-radius: 8px;
  background: #fff6f6;
  border: 1px solid #fde2e2;
}

.error-summary {
  margin-bottom: 12px;
  color: #c45656;
}

@media (max-width: 900px) {
  .page-header,
  .toolbar-card {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-card .el-input {
    max-width: none;
  }

  .detail-grid,
  .progress-panel {
    grid-template-columns: 1fr;
  }

  .download-detail-dialog :deep(.el-dialog__body) {
    max-height: 82vh;
  }

  .detail-dialog-layout {
    grid-template-columns: 1fr;
    height: 82vh;
  }

  .preview-grid {
    grid-template-columns: 1fr;
  }

  .url-cell,
  .detail-url-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .source-player {
    height: 240px;
    max-height: 36vh;
  }

  .video-player {
    width: calc(100% + 12px);
    height: auto;
    max-height: 36vh;
  }
}
</style>