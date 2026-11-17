# Pruebas manuales pendientes

## Cómo arrancar todo

```powershell
# Terminal 1 — backend
cd backend
python run.py

# Terminal 2 — cliente de escritorio (opcional)
cd desktop
python run.py

# Terminal 3 — cliente móvil / PWA (opcional)
cd mobile
python serve.py
```

## Ya confirmado por vos en esta sesión

- [x] Voz con tu voz real + TTS audible — confirmado con el wake word
      ("Atlas, ¿qué hora es?" respondió correctamente por texto y voz).
- [x] Cliente de escritorio visual (chat, panel de estado, botones).
- [x] PWA móvil: login, chat con Claude real, lista de dispositivos — desde
      el navegador de la propia PC.
- [x] Trigger de horario del Automation Engine: confirmado por log — la
      rutina "Prueba Horario" se disparó sola a las 14:09, sin intervención
      manual, y apagó la luz (ver `docs/architecture.md`, Fase 6).
- [x] Visión: "mira mi pantalla y decime qué hay" pidió confirmación y
      describió correctamente la pantalla real; subir una imagen con texto
      a `/api/v1/vision/analyze` lo leyó bien (Fase 8).
- [x] ~~Dashboard (Fase 9): login, chat...~~ **corrección**: esta fila
      estaba mal — la carpeta `dashboard/` en realidad estaba vacía (nunca
      se había escrito el HTML/CSS/JS, aunque el backend que necesita sí
      estaba listo). Se detectó y se construyó recién en esta sesión. Ahora
      sí confirmado: login, navegación entre las 7 secciones y datos reales
      cargando (dispositivos, actividad, anillos de CPU/RAM/Disco).
- [x] Control por gestos (celular controla el mouse de la PC): cursor
      siguiendo la mano derecha y clic por pellizco, confirmados en vivo.
      Scroll con puño cerrado (mano izquierda) agregado y ajustado
      (umbrales de detección/pellizco recalibrados) — pendiente de una
      última confirmación en vivo, ver más abajo.
- [x] Wake word del escritorio: no eran los umbrales de audio — el cliente
      de escritorio no estaba corriendo, y al reiniciarlo fallaba en
      silencio porque seguía apuntando a `http://` mientras el backend ya
      solo servía `https://` (certificado autofirmado). Corregido en
      `desktop/atlas_desktop/config.py` (detecta el esquema según si existe
      el certificado) y `api_client.py` (valida contra ese certificado).

## Pendiente

- [ ] **Escritorio renovado con el backend real** (Electron): *Configuración →
      Personalidad* — elegir un estilo, poner tu nombre y tu ciudad, Guardar, y
      confirmar que el panel *Hoy* muestra el clima de tu ciudad y el saludo con
      tu nombre. Probar en el chat: "¿qué clima hace?", "noticias de
      tecnología", "¿cuánto son 100 dólares en pesos dominicanos?", "calcula
      15% de 2500", "genérame una contraseña", "pon el volumen al 30 %",
      "abre youtube.com". Pedir algo de riesgo (ej. "cierra el bloc de notas")
      y usar los botones *Confirmar / Cancelar*. Comprobar que recuerda el
      mensaje anterior ("¿y mañana?" después de preguntar el clima). En
      *Memoria*: agregar y olvidar un recuerdo; en *Recordatorios*: crear uno
      desde el chat y cancelarlo desde el panel; la campana debe avisar
      cuando vence.
- [ ] **"Bloquea la PC"** (`lock_computer`) y **volumen exacto**
      (`set_volume`): solo se probaron con tests simulados; la API real de
      Windows se prueba a mano.

- [ ] **Escucha en vivo en Electron con tu micrófono real** (ver
      `docs/ATLAS_NEURAL_CORE.md`, "Escucha en vivo"): pulsar **Escuchar
      "Atlas"** y probar "Atlas, ¿qué hora es?" de un tirón y "Atlas" + pausa
      + pedido. Confirmar: que no se active con la tele o una conversación de
      fondo, que no se oiga a sí misma por los altavoces, y ajustar
      *Sensibilidad del microfono* mirando el medidor si corta o no arranca.
      Ya probado de punta a punta con voz sintética inyectada como micrófono.
- [ ] **Solo mi voz con tu voz real**: *Configuracion → Neural Core · Solo mi
      voz → Registrar mi voz* (3 frases). Luego mirar la "Ultima frase" al
      decir "Atlas, ..." vos y otra persona (o un video), y ajustar la
      *Exigencia* si hace falta (por defecto 0,50).

- [ ] **Diálogo de confirmación en el escritorio**: pedir "abre la
      calculadora" y confirmar que aparece un diálogo de Sí/No antes de
      ejecutarse, y que Cancelar de verdad no la abre.
- [ ] **control_media real**: pedir "sube el volumen" / "pausa la música" y
      confirmar que efectivamente afecta lo que estés reproduciendo.
- [ ] **close_application**: abrir cualquier app y pedirle a ATLAS que la
      cierre, confirmando que la encuentra y la cierra bien.
- [ ] **Home Assistant real**: en `backend/.env`, poner
      `SMART_HOME_PROVIDER=home_assistant`, tu `SMART_HOME_URL` y un
      Long-Lived Access Token en `SMART_HOME_TOKEN`. Reiniciar el backend y
      probar `GET /api/v1/devices` (deben aparecer tus entidades reales),
      luego por chat encender/apagar algo real, y si tienes alguna
      cerradura (`lock.*`) confirmar que pide confirmación antes de actuar.
- [ ] **PWA desde el celular real** (misma WiFi que la PC): abrir
      `http://<IP-de-tu-PC>:5173` desde el navegador del celular (la IP la
      muestra `mobile/serve.py` al arrancar), loguearte, y probar:
  - [ ] Chat de texto y ver dispositivos/rutinas/notificaciones/memoria.
  - [ ] Voz: **puede no funcionar** por HTTPS (ver limitación en
        `docs/architecture.md`, Fase 7) — confirmar si funciona o no.
  - [ ] "Agregar a pantalla de inicio" para instalarla como ícono.
- [ ] **Botón "📷 Pantalla" del escritorio**: confirmar que dispara el
      diálogo de confirmación y muestra la descripción de la pantalla.
- [ ] **Botón de foto en la PWA** (📷 junto al de voz): sacar/subir una
      foto desde el celular y confirmar que ATLAS la describe.
- [ ] **Orbe de voz del dashboard**: tocar el orbe, hablar, tocar de nuevo
      y confirmar que transcribe y manda el mensaje al chat, Y que el
      anillo alrededor del orbe se mueve de verdad con la voz (no una
      animación fija) — recién construido, todavía sin probar en vivo.
- [ ] **Scroll por gestos (puño cerrado, mano izquierda)**: confirmar en
      vivo tras el último ajuste de sensibilidad — mano derecha aparte
      controlando el cursor al mismo tiempo, sin que se pisen entre sí.
- [ ] **Dos manos a la vez en Gestos**: confirmar que la cámara detecta
      ambas manos simultáneamente de forma estable (no solo una a la vez).

Si algo falla en cualquiera de estos puntos, dime cuál y seguimos
corrigiendo.
