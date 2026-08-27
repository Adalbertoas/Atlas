"""Cliente de escritorio de ATLAS.

Fase 4 lo creó como una ventana simple para dejar de depender de
curl/Swagger. Fase 15 lo llevó a paridad con el dashboard web: misma
estructura (barra lateral navegable, mismas secciones, mismos paneles) y
misma identidad visual (ver theme.py).

Diferencias que **no** se pueden cerrar, por límites de Tkinter:
  · No hay SVG: los iconos del dashboard se sustituyen por barras de color
    y tipografía. Los anillos y el orbe se dibujan sobre Canvas.
  · No hay rgba ni degradados: los tonos translúcidos hay que precalcularlos
    (widgets._blend) y un Canvas nunca es transparente.
  · Las animaciones van por after() a ~25 fps, no por requestAnimationFrame.
  · El control por gestos necesita MediaPipe, que corre en un navegador —
    acá se muestra su estado y dónde activarlo, no la captura.

Este archivo se queda con la ventana, la navegación, el audio y los
sondeos; la construcción de cada vista vive en views.py.
"""
from __future__ import annotations

import io
import sys
import threading
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog

import customtkinter as ctk
import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

from atlas_desktop import api_client, theme
from atlas_desktop.config import ATLAS_API_URL, ATLAS_PASSWORD
from atlas_desktop.views import NAV_ITEMS, ViewsMixin
from atlas_desktop.wake_word import WakeWordListener, record_command_until_silence, to_wav_bytes
from atlas_desktop.widgets import LevelBar, VoiceOrb  # noqa: F401  (VoiceOrb lo instancia views.py)

RECORD_SAMPLE_RATE = 16000
SHAZAM_RECORD_SECONDS = 6.0  # AudD recomienda 3-10s para reconocer bien

# int16 a 0..1. No es el máximo teórico (32768) sino un nivel de voz normal:
# con el máximo real, hablar a volumen normal casi no movía el orbe.
LEVEL_REFERENCE = 6000.0

ctk.set_appearance_mode("dark")


def _audio_level(chunk: np.ndarray) -> float:
    """Amplitud RMS del bloque, normalizada a 0..1 para los visualizadores."""
    if chunk.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float64)))))
    return min(1.0, rms / LEVEL_REFERENCE)


class AtlasWindow(ctk.CTk, ViewsMixin):
    def __init__(self) -> None:
        super().__init__()
        self.title("ATLAS")
        self.geometry("1260x800")
        self.minsize(1040, 640)
        self.configure(fg_color=theme.BG)

        self.conversation_id: str | None = None
        self.user_name = ""
        self.lan_ip = ""
        self.devices: list[dict] = []
        self._recording = False
        self._record_frames: list[np.ndarray] = []
        self._record_stream: sd.InputStream | None = None
        self._current_view = "home"
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._nav_badges: dict[str, ctk.CTkLabel] = {}
        # La palabra la define el backend (ATLAS_WAKE_WORD) y llega con el
        # perfil; hasta entonces se usa el default del listener. Así los tres
        # clientes no pueden quedar escuchando palabras distintas.
        self.wake_word = "ali"
        self._wake_listener = WakeWordListener(on_activated=self._on_wake_word_detected)

        self._build_layout()
        self._go("home")

        self.refresh_all()
        self._poll_system_status()
        self._check_server_reachable()
        self._poll_gesture_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Arranca escuchando solo, sin que haga falta tocar el botón — pedido
        # explícito del usuario. El botón sigue sirviendo para apagarla si
        # no la quiere activa (ver docs/architecture.md sobre esta decisión).
        self._on_wake_word_toggle_clicked()

    def _on_close(self) -> None:
        self._wake_listener.stop()
        self.destroy()

    # ================= layout =================

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, fg_color=theme.SIDEBAR, corner_radius=0, width=236)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)

        # --- Marca ---
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 14))
        mark = ctk.CTkCanvas(brand, width=26, height=26, bg=theme.SIDEBAR, highlightthickness=0)
        mark.create_polygon(13, 4, 24, 22, 2, 22, outline=theme.ACCENT, fill="", width=2)
        mark.pack(side="left")
        ctk.CTkLabel(
            brand, text="  ATLAS", font=(theme.FONT_FAMILY, 16, "bold"), text_color=theme.TEXT
        ).pack(side="left")

        ctk.CTkFrame(sidebar, height=1, fg_color=theme.BORDER).grid(
            row=1, column=0, sticky="ew", padx=14
        )

        # --- Navegación ---
        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="new", padx=12, pady=(12, 0))
        nav.grid_columnconfigure(0, weight=1)

        for index, (key, label) in enumerate(NAV_ITEMS):
            holder = ctk.CTkFrame(nav, fg_color="transparent")
            holder.grid(row=index, column=0, sticky="ew", pady=1)
            holder.grid_columnconfigure(0, weight=1)

            button = ctk.CTkButton(
                holder, text=label, anchor="w", height=32,
                font=theme.FONT_BUTTON, corner_radius=theme.RADIUS_SM,
                fg_color="transparent", hover_color=theme.PANEL,
                text_color=theme.TEXT_DIM, border_width=1, border_color=theme.SIDEBAR,
                command=lambda k=key: self._go(k),
            )
            button.grid(row=0, column=0, sticky="ew")
            self._nav_buttons[key] = button

            badge = ctk.CTkLabel(
                holder, text="", width=20, height=18, corner_radius=9,
                font=(theme.FONT_FAMILY, 9, "bold"),
                fg_color=theme.DANGER, text_color=theme.DANGER_INK,
            )
            self._nav_badges[key] = badge  # se muestra solo si hay algo que contar

        # --- Pie: estado de conexión ---
        ctk.CTkFrame(sidebar, height=1, fg_color=theme.BORDER).grid(
            row=3, column=0, sticky="ew", padx=14, pady=(10, 0)
        )
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=18, pady=(10, 16))

        self.status_dot = ctk.CTkCanvas(
            footer, width=10, height=10, bg=theme.SIDEBAR, highlightthickness=0
        )
        self._dot_id = self.status_dot.create_oval(1, 1, 9, 9, fill=theme.TEXT_FAINT, outline="")
        self.status_dot.pack(side="left", pady=(4, 0))

        status_text = ctk.CTkFrame(footer, fg_color="transparent")
        status_text.pack(side="left", padx=(9, 0))
        self.server_status_label = ctk.CTkLabel(
            status_text, text="Conectando…", font=(theme.FONT_FAMILY, 10, "bold"),
            text_color=theme.TEXT, anchor="w",
        )
        self.server_status_label.pack(fill="x")
        self.server_detail_label = ctk.CTkLabel(
            status_text, text=ATLAS_API_URL, font=theme.FONT_TINY,
            text_color=theme.TEXT_FAINT, anchor="w",
        )
        self.server_detail_label.pack(fill="x")

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # --- Encabezado ---
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 12))
        header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            titles, text="ATLAS", font=theme.FONT_TITLE, text_color=theme.TEXT, anchor="w"
        ).pack(fill="x")
        ctk.CTkLabel(
            titles, text="Tu asistente personal inteligente", font=theme.FONT_SUBTITLE,
            text_color=theme.TEXT_FAINT, anchor="w",
        ).pack(fill="x")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")
        self.screenshot_button = self._ghost_button(actions, "Ver pantalla", self._on_screenshot_button_clicked)
        self.shazam_button = self._ghost_button(actions, "Reconocer canción", self._on_shazam_button_clicked)
        self.wake_word_button = self._ghost_button(actions, "Escucha", self._on_wake_word_toggle_clicked)
        for button in (self.screenshot_button, self.shazam_button, self.wake_word_button):
            button.pack(side="left", padx=(8, 0))

        # --- Vistas ---
        container = ctk.CTkFrame(main, fg_color="transparent")
        container.grid(row=1, column=0, sticky="nsew", padx=22)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)
        self._build_views(container)

        # --- Barra de escucha ---
        listen = ctk.CTkFrame(
            main, fg_color=theme.PANEL, corner_radius=0, height=68,
            border_width=1, border_color=theme.BORDER,
        )
        listen.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        listen.grid_columnconfigure(1, weight=1)
        listen.grid_propagate(False)

        self.listen_status = ctk.CTkLabel(
            listen, text="ATLAS en espera", font=theme.FONT_SMALL,
            text_color=theme.TEXT_DIM, anchor="w", width=190,
        )
        self.listen_status.grid(row=0, column=0, sticky="w", padx=(22, 10), pady=20)

        self.level_bar = LevelBar(listen, width=560, height=32, bg=theme.PANEL)
        self.level_bar.grid(row=0, column=1, sticky="w")

        self.voice_button = ctk.CTkButton(
            listen, text="Hablar", width=118, height=40, font=theme.FONT_BUTTON,
            corner_radius=20, fg_color=theme.ACCENT, hover_color=theme.ACCENT_DARK,
            text_color=theme.ACCENT_INK, command=self._on_voice_button_clicked,
        )
        self.voice_button.grid(row=0, column=2, padx=22)

    def _ghost_button(self, master, text: str, command) -> ctk.CTkButton:
        """Botón secundario: contorno en vez de relleno, como los `.chip` del
        dashboard. Deja el acento sólido para la acción principal."""
        return ctk.CTkButton(
            master, text=text, height=34, width=138,
            font=theme.FONT_BUTTON, corner_radius=17,
            fg_color="transparent", hover_color=theme.PANEL_2,
            border_width=1, border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT_DIM,
            command=command,
        )

    # ================= navegación =================

    def _go(self, key: str) -> None:
        for name, button in self._nav_buttons.items():
            active = name == key
            button.configure(
                fg_color=theme.PANEL if active else "transparent",
                text_color=theme.ACCENT if active else theme.TEXT_DIM,
                border_color=theme.ACCENT_DARK if active else theme.SIDEBAR,
            )
        for name, view in self.views.items():
            view.grid() if name == key else view.grid_remove()
        self._current_view = key

    def _set_nav_badge(self, key: str, count: int) -> None:
        badge = self._nav_badges.get(key)
        if badge is None:
            return
        if count > 0:
            badge.configure(text=str(count))
            badge.grid(row=0, column=1, padx=(6, 0))
        else:
            badge.grid_remove()

    # ================= estado de la UI de voz =================

    def _set_voice_state(self, status: str, *, listening: bool) -> None:
        """Un solo lugar que decide cómo se ve el estado de voz — evita que el
        orbe, la barra y los textos queden desincronizados entre sí."""
        self.orb_status.configure(text=status)
        self.listen_status.configure(text=status)
        if listening:
            self.orb.start()
        else:
            self.orb.stop()
            self.level_bar.reset()

    def _push_level(self, level: float) -> None:
        """Se llama desde hilos de audio: toda la UI pasa por self.after()."""
        self.after(0, self.orb.set_level, level)
        self.after(0, self.level_bar.push, level)

    # ================= chat =================

    def _append_chat(self, speaker: str, text: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{speaker}: {text}\n\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")

    def _send_from_ui(self, message: str, switch_to_chat: bool = False) -> None:
        """Punto de entrada único para los mensajes que dispara la interfaz
        (chips, interruptores de dispositivos): muestra el mensaje y lo manda."""
        if switch_to_chat:
            self._go("chat")
        self._append_chat("Tú", message)
        threading.Thread(target=self._send_message_background, args=(message,), daemon=True).start()

    def _on_send_clicked(self) -> None:
        message = self.entry.get().strip()
        if not message:
            return
        self.entry.delete(0, "end")
        self._send_from_ui(message)

    def _on_hero_send(self) -> None:
        message = self.hero_entry.get().strip()
        if not message:
            return
        self.hero_entry.delete(0, "end")
        self._send_from_ui(message, switch_to_chat=True)

    def _on_screenshot_button_clicked(self) -> None:
        """Fase 8: dispara analyze_screenshot vía chat, reutilizando el mismo
        diálogo de confirmación ya usado para open_application/close_application
        (analyze_screenshot es HIGH_RISK — nunca se ejecuta sin confirmar)."""
        self._send_from_ui("Mira mi pantalla y decime qué ves.", switch_to_chat=True)

    def _send_message_background(self, message: str) -> None:
        try:
            result = api_client.send_chat_message(message, self.conversation_id)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error de conexión: {exc})")
            return

        self.conversation_id = result.conversation_id
        if result.requires_confirmation:
            self.after(0, self._ask_confirmation, result)
        else:
            self.after(0, self._append_chat, "ATLAS", result.reply or "")
        # Una acción del chat pudo cambiar el estado real (encender una luz,
        # crear un recordatorio) — refrescar lo que muestra la ventana.
        self.after(0, self.refresh_devices)
        self.after(0, self.refresh_activity)
        self.after(0, self.refresh_reminders)

    def _ask_confirmation(self, result: api_client.ChatReply) -> None:
        approved = messagebox.askyesno("ATLAS — confirmación requerida", result.confirmation_description or "")
        threading.Thread(
            target=self._confirm_background, args=(result.confirmation_id, approved), daemon=True
        ).start()

    def _confirm_background(self, confirmation_id: str, approved: bool) -> None:
        spoken = True
        try:
            reply = api_client.confirm_action(confirmation_id, approved)
        except Exception as exc:  # noqa: BLE001
            reply = f"(error de conexión: {exc})"
            spoken = False  # los errores de conexión se muestran, no se dictan
        self.after(0, self._append_chat, "ATLAS", reply)
        self.after(0, self.refresh_devices)
        self.after(0, self.refresh_activity)
        # Hablar la respuesta también acá: sin esto, todo lo que pasa por
        # confirmación (abrir una app, mirar la pantalla, tocar un
        # dispositivo) respondía mudo, y parecía que la voz fallaba al azar.
        # En realidad dependía de QUÉ se pedía, no de cuándo.
        if spoken and reply:
            threading.Thread(target=self._speak_background, args=(reply,), daemon=True).start()

    # ================= Shazam (Fase 10) =================

    def _on_shazam_button_clicked(self) -> None:
        """Graba unos segundos de audio ambiente y lo manda a /music/identify
        (AudD) — no pasa por tool calling, mismo criterio que el botón de
        voz: el usuario ya decidió explícitamente grabar."""
        self.shazam_button.configure(state="disabled", text="Escuchando…")
        self._append_chat("Tú", "(Shazam: escuchando la canción…)")
        self._set_voice_state("Identificando la canción…", listening=True)
        threading.Thread(target=self._shazam_pipeline_background, daemon=True).start()

    def _shazam_pipeline_background(self) -> None:
        # El wake word mantiene el micrófono abierto en su propio stream todo
        # el tiempo (ver wake_word.py) — grabar acá al mismo tiempo con
        # sd.rec() (la API "global" de sounddevice, distinta a InputStream)
        # hizo que la grabación se quedara colgada sin tirar ningún error.
        # Se pausa igual que ya hace el propio wake word consigo mismo
        # mientras responde, y se reanuda al final pase lo que pase.
        was_listening = self._wake_listener.is_active
        if was_listening:
            self._wake_listener.stop()
        try:
            audio = sd.rec(
                int(SHAZAM_RECORD_SECONDS * RECORD_SAMPLE_RATE),
                samplerate=RECORD_SAMPLE_RATE,
                channels=1,
                dtype="int16",
            )
            sd.wait()
            buffer = io.BytesIO()
            sf.write(buffer, audio.reshape(-1), RECORD_SAMPLE_RATE, format="WAV", subtype="PCM_16")
            result = api_client.identify_song(buffer.getvalue())
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error reconociendo la canción: {exc})")
            self.after(0, self._finish_shazam, was_listening)
            return

        if not result.get("found"):
            self.after(
                0, self._append_chat, "ATLAS",
                "(No reconocí ninguna canción — probá de nuevo con más volumen.)",
            )
        else:
            reply = f"{result['title']} — {result['artist']}"
            if result.get("album"):
                reply += f" ({result['album']})"
            if result.get("song_link"):
                reply += f"\n{result['song_link']}"
            self.after(0, self._append_chat, "ATLAS", reply)

        self.after(0, self._finish_shazam, was_listening)

    def _finish_shazam(self, was_listening: bool) -> None:
        self.shazam_button.configure(state="normal", text="Reconocer canción")
        self._set_voice_state("ATLAS en espera", listening=False)
        if was_listening:
            self._wake_listener.start()

    # ================= voz =================

    def _on_voice_button_clicked(self) -> None:
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording_and_process()

    def _start_recording(self) -> None:
        self._recording = True
        self._record_frames = []
        self.voice_button.configure(
            text="Detener", fg_color=theme.DANGER, hover_color="#c85a5a", text_color=theme.DANGER_INK
        )
        self._set_voice_state("ATLAS está escuchando…", listening=True)

        def callback(indata, _frames, _time_info, _status) -> None:
            self._record_frames.append(indata.copy())
            # El visualizador se alimenta del audio real, no de un temporizador.
            self._push_level(_audio_level(indata.reshape(-1)))

        self._record_stream = sd.InputStream(
            samplerate=RECORD_SAMPLE_RATE, channels=1, dtype="int16", callback=callback
        )
        self._record_stream.start()

    def _stop_recording_and_process(self) -> None:
        self._recording = False
        self.voice_button.configure(
            text="Hablar", fg_color=theme.ACCENT, hover_color=theme.ACCENT_DARK,
            text_color=theme.ACCENT_INK,
        )
        if self._record_stream is not None:
            self._record_stream.stop()
            self._record_stream.close()
            self._record_stream = None

        if not self._record_frames:
            self._set_voice_state("ATLAS en espera", listening=False)
            return

        self._set_voice_state("Procesando…", listening=False)
        audio = np.concatenate(self._record_frames, axis=0)
        buffer = io.BytesIO()
        sf.write(buffer, audio, RECORD_SAMPLE_RATE, format="WAV", subtype="PCM_16")
        threading.Thread(
            target=self._voice_pipeline_background, args=(buffer.getvalue(),), daemon=True
        ).start()

    def _voice_pipeline_background(self, wav_bytes: bytes) -> None:
        try:
            text = api_client.transcribe_audio(wav_bytes)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error transcribiendo: {exc})")
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return

        if not text.strip():
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return
        self.after(0, self._go, "chat")
        self.after(0, self._append_chat, "Tú (voz)", text)

        try:
            result = api_client.send_chat_message(text, self.conversation_id)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error de conexión: {exc})")
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return

        self.conversation_id = result.conversation_id
        if result.requires_confirmation:
            self.after(0, self._ask_confirmation, result)
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return

        reply = result.reply or ""
        self.after(0, self._append_chat, "ATLAS", reply)
        self.after(0, self.refresh_devices)
        self.after(0, self.refresh_activity)
        if reply:
            threading.Thread(target=self._speak_background, args=(reply,), daemon=True).start()
        else:
            self.after(0, self._set_voice_state, "ATLAS en espera", False)

    def _speak_background(self, text: str) -> None:
        try:
            self._play_speech(text)
        except Exception:  # noqa: BLE001 — la respuesta de texto ya se mostró; el audio es un extra
            pass
        finally:
            self.after(0, self._set_voice_state, "ATLAS en espera", False)

    def _play_speech(self, text: str) -> None:
        """Sintetiza y reproduce, bloqueando hasta que termina. Usado tanto
        por el botón de voz (en su propio hilo) como por el flujo de wake
        word, donde bloquear es intencional: mientras ATLAS habla, el loop
        de escucha sigue pausado y no puede captar su propia voz (eco)."""
        wav_bytes = api_client.synthesize_speech(text)
        data, sample_rate = sf.read(io.BytesIO(wav_bytes), dtype="int16")
        self.after(0, self._set_voice_state, "ATLAS está hablando…", True)

        # Reproducción por bloques para poder alimentar el visualizador con
        # el audio que realmente está sonando, en vez de animar a ciegas.
        block = max(1, sample_rate // 25)
        stream = sd.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")
        stream.start()
        try:
            for start in range(0, len(data), block):
                chunk = data[start : start + block]
                stream.write(chunk.reshape(-1, 1) if chunk.ndim == 1 else chunk)
                self._push_level(_audio_level(chunk.reshape(-1)))
        finally:
            stream.stop()
            stream.close()

    # ================= wake word ("Ali") =================

    def _sync_wake_button(self) -> None:
        """Un solo lugar que decide cómo se ve el botón, para que el texto no
        quede desfasado cuando la palabra llega del backend después."""
        if self._wake_listener.is_active:
            # Estado activo en contorno de acento, no relleno: el acento
            # sólido queda reservado para la acción principal (Hablar).
            self.wake_word_button.configure(
                text=f'Escuchando "{self.wake_word.capitalize()}"',
                border_color=theme.ACCENT, text_color=theme.ACCENT,
            )
        else:
            self.wake_word_button.configure(
                text="Escucha apagada", border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT_DIM
            )

    def _on_wake_word_toggle_clicked(self) -> None:
        if self._wake_listener.is_active:
            self._wake_listener.stop()
        else:
            self._wake_listener.start()
        self._sync_wake_button()

    def _on_wake_word_detected(self) -> None:
        """Corre en el hilo del WakeWordListener, NO en el hilo de Tk — todo
        toque a la UI pasa por self.after(). Es deliberadamente síncrono
        (incluida la reproducción de la respuesta): mientras esta función no
        termine, el loop de escucha sigue pausado (ver wake_word.py)."""
        self.after(0, self._set_voice_state, "Te escuché — decime qué necesitás", True)
        # Confirmación inmediata de que "Ali" se detectó — sin esto, el
        # usuario no tiene forma de saber que ya puede hablar, ni de saber
        # si el silencio total que sigue es porque no lo escuchó o porque
        # sí lo escuchó y no captó ningún comando después.
        self.after(0, self._append_chat, "ATLAS", "(Te escuché — decime qué necesitás.)")

        audio = record_command_until_silence(on_level=self._push_level)
        if audio.size == 0:
            self.after(0, self._append_chat, "ATLAS", "(No escuché ningún comando, sigo atento.)")
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return

        self.after(0, self._set_voice_state, "Procesando…", False)
        try:
            text = api_client.transcribe_audio(to_wav_bytes(audio))
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error transcribiendo: {exc})")
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return

        if not text.strip():
            self.after(0, self._append_chat, "ATLAS", "(No entendí el comando, sigo atento.)")
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return
        self.after(0, self._go, "chat")
        self.after(0, self._append_chat, "Tú (voz)", text)

        try:
            result = api_client.send_chat_message(text, self.conversation_id)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error de conexión: {exc})")
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return

        self.conversation_id = result.conversation_id
        if result.requires_confirmation:
            # Nota: la confirmación se resuelve en su propio hilo (ver
            # _ask_confirmation) — el loop de escucha puede reanudarse antes
            # de que el usuario responda el diálogo. No es un problema de
            # seguridad (nada se ejecuta sin esa confirmación), solo una
            # limitación de UX conocida del modo wake word.
            self.after(0, self._ask_confirmation, result)
            self.after(0, self._set_voice_state, "ATLAS en espera", False)
            return

        reply = result.reply or ""
        self.after(0, self._append_chat, "ATLAS", reply)
        self.after(0, self.refresh_devices)
        self.after(0, self.refresh_activity)
        if reply:
            try:
                self._play_speech(reply)
            except Exception:  # noqa: BLE001
                pass
        self.after(0, self._set_voice_state, "ATLAS en espera", False)

    # ================= sondeos =================

    def _set_status_dot(self, color: str) -> None:
        self.status_dot.itemconfigure(self._dot_id, fill=color)

    def _check_server_reachable(self) -> None:
        def check() -> None:
            reachable = api_client.is_server_reachable()
            self.after(0, self._render_server_status, reachable)

        threading.Thread(target=check, daemon=True).start()
        self.after(10_000, self._check_server_reachable)

    def _render_server_status(self, reachable: bool) -> None:
        self.server_status_label.configure(
            text="ATLAS Online" if reachable else "Sin conexión",
            text_color=theme.TEXT if reachable else theme.DANGER,
        )
        self._set_status_dot(theme.ACCENT if reachable else theme.DANGER)

    def _poll_system_status(self) -> None:
        def poll() -> None:
            try:
                status = api_client.get_system_status()
            except Exception:  # noqa: BLE001
                status = None
            self.after(0, self._render_system_status, status)

        threading.Thread(target=poll, daemon=True).start()
        self.after(4_000, self._poll_system_status)

    def _render_system_status(self, status: dict | None) -> None:
        if status is None:
            for ring in (self.ring_cpu, self.ring_ram, self.ring_disk):
                ring.set(None)
            return

        self.ring_cpu.set(status["cpu_percent"])
        self.ring_ram.set(status["ram_percent"])
        self.ring_disk.set(status["disk_percent"])

        net = (status.get("net_recv_mbps") or 0) + (status.get("net_sent_mbps") or 0)
        self.metric_net.configure(text=f"{net:.1f} Mbps")

        uptime = status.get("uptime_seconds")
        if uptime is not None:
            days, rest = divmod(int(uptime), 86400)
            hours, rest = divmod(rest, 3600)
            minutes = rest // 60
            if days:
                text = f"{days}d {hours}h"
            elif hours:
                text = f"{hours}h {minutes}m"
            else:
                text = f"{minutes}m"
            self.metric_uptime.configure(text=text)

        # cpu_temp_c llega en null en equipos que no exponen el sensor (común
        # en desktops con Windows) — ahí la fila no se muestra, en vez de
        # inventar un número.
        temperature = status.get("cpu_temp_c")
        if temperature is not None:
            self.metric_temp.configure(text=f"{temperature} °C")
            self.metric_temp_row.grid()
        else:
            self.metric_temp_row.grid_remove()

    def _poll_gesture_status(self) -> None:
        def poll() -> None:
            try:
                status = api_client.get_gesture_status()
            except Exception:  # noqa: BLE001
                status = None
            self.after(0, self._render_gesture_status, status)

        threading.Thread(target=poll, daemon=True).start()
        self.after(5_000, self._poll_gesture_status)

    def _render_gesture_status(self, status: dict | None) -> None:
        if status is None:
            self.gesture_status_label.configure(text="No se pudo consultar", text_color=theme.TEXT_DIM)
            self.gesture_detail_label.configure(text="")
            return
        if status.get("connected"):
            self.gesture_status_label.configure(text="Control por gestos activo", text_color=theme.ACCENT)
            self.gesture_detail_label.configure(
                text=f"{status.get('events_received', 0)} gestos recibidos en esta sesión"
            )
        else:
            self.gesture_status_label.configure(text="Sin control por gestos activo", text_color=theme.TEXT)
            self.gesture_detail_label.configure(
                text="Activalo desde el dashboard web o desde la PWA del celular"
            )


def _login_or_exit() -> None:
    """Fase 7: la API ya no acepta requests anónimos. Si ATLAS_PASSWORD está
    en desktop/.env se usa directo; si no (o si falla), se pide por diálogo."""
    password = ATLAS_PASSWORD
    if password:
        try:
            api_client.login(password)
            return
        except requests.RequestException:
            pass  # cae al diálogo manual abajo

    root = ctk.CTk()
    root.withdraw()
    for _attempt in range(3):
        password = simpledialog.askstring("ATLAS — inicio de sesión", "Contraseña:", show="*", parent=root)
        if password is None:
            root.destroy()
            sys.exit(0)
        try:
            api_client.login(password)
            root.destroy()
            return
        except requests.HTTPError:
            messagebox.showerror("ATLAS", "Contraseña incorrecta.", parent=root)
        except requests.RequestException as exc:
            messagebox.showerror("ATLAS", f"No se pudo conectar a {ATLAS_API_URL}:\n{exc}", parent=root)
            root.destroy()
            sys.exit(1)

    root.destroy()
    sys.exit(1)


def main() -> None:
    _login_or_exit()
    app = AtlasWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
