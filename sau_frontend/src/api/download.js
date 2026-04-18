import { http } from '@/utils/request'

export const downloadApi = {
  listYoutubeTasks: () => http.get('/youtube/tasks'),

  getYoutubeTask: (taskId) => http.get('/youtube/task', { taskId }),

  createYoutubeDownloadTask: (url) => http.post('/youtube/download', { url }),
}
