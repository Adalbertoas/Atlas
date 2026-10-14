// Service worker mínimo: solo lo necesario para que el navegador considere
// la página instalable como PWA. No cachea la API (los datos de ATLAS
// siempre deben ser en vivo), solo permite que el ícono/manifest se registren.
const CACHE_NAME = "atlas-shell-v12"; // invalidate the prior shell after gesture calibration changes
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

  // La PWA se usa desde la red local mientras se ajustan gestos y pantallas.
  // Preferir red evita que una instalaciÃ³n vieja mantenga app.js en cachÃ©;
  // el cachÃ© queda solo como respaldo si la PC no estÃ¡ disponible.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && event.request.method === "GET") {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
