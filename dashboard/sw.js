// Service worker del dashboard: existe solo para habilitar Web Push
// (Fase 22) — el dashboard no es una PWA instalable como mobile/, así que
// a propósito no cachea nada del shell (mismo criterio de "sin caché" que
// dashboard/serve.py: los archivos cambian todo el tiempo en desarrollo, y
// una caché de shell ya causó una vez una página con botones muertos).
importScripts("/shared/push-sw.js");
