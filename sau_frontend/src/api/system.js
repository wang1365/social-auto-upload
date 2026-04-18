import { http } from '@/utils/request'

export const systemApi = {
  getSettings: () => http.get('/system/settings'),

  saveSettings: (payload) => http.post('/system/settings', payload),

  uploadYoutubeCookie: (formData) =>
    http.upload('/system/settings/youtube-cookie', formData),

  deleteYoutubeCookie: () => http.delete('/system/settings/youtube-cookie'),
}
