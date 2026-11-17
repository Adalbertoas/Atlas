// Markdown mínimo para las respuestas de ATLAS: párrafos, títulos, listas,
// bloques de código, **negrita**, *cursiva*, `código` y enlaces. Devuelve una
// estructura de datos (no HTML): la interfaz la dibuja con React, así el texto
// del modelo nunca se inyecta como HTML.

export type Inline =
  | { type: "text"; text: string }
  | { type: "bold"; children: Inline[] }
  | { type: "italic"; children: Inline[] }
  | { type: "code"; text: string }
  | { type: "link"; text: string; href: string };

export type Block =
  | { type: "paragraph"; children: Inline[] }
  | { type: "heading"; level: number; children: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "code"; language: string; text: string };

const INLINE = /(\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*([^*\s][^*]*)\*|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?]))/;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let rest = text;
  while (rest) {
    const match = INLINE.exec(rest);
    if (!match) { out.push({ type: "text", text: rest }); break; }
    if (match.index > 0) out.push({ type: "text", text: rest.slice(0, match.index) });
    const [whole, , bold1, bold2, code, linkText, linkHref, italic, bareUrl] = match;
    if (bold1 ?? bold2) out.push({ type: "bold", children: parseInline(bold1 ?? bold2) });
    else if (code !== undefined) out.push({ type: "code", text: code });
    else if (linkText !== undefined) out.push({ type: "link", text: linkText, href: linkHref });
    else if (italic !== undefined) out.push({ type: "italic", children: parseInline(italic) });
    else if (bareUrl !== undefined) out.push({ type: "link", text: bareUrl, href: bareUrl });
    rest = rest.slice(match.index + whole.length);
  }
  return out;
}

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ type: "paragraph", children: parseInline(paragraph.join("\n")) });
    paragraph = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = /^```\s*([\w+-]*)\s*$/.exec(line.trim());
    if (fence) {
      flush();
      const body: string[] = [];
      for (i++; i < lines.length && !/^```\s*$/.test(lines[i].trim()); i++) body.push(lines[i]);
      blocks.push({ type: "code", language: fence[1], text: body.join("\n") });
      continue;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) { flush(); blocks.push({ type: "heading", level: heading[1].length, children: parseInline(heading[2]) }); continue; }
    const item = /^\s*([-*•]|\d+[.)])\s+(.+)$/.exec(line);
    if (item) {
      flush();
      const ordered = /\d/.test(item[1]);
      const last = blocks[blocks.length - 1];
      const entry = parseInline(item[2]);
      if (last?.type === "list" && last.ordered === ordered) last.items.push(entry);
      else blocks.push({ type: "list", ordered, items: [entry] });
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    paragraph.push(line);
  }
  flush();
  return blocks;
}
