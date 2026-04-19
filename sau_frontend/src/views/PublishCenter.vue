<template>
  <div class="publish-center">
    <section v-if="batchMode" class="task-rail">
      <div class="task-rail-header">
        <div>
          <h2>任务工作区</h2>
          <p>每个任务独立维护素材、平台和标题，可并行准备后统一批量发布。</p>
        </div>
        <div class="task-rail-actions">
          <el-button class="ghost-action" @click="addTab">
            <el-icon><Plus /></el-icon>
            新建任务
          </el-button>
          <el-button type="success" class="primary-action" @click="batchPublish" :loading="batchPublishing">
            批量发布
          </el-button>
        </div>
      </div>

      <div class="task-list">
        <button
          v-for="tab in tabs"
          :key="tab.name"
          type="button"
          :class="['task-chip', { active: activeTab === tab.name }]"
          @click="activeTab = tab.name"
        >
          <span class="task-status" :data-state="getTabState(tab)"></span>
          <div class="task-chip-main">
            <div class="task-chip-title">{{ tab.label }}</div>
            <div class="task-chip-meta">
              <span>{{ tab.fileList.length }} 素材</span>
              <span>{{ tab.selectedPlatforms.length }} 平台</span>
              <span>{{ getTabStateLabel(tab) }}</span>
            </div>
          </div>
          <el-icon
            v-if="tabs.length > 1"
            class="close-icon"
            @click.stop="removeTab(tab.name)"
          >
            <Close />
          </el-icon>
        </button>
      </div>
    </section>

    <section v-if="currentActiveTab" class="workspace-shell">
      <el-alert
        v-if="currentActiveTab.publishStatus"
        :title="currentActiveTab.publishStatus.message"
        :type="currentActiveTab.publishStatus.type"
        :closable="false"
        show-icon
        class="workspace-alert"
      />

      <div class="top-action-dock">
        <div class="action-dock-copy">
          <strong>{{ batchMode ? currentActiveTab.label : '当前发布任务' }}</strong>
          <span>{{ currentActiveTab.publishing ? '正在发布，请稍候…' : '准备就绪后即可直接发布当前任务' }}</span>
        </div>
        <div class="top-action-center">
          <div class="batch-switch">
            <span class="top-action-meta label">批量发布</span>
            <el-switch v-model="batchMode" />
          </div>
          <span class="top-action-meta">{{ currentActiveTab.fileList.length }} 素材</span>
          <span class="top-action-meta">{{ currentActiveTab.selectedPlatforms.length }} 平台</span>
          <span class="top-action-meta">{{ currentActiveTab.selectedAccounts.length }} 账号</span>
        </div>
        <div class="action-dock-buttons">
          <el-button @click="cancelPublish(currentActiveTab)">取消</el-button>
          <el-button
            type="primary"
            :disabled="!isPublishReady(currentActiveTab)"
            :loading="currentActiveTab.publishing || false"
            @click="confirmPublish(currentActiveTab)"
          >
            {{ currentActiveTab.publishing ? '发布中...' : '发布当前任务' }}
          </el-button>
        </div>
      </div>

      <div class="workspace-grid">
        <div class="workspace-main">
          <article class="panel material-panel">
            <div class="panel-header">
              <div>
                <h3>素材</h3>
                <p>先确定视频素材，再编辑标题与话题内容。</p>
              </div>
              <div class="panel-actions">
                <el-button type="primary" @click="selectLocalUpload(currentActiveTab)">
                  <el-icon><Upload /></el-icon>
                  导入本地视频
                </el-button>
                <el-button class="secondary-button" @click="selectMaterialLibrary(currentActiveTab)">
                  <el-icon><Folder /></el-icon>
                  从素材库选择
                </el-button>
              </div>
            </div>

            <div v-if="currentActiveTab.fileList.length" class="material-card-list">
              <div
                v-for="(file, index) in currentActiveTab.fileList"
                :key="`${file.path}-${index}`"
                class="material-card"
              >
                <div class="material-card-body">
                  <div class="material-card-name">{{ file.name }}</div>
                  <div class="material-card-meta">
                    <span>{{ formatFileSize(file.size) }}</span>
                    <span>{{ inferMaterialSource(file.path) }}</span>
                  </div>
                </div>
                <div class="material-card-actions">
                  <el-link :href="file.url" target="_blank" type="primary">预览</el-link>
                  <el-button text type="danger" @click="removeFile(currentActiveTab, index)">移除</el-button>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-illustration">+</div>
              <div>
                <h4>先添加视频素材</h4>
                <p>支持本地上传或直接从素材库带入，带入后标题会自动填充。</p>
              </div>
            </div>
          </article>

          <article class="panel content-panel">
            <div class="panel-header">
              <div>
                <h3>内容编辑</h3>
                <p>围绕当前任务集中维护标题和话题，减少跨区切换。</p>
              </div>
              <div class="content-hint">
                <span>来源标题会自动带入，你可以继续手动修改。</span>
              </div>
            </div>

            <div class="field-block">
              <div class="field-label-row">
                <label class="field-label">标题</label>
                <span class="field-tip">建议直接写最终发布标题，当前平台共用这份文案。</span>
              </div>
              <el-input
                v-model="currentActiveTab.title"
                type="textarea"
                :rows="4"
                maxlength="100"
                show-word-limit
                placeholder="请输入标题"
                class="title-input"
              />
            </div>

            <div class="field-block">
              <div class="field-label-row">
                <label class="field-label">话题</label>
                <span class="field-tip">点击推荐话题即可切换，也可以直接输入自定义话题。</span>
              </div>

              <div class="topic-composer">
                <el-input
                  v-model="customTopic"
                  placeholder="输入自定义话题，不需要带 #"
                  @keyup.enter="addCustomTopicToTab(currentActiveTab)"
                >
                  <template #prepend>#</template>
                </el-input>
                <el-button type="primary" @click="addCustomTopicToTab(currentActiveTab)">添加话题</el-button>
              </div>

              <div class="topic-selected">
                <el-tag
                  v-for="(topic, index) in currentActiveTab.selectedTopics"
                  :key="`${topic}-${index}`"
                  closable
                  effect="plain"
                  @close="removeTopic(currentActiveTab, index)"
                >
                  #{{ topic }}
                </el-tag>
                <span v-if="!currentActiveTab.selectedTopics.length" class="placeholder-line">还没有选择话题</span>
              </div>

              <div class="topic-suggestions">
                <button
                  v-for="topic in recommendedTopics"
                  :key="topic"
                  type="button"
                  :class="['topic-suggestion', { active: currentActiveTab.selectedTopics.includes(topic) }]"
                  @click="toggleRecommendedTopic(currentActiveTab, topic)"
                >
                  #{{ topic }}
                </button>
              </div>
            </div>
          </article>
        </div>

        <aside class="workspace-side">
          <article class="panel platform-panel">
            <div class="panel-header compact">
              <div>
                <h3>平台与账号</h3>
                <p>按平台查看当前绑定账号，缺失项会直接高亮。</p>
              </div>
              <el-button class="secondary-button" @click="openAccountDialog(currentActiveTab)">统一选择账号</el-button>
            </div>

            <div class="platform-grid">
              <div
                v-for="platform in platforms"
                :key="platform.key"
                :class="[
                  'platform-card',
                  {
                    selected: currentActiveTab.selectedPlatforms.includes(platform.key),
                    warning: currentActiveTab.selectedPlatforms.includes(platform.key) && !hasPlatformAccounts(currentActiveTab, platform.key)
                  }
                ]"
              >
                <div class="platform-card-head">
                  <el-checkbox
                    :model-value="currentActiveTab.selectedPlatforms.includes(platform.key)"
                    @change="togglePlatformSelection(currentActiveTab, platform.key)"
                  >
                    <span class="platform-name">{{ platform.name }}</span>
                  </el-checkbox>
                  <span class="platform-inline-summary">{{ getPlatformAccountSummary(currentActiveTab, platform.key) }}</span>
                </div>
              </div>
            </div>
          </article>

          <article v-if="currentActiveTab.selectedPlatforms.includes(3)" class="panel product-panel">
            <div class="panel-header compact">
              <div>
                <h3>抖音商品信息</h3>
              </div>
            </div>

            <div class="stack-fields">
              <el-input v-model="currentActiveTab.productTitle" placeholder="请输入商品名称" maxlength="200" />
              <el-input v-model="currentActiveTab.productLink" placeholder="请输入商品链接" maxlength="200" />
            </div>
          </article>

          <article class="panel settings-panel">
            <div class="panel-header compact">
              <div>
                <h3>发布设置</h3>
              </div>
            </div>

            <div class="settings-list">
              <div class="setting-row">
                <div>
                  <div class="setting-title">声明原创</div>
                  <div class="setting-desc">默认关闭，按当前任务整体生效。</div>
                </div>
                <el-switch v-model="currentActiveTab.isOriginal" />
              </div>

              <div v-if="currentActiveTab.selectedPlatforms.includes(2)" class="setting-row">
                <div>
                  <div class="setting-title">视频号草稿</div>
                  <div class="setting-desc">开启后仅保存到视频号草稿，适合手机继续编辑。</div>
                </div>
                <el-switch v-model="currentActiveTab.isDraft" />
              </div>

              <div class="setting-row">
                <div>
                  <div class="setting-title">定时发布</div>
                  <div class="setting-desc">关闭时立即发布，开启后显示时间与天数配置。</div>
                </div>
                <el-switch v-model="currentActiveTab.scheduleEnabled" />
              </div>
            </div>

            <div v-if="currentActiveTab.scheduleEnabled" class="schedule-card">
              <div class="schedule-field">
                <span class="schedule-label">每天发布数</span>
                <el-select v-model="currentActiveTab.videosPerDay" @change="syncDailyTimes(currentActiveTab)">
                  <el-option v-for="num in 55" :key="num" :label="num" :value="num" />
                </el-select>
              </div>

              <div class="schedule-field column">
                <div class="schedule-inline-head">
                  <span class="schedule-label">发布时间</span>
                  <el-button
                    v-if="currentActiveTab.dailyTimes.length < currentActiveTab.videosPerDay"
                    text
                    type="primary"
                    @click="addScheduleTime(currentActiveTab)"
                  >
                    添加时间
                  </el-button>
                </div>
                <div class="time-list">
                  <div
                    v-for="(time, index) in currentActiveTab.dailyTimes"
                    :key="`${time}-${index}`"
                    class="time-row"
                  >
                    <el-time-select
                      v-model="currentActiveTab.dailyTimes[index]"
                      start="00:00"
                      step="00:30"
                      end="23:30"
                      placeholder="选择时间"
                    />
                    <el-button
                      v-if="currentActiveTab.dailyTimes.length > 1"
                      text
                      type="danger"
                      @click="removeScheduleTime(currentActiveTab, index)"
                    >
                      删除
                    </el-button>
                  </div>
                </div>
              </div>

              <div class="schedule-field">
                <span class="schedule-label">开始日期</span>
                <el-select v-model="currentActiveTab.startDays">
                  <el-option label="明天" :value="0" />
                  <el-option label="后天" :value="1" />
                </el-select>
              </div>
            </div>
          </article>

          <article class="panel summary-panel">
            <div class="panel-header compact">
              <div>
                <h3>发布摘要</h3>
              </div>
            </div>

            <div class="summary-grid">
              <div class="summary-item">
                <span>素材</span>
                <strong>{{ currentActiveTab.fileList.length }}</strong>
              </div>
              <div class="summary-item">
                <span>平台</span>
                <strong>{{ currentActiveTab.selectedPlatforms.length }}</strong>
              </div>
              <div class="summary-item">
                <span>账号</span>
                <strong>{{ currentActiveTab.selectedAccounts.length }}</strong>
              </div>
              <div class="summary-item">
                <span>话题</span>
                <strong>{{ currentActiveTab.selectedTopics.length }}</strong>
              </div>
            </div>

            <div class="summary-line">
              <span class="summary-key">发布模式</span>
              <span class="summary-value">{{ currentActiveTab.scheduleEnabled ? '定时发布' : '立即发布' }}</span>
            </div>
            <div class="summary-line">
              <span class="summary-key">当前平台</span>
              <span class="summary-value">{{ getSelectedPlatformNames(currentActiveTab) }}</span>
            </div>

            <div class="validation-list">
              <template v-if="getValidationIssues(currentActiveTab).length">
                <div v-for="issue in getValidationIssues(currentActiveTab)" :key="issue" class="validation-item">
                  {{ issue }}
                </div>
              </template>
              <div v-else class="validation-item success">当前任务已具备发布条件</div>
            </div>
          </article>
        </aside>
      </div>
    </section>

    <el-dialog
      v-model="localUploadVisible"
      title="本地上传"
      width="600px"
      class="local-upload-dialog"
    >
      <el-upload
        class="video-upload"
        drag
        :auto-upload="true"
        :action="`${apiBaseUrl}/upload`"
        :on-success="(response, file) => handleUploadSuccess(response, file, currentUploadTab)"
        :on-error="handleUploadError"
        multiple
        accept="video/*"
        :headers="authHeaders"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">
          将视频文件拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">支持 MP4、AVI 等视频格式，可上传多个文件</div>
        </template>
      </el-upload>
    </el-dialog>

    <el-dialog
      v-model="materialLibraryVisible"
      title="选择素材"
      width="960px"
      top="5vh"
      class="material-library-dialog"
    >
      <div class="material-library-content">
        <el-checkbox-group v-model="selectedMaterials">
          <div class="material-list">
            <div v-for="material in materials" :key="material.id" class="material-item">
              <el-checkbox :label="material.id" class="material-checkbox">
                <div class="material-info">
                  <div class="material-name">{{ material.video_title_zh || material.video_title || extractChineseTitle(material.filename) }}</div>
                  <div
                    v-if="material.video_title && material.video_title !== material.video_title_zh"
                    class="material-original-title"
                  >
                    {{ material.video_title }}
                  </div>
                  <div class="material-details">
                    <span>{{ material.filesize }}MB</span>
                    <span>{{ material.upload_time }}</span>
                  </div>
                </div>
              </el-checkbox>
            </div>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="materialLibraryVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmMaterialSelection">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="accountDialogVisible"
      title="选择账号"
      width="620px"
      class="account-dialog"
    >
      <div class="account-dialog-content">
        <el-checkbox-group v-model="tempSelectedAccounts">
          <div class="account-list">
            <el-checkbox
              v-for="account in availableAccounts"
              :key="account.id"
              :label="account.id"
              class="account-item"
            >
              <div class="account-info">
                <span class="account-name">{{ account.name }}</span>
                <span class="account-platform">{{ account.platform }}</span>
              </div>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="accountDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmAccountSelection">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="batchPublishDialogVisible"
      title="批量发布进度"
      width="520px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <div class="publish-progress">
        <el-progress :percentage="publishProgress" :status="publishProgress === 100 ? 'success' : ''" />
        <div v-if="currentPublishingTab" class="current-publishing">
          正在发布：{{ currentPublishingTab.label }}
        </div>

        <div v-if="publishResults.length > 0" class="publish-results">
          <div
            v-for="(result, index) in publishResults"
            :key="index"
            :class="['result-item', result.status]"
          >
            <el-icon v-if="result.status === 'success'"><Check /></el-icon>
            <el-icon v-else-if="result.status === 'error'"><Close /></el-icon>
            <el-icon v-else><InfoFilled /></el-icon>
            <span class="label">{{ result.label }}</span>
            <span class="message">{{ result.message }}</span>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelBatchPublish" :disabled="publishProgress === 100">取消发布</el-button>
          <el-button
            v-if="publishProgress === 100"
            type="primary"
            @click="batchPublishDialogVisible = false"
          >
            关闭
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Upload, Plus, Close, Folder, Check, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { materialApi } from '@/api/material'
import { http } from '@/utils/request'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

const authHeaders = computed(() => ({
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`
}))

const activeTab = ref('tab1')
let tabCounter = 1
const batchMode = ref(false)

const appStore = useAppStore()
const accountStore = useAccountStore()

const localUploadVisible = ref(false)
const materialLibraryVisible = ref(false)
const currentUploadTab = ref(null)
const selectedMaterials = ref([])
const materials = computed(() => appStore.materials)

const batchPublishing = ref(false)
const currentPublishingTab = ref(null)
const publishProgress = ref(0)
const publishResults = ref([])
const isCancelled = ref(false)

const accountDialogVisible = ref(false)
const tempSelectedAccounts = ref([])
const currentTab = ref(null)
const customTopic = ref('')

const platforms = [
  { key: 3, name: '抖音' },
  { key: 4, name: '快手' },
  { key: 2, name: '视频号' },
  { key: 1, name: '小红书' }
]

const defaultTabInit = {
  name: 'tab1',
  label: '发布1',
  fileList: [],
  displayFileList: [],
  selectedAccounts: [],
  selectedPlatforms: [3, 1, 4],
  title: '',
  productLink: '',
  productTitle: '',
  selectedTopics: [],
  scheduleEnabled: false,
  videosPerDay: 1,
  dailyTimes: ['10:00'],
  startDays: 0,
  publishStatus: null,
  publishing: false,
  isDraft: false,
  isOriginal: false
}

const recommendedTopics = [
  '魔兽世界', '正式服', 'WOW', '游戏', '电影', '音乐', '美食', '旅行', '文化',
  '科技', '生活', '娱乐', '体育', '教育', '艺术', '健康', '时尚', '美妆', '摄影', '宠物', '汽车'
]

const makeNewTab = () => {
  try {
    return typeof structuredClone === 'function'
      ? structuredClone(defaultTabInit)
      : JSON.parse(JSON.stringify(defaultTabInit))
  } catch (error) {
    return JSON.parse(JSON.stringify(defaultTabInit))
  }
}

const tabs = reactive([makeNewTab()])

const currentActiveTab = computed(() => tabs.find((tab) => tab.name === activeTab.value) || tabs[0] || null)

const workspaceMetrics = computed(() => ({
  tabs: tabs.length,
  ready: tabs.filter((tab) => getValidationIssues(tab).length === 0 && tab.fileList.length > 0).length,
  materials: tabs.reduce((sum, tab) => sum + tab.fileList.length, 0),
  scheduled: tabs.filter((tab) => tab.scheduleEnabled).length
}))

const availableAccounts = computed(() => {
  const platformNames = currentTab.value ? currentTab.value.selectedPlatforms.map(getPlatformName) : []
  return accountStore.accounts.filter((account) => platformNames.includes(account.platform))
})

const getPlatformName = (platformId) => {
  const platformMap = {
    3: '抖音',
    2: '视频号',
    1: '小红书',
    4: '快手'
  }
  return platformMap[platformId] || ''
}

const getPlatformAccounts = (platformId, allAccounts) => {
  const platformName = getPlatformName(platformId)
  return allAccounts.filter((accountId) => {
    const account = accountStore.accounts.find((item) => item.id === accountId)
    return account && account.platform === platformName
  })
}

const hasPlatformAccounts = (tab, platformId) => getPlatformAccounts(platformId, tab.selectedAccounts).length > 0

const getFirstAccountForPlatform = (platformId) => {
  const platformName = getPlatformName(platformId)
  const accounts = accountStore.accounts.filter((account) => account.platform === platformName)
  return accounts.length > 0 ? accounts[0].id : null
}

const handlePlatformChange = (tab) => {
  const selectedAccounts = []
  tab.selectedPlatforms.forEach((platformId) => {
    const firstAccount = getFirstAccountForPlatform(platformId)
    if (firstAccount) {
      selectedAccounts.push(firstAccount)
    }
  })
  tab.selectedAccounts = selectedAccounts
}

const togglePlatformSelection = (tab, platformId) => {
  const hasSelected = tab.selectedPlatforms.includes(platformId)
  const next = hasSelected
    ? tab.selectedPlatforms.filter((item) => item !== platformId)
    : [...tab.selectedPlatforms, platformId]
  tab.selectedPlatforms = platforms.map((platform) => platform.key).filter((key) => next.includes(key))
  handlePlatformChange(tab)
}

const extractChineseTitle = (filename) => {
  const nameWithoutExt = filename.replace(/\.[^/.]+$/, '')
  const chineseMatch = nameWithoutExt.match(/[\u4e00-\u9fa5]+/g)
  if (chineseMatch) {
    return chineseMatch.join(' ')
  }
  return nameWithoutExt
}

const buildMaterialFileInfo = (material) => ({
  name: material.filename,
  url: materialApi.getMaterialPreviewUrl(material.file_path.split('/').pop()),
  path: material.file_path,
  size: (material.filesize || 0) * 1024 * 1024,
  type: 'video/mp4'
})

const resolveMaterialTitle = (material) => {
  if (material.video_title_zh) return material.video_title_zh
  if (material.video_title) return material.video_title
  return extractChineseTitle(material.filename)
}

const applyMaterialsToTab = (tab, materialList) => {
  if (!tab || !Array.isArray(materialList) || materialList.length === 0) return 0

  let addedCount = 0
  materialList.forEach((material) => {
    if (!material) return
    const fileInfo = buildMaterialFileInfo(material)
    const exists = tab.fileList.some((file) => file.path === fileInfo.path)
    if (!exists) {
      tab.fileList.push(fileInfo)
      addedCount += 1
    }
  })

  tab.displayFileList = [...tab.fileList.map((item) => ({
    name: item.name,
    url: item.url
  }))]

  if (!tab.title && materialList[0]) {
    tab.title = resolveMaterialTitle(materialList[0])
  }

  return addedCount
}

const createTab = () => {
  tabCounter += 1
  const newTab = makeNewTab()
  newTab.name = `tab${tabCounter}`
  newTab.label = `发布${tabCounter}`
  handlePlatformChange(newTab)
  tabs.push(newTab)
  activeTab.value = newTab.name
  return newTab
}

const getOrCreateTargetTab = () => {
  const tab = currentActiveTab.value
  if (tab && tab.fileList.length === 0 && !tab.title) {
    return tab
  }
  return createTab()
}

const getTabState = (tab) => {
  if (tab.publishing) return 'publishing'
  if (tab.publishStatus?.type === 'success') return 'success'
  if (tab.publishStatus?.type === 'error') return 'error'
  if (tab.fileList.length > 0 || tab.title || tab.selectedTopics.length > 0) return 'editing'
  return 'idle'
}

const getTabStateLabel = (tab) => {
  const state = getTabState(tab)
  if (state === 'publishing') return '发布中'
  if (state === 'success') return '已完成'
  if (state === 'error') return '失败'
  if (state === 'editing') return '编辑中'
  return '空白'
}

const getSelectedPlatformNames = (tab) => {
  if (!tab.selectedPlatforms.length) return '未选择'
  return tab.selectedPlatforms.map(getPlatformName).join('、')
}

const getPlatformAccountSummary = (tab, platformId) => {
  if (!tab.selectedPlatforms.includes(platformId)) return '未启用'
  const accountNames = getPlatformAccounts(platformId, tab.selectedAccounts).map(getAccountDisplayName)
  if (accountNames.length) return accountNames.join('、')
  return '未绑定账号'
}

const getValidationIssues = (tab) => {
  const issues = []
  if (!tab.fileList.length) issues.push('请先添加视频素材')
  if (!tab.title.trim()) issues.push('请填写标题')
  if (!tab.selectedPlatforms.length) issues.push('请至少选择一个平台')
  const missingAccounts = tab.selectedPlatforms
    .filter((platformId) => !hasPlatformAccounts(tab, platformId))
    .map(getPlatformName)
  if (missingAccounts.length) {
    issues.push(`${missingAccounts.join('、')} 未绑定账号`)
  }
  return issues
}

const isPublishReady = (tab) => getValidationIssues(tab).length === 0 && !tab.publishing

const formatFileSize = (size) => `${(size / 1024 / 1024).toFixed(2)} MB`

const inferMaterialSource = (path) => (String(path || '').includes('http') ? '远程素材' : '本地素材')

const addTab = () => {
  createTab()
}

const removeTab = (tabName) => {
  const index = tabs.findIndex((tab) => tab.name === tabName)
  if (index > -1) {
    tabs.splice(index, 1)
    if (activeTab.value === tabName && tabs.length > 0) {
      activeTab.value = tabs[0].name
    }
  }
}

const handleUploadSuccess = (response, file, tab) => {
  if (response.code === 200) {
    const filePath = response.data.path || response.data
    const filename = filePath.split('/').pop()
    const fileInfo = {
      name: file.name,
      url: materialApi.getMaterialPreviewUrl(filename),
      path: filePath,
      size: file.size,
      type: file.type
    }
    tab.fileList.push(fileInfo)
    tab.displayFileList = [...tab.fileList.map((item) => ({
      name: item.name,
      url: item.url
    }))]
    if (!tab.title) {
      const chineseTitle = extractChineseTitle(file.name)
      if (chineseTitle) {
        tab.title = chineseTitle
      }
    }
    ElMessage.success('文件上传成功')
  } else {
    ElMessage.error(response.msg || '上传失败')
  }
}

const handleUploadError = () => {
  ElMessage.error('文件上传失败')
}

const removeFile = (tab, index) => {
  tab.fileList.splice(index, 1)
  tab.displayFileList = [...tab.fileList.map((item) => ({
    name: item.name,
    url: item.url
  }))]
  ElMessage.success('文件删除成功')
}

const normalizeTopic = (topic) => topic.trim().replace(/^#/, '')

const addCustomTopicToTab = (tab) => {
  if (!tab) return
  const topic = normalizeTopic(customTopic.value)
  if (!topic) {
    ElMessage.warning('请输入话题内容')
    return
  }
  if (tab.selectedTopics.includes(topic)) {
    ElMessage.warning('话题已存在')
    return
  }
  tab.selectedTopics.push(topic)
  customTopic.value = ''
}

const toggleRecommendedTopic = (tab, topic) => {
  if (!tab) return
  const index = tab.selectedTopics.indexOf(topic)
  if (index > -1) {
    tab.selectedTopics.splice(index, 1)
  } else {
    tab.selectedTopics.push(topic)
  }
}

const removeTopic = (tab, index) => {
  tab.selectedTopics.splice(index, 1)
}

const openAccountDialog = (tab) => {
  currentTab.value = tab
  tempSelectedAccounts.value = [...tab.selectedAccounts]
  accountDialogVisible.value = true
}

const confirmAccountSelection = () => {
  if (currentTab.value) {
    currentTab.value.selectedAccounts = [...tempSelectedAccounts.value]
  }
  accountDialogVisible.value = false
  currentTab.value = null
  ElMessage.success('账号选择完成')
}

const removeAccount = (tab, index) => {
  tab.selectedAccounts.splice(index, 1)
}

const getAccountDisplayName = (accountId) => {
  const account = accountStore.accounts.find((item) => item.id === accountId)
  return account ? account.name : accountId
}

const syncDailyTimes = (tab) => {
  const target = Math.max(1, tab.videosPerDay || 1)
  while (tab.dailyTimes.length < target) {
    tab.dailyTimes.push('10:00')
  }
  if (tab.dailyTimes.length > target) {
    tab.dailyTimes.splice(target)
  }
}

const addScheduleTime = (tab) => {
  if (tab.dailyTimes.length < tab.videosPerDay) {
    tab.dailyTimes.push('10:00')
  }
}

const removeScheduleTime = (tab, index) => {
  if (tab.dailyTimes.length > 1) {
    tab.dailyTimes.splice(index, 1)
  }
}

const cancelPublish = () => {
  ElMessage.info('已取消发布')
}

const confirmPublish = async (tab) => {
  if (tab.publishing) {
    throw new Error('正在发布中，请稍候...')
  }

  tab.publishing = true

  if (tab.fileList.length === 0) {
    ElMessage.error('请先上传视频文件')
    tab.publishing = false
    throw new Error('请先上传视频文件')
  }
  if (!tab.title.trim()) {
    ElMessage.error('请输入标题')
    tab.publishing = false
    throw new Error('请输入标题')
  }
  if (!tab.selectedPlatforms || tab.selectedPlatforms.length === 0) {
    ElMessage.error('请选择发布平台')
    tab.publishing = false
    throw new Error('请选择发布平台')
  }
  if (tab.selectedAccounts.length === 0) {
    ElMessage.error('请选择发布账号')
    tab.publishing = false
    throw new Error('请选择发布账号')
  }

  const publishPromises = tab.selectedPlatforms.map((platformId) => {
    const platformName = getPlatformName(platformId)
    const platformAccounts = tab.selectedAccounts.filter((accountId) => {
      const account = accountStore.accounts.find((item) => item.id === accountId)
      return account && account.platform === platformName
    })

    const publishData = {
      type: platformId,
      title: tab.title,
      tags: tab.selectedTopics,
      fileList: tab.fileList.map((file) => file.path),
      accountList: platformAccounts.map((accountId) => {
        const account = accountStore.accounts.find((item) => item.id === accountId)
        return account ? account.filePath : accountId
      }),
      enableTimer: tab.scheduleEnabled ? 1 : 0,
      videosPerDay: tab.scheduleEnabled ? tab.videosPerDay || 1 : 1,
      dailyTimes: tab.scheduleEnabled ? tab.dailyTimes || ['10:00'] : ['10:00'],
      startDays: tab.scheduleEnabled ? tab.startDays || 0 : 0,
      category: tab.isOriginal ? 1 : 0,
      productLink: tab.productLink.trim() || '',
      productTitle: tab.productTitle.trim() || '',
      isDraft: tab.isDraft
    }

    return http.post('/postVideo', publishData)
  })

  try {
    const results = await Promise.all(publishPromises)
    tab.publishStatus = {
      message: `发布成功，共发布到 ${results.length} 个平台`,
      type: 'success'
    }
    tab.fileList = []
    tab.displayFileList = []
    tab.title = ''
    tab.selectedTopics = []
    tab.selectedAccounts = []
    tab.scheduleEnabled = false
  } catch (error) {
    console.error('发布错误:', error)
    tab.publishStatus = {
      message: `发布失败：${error.message || '请检查网络连接'}`,
      type: 'error'
    }
    throw error
  } finally {
    tab.publishing = false
  }
}

const selectLocalUpload = (tab) => {
  currentUploadTab.value = tab
  localUploadVisible.value = true
}

const selectMaterialLibrary = async (tab) => {
  currentUploadTab.value = tab

  try {
    const response = await materialApi.getAllMaterials()
    appStore.setMaterials(response.data || [])
  } catch (error) {
    console.error('获取素材列表出错:', error)
    ElMessage.error('获取素材列表失败')
    return
  }

  selectedMaterials.value = []
  materialLibraryVisible.value = true
}

const confirmMaterialSelection = () => {
  if (selectedMaterials.value.length === 0) {
    ElMessage.warning('请选择至少一个素材')
    return
  }

  if (currentUploadTab.value) {
    const materialList = selectedMaterials.value
      .map((materialId) => materials.value.find((item) => item.id === materialId))
      .filter(Boolean)
    applyMaterialsToTab(currentUploadTab.value, materialList)
  }

  const addedCount = selectedMaterials.value.length
  materialLibraryVisible.value = false
  selectedMaterials.value = []
  currentUploadTab.value = null
  ElMessage.success(`已添加 ${addedCount} 个素材`)
}

const cancelBatchPublish = () => {
  isCancelled.value = true
  ElMessage.info('正在取消发布...')
}

const batchPublish = async () => {
  if (batchPublishing.value) return

  batchPublishing.value = true
  currentPublishingTab.value = null
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  batchPublishDialogVisible.value = true

  try {
    for (let index = 0; index < tabs.length; index += 1) {
      if (isCancelled.value) {
        publishResults.value.push({
          label: tabs[index].label,
          status: 'cancelled',
          message: '已取消'
        })
        continue
      }

      const tab = tabs[index]
      currentPublishingTab.value = tab
      publishProgress.value = Math.floor((index / tabs.length) * 100)

      try {
        await confirmPublish(tab)
        publishResults.value.push({
          label: tab.label,
          status: 'success',
          message: '发布成功'
        })
      } catch (error) {
        publishResults.value.push({
          label: tab.label,
          status: 'error',
          message: error.message
        })
      }
    }

    publishProgress.value = 100

    const successCount = publishResults.value.filter((item) => item.status === 'success').length
    const failCount = publishResults.value.filter((item) => item.status === 'error').length
    const cancelCount = publishResults.value.filter((item) => item.status === 'cancelled').length

    if (isCancelled.value) {
      ElMessage.warning(`发布已取消：${successCount}个成功，${failCount}个失败，${cancelCount}个未执行`)
    } else if (failCount > 0) {
      ElMessage.error(`发布完成：${successCount}个成功，${failCount}个失败`)
    } else {
      ElMessage.success('所有Tab发布成功')
      setTimeout(() => {
        batchPublishDialogVisible.value = false
      }, 1000)
    }
  } catch (error) {
    console.error('批量发布出错:', error)
    ElMessage.error('批量发布出错，请重试')
  } finally {
    batchPublishing.value = false
    isCancelled.value = false
  }
}

const batchPublishDialogVisible = ref(false)

setTimeout(() => {
  handlePlatformChange(tabs[0])
}, 0)

onMounted(async () => {
  const pendingMaterials = appStore.consumePendingPublishMaterials()
  if (!pendingMaterials.length) return

  try {
    if (!materials.value.length) {
      const response = await materialApi.getAllMaterials()
      appStore.setMaterials(response.data || [])
    }

    const normalizedMaterials = pendingMaterials.map((pendingMaterial) =>
      materials.value.find((material) => material.id === pendingMaterial.id) || pendingMaterial
    )
    const targetTab = getOrCreateTargetTab()
    const addedCount = applyMaterialsToTab(targetTab, normalizedMaterials)
    if (addedCount > 0) {
      ElMessage.success(`已带入 ${addedCount} 个素材到发布页`)
    }
  } catch (error) {
    console.error('处理待发布素材失败:', error)
    ElMessage.error('带入素材到发布页失败')
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-center {
  --surface: #ffffff;
  --surface-soft: #f5f8ff;
  --surface-muted: #eef3fb;
  --border-soft: rgba(17, 24, 39, 0.08);
  --border-strong: rgba(47, 109, 255, 0.22);
  --text-strong: #14213d;
  --text-muted: #5c6b84;
  --accent: #2f6dff;
  --accent-soft: rgba(47, 109, 255, 0.1);
  --success-soft: rgba(73, 190, 120, 0.14);
  --danger-soft: rgba(240, 87, 87, 0.12);
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--text-strong);
}

.task-rail,
.workspace-shell {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: 24px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.06);
}

.task-rail {
  padding: 14px 18px;
  background:
    linear-gradient(180deg, rgba(47, 109, 255, 0.03), transparent 70%),
    #ffffff;
}

.task-rail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.task-rail-header h2 {
  margin: 0 0 4px;
  font-size: 16px;
}

.task-rail-header p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.task-rail-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ghost-action,
.primary-action {
  height: 34px;
  padding: 0 12px;
  border-radius: 10px;
}

.task-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}

.task-chip {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 14px;
  background: #fff;
  cursor: pointer;
  transition: 0.25s ease;
  text-align: left;
}

.task-chip:hover {
  transform: translateY(-1px);
  border-color: var(--border-strong);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.08);
}

.task-chip.active {
  border-color: rgba(47, 109, 255, 0.26);
  background: linear-gradient(180deg, rgba(47, 109, 255, 0.09), rgba(47, 109, 255, 0.02));
}

.task-status {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #b8c4d9;
}

.task-status[data-state='editing'] {
  background: #ffb020;
}

.task-status[data-state='publishing'] {
  background: #2f6dff;
}

.task-status[data-state='success'] {
  background: #1f9d57;
}

.task-status[data-state='error'] {
  background: #f05757;
}

.task-chip-main {
  flex: 1;
  min-width: 0;
}

.task-chip-title {
  font-weight: 700;
  font-size: 13px;
}

.task-chip-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 11px;
}

.close-icon {
  padding: 6px;
  border-radius: 50%;
  color: #7f8aa3;
}

.close-icon:hover {
  background: rgba(15, 23, 42, 0.06);
}

.workspace-shell {
  padding: 14px;
}

.workspace-alert {
  margin-bottom: 10px;
}

.top-action-dock {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: linear-gradient(135deg, #10203b 0%, #16345f 100%);
  color: #fff;
  box-shadow: 0 12px 24px rgba(16, 32, 59, 0.18);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(320px, 0.92fr);
  gap: 12px;
}

.workspace-main,
.workspace-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.workspace-side {
  position: sticky;
  top: 20px;
  align-self: start;
}

.panel {
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: #fff;
  padding: 14px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.panel-header.compact {
  margin-bottom: 10px;
}

.panel-header h3 {
  margin: 0 0 4px;
  font-size: 15px;
}

.panel-header p {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.4;
  font-size: 12px;
}

.panel-actions {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.secondary-button {
  border-radius: 12px;
}

.content-hint {
  max-width: 280px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.material-card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.material-card {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 12px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(47, 109, 255, 0.04), rgba(47, 109, 255, 0.01));
  border: 1px solid rgba(47, 109, 255, 0.08);
}

.material-card-name {
  font-weight: 600;
  line-height: 1.35;
  word-break: break-word;
  font-size: 13px;
}

.material-card-meta {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 11px;
}

.material-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.empty-state {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px;
  border-radius: 14px;
  background: var(--surface-soft);
  border: 1px dashed rgba(47, 109, 255, 0.28);
}

.empty-illustration {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: rgba(47, 109, 255, 0.12);
  color: var(--accent);
  font-size: 22px;
  font-weight: 700;
}

.empty-state h4 {
  margin: 0 0 6px;
  font-size: 15px;
}

.empty-state p,
.inline-empty,
.placeholder-line {
  margin: 0;
  color: var(--text-muted);
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-block + .field-block {
  margin-top: 12px;
}

.field-label-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.field-label {
  font-weight: 700;
  font-size: 13px;
}

.field-tip {
  color: var(--text-muted);
  font-size: 11px;
  text-align: right;
}

.topic-composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.topic-selected {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 28px;
  align-items: center;
}

.topic-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.topic-suggestion {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(47, 109, 255, 0.12);
  background: #fff;
  color: var(--text-muted);
  cursor: pointer;
  transition: 0.2s ease;
}

.topic-suggestion:hover,
.topic-suggestion.active {
  border-color: rgba(47, 109, 255, 0.28);
  color: var(--accent);
  background: rgba(47, 109, 255, 0.08);
}

.platform-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.platform-card {
  padding: 8px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-soft);
  background: #fff;
}

.platform-card.selected {
  border-color: rgba(47, 109, 255, 0.24);
  background: linear-gradient(180deg, rgba(47, 109, 255, 0.07), rgba(47, 109, 255, 0.015));
}

.platform-card.warning {
  border-color: rgba(240, 87, 87, 0.32);
  background: linear-gradient(180deg, rgba(240, 87, 87, 0.08), rgba(240, 87, 87, 0.02));
}

.platform-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.platform-name {
  font-weight: 700;
  color: var(--text-strong);
  font-size: 13px;
}

.platform-inline-summary {
  flex-shrink: 0;
  max-width: 58%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
  color: var(--text-muted);
  font-size: 12px;
}

.stack-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.settings-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.setting-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.setting-row:last-child {
  border-bottom: 0;
}

.setting-title {
  font-weight: 700;
}

.setting-desc {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.35;
}

.schedule-card {
  margin-top: 10px;
  padding: 12px;
  border-radius: 14px;
  background: var(--surface-soft);
  border: 1px solid rgba(47, 109, 255, 0.1);
}

.schedule-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.schedule-field + .schedule-field {
  margin-top: 10px;
}

.schedule-field.column {
  align-items: stretch;
  flex-direction: column;
}

.schedule-label {
  font-weight: 600;
}

.schedule-inline-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.time-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.time-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.summary-item {
  padding: 10px;
  border-radius: 12px;
  background: var(--surface-soft);
  border: 1px solid rgba(47, 109, 255, 0.08);
}

.summary-item span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.summary-item strong {
  display: block;
  margin-top: 4px;
  font-size: 16px;
}

.summary-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 0;
  border-bottom: 1px dashed rgba(15, 23, 42, 0.08);
}

.summary-key {
  color: var(--text-muted);
}

.summary-value {
  text-align: right;
}

.validation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.validation-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--danger-soft);
  color: #b42318;
  font-size: 13px;
}

.validation-item.success {
  background: var(--success-soft);
  color: #1f7a45;
}

.action-dock,
.top-action-dock {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  background: linear-gradient(135deg, #10203b 0%, #16345f 100%);
  color: #fff;
  box-shadow: 0 10px 20px rgba(16, 32, 59, 0.16);
}

.action-dock-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.action-dock-copy span {
  color: rgba(255, 255, 255, 0.75);
  font-size: 12px;
}

.top-action-center {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
}

.top-action-meta {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  font-size: 11px;
  color: rgba(255, 255, 255, 0.85);
}

.top-action-meta.label {
  padding-left: 0;
  padding-right: 0;
  background: transparent;
}

.batch-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 4px;
}

.action-dock-buttons {
  display: flex;
  gap: 8px;
}

.video-upload :deep(.el-upload-dragger) {
  width: 100%;
  height: 200px;
  border-radius: 20px;
}

.publish-progress {
  padding: 12px 4px;
}

.current-publishing {
  margin-top: 14px;
  color: var(--text-muted);
  text-align: center;
}

.publish-results {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(15, 23, 42, 0.08);
  max-height: 320px;
  overflow-y: auto;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  color: var(--text-muted);
}

.result-item.success {
  color: #1f9d57;
}

.result-item.error {
  color: #f05757;
}

.result-item.cancelled {
  color: var(--text-muted);
}

.result-item .label {
  font-weight: 600;
}

.material-library-content {
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 4px;
}

.material-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.material-item {
  padding: 10px;
  border-radius: 12px;
  background: var(--surface-soft);
  border: 1px solid rgba(47, 109, 255, 0.08);
}

.material-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.material-name {
  font-weight: 600;
  line-height: 1.5;
  word-break: break-word;
}

.material-original-title,
.material-details {
  color: var(--text-muted);
  font-size: 11px;
}

.material-details {
  display: flex;
  gap: 12px;
}

.account-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.account-item {
  width: 100%;
  margin-right: 0;
  padding: 10px;
  border-radius: 12px;
  background: var(--surface-soft);
}

.account-item :deep(.el-checkbox__label) {
  width: 100%;
}

.account-info {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.account-name {
  font-weight: 600;
}

.account-platform {
  color: var(--text-muted);
  font-size: 12px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 1200px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .workspace-side {
    position: static;
  }
}

@media (max-width: 900px) {
  .task-rail-header,
  .panel-header,
  .top-action-dock,
  .action-dock,
  .field-label-row,
  .schedule-field,
  .schedule-inline-head,
  .topic-composer {
    flex-direction: column;
    align-items: stretch;
  }

  .panel-actions,
  .task-rail-actions,
  .top-action-center,
  .action-dock-buttons {
    width: 100%;
    flex-wrap: wrap;
  }

  .material-card,
  .platform-card-head,
  .summary-line,
  .time-row,
  .account-info {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 640px) {
  .publish-center {
    gap: 16px;
  }

  .task-rail,
  .workspace-shell {
    border-radius: 18px;
  }

  .task-rail,
  .workspace-shell,
  .panel {
    padding: 16px;
  }

  .top-action-dock {
    align-items: stretch;
  }

  .task-list {
    grid-template-columns: 1fr;
  }
}
</style>
