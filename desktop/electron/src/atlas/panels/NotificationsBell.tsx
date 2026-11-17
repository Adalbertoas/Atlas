// Campana de la barra superior: recordatorios vencidos, alertas y avisos del backend.
import { useEffect, useRef, useState } from "react";
import { api, relativeTime, usePolled, type Notification } from "./api";
import { Glyph } from "./Glyph";

export function NotificationsBell({ online, onNew }: { online: boolean; onNew: (message: string) => void }) {
  const [open, setOpen] = useState(false);
  const notifications = usePolled(() => api<Notification[]>("GET", "/notifications"), 15_000, online);
  const list = notifications.data ?? [];
  const unread = list.filter((n) => !n.read);
  const seen = useRef<Set<number> | null>(null);
  const box = useRef<HTMLDivElement>(null);

  // Aviso (toast) solo para las que llegan mientras la app está abierta, no las viejas.
  useEffect(() => {
    if (!notifications.data) return;
    if (seen.current === null) { seen.current = new Set(notifications.data.map((n) => n.id)); return; }
    for (const n of notifications.data) {
      if (!seen.current.has(n.id)) { seen.current.add(n.id); if (!n.read) onNew(n.message); }
    }
  }, [notifications.data, onNew]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  const markRead = async (n: Notification) => {
    if (n.read) return;
    notifications.setData((old) => old?.map((x) => (x.id === n.id ? { ...x, read: true } : x)) ?? null);
    try { await api("PATCH", `/notifications/${n.id}/read`); } catch { void notifications.reload(); }
  };
  const markAll = () => { for (const n of unread) void markRead(n); };

  return (
    <div className="bell" ref={box}>
      <button title="Notificaciones" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Glyph name="bell" size={18} />
        {unread.length > 0 && <span className="bell-badge">{unread.length > 9 ? "9+" : unread.length}</span>}
      </button>
      {open && (
        <div className="bell-menu" role="dialog" aria-label="Notificaciones">
          <header><b>Notificaciones</b>{unread.length > 0 && <button onClick={markAll}>Marcar todo leído</button>}</header>
          {list.length === 0 ? (
            <p className="bell-empty">{notifications.error || "Todo tranquilo por aquí."}</p>
          ) : (
            <ul>
              {list.slice(0, 20).map((n) => (
                <li key={n.id} className={n.read ? "" : "is-unread"} onClick={() => void markRead(n)}>
                  <i /><span><p>{n.message}</p><small>{relativeTime(n.created_at)}</small></span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
