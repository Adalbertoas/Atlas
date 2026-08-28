/* Manejo de Web Push dentro del service worker (Fase 22).
 *
 * Vive en shared/ y se carga con `importScripts()` desde el sw.js de cada
 * cliente (mobile/, dashboard/) — mismo criterio que wake-word.js: es la
 * misma lógica en los dos, y dos copias garantizan que se desincronicen.
 *
 * No hace falta pedir permiso ni suscribirse acá: eso lo hace push.js desde
 * la página, con un gesto del usuario. Este archivo solo reacciona cuando
 * el navegador recibe un push ya suscripto.
 */

self.addEventListener("push", (event) => {
  const message = event.data ? event.data.text() : "Tenés una notificación de ATLAS.";
  event.waitUntil(
    self.registration.showNotification("ATLAS", {
      body: message,
      icon: "/icon.svg",
      tag: "atlas-notification", // agrupa notificaciones seguidas en una sola, no las apila sin control
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // Si ya hay una pestaña de ATLAS abierta, la enfoca en vez de abrir una
  // nueva — evita juntar diez pestañas duplicadas a fuerza de notificaciones.
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("./");
    })
  );
});
