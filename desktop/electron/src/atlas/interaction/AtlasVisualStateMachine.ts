// Estado visual de ATLAS resuelto por prioridad. Módulo puro.
//
// Hay dos tipos de entrada:
//  - señales persistentes (setSignal): activas mientras dure el hecho real que
//    representan — se está grabando, hay una petición en curso, suena audio…
//  - pulsos temporales (pulse): SUCCESS y ERROR, que caducan solos.
// El estado mostrado es siempre el de mayor prioridad entre los activos.

export type AtlasVisualState = "IDLE" | "LISTENING" | "THINKING" | "SPEAKING" | "PROCESSING" | "SUCCESS" | "ERROR" | "SLEEPING";

export const STATE_PRIORITY: Record<AtlasVisualState, number> = {
  ERROR: 80,
  SPEAKING: 70,
  LISTENING: 60,
  PROCESSING: 50,
  THINKING: 40,
  SUCCESS: 30,
  SLEEPING: 10,
  IDLE: 0,
};

export const STATE_LABELS: Record<AtlasVisualState, string> = {
  IDLE: "En espera",
  LISTENING: "Escuchando",
  THINKING: "Pensando",
  SPEAKING: "Hablando",
  PROCESSING: "Procesando",
  SUCCESS: "Completado",
  ERROR: "Error",
  SLEEPING: "En reposo",
};

export type StateListener = (state: AtlasVisualState, previous: AtlasVisualState) => void;

export class AtlasVisualStateMachine {
  private readonly signals = new Set<AtlasVisualState>();
  private readonly pulses = new Map<AtlasVisualState, number>();
  private readonly listeners = new Set<StateListener>();
  private current: AtlasVisualState = "IDLE";

  get state(): AtlasVisualState {
    return this.current;
  }

  subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  setSignal(state: AtlasVisualState, active: boolean): void {
    if (active) this.signals.add(state);
    else this.signals.delete(state);
  }

  /** Activa `state` hasta `now + durationMs`. Repetirlo prolonga el pulso. */
  pulse(state: AtlasVisualState, durationMs: number, now: number): void {
    this.pulses.set(state, Math.max(this.pulses.get(state) ?? 0, now + durationMs));
  }

  /** Recalcula el estado; hay que llamarlo periódicamente para que caduquen los pulsos. */
  update(now: number): AtlasVisualState {
    let next: AtlasVisualState = "IDLE";
    for (const state of this.signals) if (STATE_PRIORITY[state] > STATE_PRIORITY[next]) next = state;
    for (const [state, expires] of this.pulses) {
      if (now >= expires) this.pulses.delete(state);
      else if (STATE_PRIORITY[state] > STATE_PRIORITY[next]) next = state;
    }
    if (next !== this.current) {
      const previous = this.current;
      this.current = next;
      for (const listener of this.listeners) listener(next, previous);
    }
    return this.current;
  }
}
