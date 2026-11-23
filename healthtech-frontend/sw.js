// HealthTech TACO - la pagina abre aunque no haya internet (guarda una copia de sus archivos).
const VERSION = 'ht-v1';
const BASE = ['./', 'index.html', 'app.js', 'config.js', 'style.css', 'recetas_biblioteca.js', 'offline.js',
  'qrcode_local.js', 'logo_HealthTech_TACO.jpeg', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png'];
const EXTERNOS = ['fonts.googleapis.com', 'fonts.gstatic.com', 'cdnjs.cloudflare.com'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.all(BASE.map(u => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const propio = url.origin === location.origin;
  if (!propio && !EXTERNOS.includes(url.hostname)) return;   // la API del servidor nunca se guarda aqui
  if (propio && /\.mp4$/i.test(url.pathname)) return;         // el video de introduccion es pesado
  e.respondWith((async () => {
    const cache = await caches.open(VERSION);
    try {
      const res = await fetch(req);
      if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone());
      return res;
    } catch (err) {
      const guardada = await cache.match(req, { ignoreSearch: true });
      if (guardada) return guardada;
      if (req.mode === 'navigate') { const i = await cache.match('index.html'); if (i) return i; }
      throw err;
    }
  })());
});
