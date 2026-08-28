/* Suscripción a Web Push desde la página (Fase 22).
 *
 * Vive en shared/ junto a wake-word.js y markdown.js: es la misma lógica en
 * mobile/ y dashboard/, y dos copias garantizan que se desincronicen (ya
 * pasó antes con la palabra de activación).
 *
 * Requiere HTTPS (contexto seguro) salvo en localhost — mismo requisito que
 * cámara/micrófono, ver certs/ y scripts/generate_dev_cert.py.
 */

/** El navegador espera la applicationServerKey como Uint8Array, no como el
 * string base64url que da el backend. */
function base64UrlToUint8Array(base64Url) {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export function isPushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window;
}

/** True si ya hay una suscripción activa en este navegador (no implica que
 * el backend la tenga guardada — eso se sincroniza en cada subscribePush()). */
export async function isPushSubscribed() {
  if (!isPushSupported()) return false;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  return subscription !== null;
}

/**
 * Pide permiso de notificaciones, suscribe este navegador al push del
 * backend, y manda la suscripción a `/notifications/push/subscribe`.
 *
 * @param {(path: string, options?: object) => Promise<any>} api - la función
 *   `api()` ya autenticada de cada cliente (inyectada, no importada, para no
 *   acoplar este módulo al `API_URL`/`TOKEN` particular de cada app).
 */
export async function subscribePush(api) {
  if (!isPushSupported()) {
    throw new Error("Este navegador no soporta notificaciones push.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Permiso de notificaciones denegado.");
  }

  const { public_key: publicKey } = await api("/api/v1/notifications/push/public-key");
  if (!publicKey) {
    throw new Error(
      "ATLAS no tiene configuradas las claves VAPID (VAPID_PUBLIC_KEY en el backend)."
    );
  }

  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ||
    (await registration.pushManager.subscribe({
      userVisibleOnly: true, // requisito del estándar: todo push debe mostrar una notificación visible
      applicationServerKey: base64UrlToUint8Array(publicKey),
    }));

  await api("/api/v1/notifications/push/subscribe", {
    method: "POST",
    body: JSON.stringify(subscription.toJSON()),
  });

  return subscription;
}

/** Desuscribe este navegador, tanto del lado del navegador como del backend. */
export async function unsubscribePush(api) {
  if (!isPushSupported()) return;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;

  const endpoint = subscription.endpoint;
  await subscription.unsubscribe();
  await api(`/api/v1/notifications/push/subscribe?endpoint=${encodeURIComponent(endpoint)}`, {
    method: "DELETE",
  });
}
