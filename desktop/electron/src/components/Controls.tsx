// Controles de formulario compartidos por los paneles de configuración.

export function Toggle({ label, value, onChange, disabled = false }: { label: string; value: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return <label className={`toggle-row ${disabled ? "is-disabled" : ""}`}><span>{label}</span><input type="checkbox" checked={value} disabled={disabled} onChange={e => onChange(e.target.checked)} /><i /></label>;
}

export function Range({ label, value, onChange, min = 20, max = 100 }: { label: string; value: number; onChange: (value: number) => void; min?: number; max?: number }) {
  return <label className="range-row"><span>{label}<b>{value}%</b></span><input type="range" min={min} max={max} value={value} onChange={e => onChange(Number(e.target.value))} /></label>;
}

export function Select<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly (readonly [T, string])[]; onChange: (value: T) => void }) {
  return <label className="select-row"><span>{label}</span><select value={value} onChange={e => onChange(e.target.value as T)}>{options.map(([option, text]) => <option key={option} value={option}>{text}</option>)}</select></label>;
}
