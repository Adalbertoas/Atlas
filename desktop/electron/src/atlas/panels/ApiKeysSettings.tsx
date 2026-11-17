// Claves de servicios externos (OpenAI) y motor de imágenes por defecto.
// La clave se escribe una vez: el backend la guarda en su .env y nunca la devuelve,
// solo informa si está configurada y sus últimos 4 caracteres.
import { useEffect, useState } from "react";
import { api, errorText } from "./api";
import { Glyph } from "./Glyph";

type KeysStatus = { openai: { configured: boolean; masked: string | null }; image_default_engine: string; env_path: string; message?: string };

/** Avisa a otros paneles (ej. el Estudio creativo) que cambiaron las claves. */
export const KEYS_CHANGED_EVENT = "atlas:keys-changed";

export function ApiKeysSettings({ online, onToast }: { online: boolean; onToast: (text: string) => void }) {
  const [status, setStatus] = useState<KeysStatus | null>(null);
  const [draft, setDraft] = useState(""), [show, setShow] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");

  useEffect(() => { if (online) api<KeysStatus>("GET", "/settings/keys").then(setStatus).catch(e => setError(errorText(e))); }, [online]);

  const save = async (body: { openai_api_key?: string; image_default_engine?: string }) => {
    setBusy(true); setError("");
    try {
      const result = await api<KeysStatus>("PUT", "/settings/keys", { body });
      setStatus(result); setDraft(""); setShow(false);
      onToast(result.message || "Guardado.");
      window.dispatchEvent(new Event(KEYS_CHANGED_EVENT));
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  if (!online) return <p className="setting-note">Conecta ATLAS para configurar las claves.</p>;
  const openai = status?.openai;
  return <div className="keys">
    <div className="key-card">
      <header>
        <span className="key-logo"><Glyph name="image" size={16} /></span>
        <span><b>OpenAI</b><small>Imágenes de alta calidad (gpt-image). Cada imagen se cobra en tu cuenta.</small></span>
        <em className={openai?.configured ? "is-on" : ""}>{openai?.configured ? `Configurada ${openai.masked}` : "Sin configurar"}</em>
      </header>
      <form onSubmit={e => { e.preventDefault(); if (draft.trim()) void save({ openai_api_key: draft }); }}>
        <label className="key-input">
          <input type={show ? "text" : "password"} value={draft} onChange={e => setDraft(e.target.value)} placeholder={openai?.configured ? "Pega una clave nueva para reemplazarla" : "sk-..."} autoComplete="off" spellCheck={false} aria-label="Clave de OpenAI" />
          <button type="button" onClick={() => setShow(v => !v)} title={show ? "Ocultar" : "Mostrar"}>{show ? "Ocultar" : "Ver"}</button>
        </label>
        <button className="primary" type="submit" disabled={busy || !draft.trim()}>{busy ? "Comprobando…" : "Guardar y probar"}</button>
        {openai?.configured && <button type="button" className="key-remove" disabled={busy} onClick={() => void save({ openai_api_key: "" })}>Quitar</button>}
      </form>
      <small className="key-help">Créala en platform.openai.com → API keys. Se guarda en el archivo .env del backend de este equipo; la interfaz nunca vuelve a mostrarla.</small>
    </div>

    <label className="select-row">
      <span>Motor de imágenes por defecto</span>
      <select value={status?.image_default_engine ?? "auto"} disabled={busy} onChange={e => void save({ image_default_engine: e.target.value })}>
        <option value="auto">Automático (OpenAI si hay clave)</option>
        <option value="openai">OpenAI</option>
        <option value="pollinations">Pollinations (gratis)</option>
      </select>
    </label>
    {error && <p className="studio-error" role="alert"><Glyph name="alert" size={14} />{error}</p>}
  </div>;
}
