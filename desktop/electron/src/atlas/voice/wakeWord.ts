// Palabra de activación sobre texto transcrito, y limpieza de alucinaciones de
// Whisper. Módulo puro.

export const WAKE_WORD = "atlas";

/** Sesga a Whisper hacia la palabra de activación. Probado sobre silencio, ruido
    y golpes: no produce "Atlas" de la nada (con "Atlas." solo sí alucinaba
    "¡Adiós!" sobre silencio). */
export const WAKE_PROMPT = "Hola Atlas.";

/** Formas en que Whisper suele escribir "Atlas" mal oído. */
const WAKE_VARIANTS = new Set(["atlas", "atla", "atlass", "hatlas", "adlas", "attlas", "aplas", "atlaz", "atlax", "athlas"]);

/** Palabras reales a distancia 1 de "atlas" que no deben activar a ATLAS. */
const NOT_WAKE = new Set(["aulas", "atras", "atlan"]);

/** Muletillas que pueden ir antes del nombre: "oye Atlas", "hola Atlas". */
const LEADING_FILLERS = new Set(["oye", "hola", "ey", "hey", "eh", "che", "a", "ah", "bueno", "ok", "okay", "vale"]);

export function words(text: string): string[] {
  return (text ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .match(/[a-zñ0-9]+/g) ?? [];
}

export function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const current = [i];
    for (let j = 1; j <= b.length; j += 1) {
      current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    previous = current;
  }
  return previous[b.length];
}

function isWakeToken(token: string): boolean {
  if (NOT_WAKE.has(token)) return false;
  if (WAKE_VARIANTS.has(token)) return true;
  return token.length >= 5 && token.length <= 6 && levenshtein(token, WAKE_WORD) <= 1;
}

export type WakeMatch = { detected: boolean; command: string };

/** "Atlas, ¿qué hora es?" → { detected, command: "¿qué hora es?" }.

    Solo cuenta si el nombre va al principio (tras una muletilla como mucho),
    igual que cuando se llama a alguien: "atlas" a mitad de una frase de fondo
    no activa nada. También acepta "at las", que Whisper a veces separa. */
export function detectWakeWord(text: string): WakeMatch {
  const original = (text ?? "").trim();
  // Se recorre el texto original token a token para poder devolver el resto
  // con su puntuación y mayúsculas.
  const tokenPattern = /[\p{L}\p{N}]+/gu;
  const tokens = [...original.matchAll(tokenPattern)].map((match) => ({ raw: match[0], norm: words(match[0])[0] ?? "", end: (match.index ?? 0) + match[0].length }));
  let index = 0;
  while (index < tokens.length && index < 2 && LEADING_FILLERS.has(tokens[index].norm) && !isWakeToken(tokens[index].norm)) index += 1;
  const token = tokens[index];
  if (!token) return { detected: false, command: "" };
  let end = -1;
  if (isWakeToken(token.norm)) end = token.end;
  else if (token.norm === "at" && tokens[index + 1]?.norm === "las") end = tokens[index + 1].end;
  if (end < 0) return { detected: false, command: "" };
  const command = original.slice(end).replace(/^[\s,.;:!¡?¿…-]+/u, "").trim();
  // Conserva el signo de apertura si la pregunta empezaba justo después del nombre.
  const opener = /^[\s,]*([¿¡])/u.exec(original.slice(end))?.[1] ?? "";
  return { detected: true, command: command && opener && !command.startsWith(opener) ? opener + command : command };
}

/** Frases que Whisper inventa sobre ruido o silencio (subtítulos de YouTube con
    los que se entrenó). Si el texto es solo eso, no se dijo nada. */
const HALLUCINATIONS = [
  /^gracias( por (ver|mirar)( el video)?)?$/,
  /^subtitulos? (realizados|hechos|creados) por/,
  /^subtitulado por/,
  /amara\.?org/,
  /^suscribete/,
  /^adios$/,
  /^musica$/,
  /^aplausos$/,
  /^risas$/,
  /^\.+$/,
];

export function cleanTranscript(text: string): string {
  const trimmed = (text ?? "").replace(/\s+/g, " ").trim();
  const plain = words(trimmed).join(" ");
  if (!plain) return "";
  const raw = trimmed.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[¡!¿?.,]+/g, "").trim();
  if (HALLUCINATIONS.some((pattern) => pattern.test(plain) || pattern.test(raw))) return "";
  return trimmed;
}
