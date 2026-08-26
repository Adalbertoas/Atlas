// Service worker mínimo: solo lo necesario para que el navegador considere
// la página instalable como PWA. No cachea la API (los datos de ATLAS
// siempre deben ser en vivo), solo permite que el ícono/manifest se registren.
const CACHE_NAME = "atlas-shell-v9"; // subir la versión invalida la caché vieja (ej. tras cambios en app.js)
const SHELL_FILES = ["./index.html", "./styles.css", "./app.js", "./manifest.json", "./icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Nunca cachear llamadas a la API del backend (puertos distintos al de este PWA).
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
