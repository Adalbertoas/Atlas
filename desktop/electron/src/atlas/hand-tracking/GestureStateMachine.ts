// Ciclo de vida de un gesto: idle → detected → confirmed → held → idle.
// Aplica tiempo mínimo de activación, cooldown y tolerancia a pérdidas breves
// de seguimiento. Módulo puro.

import type { GestureTiming } from "./GestureConfig.ts";
import type { GestureEvent, GestureName } from "./types.ts";

type Phase = "idle" | "detected" | "confirmed" | "held";

export class GestureStateMachine {
  private readonly gesture: GestureName;
  private timing: GestureTiming;
  private lostGraceMs: number;
  private phase: Phase = "idle";
  private phaseStart = 0;
  private lostSince: number | null = null;
  private cooldownUntil = 0;

  constructor(gesture: GestureName, timing: GestureTiming, lostGraceMs: number) {
    this.gesture = gesture;
    this.timing = timing;
    this.lostGraceMs = lostGraceMs;
  }

  configure(timing: GestureTiming, lostGraceMs: number): void {
    this.timing = timing;
    this.lostGraceMs = lostGraceMs;
  }

  /** true en confirmed o held: el gesto cuenta como activo. */
  get engaged(): boolean {
    return this.phase === "confirmed" || this.phase === "held";
  }

  reset(): void {
    this.phase = "idle";
    this.lostSince = null;
  }

  /**
   * @param active  el reconocedor ve el gesto en este fotograma
   * @param tracked hay manos en el fotograma
   */
  update(active: boolean, tracked: boolean, now: number): GestureEvent[] {
    const events: GestureEvent[] = [];
    const emit = (phase: GestureEvent["phase"]) => events.push({ gesture: this.gesture, phase, timestamp: now });

    if (!tracked) {
      if (this.phase === "idle") return events;
      if (this.lostSince === null) this.lostSince = now;
      // Dentro del margen se conserva la fase: un parpadeo del detector no
      // debe cortar ni volver a disparar el gesto.
      if (now - this.lostSince < this.lostGraceMs) return events;
      if (this.engaged) {
        emit("lost");
        this.cooldownUntil = now + this.timing.cooldownMs;
      }
      this.reset();
      return events;
    }
    this.lostSince = null;

    if (this.phase === "idle") {
      if (!active || now < this.cooldownUntil) return events;
      this.phase = "detected";
      this.phaseStart = now;
      emit("detected");
    }

    if (this.phase === "detected") {
      if (!active) {
        this.phase = "idle";
        return events;
      }
      if (now - this.phaseStart < this.timing.minActivationMs) return events;
      this.phase = "confirmed";
      this.phaseStart = now;
      emit("confirmed");
      return events;
    }

    if (!active) {
      emit("ended");
      this.phase = "idle";
      this.cooldownUntil = now + this.timing.cooldownMs;
      return events;
    }

    if (this.phase === "confirmed" && now - this.phaseStart >= this.timing.holdMs) {
      this.phase = "held";
      emit("held");
    }
    return events;
  }
}
