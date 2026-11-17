// Paneles con datos reales del backend: memoria, recordatorios, actividad y acciones rápidas.
import { useState } from "react";
import { api, errorText, relativeTime, TOOL_LABELS, usePolled, type Activity, type Memory, type Reminder, type ToolInfo } from "./api";
import { Glyph } from "./Glyph";

function Status({ error, loading, empty, icon, title, hint }: { error: string; loading: boolean; empty: boolean; icon: string; title: string; hint: string }) {
  if (error) return <div className="panel-status is-error"><Glyph name="alert" size={22} /><b>No se pudo cargar</b><small>{error}</small></div>;
  if (loading) return <div className="panel-status"><span className="spinner" /><small>Cargando…</small></div>;
  if (empty) return <div className="panel-status"><Glyph name={icon} size={24} /><b>{title}</b><small>{hint}</small></div>;
  return null;
}

// ---------- Memoria (lo que ATLAS sabe de vos) ----------
export function MemoryPanel({ online }: { online: boolean }) {
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const memories = usePolled(
    () => (query.trim() ? api<Memory[]>("GET", "/memory/search", { query: { q: query.trim() } }) : api<Memory[]>("GET", "/memory", { query: { limit: 50 } })),
    60_000,
    online,
  );
  const remove = async (id: number) => {
    memories.setData((old) => old?.filter((m) => m.id !== id) ?? null);
    try { await api("DELETE", `/memory/${id}`); } catch (err) { setNotice(errorText(err)); void memories.reload(); }
  };
  const add = async () => {
    const content = draft.trim();
    if (!content) return;
    setBusy(true);
    try {
      await api("POST", "/memory", { body: { content, category: "personal" } });
      setDraft("");
      setNotice("Guardado. ATLAS lo tendrá en cuenta.");
      void memories.reload();
    } catch (err) {
      setNotice(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  const list = memories.data ?? [];
  return (
    <div className="data-panel">
      <form className="panel-search" onSubmit={(e) => { e.preventDefault(); void memories.reload(); }}>
        <Glyph name="search" size={15} />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar en la memoria…" />
      </form>
      <div className="panel-scroll">
        <Status error={memories.error} loading={memories.loading} empty={!list.length} icon="brain" title={query ? "Nada coincide" : "Memoria vacía"} hint="Dile «recuerda que…» o agrégalo aquí abajo." />
        {list.map((m) => (
          <article key={m.id} className="memory-item">
            <span className="chip">{m.category}</span>
            <p>{m.content}</p>
            <footer><small>{relativeTime(m.created_at)}</small><button title="Olvidar" onClick={() => void remove(m.id)}><Glyph name="trash" size={14} /></button></footer>
          </article>
        ))}
      </div>
      {notice && <p className="panel-notice" onAnimationEnd={() => setNotice("")}>{notice}</p>}
      <form className="panel-add" onSubmit={(e) => { e.preventDefault(); void add(); }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Algo que ATLAS deba recordar…" disabled={!online || busy} />
        <button type="submit" disabled={!online || busy || !draft.trim()} title="Guardar"><Glyph name="plus" size={16} /></button>
      </form>
    </div>
  );
}

// ---------- Recordatorios ----------
export function RemindersPanel({ online, onAsk }: { online: boolean; onAsk: (prompt: string) => void }) {
  const reminders = usePolled(() => api<Reminder[]>("GET", "/reminders"), 30_000, online);
  const cancel = async (id: number) => {
    reminders.setData((old) => old?.filter((r) => r.id !== id) ?? null);
    try { await api("DELETE", `/reminders/${id}`); } catch { void reminders.reload(); }
  };
  const list = reminders.data ?? [];
  const repeatLabel: Record<string, string> = { daily: "diario", weekdays: "lun–vie", weekly: "semanal" };
  return (
    <div className="data-panel">
      <div className="panel-scroll">
        <Status error={reminders.error} loading={reminders.loading} empty={!list.length} icon="clock" title="Sin recordatorios" hint="«Recuérdame llamar a mamá en 20 minutos»." />
        {list.map((r) => (
          <article key={r.id} className="reminder-item">
            <Glyph name="clock" size={16} />
            <span><b>{r.message}</b><small>{relativeTime(r.due_at)}{repeatLabel[r.repeat] ? ` · ${repeatLabel[r.repeat]}` : ""}</small></span>
            <button title="Cancelar" onClick={() => void cancel(r.id)}><Glyph name="x" size={14} /></button>
          </article>
        ))}
      </div>
      <button className="panel-cta" onClick={() => onAsk("Recuérdame ")}><Glyph name="plus" size={14} /> Nuevo recordatorio</button>
    </div>
  );
}

// ---------- Actividad (registro de herramientas usadas) ----------
export function ActivityPanel({ online }: { online: boolean }) {
  const activity = usePolled(() => api<Activity[]>("GET", "/system/activity", { query: { limit: 15 } }), 20_000, online);
  const list = activity.data ?? [];
  return (
    <div className="data-panel">
      <div className="panel-scroll">
        <Status error={activity.error} loading={activity.loading} empty={!list.length} icon="sparkle" title="Sin actividad todavía" hint="Aquí aparece cada acción que ATLAS realiza." />
        <ol className="timeline">
          {list.map((a) => (
            <li key={a.id} className={a.success ? "ok" : "fail"} title={a.result_summary}>
              <i />
              <span><b>{TOOL_LABELS[a.tool_name] ?? a.tool_name}</b><small>{a.success ? (a.result_summary || "").slice(0, 80) : "Falló"}</small></span>
              <time>{relativeTime(a.created_at)}</time>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// ---------- Acciones rápidas ----------
const ACTIONS: { icon: string; label: string; prompt: string; tool?: string }[] = [
  { icon: "briefing", label: "Resumen del día", prompt: "Dame mi resumen del día", tool: "daily_briefing" },
  { icon: "partly", label: "Clima", prompt: "¿Cómo está el clima hoy y los próximos días?", tool: "get_weather" },
  { icon: "news", label: "Noticias", prompt: "¿Cuáles son las noticias más importantes de hoy?", tool: "get_news" },
  { icon: "coin", label: "Divisas", prompt: "¿A cuánto está el dólar hoy?", tool: "convert_currency" },
  { icon: "calc", label: "Calcular", prompt: "Calcula ", tool: "calculate" },
  { icon: "key", label: "Contraseña", prompt: "Genérame una contraseña segura", tool: "generate_password" },
  { icon: "clock", label: "Recordatorio", prompt: "Recuérdame ", tool: "create_reminder" },
  { icon: "camera", label: "Mira mi pantalla", prompt: "Mira mi pantalla y dime qué ves", tool: "analyze_screenshot" },
  { icon: "music", label: "Música", prompt: "Pausa la música", tool: "control_media" },
  { icon: "volume", label: "Volumen 50 %", prompt: "Pon el volumen al 50 %", tool: "set_volume" },
  { icon: "image", label: "Crear imagen", prompt: "Crea una imagen de ", tool: "generate_image" },
  { icon: "vector", label: "Dibujar logo", prompt: "Dibuja un logo para ", tool: "draw_vector" },
  { icon: "globe", label: "Buscar en web", prompt: "Busca en internet ", tool: "web_search" },
  { icon: "lock", label: "Bloquear PC", prompt: "Bloquea la computadora", tool: "lock_computer" },
];

export function ActionsPanel({ online, onAsk }: { online: boolean; onAsk: (prompt: string) => void }) {
  const tools = usePolled(() => api<ToolInfo[]>("GET", "/tools"), 0, online);
  const available = new Set((tools.data ?? []).map((t) => t.name));
  // Sin datos (backend apagado) se muestran todas; con datos, solo las que existen.
  const actions = tools.data ? ACTIONS.filter((a) => !a.tool || available.has(a.tool)) : ACTIONS;
  return (
    <div className="actions-panel">
      <div className="action-grid">
        {actions.map((a) => (
          <button key={a.label} onClick={() => onAsk(a.prompt)} title={a.prompt.trim()}>
            <Glyph name={a.icon} size={22} /><span>{a.label}</span>
          </button>
        ))}
      </div>
      <p className="actions-foot"><Glyph name="sparkle" size={12} /> {tools.data ? `${tools.data.length} herramientas disponibles` : online ? "Consultando herramientas…" : "ATLAS sin conexión"}</p>
    </div>
  );
}
