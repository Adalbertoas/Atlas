// ATLAS Fase 5F — adaptadores para el backend de ATLAS, con el mismo flujo que ya usa el dashboard (app.js):
//   POST /api/v1/voice/transcribe (FormData "audio") → { text }
//   POST /api/v1/chat/stream  { message, conversation_id }  → SSE: token · tool_call · confirmation · done
//   POST /api/v1/voice/speak  { text } → audio
// Sin credenciales en el código: la URL y el token los da el anfitrión en tiempo de ejecución (getToken).

/** Traducción pura de eventos del chat en streaming a estados de voz (la misma lógica que app.js). */
export class ChatStreamStateAdapter {
  /** @returns {string|null} estado a fijar, o null si el evento no cambia el estado. */
  static stateFor(type) {
    switch (type) {
      case "token": return "thinking";          // sigue pensando/escribiendo
      case "tool_call": return "executing";
      case "tool_result": return "thinking";
      case "confirmation": return "idle";       // espera a que el usuario confirme
      case "error": return "error";
      default: return null;                     // "done": decide la reproducción de la voz
    }
  }
  /** Parser de un evento SSE ("event: X\ndata: {json}") igual que parseSseEvent del dashboard. */
  static parse(raw) {
    const lines = raw.split("\n"); let type = "", data = {};
    for (const l of lines) { if (l.startsWith("event:")) type = l.slice(6).trim(); else if (l.startsWith("data:")) { try { data = JSON.parse(l.slice(5).trim()); } catch { data = { raw: l.slice(5).trim() }; } } }
    return { type, data };
  }
}

/** Procesador de VoiceSession que habla con el backend de ATLAS. */
export class AtlasBackendProcessor {
  /** @param {{apiUrl: string, getToken?: () => string|null, conversationId?: string|null, fetchImpl?: typeof fetch}} o */
  constructor({ apiUrl, getToken = () => null, conversationId = null, fetchImpl = (...a) => fetch(...a) }) {
    Object.assign(this, { apiUrl: apiUrl.replace(/\/$/, ""), getToken, conversationId, fetch: fetchImpl });
    this.name = "backend ATLAS";
  }
  _headers(json = true) { const h = json ? { "Content-Type": "application/json" } : {}; const t = this.getToken(); if (t) h.Authorization = `Bearer ${t}`; return h; }

  async process({ audio, text }, { toolStart, toolEnd, signal }) {
    let message = text;
    if (!message && audio) {
      const form = new FormData(); form.append("audio", audio, "audio.webm");
      const r = await this.fetch(`${this.apiUrl}/api/v1/voice/transcribe`, { method: "POST", body: form, headers: this._headers(false), signal });
      if (!r.ok) throw new Error(`transcripción ${r.status}`);
      message = (await r.json()).text?.trim();
      if (!message) return { text: null };      // no entendió: sin respuesta hablada
    }
    const r = await this.fetch(`${this.apiUrl}/api/v1/chat/stream`, { method: "POST", headers: this._headers(), body: JSON.stringify({ message, conversation_id: this.conversationId }), signal });
    if (!r.ok || !r.body) throw new Error(`chat ${r.status}`);
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "", acc = "", reply = null, inTool = null;
    read: while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) !== -1) {
        const ev = ChatStreamStateAdapter.parse(buf.slice(0, i)); buf = buf.slice(i + 2);
        if (ev.type === "token" && ev.data.text) { if (inTool) { toolEnd(inTool); inTool = null; } acc += ev.data.text; }
        else if (ev.type === "tool_call") { if (inTool) toolEnd(inTool); inTool = ev.data.tool_name || "herramienta"; toolStart(inTool); }
        else if (ev.type === "confirmation") { reader.cancel().catch(() => {}); if (inTool) toolEnd(inTool); return { text: null, confirmation: ev.data }; }
        else if (ev.type === "done") { if (ev.data.conversation_id) this.conversationId = ev.data.conversation_id; reply = ev.data.reply ?? acc; break read; }
      }
    }
    if (inTool) toolEnd(inTool);
    reply = reply ?? acc;
    this.lastText = reply;
    if (!reply) return { text: null };
    const s = await this.fetch(`${this.apiUrl}/api/v1/voice/speak`, { method: "POST", headers: this._headers(), body: JSON.stringify({ text: reply }), signal });
    if (!s.ok) return { text: reply };          // sin voz: el texto basta, no hay fase SPEAKING (igual que el dashboard)
    return { text: reply, audio: await s.blob() };
  }
}
