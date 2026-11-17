// Acceso a los datos del backend para los paneles del escritorio.
// Pasa por el canal "atlas:api" del proceso principal, que solo deja usar
// una lista blanca de rutas (electron/main.ts → apiRoutes).
import { useCallback, useEffect, useRef, useState } from "react";

export type Personality = {
  tone: string;
  verbosity: "breve" | "detallado";
  custom_instructions: string;
  assistant_name: string;
  user_name: string;
  formality: "tu" | "usted" | "vos";
  humor: "ninguno" | "sutil" | "frecuente";
  home_city: string;
};
export type Memory = { id: number; category: string; content: string; tags: string[]; created_at: string };
export type Reminder = { id: number; message: string; due_at: string; repeat: string; description: string };
export type Activity = { id: number; tool_name: string; risk_level: string; success: boolean; result_summary: string; created_at: string };
export type Notification = { id: number; message: string; read: boolean; created_at: string };
export type ToolInfo = { name: string; description: string; risk_level: string };
export type DayForecast = { date: string; day_name: string; description: string; icon: string; max_c: number; min_c: number; rain_chance: number | null };
export type Weather = { place: string; temperature_c: number; feels_like_c: number; humidity: number; wind_kmh: number; description: string; icon: string; is_day: boolean; days: DayForecast[] };
export type Headline = { title: string; source: string; published: string; url: string };

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export function api<T>(method: Method, path: string, options: { query?: Record<string, string | number>; body?: unknown } = {}): Promise<T> {
  return window.atlas.invoke("atlas:api", { method, path, ...options }) as Promise<T>;
}

/** Electron envuelve el error: "Error invoking remote method 'atlas:invoke': Error: <mensaje>". */
export function errorText(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^Error invoking remote method '[^']+': (Error: )?/, "");
}

/** Las fechas del backend son UTC sin zona ("2026-11-17T14:00:00"). */
export function parseUtc(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

export function relativeTime(value: string | Date, now = Date.now()): string {
  const date = typeof value === "string" ? parseUtc(value) : value;
  const seconds = Math.round((date.getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  const format = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
  if (abs < 45) return seconds >= 0 ? "en unos segundos" : "hace un momento";
  if (abs < 3600) return format.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return format.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 7) return format.format(Math.round(seconds / 86400), "day");
  return date.toLocaleDateString("es", { day: "numeric", month: "short" });
}

/**
 * Carga datos y los refresca cada `intervalMs` (0 = solo al montar).
 * `reload()` vuelve a pedirlos al instante (después de borrar algo, por ejemplo).
 */
export function usePolled<T>(load: () => Promise<T>, intervalMs: number, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;
  const reload = useCallback(async () => {
    try {
      const value = await loadRef.current();
      setData(value);
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (!enabled) return;
    void reload();
    if (!intervalMs) return;
    const timer = window.setInterval(() => void reload(), intervalMs);
    return () => window.clearInterval(timer);
  }, [reload, intervalMs, enabled]);
  return { data, error, loading, reload, setData };
}

/** Nombre legible de cada tool para el panel de actividad. */
export const TOOL_LABELS: Record<string, string> = {
  get_weather: "Consultó el clima",
  get_news: "Buscó noticias",
  convert_currency: "Convirtió divisas",
  calculate: "Hizo un cálculo",
  generate_password: "Generó una contraseña",
  open_website: "Abrió una web",
  set_volume: "Ajustó el volumen",
  lock_computer: "Bloqueó la PC",
  web_search: "Buscó en internet",
  read_web_page: "Leyó una página",
  get_system_info: "Revisó el sistema",
  get_current_time: "Consultó la hora",
  open_application: "Abrió una aplicación",
  close_application: "Cerró una aplicación",
  list_processes: "Listó procesos",
  open_file: "Abrió un archivo",
  control_media: "Controló la música",
  list_files: "Listó archivos",
  search_files: "Buscó archivos",
  search_documents: "Buscó en documentos",
  create_memory: "Guardó un recuerdo",
  search_memory: "Consultó su memoria",
  create_reminder: "Creó un recordatorio",
  list_reminders: "Revisó recordatorios",
  cancel_reminder: "Canceló un recordatorio",
  read_clipboard: "Leyó el portapapeles",
  write_clipboard: "Copió al portapapeles",
  manage_window: "Movió una ventana",
  save_screenshot: "Guardó una captura",
  analyze_screenshot: "Miró la pantalla",
  daily_briefing: "Preparó el resumen del día",
  list_devices: "Revisó dispositivos",
  set_device_state: "Controló un dispositivo",
  control_room: "Controló una habitación",
  run_routine: "Ejecutó una rutina",
  query_world: "Consultó el mundo",
  show_world_view: "Mostró el mapa",
};
