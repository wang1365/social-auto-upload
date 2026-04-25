import { http } from '@/utils/request'

export const downloadApi = {
  listYoutubeTasks: () => http.get('/youtube/tasks'),

  getYoutubeTask: (taskId) => http.get('/youtube/task', { taskId }),

  createYoutubeDownloadTask: (url, downloadSubtitles = true) =>
    http.post('/youtube/download', { url, downloadSubtitles }),

  listVideoProcessTasks: () => http.get('/video/process/tasks'),

  getVideoProcessTask: (taskId) => http.get('/video/process/task', { taskId }),
}
