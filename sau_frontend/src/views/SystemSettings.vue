<template>
  <div class="system-settings">
    <div class="page-header">
      <h1>系统配置</h1>
      <p>管理 YouTube 下载使用的全局代理和 Cookie 文件。</p>
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

            <div class="cookie-actions">
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
      </el-form>

      <div class="actions">
        <el-button @click="loadSettings" :loading="loading">刷新</el-button>
        <el-button type="primary" @click="saveSettings" :loading="saving">
          保存代理配置
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

const form = reactive({
  downloadProxy: '',
  youtubeCookieFileName: '',
  youtubeCookieConfigured: false,
})

const applySettings = (data = {}) => {
  form.downloadProxy = data.downloadProxy || ''
  form.youtubeCookieFileName = data.youtubeCookieFileName || ''
  form.youtubeCookieConfigured = Boolean(data.youtubeCookieConfigured)
}

const loadSettings = async () => {
  loading.value = true
  try {
    const response = await systemApi.getSettings()
    applySettings(response.data)
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
    const response = await systemApi.saveSettings({
      downloadProxy: form.downloadProxy.trim(),
    })
    applySettings(response.data)
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
  gap: 12px;
  width: 100%;
}

.cookie-status {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.cookie-name {
  color: #303133;
  word-break: break-all;
}

.cookie-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
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
  margin-top: 24px;
}
</style>
