// Alejandría Service Worker
// Cache-first for hashed static assets, network-first for API and HTML.
//
// CACHE INVALIDATION STRATEGY:
// The app registers this SW as /sw.js?v=<BUILD_TIME>. Each new build gets a
// different query param, so the browser re-downloads this file and runs install
// + activate. The activate handler deletes all caches that don't match the
// current CACHE_NAME, which purges stale assets automatically.

const params = new URLSearchParams(self.location.search);
const buildVersion = params.get('v') || 'dev';
const CACHE_NAME = `alejandria-${buildVersion}`;

// Only pre-cache hashed assets — never cache index.html here.
// index.html has Cache-Control: no-store on the server, so the browser always
// fetches it fresh and picks up the latest JS/CSS filenames from Vite.
const STATIC_ASSETS = [];

// Install: nothing to pre-cache (assets are cached lazily on first fetch)
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: delete every cache that does not match current CACHE_NAME
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch: network-first for /api and HTML navigation; cache-first for hashed assets
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin requests
  if (request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  // API calls: always go to network, no caching
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // HTML navigation (index.html / SPA routes): always network-first, no caching
  if (request.mode === 'navigate' || url.pathname === '/' || url.pathname === '/index.html') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/index.html'))
    );
    return;
  }

  // Hashed static assets (/assets/*.js, /assets/*.css, etc.): cache-first
  // These are safe to cache indefinitely because Vite includes content hashes
  // in their filenames — a code change produces a new filename.
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;

      return fetch(request).then((response) => {
        if (response.ok && url.pathname.startsWith('/assets/')) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      });
    })
  );
});
