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
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Barra superior: estado del servidor + estado del sistema.
        top_bar = ctk.CTkFrame(self)
        top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.server_status_label = ctk.CTkLabel(top_bar, text=f"ATLAS: conectando a {ATLAS_API_URL}...")
        self.server_status_label.pack(side="left", padx=10, pady=8)
        self.system_status_label = ctk.CTkLabel(top_bar, text="CPU: -- | RAM: -- | Disco: --")
        self.system_status_label.pack(side="right", padx=10, pady=8)

        # Panel de chat.
        self.chat_box = ctk.CTkTextbox(self, wrap="word", state="disabled")
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # Barra inferior: entrada de texto + botón enviar + botón voz.
        bottom_bar = ctk.CTkFrame(self)
        bottom_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom_bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(bottom_bar, placeholder_text="Escríbele a ATLAS...")
        self.entry.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=10)
        self.entry.bind("<Return>", lambda _event: self._on_send_clicked())

        self.send_button = ctk.CTkButton(bottom_bar, text="Enviar", width=90, command=self._on_send_clicked)
        self.send_button.grid(row=0, column=1, padx=5, pady=10)

        self.voice_button = ctk.CTkButton(
            bottom_bar, text="🎙️ Hablar", width=110, command=self._on_voice_button_clicked
        )
        self.voice_button.grid(row=0, column=2, padx=(5, 5), pady=10)

        self.wake_word_button = ctk.CTkButton(
            bottom_bar, text="👂 Escucha: Apagada", width=170, command=self._on_wake_word_toggle_clicked
        )
        self.wake_word_button.grid(row=0, column=3, padx=(5, 5), pady=10)

        self.screenshot_button = ctk.CTkButton(
            bottom_bar, text="📷 Pantalla", width=110, command=self._on_screenshot_button_clicked
        )
        self.screenshot_button.grid(row=0, column=4, padx=(5, 10), pady=10)

    # ---------- chat ----------

    def _append_chat(self, speaker: str, text: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{speaker}: {text}\n\n")
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
        else:
            self._wake_listener.start()
            self.wake_word_button.configure(text="👂 Escucha: Activa", fg_color="#2e7d32")

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
                text = (
                    f"CPU: {status['cpu_percent']:.0f}% | "
                    f"RAM: {status['ram_percent']:.0f}% | "
                    f"Disco: {status['disk_percent']:.0f}%"
                )
            except Exception:  # noqa: BLE001
                text = "CPU: -- | RAM: -- | Disco: --"
            self.after(0, self.system_status_label.configure, {"text": text})

        threading.Thread(target=poll, daemon=True).start()
        self.after(3_000, self._poll_system_status)


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
