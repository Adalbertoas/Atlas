// Configuración → Personalidad: nombre, cómo te llama, trato, humor, ciudad y estilos predefinidos.
import { useEffect, useState } from "react";
import { api, errorText, type Personality } from "./api";

type Preset = { id: string; label: string; hint: string; values: Partial<Personality> };

export const PRESETS: Preset[] = [
  { id: "mayordomo", label: "Mayordomo", hint: "Elegante y servicial, estilo asistente de película", values: { tone: "elegante, servicial y con la calma de un mayordomo británico", formality: "usted", humor: "sutil", verbosity: "breve" } },
  { id: "amigo", label: "Amigo", hint: "Cercano, relajado y con buen humor", values: { tone: "cercano, cálido y relajado, como un buen amigo", formality: "tu", humor: "frecuente", verbosity: "breve" } },
  { id: "ejecutivo", label: "Ejecutivo", hint: "Directo al grano, sin adornos", values: { tone: "directo, eficiente y preciso", formality: "tu", humor: "ninguno", verbosity: "breve" } },
  { id: "profesor", label: "Profesor", hint: "Paciente y explica con detalle", values: { tone: "paciente, didáctico y claro", formality: "tu", humor: "sutil", verbosity: "detallado" } },
];

const EMPTY: Personality = { tone: "", verbosity: "breve", custom_instructions: "", assistant_name: "ATLAS", user_name: "", formality: "tu", humor: "sutil", home_city: "" };

export function PersonalitySettings({ online, onSaved }: { online: boolean; onSaved: (p: Personality) => void }) {
  const [form, setForm] = useState<Personality>(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!online) return;
    api<Personality>("GET", "/settings/personality")
      .then((p) => { setForm(p); setLoaded(true); })
      .catch((err) => { setMessage(errorText(err)); setState("error"); });
  }, [online]);

  const set = <K extends keyof Personality>(key: K, value: Personality[K]) => { setForm((old) => ({ ...old, [key]: value })); setState("idle"); };
  const activePreset = PRESETS.find((p) => Object.entries(p.values).every(([k, v]) => form[k as keyof Personality] === v))?.id;

  const save = async () => {
    setState("saving");
    try {
      const saved = await api<Personality>("PUT", "/settings/personality", { body: form });
      setForm(saved);
      onSaved(saved);
      setState("saved");
      setMessage("Guardado. Se aplica desde el próximo mensaje.");
    } catch (err) {
      setState("error");
      setMessage(errorText(err));
    }
  };

  if (!online) return <p className="setting-note">La personalidad se configura con ATLAS en línea.</p>;
  if (!loaded && state !== "error") return <p className="setting-note">Cargando personalidad…</p>;

  return (
    <form className="personality" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <div className="preset-row" role="radiogroup" aria-label="Estilo">
        {PRESETS.map((p) => (
          <button type="button" key={p.id} role="radio" aria-checked={activePreset === p.id} className={activePreset === p.id ? "is-active" : ""} title={p.hint} onClick={() => { setForm((old) => ({ ...old, ...p.values })); setState("idle"); }}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="field-grid">
        <label>Nombre del asistente<input value={form.assistant_name} maxLength={40} onChange={(e) => set("assistant_name", e.target.value)} /></label>
        <label>¿Cómo te llamo?<input value={form.user_name} maxLength={80} placeholder="Tu nombre" onChange={(e) => set("user_name", e.target.value)} /></label>
        <label>Tu ciudad<input value={form.home_city} maxLength={120} placeholder="Ej.: Santo Domingo, República Dominicana" onChange={(e) => set("home_city", e.target.value)} /></label>
        <label>Trato
          <select value={form.formality} onChange={(e) => set("formality", e.target.value as Personality["formality"])}>
            <option value="tu">Tú</option><option value="usted">Usted</option><option value="vos">Vos</option>
          </select>
        </label>
        <label>Humor
          <select value={form.humor} onChange={(e) => set("humor", e.target.value as Personality["humor"])}>
            <option value="ninguno">Serio</option><option value="sutil">Sutil</option><option value="frecuente">Bromista</option>
          </select>
        </label>
        <label>Respuestas
          <select value={form.verbosity} onChange={(e) => set("verbosity", e.target.value as Personality["verbosity"])}>
            <option value="breve">Breves</option><option value="detallado">Detalladas</option>
          </select>
        </label>
      </div>
      <label className="field-wide">Tono<input value={form.tone} maxLength={200} onChange={(e) => set("tone", e.target.value)} /></label>
      <label className="field-wide">Instrucciones extra<textarea rows={3} value={form.custom_instructions} placeholder="Ej.: Cuando hable de dinero, dame cifras en pesos dominicanos." onChange={(e) => set("custom_instructions", e.target.value)} /></label>
      <div className="personality-foot">
        <small className={state === "error" ? "offline-text" : ""}>{state === "saved" || state === "error" ? message : "La palabra de activación por voz sigue siendo «Atlas»."}</small>
        <button type="submit" className="primary" disabled={state === "saving" || !form.assistant_name.trim()}>{state === "saving" ? "Guardando…" : "Guardar"}</button>
      </div>
    </form>
  );
}
