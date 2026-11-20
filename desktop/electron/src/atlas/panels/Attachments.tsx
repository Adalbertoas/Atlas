// Adjuntos del chat: imágenes y PDF que se arrastran a la ventana, se pegan con
// Ctrl+V o se eligen con el clip. Se leen en el renderer (base64) y viajan con
// el mensaje; ATLAS los ve directamente (Claude es multimodal).
export type Attachment = { id: string; name: string; mimeType: string; data: string };

export const ATTACHMENT_ACCEPT = "image/png,image/jpeg,image/webp,image/gif,application/pdf";
const TYPES = new Set(ATTACHMENT_ACCEPT.split(","));
export const MAX_ATTACHMENTS = 6;
const MAX_BYTES = 20 * 1024 * 1024;

function readAsBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).replace(/^data:[^,]*,/, ""));
    reader.onerror = () => reject(reader.error ?? new Error("No se pudo leer el archivo."));
    reader.readAsDataURL(file);
  });
}

/** Lee los archivos válidos; devuelve también por qué se descartó el resto. */
export async function readAttachments(files: Iterable<File>, already: number) {
  const items: Attachment[] = [];
  const problems: string[] = [];
  for (const file of files) {
    // Las capturas pegadas desde el portapapeles llegan sin nombre.
    const name = file.name || `captura-${new Date().toLocaleTimeString().replace(/\W/g, "")}.png`;
    if (!TYPES.has(file.type)) { problems.push(`${name}: solo imágenes o PDF`); continue; }
    if (file.size > MAX_BYTES) { problems.push(`${name}: pesa más de 20 MB`); continue; }
    if (already + items.length >= MAX_ATTACHMENTS) { problems.push(`máximo ${MAX_ATTACHMENTS} archivos por mensaje`); break; }
    try {
      items.push({ id: crypto.randomUUID(), name, mimeType: file.type, data: await readAsBase64(file) });
    } catch {
      problems.push(`${name}: no se pudo leer`);
    }
  }
  return { items, problems };
}

export const hasFiles = (event: DragEvent | React.DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files");

function Thumb({ item }: { item: Pick<Attachment, "name" | "mimeType" | "data"> }) {
  return item.mimeType.startsWith("image/")
    ? <img src={`data:${item.mimeType};base64,${item.data}`} alt={item.name} />
    : <span className="attachment-pdf">PDF</span>;
}

/** Archivos listos para enviar, encima del cuadro de texto. */
export function AttachmentTray({ items, onRemove }: { items: Attachment[]; onRemove: (id: string) => void }) {
  if (!items.length) return null;
  return <div className="attachment-tray">{items.map(item => <figure key={item.id} title={item.name}>
    <Thumb item={item} /><figcaption>{item.name}</figcaption>
    <button type="button" title="Quitar" aria-label={`Quitar ${item.name}`} onClick={() => onRemove(item.id)}>×</button>
  </figure>)}</div>;
}

/** Adjuntos ya enviados, dentro de la burbuja del usuario. */
export function SentAttachments({ items, onZoom }: { items: Attachment[]; onZoom: (image: { mime_type: string; data: string }) => void }) {
  return <div className="sent-attachments">{items.map(item => item.mimeType.startsWith("image/")
    ? <button key={item.id} type="button" title={item.name} onClick={() => onZoom({ mime_type: item.mimeType, data: item.data })}><Thumb item={item} /></button>
    : <span key={item.id} className="sent-file" title={item.name}><Thumb item={item} />{item.name}</span>)}</div>;
}

/** Archivo que generó ATLAS (ej. un Excel): el proceso principal guarda la ruta, aquí solo viaja el id. */
export type GeneratedFile = { id: string; name: string; size: number; mimeType: string };

const formatSize = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const kindOf = (name: string) => /\.xlsx?$/i.test(name) ? { label: "XLSX", className: "is-excel" } : { label: (name.split(".").pop() || "FILE").slice(0, 4).toUpperCase(), className: "" };

/** Tarjetas de descarga bajo la respuesta de ATLAS. */
export function FileCards({ files, onToast }: { files: GeneratedFile[]; onToast: (text: string) => void }) {
  const run = async (channel: "files:save" | "files:open" | "files:reveal", file: GeneratedFile) => {
    try {
      const result = await window.atlas.invoke(channel, { id: file.id });
      if (channel === "files:save" && typeof result === "string") onToast(`Guardado en ${result}`);
    } catch (error) {
      onToast(error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': (Error: )?/, "") : String(error));
    }
  };
  return <div className="file-cards">{files.map(file => {
    const kind = kindOf(file.name);
    return <div key={file.id} className="file-card">
      <span className={`file-card-icon ${kind.className}`}>{kind.label}</span>
      <div className="file-card-copy"><b title={file.name}>{file.name}</b><small>{formatSize(file.size)}</small></div>
      <button type="button" className="file-card-primary" onClick={() => run("files:save", file)} title="Guardar una copia donde quieras">Descargar</button>
      <button type="button" onClick={() => run("files:open", file)} title="Abrir con Excel">Abrir</button>
      <button type="button" onClick={() => run("files:reveal", file)} title="Mostrar en la carpeta">Carpeta</button>
    </div>;
  })}</div>;
}
