"""Vistas del cliente de escritorio (Fase 15).

Mixin de `AtlasWindow`: construye y refresca cada pantalla. Está separado de
main.py, que se queda con el ciclo de vida de la ventana, el audio y los
sondeos — mezclarlo todo hacía un archivo imposible de navegar.

Consume exactamente los mismos endpoints que `dashboard/app.js`, para que
las dos interfaces muestren los mismos datos y no se contradigan.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import customtkinter as ctk

from atlas_desktop import api_client, theme
from atlas_desktop.widgets import (
    LevelBar,
    MetricRing,
    MiniRow,
    Panel,
    Toggle,
    VoiceOrb,
    clear,
    empty_state,
)

# Tipos que se pueden encender/apagar directo desde la UI. Cerraduras,
# cámaras, sensores y clima quedan afuera a propósito: misma política de
# riesgo que el backend y que el dashboard.
SAFE_TYPES = ("LIGHT", "SWITCH", "PLUG", "FAN", "TV")

TYPE_ACCENT = {
    "LIGHT": theme.WARN,
    "SWITCH": "#a78bfa",
    "PLUG": "#a78bfa",
    "FAN": "#a78bfa",
    "TV": "#a78bfa",
    "LOCK": "#fb923c",
    "CAMERA": "#fb923c",
    "CLIMATE": "#38bdf8",
    "THERMOSTAT": "#38bdf8",
}

# Nombre legible por tool. El AuditLog guarda el identificador técnico
# (`get_current_time`); mostrarlo crudo se lee como ruido. Mismo mapa que
# el dashboard.
TOOL_LABELS = {
    "get_current_time": "Consultaste la hora",
    "get_system_info": "Consultaste el estado del equipo",
    "list_processes": "Listaste los procesos",
    "open_application": "Abriste una aplicación",
    "close_application": "Cerraste una aplicación",
    "open_file": "Abriste un archivo",
    "control_media": "Controlaste la reproducción",
    "list_files": "Listaste archivos",
    "search_files": "Buscaste archivos",
    "create_memory": "ATLAS guardó algo en memoria",
    "search_memory": "ATLAS consultó su memoria",
    "list_devices": "Listaste los dispositivos",
    "set_device_state": "Cambiaste un dispositivo",
    "control_room": "Controlaste una habitación",
    "run_routine": "Ejecutaste una rutina",
    "analyze_screenshot": "ATLAS miró la pantalla",
    "search_wikipedia": "Buscaste en Wikipedia",
    "get_weather": "Consultaste el clima",
    "search_youtube": "Buscaste en YouTube",
    "search_spotify": "Buscaste en Spotify",
    "create_reminder": "Creaste un recordatorio",
    "list_reminders": "Consultaste tus recordatorios",
}

QUICK_CHIPS = (
    ("Estado de la casa", "¿Cómo está la casa? Listá los dispositivos y su estado."),
    ("Mis recordatorios", "¿Qué recordatorios tengo pendientes?"),
    ("El clima", "¿Cómo está el clima hoy?"),
    ("Estado del equipo", "¿Cómo está el uso de CPU, RAM y disco?"),
)

NAV_ITEMS = (
    ("home", "Inicio"),
    ("chat", "Conversación"),
    ("devices", "Dispositivos"),
    ("automations", "Automatizaciones"),
    ("reminders", "Recordatorios"),
    ("memory", "Memoria"),
    ("gestures", "Gestos"),
    ("tools", "Herramientas"),
    ("activity", "Actividad"),
    ("notifications", "Notificaciones"),
    ("settings", "Configuración"),
)


def is_device_on(device: dict) -> bool:
    return device.get("state") in ("on", "unlocked", "playing")


def is_toggleable(device: dict) -> bool:
    return device.get("type") in SAFE_TYPES


def describe_tool(name: str) -> str:
    return TOOL_LABELS.get(name, name)


def format_due(iso: str) -> str:
    due = datetime.fromisoformat(iso)
    today = datetime.now()
    time = due.strftime("%H:%M")
    if due.date() == today.date():
        return f"Hoy, {time}"
    if due.date() == (today + timedelta(days=1)).date():
        return f"Mañana, {time}"
    return f"{due.strftime('%d/%m')}, {time}"


class ViewsMixin:
    """Se mezcla en AtlasWindow. Usa self.after / self._append_chat / etc."""

    # ================= construcción =================

    def _build_views(self, parent) -> None:
        """Todas las vistas se crean una sola vez y se muestran/ocultan con
        grid_remove(): reconstruirlas en cada navegación perdería el scroll y
        el contenido del chat."""
        self.views: dict[str, ctk.CTkFrame] = {}
        for key in (
            "home", "chat", "devices", "automations", "reminders", "memory",
            "gestures", "tools", "activity", "notifications", "settings",
        ):
            view = ctk.CTkFrame(parent, fg_color="transparent")
            view.grid(row=0, column=0, sticky="nsew")
            view.grid_remove()
            self.views[key] = view
            getattr(self, f"_build_{key}_view")(view)

    def _scroll_body(self, view, title: str, action: tuple[str, object] | None = None):
        """Cabecera + área con scroll — el esqueleto de las vistas de lista."""
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(view, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text=title, font=(theme.FONT_FAMILY, 14, "bold"),
            text_color=theme.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        if action:
            label, command = action
            ctk.CTkButton(
                head, text=label, width=1, height=24, font=theme.FONT_TINY,
                corner_radius=6, fg_color="transparent", hover_color=theme.PANEL,
                text_color=theme.ACCENT, command=command,
            ).grid(row=0, column=1, sticky="e")

        body = ctk.CTkScrollableFrame(
            view, fg_color="transparent",
            scrollbar_button_color=theme.BORDER_BRIGHT,
            scrollbar_button_hover_color=theme.TEXT_FAINT,
        )
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        return body

    # ---------- Inicio ----------

    def _build_home_view(self, view) -> None:
        scroll = ctk.CTkScrollableFrame(
            view, fg_color="transparent",
            scrollbar_button_color=theme.BORDER_BRIGHT,
            scrollbar_button_hover_color=theme.TEXT_FAINT,
        )
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=3, uniform="home")
        scroll.grid_columnconfigure(1, weight=2, uniform="home")
        scroll.grid_columnconfigure(2, weight=2, uniform="home")

        # --- Hero: orbe, saludo, entrada y accesos rápidos ---
        hero = Panel(scroll)
        hero.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 7), pady=(0, 7))
        hero.body.grid_columnconfigure(0, weight=1)

        # bg=PANEL: el orbe vive dentro de una tarjeta, no sobre el fondo.
        self.orb = VoiceOrb(hero.body, size=168, bg=theme.PANEL)
        self.orb.grid(row=0, column=0, pady=(10, 6))

        self.greeting_label = ctk.CTkLabel(
            hero.body, text="¡Hola!", font=(theme.FONT_FAMILY, 20, "bold"), text_color=theme.TEXT
        )
        self.greeting_label.grid(row=1, column=0)

        self.orb_status = ctk.CTkLabel(
            hero.body, text="¿En qué puedo ayudarte hoy?",
            font=theme.FONT_SMALL, text_color=theme.TEXT_DIM,
        )
        self.orb_status.grid(row=2, column=0, pady=(2, 14))

        entry_row = ctk.CTkFrame(hero.body, fg_color="transparent")
        entry_row.grid(row=3, column=0, sticky="ew", padx=14)
        entry_row.grid_columnconfigure(0, weight=1)

        self.hero_entry = ctk.CTkEntry(
            entry_row, placeholder_text="Escribí tu mensaje o usá el micrófono…",
            height=42, corner_radius=theme.RADIUS_SM,
            fg_color=theme.INPUT_BG, border_color=theme.BORDER_BRIGHT,
            text_color=theme.TEXT, placeholder_text_color=theme.TEXT_FAINT,
            font=theme.FONT_BODY,
        )
        self.hero_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.hero_entry.bind("<Return>", lambda _e: self._on_hero_send())

        ctk.CTkButton(
            entry_row, text="Enviar", width=88, height=42, font=theme.FONT_BUTTON,
            corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_DARK, text_color=theme.ACCENT_INK,
            command=self._on_hero_send,
        ).grid(row=0, column=1)

        # Grilla 2x2 y no una fila: en una sola fila el último chip se salía
        # del panel cuando la ventana no está maximizada. El dashboard puede
        # usar flex-wrap; Tkinter no tiene equivalente.
        chips = ctk.CTkFrame(hero.body, fg_color="transparent")
        chips.grid(row=4, column=0, sticky="ew", padx=14, pady=(14, 8))
        chips.grid_columnconfigure((0, 1), weight=1, uniform="chip")
        for index, (label, prompt) in enumerate(QUICK_CHIPS):
            ctk.CTkButton(
                chips, text=label, height=32, font=theme.FONT_TINY, corner_radius=16,
                fg_color="transparent", hover_color=theme.PANEL_2,
                border_width=1, border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT_DIM,
                command=lambda p=prompt: self._send_from_ui(p, switch_to_chat=True),
            ).grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)

        # --- Sistema ---
        system = Panel(scroll, "Sistema")
        system.grid(row=0, column=1, sticky="nsew", padx=7, pady=(0, 7))
        rings = ctk.CTkFrame(system.body, fg_color="transparent")
        rings.grid(row=0, column=0, pady=(0, 10))
        self.ring_cpu = MetricRing(rings, "CPU")
        self.ring_ram = MetricRing(rings, "RAM")
        self.ring_disk = MetricRing(rings, "DISCO")
        for ring in (self.ring_cpu, self.ring_ram, self.ring_disk):
            ring.pack(side="left", padx=4)

        self.metric_net = self._metric_row(system.body, "Red", 1)
        self.metric_uptime = self._metric_row(system.body, "Encendida hace", 2)
        # La temperatura solo aparece si el equipo expone el sensor — muchas
        # placas de escritorio no lo hacen, y el backend manda null.
        self.metric_temp_row, self.metric_temp = self._metric_row(system.body, "Temperatura", 3, keep=True)
        self.metric_temp_row.grid_remove()

        # --- Recordatorios ---
        reminders = Panel(scroll, "Recordatorios", ("Ver todos ›", lambda: self._go("reminders")))
        reminders.grid(row=1, column=1, sticky="nsew", padx=7, pady=(0, 7))
        self.home_reminders = reminders.body

        # --- Dispositivos ---
        devices = Panel(scroll, "Dispositivos", ("Ver todos ›", lambda: self._go("devices")))
        devices.grid(row=0, column=2, sticky="nsew", padx=(7, 0), pady=(0, 7))
        self.home_devices = devices.body

        # --- Acciones rápidas ---
        actions = Panel(scroll, "Acciones rápidas")
        actions.grid(row=1, column=2, sticky="nsew", padx=(7, 0), pady=(0, 7))
        self.home_shortcuts = actions.body

        # --- Automatizaciones ---
        automations = Panel(scroll, "Automatizaciones", ("Ver todas ›", lambda: self._go("automations")))
        automations.grid(row=2, column=0, sticky="nsew", padx=(0, 7), pady=(0, 7))
        self.home_automations = automations.body

        # --- Actividad ---
        activity = Panel(scroll, "Actividad reciente", ("Ver historial ›", lambda: self._go("activity")))
        activity.grid(row=2, column=1, sticky="nsew", padx=7, pady=(0, 7))
        self.home_activity = activity.body

        # --- Estado de la casa ---
        house = Panel(scroll, "Estado de la casa")
        house.grid(row=2, column=2, sticky="nsew", padx=(7, 0), pady=(0, 7))
        self.house_headline = ctk.CTkLabel(
            house.body, text="—", font=(theme.FONT_FAMILY, 13, "bold"),
            text_color=theme.OK, anchor="w",
        )
        self.house_headline.grid(row=0, column=0, sticky="ew", padx=4)
        self.house_body = ctk.CTkFrame(house.body, fg_color="transparent")
        self.house_body.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.house_body.grid_columnconfigure(0, weight=1)

    def _metric_row(self, master, label: str, row: int, keep: bool = False):
        """Fila 'etiqueta …… valor' de la tarjeta de Sistema."""
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=4, pady=2)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame, text=label, font=theme.FONT_TINY, text_color=theme.TEXT_FAINT, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        value = ctk.CTkLabel(
            frame, text="--", font=(theme.FONT_FAMILY, 11, "bold"), text_color=theme.ACCENT, anchor="e"
        )
        value.grid(row=0, column=1, sticky="e")
        return (frame, value) if keep else value

    # ---------- Conversación ----------

    def _build_chat_view(self, view) -> None:
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            view, text="Conversación", font=(theme.FONT_FAMILY, 14, "bold"),
            text_color=theme.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self.chat_box = ctk.CTkTextbox(
            view, wrap="word", state="disabled",
            fg_color=theme.PANEL, border_width=1, border_color=theme.BORDER,
            corner_radius=theme.RADIUS, font=theme.FONT_BODY, text_color=theme.TEXT,
            scrollbar_button_color=theme.BORDER_BRIGHT,
            scrollbar_button_hover_color=theme.TEXT_FAINT,
        )
        self.chat_box.grid(row=1, column=0, sticky="nsew")

        row = ctk.CTkFrame(view, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        row.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            row, placeholder_text="Escribile a ATLAS…", height=42,
            corner_radius=theme.RADIUS_SM, fg_color=theme.INPUT_BG,
            border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT,
            placeholder_text_color=theme.TEXT_FAINT, font=theme.FONT_BODY,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._on_send_clicked())

        ctk.CTkButton(
            row, text="Enviar", width=92, height=42, font=theme.FONT_BUTTON,
            corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_DARK, text_color=theme.ACCENT_INK,
            command=self._on_send_clicked,
        ).grid(row=0, column=1)

    # ---------- Vistas de lista ----------

    def _build_devices_view(self, view) -> None:
        self.devices_body = self._scroll_body(view, "Dispositivos", ("↻ Actualizar", self.refresh_devices))

    def _build_automations_view(self, view) -> None:
        self.automations_body = self._scroll_body(
            view, "Automatizaciones", ("↻ Actualizar", self.refresh_automations)
        )

    def _build_memory_view(self, view) -> None:
        self.memory_body = self._scroll_body(view, "Memoria", ("↻ Actualizar", self.refresh_memory))

    def _build_tools_view(self, view) -> None:
        self.tools_body = self._scroll_body(view, "Herramientas", ("↻ Actualizar", self.refresh_tools))

    def _build_activity_view(self, view) -> None:
        self.activity_body = self._scroll_body(view, "Actividad", ("↻ Actualizar", self.refresh_activity))

    def _build_notifications_view(self, view) -> None:
        self.notifications_body = self._scroll_body(
            view, "Notificaciones", ("↻ Actualizar", self.refresh_notifications)
        )

    def _build_reminders_view(self, view) -> None:
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(view, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="Recordatorios", font=(theme.FONT_FAMILY, 14, "bold"),
            text_color=theme.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            head, text="↻ Actualizar", width=1, height=24, font=theme.FONT_TINY,
            corner_radius=6, fg_color="transparent", hover_color=theme.PANEL,
            text_color=theme.ACCENT, command=self.refresh_reminders,
        ).grid(row=0, column=1, sticky="e")

        form = ctk.CTkFrame(view, fg_color="transparent")
        form.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        form.grid_columnconfigure(0, weight=1)

        self.reminder_text = ctk.CTkEntry(
            form, placeholder_text="¿Qué querés recordar?", height=38,
            corner_radius=theme.RADIUS_SM, fg_color=theme.INPUT_BG,
            border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT,
            placeholder_text_color=theme.TEXT_FAINT, font=theme.FONT_SMALL,
        )
        self.reminder_text.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        # Tkinter no tiene datetime-local: se pide en texto con un formato
        # explícito y se valida al enviar.
        self.reminder_due = ctk.CTkEntry(
            form, placeholder_text="DD/MM/AAAA HH:MM", width=170, height=38,
            corner_radius=theme.RADIUS_SM, fg_color=theme.INPUT_BG,
            border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT,
            placeholder_text_color=theme.TEXT_FAINT, font=theme.FONT_SMALL,
        )
        self.reminder_due.grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            form, text="Agregar", width=92, height=38, font=theme.FONT_BUTTON,
            corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_DARK, text_color=theme.ACCENT_INK,
            command=self._on_create_reminder,
        ).grid(row=0, column=2)

        body = ctk.CTkScrollableFrame(
            view, fg_color="transparent",
            scrollbar_button_color=theme.BORDER_BRIGHT,
            scrollbar_button_hover_color=theme.TEXT_FAINT,
        )
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        self.reminders_body = body

    # ---------- Gestos ----------

    def _build_gestures_view(self, view) -> None:
        body = self._scroll_body(view, "Control por gestos")

        ctk.CTkLabel(
            body,
            text=(
                "El control por gestos mueve el mouse de esta PC con la mano. La detección "
                "corre en un navegador (MediaPipe), así que se activa desde el dashboard web "
                "o desde la PWA del celular — esta ventana muestra el estado del receptor."
            ),
            font=theme.FONT_SMALL, text_color=theme.TEXT_DIM,
            wraplength=620, justify="left", anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 14))

        status = Panel(body, "Estado")
        status.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.gesture_status_label = ctk.CTkLabel(
            status.body, text="Consultando…", font=theme.FONT_SMALL,
            text_color=theme.TEXT, anchor="w",
        )
        self.gesture_status_label.grid(row=0, column=0, sticky="ew", padx=4)
        self.gesture_detail_label = ctk.CTkLabel(
            status.body, text="", font=theme.FONT_TINY, text_color=theme.TEXT_FAINT, anchor="w",
        )
        self.gesture_detail_label.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 0))

        howto = Panel(body, "Los gestos")
        howto.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for text in (
            "Mano derecha — el nudillo del índice mueve el cursor.",
            "Pellizco (pulgar + índice) — clic; mantenerlo arrastra.",
            "Mano izquierda en puño — moverla arriba/abajo hace scroll.",
        ):
            ctk.CTkLabel(
                howto.body, text=f"·  {text}", font=theme.FONT_SMALL,
                text_color=theme.TEXT_DIM, anchor="w",
            ).grid(sticky="ew", padx=4, pady=3)

        where = Panel(body, "Dónde activarlo")
        where.grid(row=3, column=0, sticky="ew")
        self.gesture_where_label = ctk.CTkLabel(
            where.body, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_DIM,
            wraplength=600, justify="left", anchor="w",
        )
        self.gesture_where_label.grid(sticky="ew", padx=4)

    # ---------- Configuración ----------

    def _build_settings_view(self, view) -> None:
        body = self._scroll_body(view, "Configuración")
        self.settings_body = body

    # ================= refrescos =================

    def refresh_all(self) -> None:
        for refresh in (
            self.refresh_devices, self.refresh_automations, self.refresh_reminders,
            self.refresh_memory, self.refresh_tools, self.refresh_activity,
            self.refresh_notifications, self.refresh_profile,
        ):
            refresh()
        self._render_settings()

    def _load(self, fetch, render) -> None:
        """Trae datos en un hilo y pinta en el de Tk. Toda vista sigue este
        patrón: la UI de Tkinter no es thread-safe."""
        def worker() -> None:
            try:
                data = fetch()
            except Exception as exc:  # noqa: BLE001
                self.after(0, render, None, str(exc))
                return
            self.after(0, render, data, None)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ---------- perfil / saludo ----------

    def refresh_profile(self) -> None:
        self._load(api_client.get_profile, self._render_profile)

    def _render_profile(self, profile: dict | None, error: str | None) -> None:
        self.user_name = (profile or {}).get("user_name", "") if not error else ""
        self.lan_ip = (profile or {}).get("lan_ip", "") if not error else ""
        if not error and (profile or {}).get("wake_word"):
            self.wake_word = profile["wake_word"]
            # El listener ya está construido: se actualiza en caliente para no
            # obligar a reiniciar la ventana si cambia en .env.
            self._wake_listener._wake_word = self.wake_word
            self._sync_wake_button()

        hour = datetime.now().hour
        if 6 <= hour < 13:
            saludo = "Buenos días"
        elif 13 <= hour < 20:
            saludo = "Buenas tardes"
        else:
            saludo = "Buenas noches"
        self.greeting_label.configure(
            text=f"{saludo}, {self.user_name}" if self.user_name else saludo
        )

        scheme = "https" if str(api_client.ATLAS_API_URL).startswith("https") else "http"
        host = self.lan_ip or "<IP-de-esta-PC>"
        self.gesture_where_label.configure(
            text=(
                f"·  En esta PC: abrí el dashboard en {scheme}://127.0.0.1:5174 → pestaña Gestos.\n"
                f"·  Desde el celular: abrí {scheme}://{host}:5173 en el teléfono → pestaña Gestos."
            )
        )
        self._render_settings()

    # ---------- dispositivos ----------

    def refresh_devices(self) -> None:
        self._load(api_client.list_devices, self._render_devices)

    def _render_devices(self, devices: list[dict] | None, error: str | None) -> None:
        clear(self.devices_body)
        clear(self.home_devices)

        if error:
            empty_state(self.devices_body, f"Error cargando dispositivos: {error}").grid(pady=20)
            return
        self.devices = devices or []
        if not self.devices:
            empty_state(
                self.devices_body,
                "No hay dispositivos. Configurá SMART_HOME_PROVIDER en el backend.",
            ).grid(pady=20)
            empty_state(self.home_devices, "Sin dispositivos.").grid(pady=12)
            self._render_house_state()
            return

        for index, device in enumerate(self.devices):
            self._device_row(self.devices_body, device).grid(row=index, column=0, sticky="ew", pady=3)
        for index, device in enumerate(self.devices[:4]):
            self._device_row(self.home_devices, device).grid(row=index, column=0, sticky="ew", pady=3)

        self._render_house_state()

    def _device_row(self, master, device: dict) -> MiniRow:
        on = is_device_on(device)
        subtitle = device.get("room") or "Sin sala"
        if is_toggleable(device):
            subtitle += " · Encendido" if on else " · Apagado"

        row = MiniRow(
            master, device.get("name", "?"), subtitle,
            accent=TYPE_ACCENT.get(device.get("type"), theme.BORDER_BRIGHT),
        )
        if is_toggleable(device):
            Toggle(
                row.trailing, on,
                command=lambda d=device, o=on: self._send_from_ui(
                    f"{'apagá' if o else 'encendé'} {d['name']}"
                ),
            ).pack()
        else:
            ctk.CTkLabel(
                row.trailing, text=str(device.get("state", "")),
                font=theme.FONT_TINY, text_color=theme.TEXT_DIM,
            ).pack()
        return row

    def _render_house_state(self) -> None:
        clear(self.house_body)
        devices = getattr(self, "devices", [])
        # Solo lo que realmente se enciende/apaga entra en el conteo: contar
        # una cerradura cerrada como "apagada" informaría mal.
        toggleable = [d for d in devices if is_toggleable(d)]
        on = sum(1 for d in toggleable if is_device_on(d))
        off = len(toggleable) - on
        unlocked = sum(1 for d in devices if d.get("type") == "LOCK" and d.get("state") == "unlocked")
        locked = sum(1 for d in devices if d.get("type") == "LOCK" and d.get("state") == "locked")

        if not devices:
            self.house_headline.configure(text="—", text_color=theme.TEXT_DIM)
        elif unlocked:
            self.house_headline.configure(text="Puerta sin trabar", text_color=theme.WARN)
        else:
            self.house_headline.configure(text="Todo normal", text_color=theme.OK)

        lines = [
            (f"{len(devices)} dispositivo(s) conectado(s)", theme.TEXT_FAINT),
            (f"{on} encendido(s)", theme.TEXT_DIM),
            (f"{off} apagado(s)", theme.TEXT_DIM),
        ]
        if unlocked or locked:
            lines.append(
                (f"{unlocked} sin trabar" if unlocked else f"{locked} trabada(s)",
                 theme.WARN if unlocked else theme.TEXT_DIM)
            )
        temperature = self._ambient_temperature()
        if temperature is not None:
            lines.append((f"Ambiente {temperature} °C", "#38bdf8"))

        for index, (text, color) in enumerate(lines):
            ctk.CTkLabel(
                self.house_body, text=text, font=theme.FONT_TINY, text_color=color, anchor="w"
            ).grid(row=index, column=0, sticky="ew", padx=4, pady=1)

    def _ambient_temperature(self) -> float | None:
        """Temperatura informada por un termostato/sensor real, si hay alguno.
        Si no, la fila no se muestra — no se inventa un valor."""
        for device in getattr(self, "devices", []):
            if device.get("type") not in ("CLIMATE", "THERMOSTAT", "SENSOR"):
                continue
            capabilities = device.get("capabilities") or {}
            value = capabilities.get("temperature", capabilities.get("current_temperature"))
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    # ---------- automatizaciones ----------

    def refresh_automations(self) -> None:
        self._load(api_client.list_automations, self._render_automations)

    def _render_automations(self, routines: list[dict] | None, error: str | None) -> None:
        clear(self.automations_body)
        clear(self.home_automations)
        clear(self.home_shortcuts)

        if error:
            empty_state(self.automations_body, f"Error cargando rutinas: {error}").grid(pady=20)
            return
        routines = routines or []
        if not routines:
            empty_state(self.automations_body, "No hay rutinas creadas todavía.").grid(pady=20)
            empty_state(self.home_automations, "Sin rutinas.").grid(pady=12)
            empty_state(self.home_shortcuts, "Todavía no creaste rutinas.").grid(pady=12)
            return

        for index, routine in enumerate(routines):
            subtitle = f"{len(routine['actions'])} acción(es) · {len(routine['triggers'])} trigger(s)"
            for container in (self.automations_body, self.home_automations):
                row = MiniRow(container, routine["name"], subtitle, accent=theme.ACCENT)
                ctk.CTkButton(
                    row.trailing, text="Ejecutar", width=76, height=26,
                    font=theme.FONT_TINY, corner_radius=13,
                    fg_color="transparent", hover_color=theme.PANEL,
                    border_width=1, border_color=theme.BORDER_BRIGHT, text_color=theme.ACCENT,
                    command=lambda r=routine: self._run_routine(r),
                ).pack()
                row.grid(row=index, column=0, sticky="ew", pady=3)

        for index, routine in enumerate(routines[:6]):
            ctk.CTkButton(
                self.home_shortcuts, text=routine["name"], height=34,
                font=theme.FONT_TINY, corner_radius=theme.RADIUS_SM,
                fg_color=theme.PANEL_2, hover_color=theme.BORDER_BRIGHT,
                border_width=1, border_color=theme.BORDER, text_color=theme.TEXT_DIM,
                command=lambda r=routine: self._run_routine(r),
            ).grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
        self.home_shortcuts.grid_columnconfigure((0, 1), weight=1)

    def _run_routine(self, routine: dict) -> None:
        def worker() -> None:
            try:
                result = api_client.run_routine(routine["id"])
                message = f"Rutina '{result['routine_name']}' ejecutada."
            except Exception as exc:  # noqa: BLE001
                message = f"(error ejecutando la rutina: {exc})"
            self.after(0, self._append_chat, "ATLAS", message)
            self.after(0, self.refresh_devices)
            self.after(0, self.refresh_activity)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ---------- recordatorios ----------

    def refresh_reminders(self) -> None:
        self._load(api_client.list_reminders, self._render_reminders)

    def _render_reminders(self, reminders: list[dict] | None, error: str | None) -> None:
        clear(self.reminders_body)
        clear(self.home_reminders)

        if error:
            empty_state(self.reminders_body, f"Error cargando recordatorios: {error}").grid(pady=20)
            return
        reminders = reminders or []

        pending = [r for r in reminders if not r["done"]][:4]
        if pending:
            for index, reminder in enumerate(pending):
                overdue = datetime.fromisoformat(reminder["due_at"]) < datetime.now()
                MiniRow(
                    self.home_reminders, reminder["text"], format_due(reminder["due_at"]),
                    accent=theme.WARN if overdue else theme.ACCENT,
                ).grid(row=index, column=0, sticky="ew", pady=3)
        else:
            empty_state(self.home_reminders, "Sin recordatorios pendientes.").grid(pady=12)

        if not reminders:
            empty_state(
                self.reminders_body,
                "No tenés recordatorios. Creá uno arriba, o pedíselo a ATLAS por voz.",
            ).grid(pady=20)
            return

        for index, reminder in enumerate(reminders):
            subtitle = "Hecho" if reminder["done"] else format_due(reminder["due_at"])
            row = MiniRow(
                self.reminders_body, reminder["text"], subtitle,
                accent=theme.OK if reminder["done"] else theme.ACCENT,
            )
            if not reminder["done"]:
                ctk.CTkButton(
                    row.trailing, text="Listo", width=58, height=26, font=theme.FONT_TINY,
                    corner_radius=13, fg_color="transparent", hover_color=theme.PANEL,
                    border_width=1, border_color=theme.BORDER_BRIGHT, text_color=theme.ACCENT,
                    command=lambda r=reminder: self._reminder_action(api_client.complete_reminder, r["id"]),
                ).pack(side="left", padx=(0, 5))
            ctk.CTkButton(
                row.trailing, text="Borrar", width=62, height=26, font=theme.FONT_TINY,
                corner_radius=13, fg_color="transparent", hover_color=theme.PANEL,
                border_width=1, border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT_DIM,
                command=lambda r=reminder: self._reminder_action(api_client.delete_reminder, r["id"]),
            ).pack(side="left")
            row.grid(row=index, column=0, sticky="ew", pady=3)

    def _reminder_action(self, action, reminder_id: int) -> None:
        def worker() -> None:
            try:
                action(reminder_id)
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._append_chat, "ATLAS", f"(error: {exc})")
            self.after(0, self.refresh_reminders)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_create_reminder(self) -> None:
        text = self.reminder_text.get().strip()
        raw_due = self.reminder_due.get().strip()
        if not text or not raw_due:
            self._append_chat("ATLAS", "(Completá el texto y la fecha del recordatorio.)")
            return
        try:
            due = datetime.strptime(raw_due, "%d/%m/%Y %H:%M")
        except ValueError:
            self._append_chat("ATLAS", "(La fecha debe tener el formato DD/MM/AAAA HH:MM.)")
            return

        def worker() -> None:
            try:
                api_client.create_reminder(text, due.isoformat())
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._append_chat, "ATLAS", f"(error creando el recordatorio: {exc})")
                return
            self.after(0, self.reminder_text.delete, 0, "end")
            self.after(0, self.reminder_due.delete, 0, "end")
            self.after(0, self.refresh_reminders)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ---------- memoria ----------

    def refresh_memory(self) -> None:
        self._load(api_client.list_memory, self._render_memory)

    def _render_memory(self, entries: list[dict] | None, error: str | None) -> None:
        clear(self.memory_body)
        if error:
            empty_state(self.memory_body, f"Error cargando memoria: {error}").grid(pady=20)
            return
        if not entries:
            empty_state(self.memory_body, "ATLAS todavía no tiene nada guardado sobre vos.").grid(pady=20)
            return
        for index, entry in enumerate(entries):
            row = MiniRow(self.memory_body, entry["content"], entry["category"], accent=theme.ACCENT)
            ctk.CTkButton(
                row.trailing, text="Olvidar", width=68, height=26, font=theme.FONT_TINY,
                corner_radius=13, fg_color="transparent", hover_color=theme.PANEL,
                border_width=1, border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT_DIM,
                command=lambda e=entry: self._forget_memory(e["id"]),
            ).pack()
            row.grid(row=index, column=0, sticky="ew", pady=3)

    def _forget_memory(self, memory_id: int) -> None:
        def worker() -> None:
            try:
                api_client.delete_memory(memory_id)
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._append_chat, "ATLAS", f"(error: {exc})")
            self.after(0, self.refresh_memory)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ---------- herramientas ----------

    def refresh_tools(self) -> None:
        self._load(api_client.list_tools, self._render_tools)

    def _render_tools(self, tools: list[dict] | None, error: str | None) -> None:
        clear(self.tools_body)
        if error:
            empty_state(self.tools_body, f"Error cargando herramientas: {error}").grid(pady=20)
            return
        ctk.CTkLabel(
            self.tools_body,
            text="Todo lo que ATLAS sabe hacer. La IA elige cuál usar según lo que le pidas.",
            font=theme.FONT_TINY, text_color=theme.TEXT_FAINT, anchor="w", wraplength=600, justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for index, tool in enumerate(tools or [], start=1):
            MiniRow(
                self.tools_body, tool["name"], tool.get("description", ""), accent=theme.ACCENT,
            ).grid(row=index, column=0, sticky="ew", pady=3)

    # ---------- actividad ----------

    def refresh_activity(self) -> None:
        self._load(lambda: api_client.get_activity(30), self._render_activity)

    def _render_activity(self, entries: list[dict] | None, error: str | None) -> None:
        clear(self.activity_body)
        clear(self.home_activity)
        if error:
            empty_state(self.activity_body, f"Error cargando actividad: {error}").grid(pady=20)
            return
        entries = entries or []
        if not entries:
            empty_state(self.activity_body, "Todavía no hay actividad registrada.").grid(pady=20)
            empty_state(self.home_activity, "Sin actividad todavía.").grid(pady=12)
            return

        for index, entry in enumerate(entries):
            when = datetime.fromisoformat(entry["created_at"]).strftime("%H:%M")
            MiniRow(
                self.activity_body, describe_tool(entry["tool_name"]),
                f"{when} · {entry.get('result_summary') or ''}"[:110],
                accent=theme.ACCENT if entry["success"] else theme.DANGER,
            ).grid(row=index, column=0, sticky="ew", pady=3)

        for index, entry in enumerate(entries[:6]):
            when = datetime.fromisoformat(entry["created_at"]).strftime("%H:%M")
            frame = ctk.CTkFrame(self.home_activity, fg_color="transparent")
            frame.grid(row=index, column=0, sticky="ew", pady=2)
            frame.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                frame, text=when, font=theme.FONT_TINY, text_color=theme.TEXT_FAINT, width=38, anchor="w"
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(
                frame, text=describe_tool(entry["tool_name"]), font=theme.FONT_TINY,
                text_color=theme.TEXT if entry["success"] else theme.DANGER, anchor="w",
            ).grid(row=0, column=1, sticky="ew")

    # ---------- notificaciones ----------

    def refresh_notifications(self) -> None:
        self._load(api_client.list_notifications, self._render_notifications)

    def _render_notifications(self, notifications: list[dict] | None, error: str | None) -> None:
        clear(self.notifications_body)
        if error:
            empty_state(self.notifications_body, f"Error cargando notificaciones: {error}").grid(pady=20)
            return
        notifications = notifications or []
        unread = sum(1 for n in notifications if not n["read"])
        self._set_nav_badge("notifications", unread)

        if not notifications:
            empty_state(self.notifications_body, "Sin notificaciones.").grid(pady=20)
            return
        for index, notification in enumerate(notifications):
            when = datetime.fromisoformat(notification["created_at"]).strftime("%d/%m %H:%M")
            row = MiniRow(
                self.notifications_body, notification["message"],
                f"{'Nueva' if not notification['read'] else 'Leída'} · {when}",
                accent=theme.ACCENT if not notification["read"] else theme.BORDER_BRIGHT,
            )
            if not notification["read"]:
                ctk.CTkButton(
                    row.trailing, text="Marcar leída", width=100, height=26, font=theme.FONT_TINY,
                    corner_radius=13, fg_color="transparent", hover_color=theme.PANEL,
                    border_width=1, border_color=theme.BORDER_BRIGHT, text_color=theme.TEXT_DIM,
                    command=lambda n=notification: self._mark_read(n["id"]),
                ).pack()
            row.grid(row=index, column=0, sticky="ew", pady=3)

    def _mark_read(self, notification_id: int) -> None:
        def worker() -> None:
            try:
                api_client.mark_notification_read(notification_id)
            except Exception:  # noqa: BLE001
                pass
            self.after(0, self.refresh_notifications)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ---------- configuración ----------

    def _render_settings(self) -> None:
        if not hasattr(self, "settings_body"):
            return
        clear(self.settings_body)
        rows = [
            ("Servidor", str(api_client.ATLAS_API_URL)),
            (
                "Palabra de activación",
                f'"{getattr(self, "wake_word", "ali").capitalize()}" — ATLAS_WAKE_WORD en backend/.env',
            ),
            (
                "Nombre del saludo",
                getattr(self, "user_name", "") or "Sin configurar (ATLAS_USER_NAME en backend/.env)",
            ),
            ("IP en la red local", getattr(self, "lan_ip", "") or "desconocida"),
        ]
        for index, (title, value) in enumerate(rows):
            MiniRow(self.settings_body, title, value, accent=theme.BORDER_BRIGHT).grid(
                row=index, column=0, sticky="ew", pady=3
            )
