// Dibuja el markdown de las respuestas (ver markdown.ts) y la tarjeta de confirmación.
import { useState, type ReactNode } from "react";
import { parseMarkdown, type Inline } from "./markdown";
import { Glyph } from "./Glyph";

function inline(nodes: Inline[]): ReactNode[] {
  return nodes.map((node, i) => {
    switch (node.type) {
      case "text": return <span key={i}>{node.text}</span>;
      case "bold": return <strong key={i}>{inline(node.children)}</strong>;
      case "italic": return <em key={i}>{inline(node.children)}</em>;
      case "code": return <code key={i}>{node.text}</code>;
      // Enlaces: se abren en el navegador del sistema (main.ts deniega abrir ventanas nuevas en la app).
      case "link": return <a key={i} href={node.href} target="_blank" rel="noreferrer noopener">{node.text}</a>;
    }
  });
}

function CodeBlock({ text, language }: { text: string; language: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="md-code">
      <header><span>{language || "código"}</span><button onClick={() => { void navigator.clipboard?.writeText(text); setCopied(true); window.setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copiado" : "Copiar"}</button></header>
      <pre><code>{text}</code></pre>
    </div>
  );
}

export function RichText({ text }: { text: string }) {
  return (
    <div className="md">
      {parseMarkdown(text).map((block, i) => {
        switch (block.type) {
          case "paragraph": return <p key={i}>{inline(block.children)}</p>;
          case "heading": return <h4 key={i} className={`md-h${block.level}`}>{inline(block.children)}</h4>;
          case "list": {
            const items = block.items.map((item, j) => <li key={j}>{inline(item)}</li>);
            return block.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
          }
          case "code": return <CodeBlock key={i} text={block.text} language={block.language} />;
        }
      })}
    </div>
  );
}

export function ConfirmCard({ description, onAnswer }: { description: string; onAnswer: (approve: boolean) => Promise<void> }) {
  const [state, setState] = useState<"ask" | "busy" | "done">("ask");
  const answer = async (approve: boolean) => {
    setState("busy");
    try { await onAnswer(approve); } finally { setState("done"); }
  };
  return (
    <div className={`confirm-card is-${state}`} role="group" aria-label="Confirmación requerida">
      <header><Glyph name="alert" size={15} /> Necesito tu confirmación</header>
      <p>{description}</p>
      {state !== "done" && (
        <div>
          <button className="primary" disabled={state === "busy"} onClick={() => void answer(true)}><Glyph name="check" size={14} /> Confirmar</button>
          <button disabled={state === "busy"} onClick={() => void answer(false)}><Glyph name="x" size={14} /> Cancelar</button>
        </div>
      )}
    </div>
  );
}
