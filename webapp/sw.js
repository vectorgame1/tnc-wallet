
const CACHE_NAME = 'tnc-wallet-v3';

const APP_FILES = [
  '/app/',
  '/app/manifest.webmanifest',
  '/app/icon.svg'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key.startsWith('tnc-wallet-') && key !== CACHE_NAME)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;

  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  if (url.origin !== self.location.origin) return;

  // API всегда запрашиваем с сервера: баланс и история не берутся из кэша.
  if (url.pathname.startsWith('/api/')) return;

  if (!url.pathname.startsWith('/app/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put('/app/', copy));
          }
          return response;
        })
        .catch(async () => {
          return (await caches.match('/app/')) ||
            new Response('TNC Wallet сейчас недоступен офлайн.', {
              status: 503,
              headers: {'Content-Type':'text/plain; charset=utf-8'}
            });
        })
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;

      return fetch(request).then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
