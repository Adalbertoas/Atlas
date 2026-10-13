import { type ReactNode, useEffect, useRef, useState } from "react";

export type WindowBox = { x: number; y: number; w: number; h: number };
export type FloatingPanelProps = {
  id: string;
  title: string;
  icon?: ReactNode;
  children: ReactNode;
  initial: WindowBox;
  zIndex: number;
  onFocus: () => void;
  onClose: () => void;
  onMinimize?: (value: boolean) => void;
};

const storageKey = "atlas.window-layout.v1";
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

export function FloatingPanel({ id, title, icon, children, initial, zIndex, onFocus, onClose, onMinimize }: FloatingPanelProps) {
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
  const toggleMaximize = () => { onFocus(); if (maximized && restore.current) { setBox(restore.current); setMaximized(false); } else { restore.current = box; setBox({ x: 178, y: 92, w: window.innerWidth - 570, h: window.innerHeight - 174 }); setMaximized(true); } };
  return <section data-panel={id} className={`float ${minimized ? "is-minimized" : ""} ${maximized ? "is-maximized" : ""}`} style={{ left: box.x, top: box.y, width: box.w, height: minimized ? 44 : box.h, zIndex }} onPointerDown={onFocus}>
    <header className="float-titlebar" onPointerDown={beginDrag}><span>{icon}<b>{title}</b></span><div><button aria-label={`Minimizar ${title}`} onClick={toggleMinimize}>-</button><button aria-label={`Maximizar ${title}`} onClick={toggleMaximize}>□</button><button aria-label={`Cerrar ${title}`} onClick={onClose}>×</button></div></header>
    {!minimized && <div className="float-content">{children}</div>}
    {!minimized && <button className="resize-handle" aria-label={`Redimensionar ${title}`} onPointerDown={beginResize} />}
  </section>;
}
