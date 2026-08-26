# [SUPERADO] Futuro: control de PC por gestos de mano (cámara)

> **Este diseño no se implementó tal cual — se reemplazó por uno mejor.**
> En vez de la webcam de la PC + MediaPipe en Python (riesgo señalado
> abajo: sin wheel confiable para Python 3.13), se implementó con la
> **cámara del celular** + MediaPipe corriendo en el navegador (JS/WASM,
> sin instalar nada en Python) + WebSocket al backend, que mueve el mouse
> real con `pyautogui`. Documentado y funcionando: ver "Cómo usar el
> control por gestos" en `README.md` y `docs/architecture.md`. El resto de
> este archivo queda solo como referencia histórica de la decisión
> original — el alcance de gestos (mover cursor, pellizco = clic, sin
> Permission Manager, cámara apagada por defecto) sigue vigente, solo
> cambió *dónde* corre la cámara.

## Alcance acordado

- **Mouse completo por gestos**: mover el cursor con la mano, pellizco
  (pulgar + índice) para hacer clic (y arrastrar, manteniendo el pellizco).
  El teclado se reemplaza por voz (ya existe, Fase 3) — escribir en el aire
  no es práctico.
- **Sin Permission Manager**: mover el cursor y hacer clic es control
  directo de bajo nivel (como usar el mouse con la mano), no una "tool" de
  IA — no pasa por el Orchestrator ni pide confirmación.
- **Cámara apagada por defecto** (sección 16 del prompt maestro): un botón
  explícito en el cliente de escritorio la activa/desactiva. Nunca arranca
  sola.

## Por qué vive en `desktop/`, no en el backend

La cámara, el mouse y la pantalla son recursos de la máquina local — igual
que la grabación de audio del botón de voz. Es control directo de la PC
donde corre el cliente, sin necesidad de IA/servidor en el medio.

## Riesgo técnico a verificar primero

Detección de manos con **MediaPipe** (Hands solution) — gratis, corre en
CPU. El venv actual usa Python 3.13.5; MediaPipe históricamente tarda en
soportar versiones nuevas de Python. Primer paso al retomar esto: probar
`pip install mediapipe` en el venv de `desktop/`; si no hay wheel para esa
versión, crear un venv dedicado con Python 3.11/3.12 solo para `desktop/`.

## Diseño

`desktop/atlas_desktop/gesture_control.py`:
- `GestureController`: hilo en background (mismo patrón que la grabación de
  voz en `main.py`). Abre la cámara (`cv2.VideoCapture(0)`), corre MediaPipe
  Hands por frame, mueve el cursor con `pyautogui.moveTo` (suavizado por
  media móvil exponencial), detecta pellizco para `mouseDown`/`mouseUp`.
  Ventana de vista previa (`cv2.imshow`) con los landmarks dibujados.
  Libera la cámara limpio al desactivar.

`desktop/atlas_desktop/gesture_math.py` (funciones puras, testeables sin
cámara/hardware):
- `map_to_screen(x_norm, y_norm, screen_w, screen_h, margin) -> (x, y)`
- `smooth(previous, new, alpha) -> value`
- `is_pinching(thumb_tip, index_tip, threshold) -> bool`

**Fail-safes**: `pyautogui.FAILSAFE = True` (esquina de pantalla aborta);
el botón de apagado siempre es alcanzable con el mouse/teclado físico real.

## Cliente de escritorio

Nuevo botón "🖐️ Gestos" junto a "🎙️ Hablar" en
`desktop/atlas_desktop/main.py`, mismo patrón de arranque/parada en hilo que
el botón de voz.

## Archivos a tocar cuando se retome

```
desktop/atlas_desktop/gesture_math.py       (nuevo)
desktop/atlas_desktop/gesture_control.py    (nuevo)
desktop/atlas_desktop/main.py               (+botón)
desktop/requirements.txt                    (+opencv-python, mediapipe, pyautogui)
desktop/tests/test_gesture_math.py          (nuevo)
README.md, docs/architecture.md             (documentar al implementar)
```

## Limitaciones conocidas (documentadas, no a medias)

- Sin soporte de scroll ni clic derecho en la primera versión.
- La iluminación y el fondo pueden afectar la detección de MediaPipe.
