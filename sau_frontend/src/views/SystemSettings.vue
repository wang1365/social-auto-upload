<template>
  <div class="system-settings">
    <div class="page-header">
      <h1>系统配置</h1>
    </div>

    <div class="settings-card">
      <el-form label-width="120px">
        <el-form-item label="下载代理">
          <el-input
            v-model="form.downloadProxy"
            placeholder="例如 http://127.0.0.1:7890 或 socks5://127.0.0.1:1080"
            clearable
          />
          <div class="field-tip">
            留空表示不使用代理。该配置仅作用于 YouTube 下载。
          </div>
        </el-form-item>

        <el-divider />

        <el-form-item label="YouTube Cookie">
          <div class="cookie-panel">
            <div class="cookie-status">
              <el-tag :type="form.youtubeCookieConfigured ? 'success' : 'info'">
                {{ form.youtubeCookieConfigured ? '已配置' : '未配置' }}
              </el-tag>
              <span class="cookie-name">
                {{ form.youtubeCookieFileName || '未上传 Cookie 文件' }}
              </span>
            </div>

            <div class="cookie-buttons">
              <el-upload
                class="cookie-upload"
                :auto-upload="false"
                :show-file-list="false"
                accept=".txt"
                :on-change="handleCookieSelect"
              >
                <template #trigger>
                  <el-button :loading="uploadingCookie">选择 Cookie 文件</el-button>
                </template>
              </el-upload>

              <el-button
                type="primary"
                :disabled="!selectedCookieFile"
                :loading="uploadingCookie"
                @click="uploadCookie"
              >
                上传 Cookie
              </el-button>
              <el-button
                danger
                plain
                :disabled="!form.youtubeCookieConfigured"
                :loading="clearingCookie"
                @click="clearCookie"
              >
                清除 Cookie
              </el-button>
            </div>

            <div class="field-tip">
              仅支持 Netscape 格式的 `cookies.txt`，只用于 YouTube 下载。Cookie
              失效后需要重新上传。
            </div>
            <div v-if="selectedCookieFile" class="selected-file">
              当前选择：{{ selectedCookieFile.name }}
            </div>
          </div>
        </el-form-item>

        <el-divider />

        <el-form-item label="视频处理">
          <div class="video-process-panel">
            <el-switch
              v-model="form.videoProcessing.autoProcess"
              inline-prompt
              active-text="开启"
              inactive-text="关闭"
            />
            <div class="process-groups">
              <div class="process-group">
                <div class="group-header">
                  <span class="group-label">片头处理</span>
                  <el-switch v-model="form.videoProcessing.enableTrimHead" />
                </div>
                <div class="group-controls">
                  <div class="process-item">
                    <span class="process-label">最小秒</span>
                    <el-input-number v-model="form.videoProcessing.trimHeadMin" :min="0" :max="10" :step="0.1" />
                  </div>
                  <div class="process-item">
                    <span class="process-label">最大秒</span>
                    <el-input-number v-model="form.videoProcessing.trimHeadMax" :min="0" :max="10" :step="0.1" />
                  </div>
                </div>
              </div>
              
              <div class="process-group">
                <div class="group-header">
                  <span class="group-label">片尾处理</span>
                  <el-switch v-model="form.videoProcessing.enableTrimTail" />
                </div>
                <div class="group-controls">
                  <div class="process-item">
                    <span class="process-label">最小秒</span>
                    <el-input-number v-model="form.videoProcessing.trimTailMin" :min="0" :max="10" :step="0.1" />
                  </div>
                  <div class="process-item">
                    <span class="process-label">最大秒</span>
                    <el-input-number v-model="form.videoProcessing.trimTailMax" :min="0" :max="10" :step="0.1" />
                  </div>
                </div>
              </div>
              
              <div class="process-group">
                <div class="group-header">
                  <span class="group-label">变速处理</span>
                  <el-switch v-model="form.videoProcessing.enableSpeed" />
                </div>
                <div class="group-controls">
                  <div class="process-item">
                    <span class="process-label">最小</span>
                    <el-input-number v-model="form.videoProcessing.speedMin" :min="0.5" :max="2" :step="0.01" />
                  </div>
                  <div class="process-item">
                    <span class="process-label">最大</span>
                    <el-input-number v-model="form.videoProcessing.speedMax" :min="0.5" :max="2" :step="0.01" />
                  </div>
                </div>
              </div>
              
              <div class="process-group">
                <div class="group-header">
                  <span class="group-label">裁剪处理</span>
                  <el-switch v-model="form.videoProcessing.enableCrop" />
                </div>
                <div class="group-controls">
                  <div class="process-item">
                    <span class="process-label">最小%</span>
                    <el-input-number v-model="form.videoProcessing.cropPercentMin" :min="0" :max="10" :step="0.1" />
                  </div>
                  <div class="process-item">
                    <span class="process-label">最大%</span>
                    <el-input-number v-model="form.videoProcessing.cropPercentMax" :min="0" :max="10" :step="0.1" />
                  </div>
                </div>
              </div>
            </div>
            
            <div class="process-row">
              <div class="process-item-half">
                <span class="process-label">粉色滤镜</span>
                <el-slider v-model="form.videoProcessing.pinkFilterStrength" :min="0" :max="1" :step="0.01" />
              </div>
              <div class="process-item-half">
                <span class="process-label">随机抽帧</span>
                <el-slider v-model="form.videoProcessing.frameDropStrength" :min="0" :max="0.2" :step="0.01" />
              </div>
            </div>
            <div class="process-inline">
              <el-switch v-model="form.videoProcessing.lightSweep" active-text="扫光" inactive-text="不扫光" />
              <div class="process-item-inline">
                <span class="process-label">并发数</span>
                <el-input-number v-model="form.videoProcessing.maxConcurrent" :min="1" :max="8" :step="1" />
              </div>
              <div class="process-item-inline">
                <span class="process-label">硬件模式</span>
                <el-select v-model="form.videoProcessing.hardwareMode" style="width: 100px">
                  <el-option label="CPU" value="cpu" />
                  <el-option label="GPU" value="gpu" />
                </el-select>
              </div>
            </div>
            <div class="field-tip">
              下载完成后自动生成处理后视频；原视频保留，处理后视频会在素材库显示“已处理”标签。
            </div>
            <div class="process-actions">
              <el-button type="info" plain @click="resetVideoProcessSettings">重置视频处理参数</el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <div class="actions">
        <el-button @click="loadSettings" :loading="loading">刷新</el-button>
        <el-button type="primary" @click="saveSettings" :loading="saving">
          保存配置
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { systemApi } from '@/api/system'

const loading = ref(false)
const saving = ref(false)
const uploadingCookie = ref(false)
const clearingCookie = ref(false)
const selectedCookieFile = ref(null)

// 默认视频处理参数
const defaultVideoProcessSettings = {
  autoProcess: true,
  enableTrimHead: true,
  trimHeadMin: 0.3,
  trimHeadMax: 1.2,
  enableTrimTail: true,
  trimTailMin: 0.3,
  trimTailMax: 1.2,
  enableSpeed: true,
  speedMin: 0.97,
  speedMax: 1.03,
  enableCrop: true,
  cropPercentMin: 1,
  cropPercentMax: 3,
  pinkFilterStrength: 0.12,
  lightSweep: true,
  frameDropStrength: 0.02,
  maxConcurrent: 4,
  hardwareMode: 'cpu',
}

const form = reactive({
  downloadProxy: '',
  youtubeCookieFileName: '',
  youtubeCookieConfigured: false,
  videoProcessing: {
    ...defaultVideoProcessSettings
  },
})

const applySettings = (data = {}) => {
  form.downloadProxy = data.downloadProxy || ''
  form.youtubeCookieFileName = data.youtubeCookieFileName || ''
  form.youtubeCookieConfigured = Boolean(data.youtubeCookieConfigured)
}

const applyVideoProcessSettings = (data = {}) => {
  // 将后端返回的字段名映射到前端期望的字段名
  const mappedData = {
    ...data,
    enableTrimHead: data.trimEnabled,
    enableTrimTail: data.trimEnabled,
    enableSpeed: data.speedEnabled,
    enableCrop: data.cropEnabled,
  }
  // 确保所有必要的字段都存在，包括新添加的开关字段
  Object.assign(form.videoProcessing, {
    ...defaultVideoProcessSettings,
    ...mappedData
  })
}

const loadSettings = async () => {
  loading.value = true
  try {
    const response = await systemApi.getSettings()
    applySettings(response.data)
    applyVideoProcessSettings(response.data.videoProcessing)
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '加载系统配置失败')
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  saving.value = true
  try {
    const videoProcessingPayload = {
      ...form.videoProcessing,
      trimEnabled: form.videoProcessing.enableTrimHead || form.videoProcessing.enableTrimTail,
      speedEnabled: form.videoProcessing.enableSpeed,
      cropEnabled: form.videoProcessing.enableCrop,
    }
    const response = await systemApi.saveSettings({
      downloadProxy: form.downloadProxy.trim(),
      videoProcessing: videoProcessingPayload,
    })
    applySettings(response.data)
    applyVideoProcessSettings(response.data.videoProcessing)
    ElMessage.success('系统配置已保存')
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '保存系统配置失败')
  } finally {
    saving.value = false
  }
}

const handleCookieSelect = (uploadFile) => {
  const file = uploadFile?.raw
  if (!file) {
    selectedCookieFile.value = null
    return
  }
  if (!file.name.toLowerCase().endsWith('.txt')) {
    selectedCookieFile.value = null
    ElMessage.error('仅支持上传 .txt 格式的 Netscape Cookie 文件')
    return
  }
  selectedCookieFile.value = file
}

const uploadCookie = async () => {
  if (!selectedCookieFile.value) {
    ElMessage.error('请先选择 Cookie 文件')
    return
  }

  const formData = new FormData()
  formData.append('file', selectedCookieFile.value)

  uploadingCookie.value = true
  try {
    const response = await systemApi.uploadYoutubeCookie(formData)
    applySettings(response.data)
    selectedCookieFile.value = null
    ElMessage.success('YouTube Cookie 上传成功')
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '上传 YouTube Cookie 失败')
  } finally {
    uploadingCookie.value = false
  }
}

const clearCookie = async () => {
  clearingCookie.value = true
  try {
    const response = await systemApi.deleteYoutubeCookie()
    applySettings(response.data)
    selectedCookieFile.value = null
    ElMessage.success('YouTube Cookie 已清除')
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '清除 YouTube Cookie 失败')
  } finally {
    clearingCookie.value = false
  }
}

const resetVideoProcessSettings = () => {
  Object.assign(form.videoProcessing, defaultVideoProcessSettings)
  ElMessage.success('视频处理参数已重置为默认值')
}

onMounted(() => {
  loadSettings()
})
</script>

<style lang="scss" scoped>
.system-settings {
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

.settings-card {
  padding: 24px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.cookie-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.video-process-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.process-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.process-group {
  background: #f9f9f9;
  border-radius: 6px;
  padding: 10px;
  border: 1px solid #f0f0f0;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.group-label {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.group-controls {
  display: flex;
  gap: 12px;
}

.process-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.process-item-half {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 10px;
}

.process-item-half:last-child {
  padding-right: 0;
}

.process-item-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.process-label {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
}

.process-row {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.process-inline {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.process-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-start;
}

.cookie-status {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.cookie-name {
  color: #303133;
  word-break: break-all;
}

.cookie-buttons {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}

.cookie-upload {
  margin-right: 0;
}

.field-tip {
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.selected-file {
  color: #606266;
  font-size: 13px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

@media (max-width: 900px) {
  .process-groups {
    grid-template-columns: 1fr;
  }

  .process-row {
    flex-direction: column;
    gap: 10px;
  }

  .process-item-half {
    padding-right: 0;
  }
}
</style>