import { type ReactNode, useEffect, useRef, useState } from "react";

export type WindowBox = { x: number; y: number; w: number; h: number };
export type FloatingPanelProps = {
  id: string;
  title: string;
  icon?: ReactNode;
  children: ReactNode;
  initial: WindowBox;
  zIndex: number;
  active?: boolean;
  onFocus: () => void;
  onClose: () => void;
  onMinimize?: (value: boolean) => void;
};

// v2: distribución nueva sin ventanas superpuestas (la v1 quedaba encimada con la barra lateral).
export const LAYOUT_STORAGE_KEY = "atlas.window-layout.v2";
const storageKey = LAYOUT_STORAGE_KEY;
const minSize = { w: 260, h: 150 };

function clampToViewport(box: WindowBox): WindowBox {
  const maxW = Math.max(minSize.w, window.innerWidth - 16);
  const maxH = Math.max(minSize.h, window.innerHeight - 84);
  const w = Math.min(Math.max(minSize.w, box.w), maxW);
  const h = Math.min(Math.max(minSize.h, box.h), maxH);
  return { x: Math.max(8, Math.min(window.innerWidth - w - 8, box.x)), y: Math.max(76, Math.min(window.innerHeight - h - 8, box.y)), w, h };
}

function readBox(id: string, initial: WindowBox): WindowBox {
  try {
    const all = JSON.parse(localStorage.getItem(storageKey) || "{}") as Record<string, WindowBox>;
    const saved = all[id];
    if (!saved || !Number.isFinite(saved.x) || !Number.isFinite(saved.y)) return initial;
    return { x: Math.max(8, saved.x), y: Math.max(76, saved.y), w: Math.max(minSize.w, saved.w), h: Math.max(minSize.h, saved.h) };
  } catch { return initial; }
}
function persist(id: string, box: WindowBox) {
  try { const all = JSON.parse(localStorage.getItem(storageKey) || "{}"); localStorage.setItem(storageKey, JSON.stringify({ ...all, [id]: box })); } catch { /* persistence is optional */ }
}

export function FloatingPanel({ id, title, icon, children, initial, zIndex, active = false, onFocus, onClose, onMinimize }: FloatingPanelProps) {
  const [box, setBox] = useState(() => clampToViewport(readBox(id, initial)));
  const [minimized, setMinimized] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const restore = useRef<WindowBox | null>(null);
  const boxRef = useRef(box); boxRef.current = box;
  useEffect(() => persist(id, box), [box, id]);
  useEffect(() => { const resize = () => setBox(current => clampToViewport(current)); window.addEventListener("resize", resize); return () => window.removeEventListener("resize", resize); }, []);
  const beginDrag = (event: React.PointerEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest("button")) return;
    event.currentTarget.setPointerCapture(event.pointerId); onFocus();
    const start = boxRef.current, sx = event.clientX, sy = event.clientY;
    const move = (moveEvent: PointerEvent) => setBox(current => ({ ...current, x: Math.max(8, Math.min(window.innerWidth - 120, start.x + moveEvent.clientX - sx)), y: Math.max(76, Math.min(window.innerHeight - 52, start.y + moveEvent.clientY - sy)) }));
    const end = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", end);
  };
  const beginResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId); onFocus();
    const start = boxRef.current, sx = event.clientX, sy = event.clientY;
    const move = (moveEvent: PointerEvent) => setBox(current => ({ ...current, w: Math.max(minSize.w, Math.min(window.innerWidth - current.x - 8, start.w + moveEvent.clientX - sx)), h: Math.max(minSize.h, Math.min(window.innerHeight - current.y - 8, start.h + moveEvent.clientY - sy)) }));
    const end = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", end);
  };
  const toggleMinimize = () => { setMinimized(value => { onMinimize?.(!value); return !value; }); };
  const toggleMaximize = () => { onFocus(); if (maximized && restore.current) { setBox(restore.current); setMaximized(false); } else { restore.current = box; setBox({ x: initial.x < 260 ? initial.x : 182, y: 88, w: window.innerWidth - 198, h: window.innerHeight - 180 }); setMaximized(true); } };
  return <section data-panel={id} className={`float ${active ? "is-active" : ""} ${minimized ? "is-minimized" : ""} ${maximized ? "is-maximized" : ""}`} style={{ left: box.x, top: box.y, width: box.w, height: minimized ? 44 : box.h, zIndex }} onPointerDown={onFocus}>
    <header className="float-titlebar" onPointerDown={beginDrag}><span>{icon}<b>{title}</b></span><div><button aria-label={`Minimizar ${title}`} title="Minimizar" onClick={toggleMinimize}><svg viewBox="0 0 12 12"><path d="M2 6h8" /></svg></button><button aria-label={`Maximizar ${title}`} title={maximized ? "Restaurar" : "Maximizar"} onClick={toggleMaximize}><svg viewBox="0 0 12 12">{maximized ? <path d="M4 2h6v6M2 4h6v6H2Z" /> : <path d="M2 2h8v8H2Z" />}</svg></button><button className="close" aria-label={`Cerrar ${title}`} title="Cerrar" onClick={onClose}><svg viewBox="0 0 12 12"><path d="m2.5 2.5 7 7m0-7-7 7" /></svg></button></div></header>
    {!minimized && <div className="float-content">{children}</div>}
    {!minimized && <button className="resize-handle" aria-label={`Redimensionar ${title}`} onPointerDown={beginResize} />}
  </section>;
}
