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
};

// Comics API
export const comicApi = {
  // Search (ComicVine)
  search: (query, page = 1, limit = 20) =>
    api.get(`/comics/search`, { params: { q: query, page, limit } }),

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
  addComic: (comicvineId) =>
    api.post(`/comics/`, { comicvine_id: comicvineId }),

  updateComic: (id, data) =>
    api.patch(`/comics/${id}`, data),

  deleteComic: (id) =>
    api.delete(`/comics/${id}`),

  refreshComic: (id) =>
    api.post(`/comics/${id}/refresh`),

  // Issues
  getIssues: (comicId, params = {}) =>
    api.get(`/comics/${comicId}/issues`, { params }),
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
  addFromGoogleBooks: (data) =>
    api.post(`/books/from-google-books`, data),

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
};

export default api;
