/* Laboratorio SMAE · INCAP — guarda la app en el dispositivo para usarla sin internet.
   Cada versión publicada cambia VERSION; al abrir la app con internet, el navegador detecta el cambio
   y la app muestra «Hay una versión nueva». No envía datos a ningún servidor. */
const VERSION = 'smae-v0.6.11';
const FILES = ['./', 'index.html', 'ayuda.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES))); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('message', e => { if (e.data === 'skip') self.skipWaiting(); });
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(r => r || fetch(e.request)));
});
