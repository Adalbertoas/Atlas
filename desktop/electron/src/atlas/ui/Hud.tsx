import { useEffect, useState } from "react";

/* Piezas decorativas e informativas del HUD estilo holográfico:
   la retícula del fondo, el reloj y los medidores de CPU/RAM. */

const ticks = (count: number, r: number, long: number, short: number, every: number) =>
  Array.from({ length: count }, (_, i) => {
    const a = (i / count) * Math.PI * 2, len = i % every === 0 ? long : short;
    const c = Math.cos(a), s = Math.sin(a);
    return <line key={i} x1={c * r} y1={s * r} x2={c * (r - len)} y2={s * (r - len)} />;
  });

/** Anillos concéntricos con marcas, centrados donde vive el Neural Core (42 % de alto). */
export function HudBackdrop() {
  return <>
    <div className="hud-grid" />
    <svg className="hud-reticle" viewBox="-520 -520 1040 1040" aria-hidden="true">
      <g className="ring r-outer">{ticks(180, 500, 16, 6, 15)}<circle r="500" /></g>
      <g className="ring r-dash"><circle r="455" strokeDasharray="2 10" /></g>
      <g className="ring r-arcs">
        <circle r="410" strokeDasharray="220 60 40 60 120 320" />
        <circle r="398" strokeDasharray="4 18" className="faint" />
      </g>
      <g className="ring r-inner">{ticks(72, 340, 12, 5, 6)}<circle r="340" className="faint" /></g>
      <g className="ring r-core"><circle r="270" strokeDasharray="90 30" className="accent" /></g>
      <g className="crosshair">
        <line x1="-520" y1="0" x2="-300" y2="0" /><line x1="300" y1="0" x2="520" y2="0" />
        <line x1="0" y1="-520" x2="0" y2="-300" /><line x1="0" y1="300" x2="0" y2="520" />
      </g>
    </svg>
    <div className="hud-vignette" />
  </>;
}

/** Reloj en vivo con fecha. Se actualiza cada segundo. */
export function HudClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 1000); return () => clearInterval(timer); }, []);
  const time = now.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const date = now.toLocaleDateString("es", { weekday: "short", day: "2-digit", month: "short" }).replace(/\./g, "");
  return <div className="hud-clock" aria-label={`Hora ${time}`}><b>{time}</b><small>{date}</small></div>;
}

/** Medidor segmentado (10 bloques). Cambia a ámbar al 75 % y a rojo al 90 %. */
export function HudMeter({ label, value, available }: { label: string; value: number; available: boolean }) {
  const lit = available ? Math.round(Math.min(100, Math.max(0, value)) / 10) : 0;
  const level = value >= 90 ? "is-hot" : value >= 75 ? "is-warm" : "";
  return <div className={`hud-meter ${level}`} title={available ? `${label} ${value}%` : `${label} no disponible`}>
    <span>{label}</span>
    <i>{Array.from({ length: 10 }, (_, index) => <em key={index} className={index < lit ? "on" : ""} />)}</i>
    <b>{available ? `${value}%` : "--"}</b>
  </div>;
}
