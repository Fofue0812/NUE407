/* Laboratorio SMAE · INCAP — guarda la app en el dispositivo para usarla sin internet.
   Cada versión publicada cambia VERSION; al abrir la app con internet, el navegador detecta el cambio
   y la app muestra «Hay una versión nueva». No envía datos a ningún servidor. */
const CACHE_PREFIX = 'smae:' + encodeURIComponent(self.registration.scope) + ':';
const VERSION = CACHE_PREFIX + 'v0.6.12';
const LEGACY_CACHES = new Set(['smae-v0.6.10', 'smae-v0.6.11']);
const FILES = ['./', 'index.html', 'ayuda.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png'];
self.addEventListener('activate', e => {
  e.waitUntil(clearPreviousCaches().then(() => self.clients.claim()));
});

async function clearPreviousCaches() {
  const ownFiles = new Set(FILES.map(path => new URL(path, self.registration.scope).href));
  for (const name of await caches.keys()) {
    if (name.startsWith(CACHE_PREFIX) && name !== VERSION) {
      await caches.delete(name);
    } else if (LEGACY_CACHES.has(name)) {
      // Las versiones anteriores compartían nombre entre instalaciones del mismo origen.
      const requests = await (await caches.open(name)).keys();
      if (requests.length && requests.every(request => ownFiles.has(request.url))) {
        await caches.delete(name);
      }
    }
  }
}

self.addEventListener('install', e => { e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES))); });
self.addEventListener('message', e => { if (e.data === 'skip') self.skipWaiting(); });
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(caches.match(e.request, { cacheName: VERSION, ignoreSearch: true }).then(r => r || fetch(e.request)));
});
