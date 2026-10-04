const CACHE_NAME = 'stiebel-monitor-pwa-v1';
const APP_SHELL = [
  '/', '/registers', '/app.js', '/charts.js', '/registers.js', '/pwa.js', '/style.css',
  '/manifest.webmanifest', '/icon.svg', '/icon-192.png', '/icon-512.png',
];

function markOffline(response) {
  const headers = new Headers(response.headers);
  headers.set('X-Offline-Cache', 'true');
  return new Response(response.body, {status: response.status, statusText: response.statusText, headers});
}

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(APP_SHELL);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(name => name.startsWith('stiebel-monitor-pwa-') && name !== CACHE_NAME)
      .map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (url.pathname === '/api/dashboard') {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch {
        const exact = await cache.match(request);
        if (exact) return markOffline(exact);
        const keys = await cache.keys();
        const previousDashboard = keys.find(key => new URL(key.url).pathname === '/api/dashboard');
        if (previousDashboard) return markOffline(await cache.match(previousDashboard));
        return new Response(JSON.stringify({error: 'Dashboard ist offline und es gibt noch keine gespeicherte Momentaufnahme.'}), {
          status: 503,
          headers: {'Content-Type': 'application/json; charset=utf-8'},
        });
      }
    })());
    return;
  }

  if (url.pathname.startsWith('/api/')) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    try {
      const response = await fetch(request);
      if (response.ok) await cache.put(request, response.clone());
      return response;
    } catch {
      const cached = await cache.match(request);
      if (cached) return cached;
      if (request.mode === 'navigate') return cache.match('/');
      return Response.error();
    }
  })());
});
