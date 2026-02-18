import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Redirect to login on 401 (expired/invalid token)
    if (error.response?.status === 401 && !error.config.url?.includes('/auth/')) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
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
  addFromAnilist: (data, force = false) =>
    api.post(`/manga/add/anilist${force ? '?force=true' : ''}`, data),

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

  markChapterRead: (mangaId, chapterId) =>
    api.post(`/manga/${mangaId}/chapters/${chapterId}/mark-read`),

  markAllRead: (mangaId) =>
    api.post(`/manga/${mangaId}/mark-all-read`),

  // System
  getSystemStatus: () =>
    api.get(`/system/status`),

  getSystemStats: () =>
    api.get(`/system/stats`),

  // Translation
  translateText: (text) =>
    api.post(`/system/translate`, null, { params: { text } }),

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

  // STK - Send to Kindle API
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

  checkKindleConfigured: () =>
    api.get(`/kindle/can-send`),

  getKindleStatus: (chapterId) =>
    api.get(`/kindle/status/${chapterId}`),

  // Import folder (Feature 5)
  getImportStatus: () =>
    api.get(`/import/status`),

  triggerImportProcess: () =>
    api.post(`/import/process`),

  retryFailedImport: (filename) =>
    api.post(`/import/retry/${encodeURIComponent(filename)}`),
};

// Comics API
export const comicApi = {
  // Search (ComicVine) with cross-filtering
  search: (query, page = 1, limit = 20) =>
    api.get(`/comics/search`, { params: { q: query, page, limit, check_availability: true } }),

  // Preview from ComicVine
  getComicVineDetails: (comicvineId) =>
    api.get(`/comics/comicvine/${comicvineId}`),

  // Library
  getLibrary: (params = {}) =>
    api.get(`/comics/`, { params }),

  getComic: (id) =>
    api.get(`/comics/${id}`),

  getStats: () =>
    api.get(`/comics/stats`),

  // Add/Update/Delete
  addComic: (payload, force = false) => {
    // Support both old format (just ID) and new format (object with volume_to_add)
    const data = typeof payload === 'number'
      ? { comicvine_id: payload }
      : payload;
    return api.post(`/comics/${force ? '?force=true' : ''}`, data);
  },

  addComicFromUrl: (data) =>
    api.post(`/comics/from-url`, null, { params: data }),

  updateComic: (id, data) =>
    api.patch(`/comics/${id}`, data),

  deleteComic: (id) =>
    api.delete(`/comics/${id}`),

  refreshComic: (id) =>
    api.post(`/comics/${id}/refresh`),

  // Issues
  getIssues: (comicId, params = {}) =>
    api.get(`/comics/${comicId}/issues`, { params }),

  // Stats
  getComicStats: (id) =>
    api.get(`/comics/${id}/stats`),

  // Download
  downloadIssues: (comicId, issueIds) =>
    api.post(`/comics/${comicId}/issues/download`, { issue_ids: issueIds }),

  // Search sources
  searchSources: (comicId) =>
    api.post(`/comics/${comicId}/search-sources`),

  // Send to Kindle
  sendToKindle: (comicId, issueId) =>
    api.post(`/comics/${comicId}/issues/${issueId}/send-to-kindle`),

  markIssueRead: (comicId, issueId) =>
    api.post(`/comics/${comicId}/issues/${issueId}/mark-read`),

  markAllIssuesRead: (comicId) =>
    api.post(`/comics/${comicId}/mark-all-read`),

  // Queue actions
  cancelDownload: (issueId) =>
    api.post(`/queue/comic/${issueId}/cancel`),

  retryDownload: (issueId) =>
    api.post(`/queue/comic/${issueId}/retry`),

  deleteFile: (issueId) =>
    api.delete(`/queue/comic/${issueId}/file`),
};

// Books API
export const bookApi = {
  // Search (Google Books / Open Library)
  searchGoogleBooks: (query, page = 1, limit = 20, language = null) =>
    api.get(`/books/search`, { params: { q: query, page, limit, language, source: 'all' } }),

  searchOpenLibrary: (query, page = 1, limit = 20) =>
    api.get(`/books/search`, { params: { q: query, page, limit, source: 'openlibrary' } }),

  // Library
  getLibrary: (params = {}) =>
    api.get(`/books/library`, { params }),

  getBook: (id) =>
    api.get(`/books/${id}`),

  getBookStats: (id) =>
    api.get(`/books/${id}/stats`),

  getStats: () =>
    api.get(`/books/library/stats`),

  // Add books
  addFromGoogleBooks: (data, force = false) =>
    api.post(`/books/from-google-books${force ? '?force=true' : ''}`, data),

  addFromUrl: (data) =>
    api.post(`/books/from-url`, data),

  // Update/Delete
  updateBook: (id, data) =>
    api.patch(`/books/${id}`, data),

  deleteBook: (id) =>
    api.delete(`/books/${id}`),

  refreshBook: (id) =>
    api.post(`/books/${id}/refresh`),

  // Chapters
  getChapters: (bookId) =>
    api.get(`/books/${bookId}/chapters`),

  downloadChapters: (bookId, chapterIds) =>
    api.post(`/books/${bookId}/chapters/download`, { chapter_ids: chapterIds }),

  // Send to Kindle
  sendToKindle: (bookId, chapterId) =>
    api.post(`/books/${bookId}/chapters/${chapterId}/send-to-kindle`),

  markChapterRead: (bookId, chapterId) =>
    api.post(`/books/${bookId}/chapters/${chapterId}/mark-read`),

  markAllRead: (bookId) =>
    api.post(`/books/${bookId}/mark-all-read`),
};

// Recommendations API (Feature 10)
export const recommendationsApi = {
  get: (params = {}) =>
    api.get('/recommendations', { params }),
};

export default api;
