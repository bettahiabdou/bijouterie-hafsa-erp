const CACHE_NAME = 'hafsa-erp-v1';

// Assets to cache on install (app shell)
const PRECACHE_URLS = [
  '/static/css/design-system.css',
  '/static/css/mobile-forms.css',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
];

// Install: cache app shell
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first strategy for HTML, cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // Skip cross-origin requests (CDN, etc.)
  if (url.origin !== location.origin) return;

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/media/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: network-first (always get fresh data for ERP)
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful HTML responses
        if (response.ok && event.request.headers.get('accept')?.includes('text/html')) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Offline: try cache
        return caches.match(event.request).then(cached => {
          if (cached) return cached;
          // Return offline page if available
          return caches.match('/').then(home => {
            if (home) return home;
            return new Response('<h1>Hors ligne</h1><p>Verifiez votre connexion internet.</p>', {
              headers: { 'Content-Type': 'text/html; charset=utf-8' }
            });
          });
        });
      })
  );
});
