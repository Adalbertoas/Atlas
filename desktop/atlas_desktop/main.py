"""Cliente de escritorio de ATLAS — Fase 4.

No es el dashboard futurista final (eso es Fase 9): es una ventana simple y
funcional para dejar de depender de curl/Swagger. Todo el negocio vive en el
backend; esta ventana solo llama a atlas_desktop.api_client.
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

from atlas_desktop import api_client
from atlas_desktop.config import ATLAS_API_URL, ATLAS_PASSWORD
from atlas_desktop.wake_word import WakeWordListener, record_command_until_silence, to_wav_bytes

RECORD_SAMPLE_RATE = 16000

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AtlasWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ATLAS")
        self.geometry("820x600")

        self.conversation_id: str | None = None
        self._recording = False
        self._record_frames: list[np.ndarray] = []
        self._record_stream: sd.InputStream | None = None
        self._wake_listener = WakeWordListener(on_activated=self._on_wake_word_detected)

        self._build_layout()
        self._poll_system_status()
        self._check_server_reachable()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Arranca escuchando solo, sin que haga falta tocar el botón — pedido
        # explícito del usuario. El botón sigue sirviendo para apagarla si
        # no la quiere activa (ver docs/architecture.md sobre esta decisión).
        self._on_wake_word_toggle_clicked()

    def _on_close(self) -> None:
        self._wake_listener.stop()
        self.destroy()

    # ---------- layout ----------

    def _build_layout(self) -> None:
        """Interfaz de escritorio: consola nativa con navegación y estado en vivo."""
        self.geometry("1180x760")
        self.minsize(960, 620)
        self.configure(fg_color="#08111f")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=224, corner_radius=0, fg_color="#0c1b30")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        ctk.CTkLabel(sidebar, text="A", width=38, height=38, corner_radius=12, fg_color="#58d6ff", text_color="#06131f", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=22, pady=(25, 4))
        ctk.CTkLabel(sidebar, text="ATLAS", font=ctk.CTkFont(size=24, weight="bold"), text_color="#f4f8ff").pack(anchor="w", padx=22)
        ctk.CTkLabel(sidebar, text="ASISTENTE PERSONAL", font=ctk.CTkFont(size=10, weight="bold"), text_color="#71a9c7").pack(anchor="w", padx=22, pady=(0, 28))

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for key, label, command in (
            ("chat", "  ◉  Conversación", lambda: self._show_page("chat")),
            ("system", "  ◈  Sistema", lambda: self._show_page("system")),
            ("voice", "  ◌  Voz y escucha", self._focus_voice),
            ("vision", "  ◫  Analizar pantalla", self._on_screenshot_button_clicked),
        ):
            button = ctk.CTkButton(sidebar, text=label, anchor="w", height=42, corner_radius=10, fg_color="transparent", hover_color="#163454", text_color="#b9c9dc", command=command)
            button.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = button

        self.desktop_mode_label = ctk.CTkLabel(sidebar, text="●  ESCUCHA ACTIVA", text_color="#5fe49b", font=ctk.CTkFont(size=11, weight="bold"))
        self.desktop_mode_label.pack(side="bottom", anchor="w", padx=22, pady=(0, 8))
        ctk.CTkLabel(sidebar, text="ATLAS Desktop · local-first", text_color="#66809b", font=ctk.CTkFont(size=10)).pack(side="bottom", anchor="w", padx=22, pady=(0, 22))

        main = ctk.CTkFrame(self, corner_radius=0, fg_color="#08111f")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, height=82, corner_radius=0, fg_color="#0a1628")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.page_title = ctk.CTkLabel(header, text="Conversación", font=ctk.CTkFont(size=23, weight="bold"), text_color="#f4f8ff")
        self.page_title.grid(row=0, column=0, sticky="w", padx=28, pady=(18, 0))
        self.server_status_label = ctk.CTkLabel(header, text="● Conectando…", text_color="#9badc5", font=ctk.CTkFont(size=12))
        self.server_status_label.grid(row=1, column=0, sticky="w", padx=28, pady=(0, 16))
        self.system_status_label = ctk.CTkLabel(header, text="CPU -- · RAM -- · Disco --", text_color="#9badc5", font=ctk.CTkFont(size=12))
        self.system_status_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=28)

        self.pages = ctk.CTkFrame(main, fg_color="transparent")
        self.pages.grid(row=1, column=0, sticky="nsew", padx=24, pady=22)
        self.pages.grid_columnconfigure(0, weight=1)
        self.pages.grid_rowconfigure(0, weight=1)

        self.chat_page = ctk.CTkFrame(self.pages, fg_color="transparent")
        self.chat_page.grid_columnconfigure(0, weight=1)
        self.chat_page.grid_rowconfigure(0, weight=1)
        self.chat_box = ctk.CTkTextbox(self.chat_page, wrap="word", state="disabled", corner_radius=16, fg_color="#10233a", border_width=1, border_color="#1c4567", text_color="#edf6ff", font=ctk.CTkFont(size=14), scrollbar_button_color="#275878")
        self.chat_box.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
        self.chat_box.tag_config("user", foreground="#7cddff")
        self.chat_box.tag_config("atlas", foreground="#84efbc")
        self.chat_box.tag_config("body", foreground="#edf6ff")

        composer = ctk.CTkFrame(self.chat_page, corner_radius=16, fg_color="#10233a", border_width=1, border_color="#1c4567")
        composer.grid(row=1, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(composer, placeholder_text="Escribile a ATLAS…", height=44, border_width=0, fg_color="transparent", font=ctk.CTkFont(size=14))
        self.entry.grid(row=0, column=0, sticky="ew", padx=(16, 8), pady=10)
        self.entry.bind("<Return>", lambda _event: self._on_send_clicked())
        self.voice_button = ctk.CTkButton(composer, text="🎙 Hablar", width=96, height=40, corner_radius=12, fg_color="#1b5274", command=self._on_voice_button_clicked)
        self.voice_button.grid(row=0, column=1, padx=5, pady=10)
        self.screenshot_button = ctk.CTkButton(composer, text="▣", width=42, height=40, corner_radius=12, fg_color="#1a3049", command=self._on_screenshot_button_clicked)
        self.screenshot_button.grid(row=0, column=2, padx=5, pady=10)
        self.send_button = ctk.CTkButton(composer, text="Enviar", width=82, height=40, corner_radius=12, fg_color="#58d6ff", text_color="#06131f", hover_color="#82e4ff", command=self._on_send_clicked)
        self.send_button.grid(row=0, column=3, padx=(5, 10), pady=10)

        self.system_page = ctk.CTkFrame(self.pages, fg_color="transparent")
        self.system_page.grid_columnconfigure((0, 1, 2), weight=1)
        self.system_page.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self.system_page, text="Estado de tu equipo", font=ctk.CTkFont(size=20, weight="bold"), text_color="#f4f8ff").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))
        self.metric_widgets: dict[str, tuple[ctk.CTkLabel, ctk.CTkProgressBar]] = {}
        for column, (key, label, tint) in enumerate((("cpu", "CPU", "#65ddff"), ("ram", "Memoria", "#8fa4ff"), ("disk", "Disco", "#5fe49b"))):
            card = ctk.CTkFrame(self.system_page, corner_radius=16, fg_color="#10233a", border_width=1, border_color="#1c4567")
            card.grid(row=1, column=column, sticky="nsew", padx=6)
            ctk.CTkLabel(card, text=label.upper(), text_color="#9badc5", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=18, pady=(20, 6))
            value = ctk.CTkLabel(card, text="--%", text_color="#f4f8ff", font=ctk.CTkFont(size=32, weight="bold"))
            value.pack(anchor="w", padx=18)
            bar = ctk.CTkProgressBar(card, progress_color=tint, fg_color="#1c3651", height=9)
            bar.pack(fill="x", padx=18, pady=(15, 8))
            bar.set(0)
            ctk.CTkLabel(card, text="Actualización automática", text_color="#66809b", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=18, pady=(0, 18))
            self.metric_widgets[key] = (value, bar)
        voice_card = ctk.CTkFrame(self.system_page, corner_radius=16, fg_color="#10233a", border_width=1, border_color="#1c4567")
        voice_card.grid(row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=(16, 0))
        voice_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(voice_card, text="Escucha por palabra clave", font=ctk.CTkFont(size=16, weight="bold"), text_color="#f4f8ff").grid(row=0, column=0, sticky="w", padx=18, pady=(17, 2))
        ctk.CTkLabel(voice_card, text="ATLAS se activa al detectar su nombre. Podés pausarlo cuando quieras.", text_color="#9badc5").grid(row=1, column=0, sticky="w", padx=18, pady=(0, 17))
        self.wake_word_button = ctk.CTkButton(voice_card, text="👂 Escucha: Apagada", width=176, height=38, corner_radius=12, command=self._on_wake_word_toggle_clicked)
        self.wake_word_button.grid(row=0, column=1, rowspan=2, padx=18)

        self._show_page("chat")

    def _show_page(self, page: str) -> None:
        for frame in (self.chat_page, self.system_page):
            frame.grid_forget()
        target = self.chat_page if page in {"chat", "voice"} else self.system_page
        target.grid(row=0, column=0, sticky="nsew")
        self.page_title.configure(text="Conversación" if page in {"chat", "voice"} else "Sistema")
        for key, button in self.nav_buttons.items():
            button.configure(fg_color="#163d5e" if key == page or (page == "chat" and key == "voice") else "transparent", text_color="#f4f8ff" if key == page else "#b9c9dc")
        if page == "voice":
            self.entry.focus()

    def _focus_voice(self) -> None:
        self._show_page("voice")
        self._on_voice_button_clicked()
    # ---------- chat ----------

    def _append_chat(self, speaker: str, text: str) -> None:
        self.chat_box.configure(state="normal")
        tag = "atlas" if speaker == "ATLAS" else "user"
        self.chat_box.insert("end", f"{speaker}\n", tag)
        self.chat_box.insert("end", f"{text}\n\n", "body")
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")

    def _on_send_clicked(self) -> None:
        message = self.entry.get().strip()
        if not message:
            return
        self.entry.delete(0, "end")
        self._append_chat("Tú", message)
        threading.Thread(target=self._send_message_background, args=(message,), daemon=True).start()

    def _on_screenshot_button_clicked(self) -> None:
        """Fase 8: dispara analyze_screenshot vía chat, reutilizando el mismo
        diálogo de confirmación ya usado para open_application/close_application
        (analyze_screenshot es HIGH_RISK — nunca se ejecuta sin confirmar)."""
        message = "Mira mi pantalla y decime qué ves."
        self._append_chat("Tú", message)
        threading.Thread(target=self._send_message_background, args=(message,), daemon=True).start()

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

    def _ask_confirmation(self, result: api_client.ChatReply) -> None:
        approved = messagebox.askyesno("ATLAS — confirmación requerida", result.confirmation_description or "")
        threading.Thread(
            target=self._confirm_background, args=(result.confirmation_id, approved), daemon=True
        ).start()

    def _confirm_background(self, confirmation_id: str, approved: bool) -> None:
        try:
            reply = api_client.confirm_action(confirmation_id, approved)
        except Exception as exc:  # noqa: BLE001
            reply = f"(error de conexión: {exc})"
        self.after(0, self._append_chat, "ATLAS", reply)

    # ---------- voz ----------

    def _on_voice_button_clicked(self) -> None:
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording_and_process()

    def _start_recording(self) -> None:
        self._recording = True
        self._record_frames = []
        self.voice_button.configure(text="⏹️ Detener", fg_color="#b3261e")

        def callback(indata, _frames, _time_info, _status) -> None:
            self._record_frames.append(indata.copy())

        self._record_stream = sd.InputStream(
            samplerate=RECORD_SAMPLE_RATE, channels=1, dtype="int16", callback=callback
        )
        self._record_stream.start()

    def _stop_recording_and_process(self) -> None:
        self._recording = False
        self.voice_button.configure(text="🎙️ Hablar", fg_color=("#3a7ebf", "#1f538d"))
        if self._record_stream is not None:
            self._record_stream.stop()
            self._record_stream.close()
            self._record_stream = None

        if not self._record_frames:
            return
        audio = np.concatenate(self._record_frames, axis=0)
        buffer = io.BytesIO()
        sf.write(buffer, audio, RECORD_SAMPLE_RATE, format="WAV", subtype="PCM_16")
        wav_bytes = buffer.getvalue()
        threading.Thread(target=self._voice_pipeline_background, args=(wav_bytes,), daemon=True).start()

    def _voice_pipeline_background(self, wav_bytes: bytes) -> None:
        try:
            text = api_client.transcribe_audio(wav_bytes)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error transcribiendo: {exc})")
            return

        if not text.strip():
            return
        self.after(0, self._append_chat, "Tú (voz)", text)

        try:
            result = api_client.send_chat_message(text, self.conversation_id)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error de conexión: {exc})")
            return

        self.conversation_id = result.conversation_id
        if result.requires_confirmation:
            self.after(0, self._ask_confirmation, result)
            return

        reply = result.reply or ""
        self.after(0, self._append_chat, "ATLAS", reply)
        if reply:
            threading.Thread(target=self._speak_background, args=(reply,), daemon=True).start()

    def _speak_background(self, text: str) -> None:
        try:
            self._play_speech(text)
        except Exception:  # noqa: BLE001 — la respuesta de texto ya se mostró; el audio es un extra
            pass

    def _play_speech(self, text: str) -> None:
        """Sintetiza y reproduce, bloqueando hasta que termina. Usado tanto
        por el botón de voz (en su propio hilo) como por el flujo de wake
        word, donde bloquear es intencional: mientras ATLAS habla, el loop
        de escucha sigue pausado y no puede captar su propia voz (eco)."""
        wav_bytes = api_client.synthesize_speech(text)
        data, sample_rate = sf.read(io.BytesIO(wav_bytes), dtype="int16")
        sd.play(data, sample_rate)
        sd.wait()

    # ---------- wake word ("Atlas") ----------

    def _on_wake_word_toggle_clicked(self) -> None:
        if self._wake_listener.is_active:
            self._wake_listener.stop()
            self.wake_word_button.configure(text="👂 Escucha: Apagada", fg_color=("#3a7ebf", "#1f538d"))
            self.desktop_mode_label.configure(text="○  ESCUCHA PAUSADA", text_color="#9badc5")
        else:
            self._wake_listener.start()
            self.wake_word_button.configure(text="👂 Escucha: Activa", fg_color="#2e7d32")
            self.desktop_mode_label.configure(text="●  ESCUCHA ACTIVA", text_color="#5fe49b")

    def _on_wake_word_detected(self) -> None:
        """Corre en el hilo del WakeWordListener, NO en el hilo de Tk — todo
        toque a la UI pasa por self.after(). Es deliberadamente síncrono
        (incluida la reproducción de la respuesta): mientras esta función no
        termine, el loop de escucha sigue pausado (ver wake_word.py)."""
        self.after(0, self.wake_word_button.configure, {"text": "👂 Escuchando el comando..."})
        # Confirmación inmediata de que "Atlas" se detectó — sin esto, el
        # usuario no tiene forma de saber que ya puede hablar, ni de saber
        # si el silencio total que sigue es porque no lo escuchó o porque
        # sí lo escuchó y no captó ningún comando después.
        self.after(0, self._append_chat, "ATLAS", "(Te escuché — decime qué necesitás.)")

        audio = record_command_until_silence()
        if audio.size == 0:
            self.after(0, self._append_chat, "ATLAS", "(No escuché ningún comando, sigo atento.)")
            self.after(0, self.wake_word_button.configure, {"text": "👂 Escucha: Activa"})
            return

        try:
            text = api_client.transcribe_audio(to_wav_bytes(audio))
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error transcribiendo: {exc})")
            self.after(0, self.wake_word_button.configure, {"text": "👂 Escucha: Activa"})
            return

        if not text.strip():
            self.after(0, self._append_chat, "ATLAS", "(No entendí el comando, sigo atento.)")
            self.after(0, self.wake_word_button.configure, {"text": "👂 Escucha: Activa"})
            return
        self.after(0, self._append_chat, "Tú (voz)", text)

        try:
            result = api_client.send_chat_message(text, self.conversation_id)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._append_chat, "ATLAS", f"(error de conexión: {exc})")
            self.after(0, self.wake_word_button.configure, {"text": "👂 Escucha: Activa"})
            return

        self.conversation_id = result.conversation_id
        if result.requires_confirmation:
            # Nota: la confirmación se resuelve en su propio hilo (ver
            # _ask_confirmation) — el loop de escucha puede reanudarse antes
            # de que el usuario responda el diálogo. No es un problema de
            # seguridad (nada se ejecuta sin esa confirmación), solo una
            # limitación de UX conocida del modo wake word.
            self.after(0, self._ask_confirmation, result)
            self.after(0, self.wake_word_button.configure, {"text": "👂 Escucha: Activa"})
            return

        reply = result.reply or ""
        self.after(0, self._append_chat, "ATLAS", reply)
        if reply:
            try:
                self._play_speech(reply)
            except Exception:  # noqa: BLE001
                pass
        self.after(0, self.wake_word_button.configure, {"text": "👂 Escucha: Activa"})

    # ---------- estado del sistema / servidor ----------

    def _check_server_reachable(self) -> None:
        def check() -> None:
            reachable = api_client.is_server_reachable()
            text = f"ATLAS: conectado ({ATLAS_API_URL})" if reachable else f"ATLAS: sin conexión ({ATLAS_API_URL})"
            self.after(0, self.server_status_label.configure, {"text": text})

        threading.Thread(target=check, daemon=True).start()
        self.after(10_000, self._check_server_reachable)

    def _poll_system_status(self) -> None:
        def poll() -> None:
            try:
                status = api_client.get_system_status()
                values = {
                    "cpu": status["cpu_percent"],
                    "ram": status["ram_percent"],
                    "disk": status["disk_percent"],
                }
                text = f"CPU {values['cpu']:.0f}% · RAM {values['ram']:.0f}% · Disco {values['disk']:.0f}%"
            except Exception:  # noqa: BLE001
                values = {}
                text = "CPU -- · RAM -- · Disco --"
            self.after(0, self._update_system_metrics, values, text)

        threading.Thread(target=poll, daemon=True).start()
        self.after(3_000, self._poll_system_status)

    def _update_system_metrics(self, values: dict[str, float], summary: str) -> None:
        self.system_status_label.configure(text=summary)
        for key, (label, bar) in self.metric_widgets.items():
            value = values.get(key)
            label.configure(text=f"{value:.0f}%" if value is not None else "--%")
            bar.set((value or 0) / 100)

def _login_or_exit() -> None:
    """Fase 7: la API ya no acepta requests anónimos. Si ATLAS_PASSWORD está
    en desktop/.env se usa directo; si no (o si falla), se pide por diálogo.
    Con el login desactivado en el backend (AUTH_ENABLED=false) cualquier
    contraseña sirve, incluida la vacía, así que se entra sin diálogo."""
    try:
        api_client.login(ATLAS_PASSWORD)
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
