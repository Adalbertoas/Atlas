// Estudio creativo: generar imágenes (OpenAI / Pollinations) y dibujos vectoriales
// (Claude) sin pasar por el chat, con galería persistente y atajos de escritura creativa.
import { useCallback, useEffect, useState } from "react";
import { api, errorText, relativeTime } from "./api";
import { Glyph } from "./Glyph";
import "./studio.css";
import { KEYS_CHANGED_EVENT } from "./ApiKeysSettings";

export type Creation = { id: string; mime_type: string; engine: string; prompt: string; width: number; height: number; created_at: string; path: string; data?: string; thumb?: string; thumb_mime?: string };
type Engines = { available: string[]; default: string | null; styles: string[]; aspects: string[]; folder: string };

const ENGINE_INFO: Record<string, { label: string; hint: string }> = {
  auto: { label: "Auto", hint: "El mejor motor disponible" },
  openai: { label: "OpenAI", hint: "Máxima calidad · de pago" },
  pollinations: { label: "Pollinations", hint: "Gratis · con marca de agua" },
  claude: { label: "Vectorial", hint: "Claude dibuja logos, íconos y diagramas (SVG)" },
};
const STYLE_LABELS: Record<string, string> = { foto: "Foto", cine: "Cine", ilustracion: "Ilustración", anime: "Anime", acuarela: "Acuarela", oleo: "Óleo", "3d": "3D", pixel: "Pixel art", boceto: "Boceto", neon: "Neón" };
const ASPECT_ICONS: Record<string, [string, number, number]> = { cuadrado: ["Cuadrado", 14, 14], horizontal: ["Horizontal", 18, 12], vertical: ["Vertical", 12, 18] };
const IDEAS = ["Un faro solitario bajo una tormenta eléctrica", "Un zorro astronauta flotando sobre la Tierra", "Una ciudad flotante al atardecer, estilo Ghibli", "Retrato de una robot pintora en su estudio", "Un bosque bioluminiscente de noche", "Una taza de café humeante sobre libros antiguos"];
const WRITING: [string, string, string][] = [
  ["pen", "Cuento corto", "Escribe un cuento corto original y sorprendente sobre "],
  ["quote", "Poema", "Escribe un poema sobre "],
  ["bulb", "Lluvia de ideas", "Dame 10 ideas creativas y poco obvias para "],
  ["sparkle", "Eslogan", "Propón 8 eslóganes memorables para "],
  ["music", "Letra de canción", "Escribe la letra de una canción sobre "],
  ["film", "Guion", "Escribe un guion corto (escena) sobre "],
];

export const creationSrc = (c: Pick<Creation, "mime_type" | "data">) => `data:${c.mime_type};base64,${c.data}`;
export const creationFilename = (c: Pick<Creation, "path" | "mime_type">) => c.path.split(/[\\/]/).pop() || `atlas${c.mime_type === "image/svg+xml" ? ".svg" : ".png"}`;

/** Visor a pantalla completa con descarga. Esc o clic afuera para cerrar. */
export function Lightbox({ src, caption, filename, onClose }: { src: string; caption?: string; filename?: string; onClose: () => void }) {
  useEffect(() => { const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, [onClose]);
  return <div className="lightbox" role="dialog" aria-label="Imagen ampliada" onClick={onClose}>
    <figure onClick={e => e.stopPropagation()}>
      <img src={src} alt={caption || "Imagen"} />
      <figcaption>
        <span>{caption}</span>
        <a className="lightbox-btn" href={src} download={filename || "atlas-imagen"}><Glyph name="download" size={15} /> Descargar</a>
        <button className="lightbox-btn" onClick={onClose}><Glyph name="x" size={15} /> Cerrar</button>
      </figcaption>
    </figure>
  </div>;
}

export function CreativeStudio({ online, onAsk, onToast, onOpenSettings }: { online: boolean; onAsk: (prompt: string) => void; onToast: (text: string) => void; onOpenSettings: () => void }) {
  const [engines, setEngines] = useState<Engines | null>(null);
  const [engine, setEngine] = useState("auto"), [style, setStyle] = useState(""), [aspect, setAspect] = useState("cuadrado");
  const [prompt, setPrompt] = useState(""), [busy, setBusy] = useState<"" | "image" | "enhance">(""), [error, setError] = useState("");
  const [current, setCurrent] = useState<Creation | null>(null), [gallery, setGallery] = useState<Creation[]>([]), [zoom, setZoom] = useState<Creation | null>(null);

  const loadGallery = useCallback(() => api<Creation[]>("GET", "/creative/gallery", { query: { limit: 18 } }).then(setGallery).catch(() => {}), []);
  useEffect(() => {
    if (!online) return;
    const loadEngines = () => api<Engines>("GET", "/creative/engines").then(setEngines).catch(e => setError(errorText(e)));
    void loadEngines(); void loadGallery();
    // Al guardar o quitar la clave de OpenAI en Configuración, el motor aparece o desaparece al instante.
    window.addEventListener(KEYS_CHANGED_EVENT, loadEngines);
    return () => window.removeEventListener(KEYS_CHANGED_EVENT, loadEngines);
  }, [online, loadGallery]);

  const can = (name: string) => name === "auto" ? Boolean(engines?.default) : Boolean(engines?.available.includes(name));
  const vector = engine === "claude";
  const generate = async (source = prompt) => {
    const text = source.trim();
    if (text.length < 3 || busy) return;
    setBusy("image"); setError("");
    try {
      const made = await api<Creation>("POST", "/creative/image", { body: { prompt: text, engine, style: vector ? "" : style, aspect } });
      setCurrent(made); void loadGallery();
    } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };
  const enhance = async () => {
    if (prompt.trim().length < 3 || busy) return;
    setBusy("enhance"); setError("");
    try { setPrompt((await api<{ prompt: string }>("POST", "/creative/enhance", { body: { prompt } })).prompt); } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };
  const open = async (item: Creation) => {
    try { const full = item.data ? item : await api<Creation>("GET", `/creative/gallery/${item.id}`); setCurrent(full); setZoom(full); } catch (e) { onToast(errorText(e)); }
  };
  const remove = async (item: Creation) => {
    try { await api("DELETE", `/creative/gallery/${item.id}`); if (current?.id === item.id) setCurrent(null); void loadGallery(); } catch (e) { onToast(errorText(e)); }
  };
  const busyLabel = busy === "enhance" ? "Mejorando el prompt…" : vector ? "Claude está dibujando… (puede tardar hasta un minuto)" : `Generando${engine !== "auto" ? ` con ${ENGINE_INFO[engine]?.label}` : ""}…`;

  return <div className="studio">
    <section className="studio-compose">
      <div className="studio-engines" role="radiogroup" aria-label="Motor">
        {["auto", "openai", "pollinations", "claude"].map(name => <button key={name} role="radio" aria-checked={engine === name} className={engine === name ? "is-active" : ""} disabled={!can(name)} title={can(name) ? ENGINE_INFO[name].hint : name === "openai" ? "Agrega tu clave de OpenAI en Configuración" : "No disponible con la configuración actual"} onClick={() => setEngine(name)}><b>{ENGINE_INFO[name].label}</b><small>{ENGINE_INFO[name].hint}</small></button>)}
      </div>
      {engines && !engines.available.includes("openai") && <button className="studio-keyhint" onClick={onOpenSettings}><Glyph name="key" size={13} /> ¿Quieres más calidad? Agrega tu clave de OpenAI</button>}
      <div className="studio-prompt">
        <textarea value={prompt} maxLength={3000} onChange={e => setPrompt(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void generate(); } }} placeholder={vector ? "Describe el logo, ícono o ilustración… (ej: logo minimalista de un búho para una librería, azul y dorado)" : "Describe tu imagen… (ej: un faro bajo una tormenta eléctrica, al óleo)"} />
        <div className="studio-prompt-tools">
          <button onClick={() => setPrompt(IDEAS[Math.floor(Math.random() * IDEAS.length)])} title="Una idea al azar"><Glyph name="bulb" size={14} /> Inspírame</button>
          {!vector && <button onClick={enhance} disabled={prompt.trim().length < 3 || Boolean(busy)} title="La IA convierte tu idea en un prompt detallado (en inglés, que los motores entienden mejor)"><Glyph name="sparkle" size={14} /> Mejorar con IA</button>}
          <small>{prompt.length}/3000 · Ctrl+Enter</small>
        </div>
      </div>
      {!vector && <div className="studio-styles" role="radiogroup" aria-label="Estilo">
        <button role="radio" aria-checked={!style} className={!style ? "is-active" : ""} onClick={() => setStyle("")}>Libre</button>
        {(engines?.styles ?? Object.keys(STYLE_LABELS)).map(s => <button key={s} role="radio" aria-checked={style === s} className={style === s ? "is-active" : ""} onClick={() => setStyle(s)}>{STYLE_LABELS[s] ?? s}</button>)}
      </div>}
      <div className="studio-actions">
        <div className="studio-aspects" role="radiogroup" aria-label="Formato">
          {Object.entries(ASPECT_ICONS).map(([key, [label, w, h]]) => <button key={key} role="radio" aria-checked={aspect === key} className={aspect === key ? "is-active" : ""} title={label} onClick={() => setAspect(key)}><i style={{ width: w, height: h }} />{label}</button>)}
        </div>
        <button className="studio-go" onClick={() => void generate()} disabled={!online || prompt.trim().length < 3 || Boolean(busy) || !can(engine)}><Glyph name={vector ? "vector" : "brush"} size={16} />{busy === "image" ? "Creando…" : vector ? "Dibujar" : "Generar"}</button>
      </div>
      {busy && <div className="studio-progress" role="status"><span>{busyLabel}</span><i /></div>}
      {error && <p className="studio-error" role="alert"><Glyph name="alert" size={14} />{error}</p>}
      {!online && <p className="studio-error"><Glyph name="alert" size={14} />ATLAS sin conexión.</p>}
    </section>

    <section className={`studio-stage ${current ? "" : "is-empty"}`}>
      {current?.data ? <>
        <button className="studio-stage-img" onClick={() => setZoom(current)} title="Ampliar"><img src={creationSrc(current)} alt={current.prompt} /></button>
        <div className="studio-stage-bar">
          <span title={current.prompt}><em>{ENGINE_INFO[current.engine]?.label ?? current.engine}</em>{current.prompt}</span>
          <button title="Ampliar" onClick={() => setZoom(current)}><Glyph name="expand" size={15} /></button>
          <a title="Descargar" href={creationSrc(current)} download={creationFilename(current)}><Glyph name="download" size={15} /></a>
          <button title="Otra versión con el mismo texto" onClick={() => { setPrompt(current.prompt); void generate(current.prompt); }} disabled={Boolean(busy)}><Glyph name="refresh" size={15} /></button>
        </div>
      </> : <div className="studio-placeholder"><Glyph name="image" size={34} /><b>Tu lienzo</b><small>Lo que crees aparece aquí y se guarda solo en tu galería.</small></div>}
    </section>

    <section className="studio-gallery">
      <header><Glyph name="image" size={13} /> Galería <span>{gallery.length ? `${gallery.length} recientes` : ""}</span><button onClick={() => window.atlas.invoke("creative:open-folder").catch(e => onToast(errorText(e)))} title={engines?.folder}><Glyph name="folder" size={13} /> Abrir carpeta</button></header>
      {gallery.length ? <ul>{gallery.map(item => <li key={item.id} className={current?.id === item.id ? "is-current" : ""}>
        <button onClick={() => open(item)} title={`${item.prompt}\n${relativeTime(item.created_at)}`}><img src={`data:${item.thumb_mime};base64,${item.thumb}`} alt={item.prompt} loading="lazy" /></button>
        <button className="studio-del" title="Borrar" aria-label="Borrar creación" onClick={() => remove(item)}><Glyph name="trash" size={12} /></button>
      </li>)}</ul> : <p className="studio-muted">Todavía no hay creaciones.</p>}
    </section>

    <section className="studio-write">
      <header><Glyph name="pen" size={13} /> Escritura creativa</header>
      <div>{WRITING.map(([icon, label, text]) => <button key={label} onClick={() => onAsk(text)}><Glyph name={icon} size={14} />{label}</button>)}</div>
    </section>

    {zoom?.data && <Lightbox src={creationSrc(zoom)} caption={zoom.prompt} filename={creationFilename(zoom)} onClose={() => setZoom(null)} />}
  </div>;
}
