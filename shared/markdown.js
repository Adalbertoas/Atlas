/* Markdown a HTML para las burbujas del chat (dashboard y PWA móvil).
 *
 * Escrito a mano y no con una librería: es el único lugar del proyecto que
 * lo necesita, y traer un parser entero desde un CDN por esto sería la
 * segunda dependencia externa de todo el frontend (la primera es MediaPipe,
 * que no tiene alternativa).
 *
 * Vive en shared/ por la misma razón que wake-word.js: dashboard y móvil
 * deben renderizar igual, y dos copias terminan divergiendo.
 *
 * Complementa a backend/app/voice/markdown_speech.py: allá el Markdown se
 * limpia para que el TTS no lea los asteriscos; acá se convierte en texto
 * enriquecido para que tampoco se vean en pantalla.
 */

/** Escapa HTML. Va SIEMPRE primero: el texto viene de un modelo de lenguaje
 *  que a su vez repite contenido de páginas web, memorias y dispositivos, así
 *  que insertarlo crudo en innerHTML sería inyección de HTML. Recién después
 *  de escapar se reintroducen las etiquetas conocidas. */
export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// youtube.com/watch?v=ID, youtu.be/ID y youtube.com/shorts/ID — el id de
// video de YouTube son siempre 11 caracteres [A-Za-z0-9_-].
const YOUTUBE_ID_RE = /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([\w-]{11})/;

/** Arma la tarjeta con miniatura para un link de YouTube, o un <a> normal
 *  para cualquier otro link. img.youtube.com sirve las miniaturas sin
 *  necesitar API key ni CORS — es la misma URL que usa cualquier sitio que
 *  embebe previews de YouTube. */
function renderLink(url, label) {
  const videoId = url.match(YOUTUBE_ID_RE)?.[1];
  if (!videoId) {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  }
  return (
    `<a class="chat-link-card" href="${url}" target="_blank" rel="noopener noreferrer">` +
    `<img src="https://img.youtube.com/vi/${videoId}/mqdefault.jpg" alt="" loading="lazy">` +
    `<span class="chat-link-card-label">▶ Ver en YouTube</span>` +
    `</a>`
  );
}

export function renderMarkdown(text) {
  const escaped = escapeHtml(text);

  // Bloques de código primero: adentro no se interpreta nada más.
  const codeBlocks = [];
  let html = escaped.replace(/```[\w+-]*\n?([\s\S]*?)```/g, (_m, code) => {
    codeBlocks.push(code.replace(/\n$/, ""));
    return ` CODE${codeBlocks.length - 1} `;
  });

  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");

  // Enlaces: solo http(s). Markdown `[texto](url)` y URLs sueltas (el
  // modelo suele pegar el link crudo, no en formato Markdown) — ambos casos
  // se sacan a un placeholder para resolverlos recién al final, así no
  // interfieren con las demás reglas (ni una URL con guiones bajos con la
  // cursiva, por ejemplo). Sin lista blanca de esquema, un
  // `[texto](javascript:...)` sería ejecutable.
  const links = [];
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, label, url) => {
    links.push(renderLink(url, label));
    return ` LINK${links.length - 1} `;
  });
  html = html.replace(/https?:\/\/[^\s<]+[^\s<.,;:!?)]/g, (url) => {
    links.push(renderLink(url, url));
    return ` LINK${links.length - 1} `;
  });

  html = html.replace(/(\*\*\*|___)(.+?)\1/g, "<strong><em>$2</em></strong>");
  html = html.replace(/(\*\*|__)(.+?)\1/g, "<strong>$2</strong>");
  html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");
  // Cursiva: se exige que no haya carácter de palabra alrededor, para no
  // romper identificadores como get_system_info.
  html = html.replace(/(^|[\s(])[*_]([^*_\n]+)[*_](?=[\s.,;:!?)]|$)/g, "$1<em>$2</em>");

  html = html.replace(/^\s{0,3}(#{1,6})\s+(.*)$/gm, (_m, hashes, body) => {
    const level = Math.min(6, hashes.length + 2); // h1 del modelo -> h3 en la burbuja
    return `<h${level}>${body}</h${level}>`;
  });

  // Listas: se agrupan las líneas consecutivas en un solo <ul>/<ol>.
  html = html.replace(/(?:^\s*[-*+]\s+.*(?:\n|$))+/gm, (block) => {
    const items = block.trim().split("\n").map((line) => line.replace(/^\s*[-*+]\s+/, ""));
    return `<ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>`;
  });
  html = html.replace(/(?:^\s*\d+\.\s+.*(?:\n|$))+/gm, (block) => {
    const items = block.trim().split("\n").map((line) => line.replace(/^\s*\d+\.\s+/, ""));
    return `<ol>${items.map((i) => `<li>${i}</li>`).join("")}</ol>`;
  });

  html = html.replace(/\n{2,}/g, "<br><br>").replace(/\n/g, "<br>");
  // Los <br> que el agrupado de listas dejó pegados a las etiquetas sobran.
  html = html.replace(/<br>\s*(<\/?(?:ul|ol|li|h[1-6])>)/g, "$1");
  html = html.replace(/(<\/(?:ul|ol|h[1-6])>)\s*<br>/g, "$1");

  html = html.replace(/ CODE(\d+) /g, (_m, i) => `<pre><code>${codeBlocks[i]}</code></pre>`);
  return html.replace(/ LINK(\d+) /g, (_m, i) => links[i]);
}
