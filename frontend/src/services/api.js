import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

export const mangaApi = {
  // Discovery
  getTrending: (page = 1, limit = 20) =>
    api.get(`/manga/discover/trending`, { params: { page, limit } }),

  getPopular: (page = 1, limit = 20) =>
    api.get(`/manga/discover/popular`, { params: { page, limit } }),

  // Search (AniList only)
  search: (query, page = 1, limit = 20) =>
    api.get(`/manga/search`, { params: { q: query, page, limit } }),

  // Library
  getLibrary: (params = {}) =>
    api.get(`/manga/`, { params }),

  getManga: (id) =>
    api.get(`/manga/${id}`),

  getMangaStats: (id) =>
    api.get(`/manga/${id}/stats`),

  getLibraryStats: () =>
    api.get(`/manga/library/stats`),

  // Add manga
  addFromAnilist: (data) =>
    api.post(`/manga/add/anilist`, data),

  addFromURL: (data) =>
    api.post(`/manga/add/url`, data),

  // Update/Delete
  updateManga: (id, data) =>
    api.put(`/manga/${id}`, data),

  deleteManga: (id) =>
    api.delete(`/manga/${id}`),

  refreshManga: (id) =>
    api.post(`/manga/${id}/refresh`),

  // Chapters
  getChapters: (mangaId, params = {}) =>
    api.get(`/manga/${mangaId}/chapters`, { params }),

  downloadChapters: (mangaId, chapterIds) =>
    api.post(`/manga/${mangaId}/chapters/download`, { chapter_ids: chapterIds }),

  // System
  getSystemStatus: () =>
    api.get(`/system/status`),

  getSystemStats: () =>
    api.get(`/system/stats`),

  // Queue
  getQueue: (params = {}) =>
    api.get(`/queue/`, { params }),

  getQueueStats: () =>
    api.get(`/queue/stats`),

  clearQueue: (status) =>
    api.post(`/queue/clear`, null, { params: { status } }),

  cancelDownload: (chapterId) =>
    api.post(`/queue/${chapterId}/cancel`),

  retryDownload: (chapterId) =>
    api.post(`/queue/${chapterId}/retry`),

  deleteDownloadFile: (chapterId) =>
    api.delete(`/queue/${chapterId}/file`),

  // Settings
  getSettings: () =>
    api.get(`/settings`),

  saveSettings: (data) =>
    api.post(`/settings`, data),

  testSmtp: () =>
    api.post(`/settings/test-smtp`),

  testAmazon: () =>
    api.post(`/settings/test-amazon`),

  getSmtpGuide: () =>
    api.get(`/settings/smtp-guide`),

  // Kindle (Email - max 25MB)
  sendToKindle: (chapterId) =>
    api.post(`/kindle/send/${chapterId}`),

  sendBatchToKindle: (chapterIds) =>
    api.post(`/kindle/send-batch`, { chapter_ids: chapterIds }),

  getKindleStatus: (chapterId) =>
    api.get(`/kindle/status/${chapterId}`),

  checkKindleConfigured: () =>
    api.get(`/kindle/can-send`),

  // STK - Send to Kindle API (OAuth2 - supports large files)
  stkGetStatus: () =>
    api.get(`/kindle/stk/status`),

  stkGetSigninUrl: () =>
    api.get(`/kindle/stk/signin-url`),

  stkAuthorize: (redirectUrl) =>
    api.post(`/kindle/stk/authorize`, { redirect_url: redirectUrl }),

  stkGetDevices: () =>
    api.get(`/kindle/stk/devices`),

  stkSendToKindle: (chapterId) =>
    api.post(`/kindle/stk/send/${chapterId}`),

  stkLogout: () =>
    api.post(`/kindle/stk/logout`),
};

export default api;
