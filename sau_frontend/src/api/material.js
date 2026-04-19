import { http } from '@/utils/request'

const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

export const materialApi = {
  getAllMaterials: () => http.get('/getFiles'),

  uploadMaterial: (formData, onUploadProgress) => http.upload('/uploadSave', formData, onUploadProgress),

  createYoutubeDownloadTask: (url) => http.post('/youtube/download', { url }),

  getYoutubeDownloadTask: (taskId) => http.get('/youtube/task', { taskId }),

  deleteMaterial: (id) => http.get(`/deleteFile?id=${id}`),

  deleteMaterials: (ids) => http.post('/deleteFiles', { ids }),

  downloadMaterial: (filePath) => `${baseUrl}/download/${filePath}`,

  getMaterialPreviewUrl: (filename) => `${baseUrl}/getFile?filename=${encodeURIComponent(filename)}`,
}
