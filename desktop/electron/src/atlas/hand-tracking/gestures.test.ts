import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { gestureConfigFor } from "./GestureConfig.ts";
import { GestureController, type GestureAction } from "./GestureController.ts";
import { GestureRecognizer, Hysteresis } from "./GestureRecognizer.ts";
import { GestureStateMachine } from "./GestureStateMachine.ts";
import { extractHandFeatures } from "./handFeatures.ts";
import { LandmarkSmoother, OneEuroFilter } from "./LandmarkSmoother.ts";
import { frameOf, makeHand, type HandPose } from "./testHands.ts";
import type { GestureEvent, GestureName, GestureOutput } from "./types.ts";

const config = () => gestureConfigFor(0.5, 1);
const STEP = 50; // ms entre fotogramas (20 Hz, como la inferencia real)

/** Reproduce una secuencia de poses y devuelve todos los eventos emitidos. */
function play(recognizer: GestureRecognizer, start: number, frames: HandPose[][]): { events: GestureEvent[]; last: GestureOutput; end: number } {
  const events: GestureEvent[] = [];
  let last!: GestureOutput;
  let t = start;
  for (const poses of frames) {
    last = recognizer.update(frameOf(t, ...poses));
    events.push(...last.events);
    t += STEP;
  }
  return { events, last, end: t };
}

const repeat = (count: number, poses: HandPose[]) => Array.from({ length: count }, () => poses);
const confirmed = (events: GestureEvent[], gesture: GestureName) => events.filter((event) => event.gesture === gesture && event.phase === "confirmed").length;

describe("handFeatures", () => {
  it("clasifica una mano abierta", () => {
    const features = extractHandFeatures(makeHand({ cx: 0.5, cy: 0.5, open: 1 }).landmarks, 1);
    assert.ok(features);
    assert.ok(features.openness > 0.95, `openness ${features.openness}`);
    assert.ok(features.pinchRatio > 0.8);
  });

  it("clasifica un puño", () => {
    const features = extractHandFeatures(makeHand({ cx: 0.5, cy: 0.5, open: 0 }).landmarks, 1);
    assert.ok(features);
    assert.ok(features.openness < 0.05, `openness ${features.openness}`);
  });

  it("detecta la pinza con el resto de la mano abierta", () => {
    const features = extractHandFeatures(makeHand({ cx: 0.5, cy: 0.5, open: 1, pinch: true }).landmarks, 1);
    assert.ok(features);
    assert.ok(features.pinchRatio < 0.15, `pinchRatio ${features.pinchRatio}`);
    assert.ok(features.restOpenness > 0.9);
  });

  it("es independiente de la distancia a la cámara", () => {
    const near = makeHand({ cx: 0.5, cy: 0.5, open: 0.7 }).landmarks;
    const far = near.map((point) => ({ x: 0.5 + (point.x - 0.5) * 0.4, y: 0.5 + (point.y - 0.5) * 0.4, z: 0 }));
    const a = extractHandFeatures(near, 1);
    const b = extractHandFeatures(far, 1);
    assert.ok(a && b);
    assert.ok(Math.abs(a.openness - b.openness) < 1e-6);
    assert.ok(Math.abs(a.pinchRatio - b.pinchRatio) < 1e-6);
  });

  it("rechaza datos incompletos", () => {
    assert.equal(extractHandFeatures([], 1), null);
  });
});

describe("LandmarkSmoother", () => {
  it("reduce el temblor de una mano quieta", () => {
    const filter = new OneEuroFilter();
    let rawSpread = 0;
    let smoothSpread = 0;
    for (let i = 0; i < 200; i += 1) {
      const noise = (i % 2 === 0 ? 1 : -1) * 0.004;
      const value = filter.filter(0.5 + noise, i / 30);
      if (i > 50) {
        rawSpread = Math.max(rawSpread, Math.abs(noise));
        smoothSpread = Math.max(smoothSpread, Math.abs(value - 0.5));
      }
    }
    assert.ok(smoothSpread < rawSpread * 0.5, `suavizado ${smoothSpread} vs crudo ${rawSpread}`);
  });

  it("sigue un movimiento rápido sin retardo apreciable", () => {
    const filter = new OneEuroFilter();
    let value = 0;
    for (let i = 0; i <= 30; i += 1) value = filter.filter(i / 30, i / 30); // 1 unidad/s
    assert.ok(Math.abs(value - 1) < 0.05, `retardo ${1 - value}`);
  });

  it("mantiene 21 puntos y olvida las manos que desaparecen", () => {
    const smoother = new LandmarkSmoother();
    const far = makeHand({ cx: 0.2, cy: 0.5, open: 1 }).landmarks;
    const near = makeHand({ cx: 0.8, cy: 0.5, open: 1 }).landmarks;
    assert.equal(smoother.smooth("a", far, 0).length, 21);
    smoother.retain([]);
    // Sin historial, la primera muestra tras reaparecer se devuelve tal cual.
    assert.deepEqual(smoother.smooth("a", near, 33)[0], near[0]);
  });
});

describe("GestureStateMachine", () => {
  const timing = { minActivationMs: 100, holdMs: 300, cooldownMs: 500 };
  const phases = (events: GestureEvent[]) => events.map((event) => event.phase);

  it("exige el tiempo mínimo de activación", () => {
    const machine = new GestureStateMachine("fist", timing, 200);
    assert.deepEqual(phases(machine.update(true, true, 0)), ["detected"]);
    assert.deepEqual(phases(machine.update(true, true, 50)), []);
    assert.equal(machine.engaged, false);
    assert.deepEqual(phases(machine.update(true, true, 100)), ["confirmed"]);
    assert.equal(machine.engaged, true);
  });

  it("descarta un gesto que no llega a confirmarse", () => {
    const machine = new GestureStateMachine("fist", timing, 200);
    machine.update(true, true, 0);
    assert.deepEqual(phases(machine.update(false, true, 50)), []);
    assert.equal(machine.engaged, false);
  });

  it("distingue confirmado, sostenido y finalizado", () => {
    const machine = new GestureStateMachine("fist", timing, 200);
    machine.update(true, true, 0);
    machine.update(true, true, 100);
    assert.deepEqual(phases(machine.update(true, true, 250)), []);
    assert.deepEqual(phases(machine.update(true, true, 400)), ["held"]);
    assert.deepEqual(phases(machine.update(false, true, 450)), ["ended"]);
  });

  it("aplica el cooldown tras terminar", () => {
    const machine = new GestureStateMachine("pinch", timing, 200);
    machine.update(true, true, 0);
    machine.update(true, true, 100);
    machine.update(false, true, 150);
    assert.deepEqual(phases(machine.update(true, true, 300)), [], "dentro del cooldown");
    assert.deepEqual(phases(machine.update(true, true, 650)), ["detected"]);
  });

  it("tolera una pérdida breve y emite 'lost' en una prolongada", () => {
    const machine = new GestureStateMachine("fist", timing, 200);
    machine.update(true, true, 0);
    machine.update(true, true, 100);
    assert.deepEqual(phases(machine.update(false, false, 150)), []);
    assert.equal(machine.engaged, true, "sigue activo dentro del margen");
    assert.deepEqual(phases(machine.update(true, true, 250)), [], "no vuelve a dispararse al recuperarse");
    machine.update(false, false, 300);
    assert.deepEqual(phases(machine.update(false, false, 520)), ["lost"]);
    assert.equal(machine.engaged, false);
  });

  it("un impulso de un fotograma se confirma una sola vez", () => {
    const machine = new GestureStateMachine("burst", { minActivationMs: 0, holdMs: 0, cooldownMs: 1000 }, 200);
    assert.deepEqual(phases(machine.update(true, true, 0)), ["detected", "confirmed"]);
    assert.deepEqual(phases(machine.update(false, true, 50)), ["ended"]);
    assert.deepEqual(phases(machine.update(true, true, 100)), []);
  });
});

describe("Hysteresis", () => {
  it("usa umbrales distintos para entrar y salir", () => {
    const band = { enter: 0.7, exit: 0.5 };
    const h = new Hysteresis();
    assert.equal(h.update(0.6, band), false);
    assert.equal(h.update(0.75, band), true);
    assert.equal(h.update(0.6, band), true, "entre umbrales conserva el estado");
    assert.equal(h.update(0.45, band), false);
  });
});

describe("GestureRecognizer", () => {
  it("mano abierta y puño son excluyentes y pasan por confirmación", () => {
    const recognizer = new GestureRecognizer(config());
    const open = play(recognizer, 0, repeat(8, [{ cx: 0.5, cy: 0.5, open: 1 }]));
    assert.equal(confirmed(open.events, "open_hand"), 1);
    assert.ok(open.last.active.has("open_hand"));
    assert.ok(!open.last.active.has("fist"));

    const fist = play(recognizer, open.end, repeat(8, [{ cx: 0.5, cy: 0.5, open: 0 }]));
    assert.equal(confirmed(fist.events, "fist"), 1);
    assert.ok(fist.last.active.has("fist"));
    assert.ok(!fist.last.active.has("open_hand"));
    assert.ok(fist.events.some((event) => event.gesture === "open_hand" && event.phase === "ended"));
  });

  it("un fotograma suelto no confirma nada", () => {
    const recognizer = new GestureRecognizer(config());
    const { events } = play(recognizer, 0, [[{ cx: 0.5, cy: 0.5, open: 0.5 }], [{ cx: 0.5, cy: 0.5, open: 0 }], ...repeat(6, [{ cx: 0.5, cy: 0.5, open: 0.5 }])]);
    assert.equal(confirmed(events, "fist"), 0);
  });

  it("detecta la pinza y da su posición; un puño no cuenta como pinza", () => {
    const recognizer = new GestureRecognizer(config());
    const pinch = play(recognizer, 0, repeat(8, [{ cx: 0.7, cy: 0.3, open: 1, pinch: true }]));
    assert.equal(confirmed(pinch.events, "pinch"), 1);
    assert.ok(pinch.last.pinchPoint);
    assert.ok(pinch.last.pinchPoint.x > 0, "a la derecha del centro");
    assert.ok(pinch.last.pinchPoint.y > 0, "por encima del centro");

    const other = new GestureRecognizer(config());
    const fist = play(other, 0, repeat(10, [{ cx: 0.5, cy: 0.5, open: 0 }]));
    assert.equal(confirmed(fist.events, "pinch"), 0);
  });

  it("informa del desplazamiento horizontal y vertical de la mano", () => {
    const recognizer = new GestureRecognizer(config());
    const right = recognizer.update(frameOf(0, { cx: 0.85, cy: 0.5, open: 0.5 }));
    assert.ok(right.pan.x > 0.5);
    const up = recognizer.update(frameOf(50, { cx: 0.5, cy: 0.15, open: 0.5 }));
    assert.ok(up.pan.y > 0.3);
    const centre = recognizer.update(frameOf(100, { cx: 0.495, cy: 0.42, open: 0.5 }));
    assert.equal(centre.pan.x, 0, "zona muerta en el centro");
  });

  it("mide la distancia entre manos: separar y juntar", () => {
    const recognizer = new GestureRecognizer(config());
    const apart = play(recognizer, 0, repeat(10, [{ cx: 0.15, cy: 0.5, open: 0.5 }, { cx: 0.85, cy: 0.5, open: 0.5 }]));
    assert.ok(apart.last.handsDistance !== null && apart.last.handsDistance > 0.6);
    assert.equal(confirmed(apart.events, "spread"), 1);

    const together = play(recognizer, apart.end, repeat(12, [{ cx: 0.44, cy: 0.5, open: 0.5 }, { cx: 0.56, cy: 0.5, open: 0.5 }]));
    assert.equal(confirmed(together.events, "gather"), 1);
    assert.ok(!together.last.active.has("spread"));
  });

  it("reconoce un movimiento circular sostenido como torbellino", () => {
    const recognizer = new GestureRecognizer(config());
    const circle = Array.from({ length: 50 }, (_, i) => {
      const angle = (i * STEP * 2 * Math.PI) / 1000; // una vuelta por segundo
      return [{ cx: 0.5 + Math.cos(angle) * 0.08, cy: 0.5 + Math.sin(angle) * 0.08, open: 0.5 }];
    });
    const { events, last } = play(recognizer, 0, circle);
    assert.equal(confirmed(events, "swirl"), 1);
    assert.ok(last.active.has("swirl"));
  });

  it("no confunde una mano quieta ni un barrido lateral con un torbellino", () => {
    const still = new GestureRecognizer(config());
    const jitter = Array.from({ length: 60 }, (_, i) => [{ cx: 0.5 + (i % 2 ? 0.002 : -0.002), cy: 0.5 + (i % 3 ? 0.002 : -0.002), open: 0.5 }]);
    assert.equal(confirmed(play(still, 0, jitter).events, "swirl"), 0);

    const sweep = new GestureRecognizer(config());
    const line = Array.from({ length: 60 }, (_, i) => [{ cx: 0.5 + Math.sin((i * STEP * 2 * Math.PI) / 1000) * 0.15, cy: 0.5, open: 0.5 }]);
    assert.equal(confirmed(play(sweep, 0, line).events, "swirl"), 0);
  });

  it("la apertura rápida de ambas manos dispara una explosión, con cooldown", () => {
    const recognizer = new GestureRecognizer(config());
    const closed = [{ cx: 0.3, cy: 0.5, open: 0 }, { cx: 0.7, cy: 0.5, open: 0 }];
    const opened = [{ cx: 0.3, cy: 0.5, open: 1 }, { cx: 0.7, cy: 0.5, open: 1 }];

    const first = play(recognizer, 0, [...repeat(6, closed), ...repeat(6, opened)]);
    assert.equal(confirmed(first.events, "burst"), 1, "una sola explosión por gesto");

    // Repetirlo de inmediato cae dentro del cooldown de 2,5 s.
    const second = play(recognizer, first.end, [...repeat(6, closed), ...repeat(6, opened)]);
    assert.equal(confirmed(second.events, "burst"), 0);

    const third = play(recognizer, second.end + 3000, [...repeat(6, closed), ...repeat(6, opened)]);
    assert.equal(confirmed(third.events, "burst"), 1);
  });

  it("abrir las manos despacio no es una explosión", () => {
    const recognizer = new GestureRecognizer(config());
    const slow = Array.from({ length: 40 }, (_, i) => [{ cx: 0.3, cy: 0.5, open: i / 39 }, { cx: 0.7, cy: 0.5, open: i / 39 }]);
    assert.equal(confirmed(play(recognizer, 0, slow).events, "burst"), 0);
  });

  it("al perder las manos emite 'lost' y deja de informar gestos", () => {
    const recognizer = new GestureRecognizer(config());
    const held = play(recognizer, 0, repeat(8, [{ cx: 0.5, cy: 0.5, open: 0 }]));
    assert.ok(held.last.active.has("fist"));
    const gone = play(recognizer, held.end, repeat(12, []));
    assert.equal(gone.last.tracked, false);
    assert.equal(gone.last.active.size, 0);
    assert.ok(gone.events.some((event) => event.gesture === "fist" && event.phase === "lost"));
  });
});

describe("gestureConfigFor", () => {
  it("más sensibilidad = umbrales más fáciles y activación más rápida", () => {
    const strict = gestureConfigFor(0);
    const loose = gestureConfigFor(1);
    assert.ok(loose.open.enter < strict.open.enter);
    assert.ok(loose.fist.enter > strict.fist.enter);
    assert.ok(loose.pinch.enter > strict.pinch.enter);
    assert.ok(loose.timing.fist.minActivationMs < strict.timing.fist.minActivationMs);
  });

  it("conserva la histéresis en todo el rango", () => {
    for (const s of [0, 0.25, 0.5, 0.75, 1]) {
      const c = gestureConfigFor(s);
      assert.ok(c.open.enter > c.open.exit);
      assert.ok(c.fist.enter < c.fist.exit);
      assert.ok(c.pinch.enter < c.pinch.exit);
      assert.ok(c.spread.enter > c.spread.exit);
      assert.ok(c.gather.enter < c.gather.exit);
      assert.ok(c.swirl.enterAngle > c.swirl.exitAngle);
      // Abierta y puño nunca pueden solaparse.
      assert.ok(c.fist.exit < c.open.exit);
    }
  });

  it("acota valores fuera de rango", () => {
    assert.deepEqual(gestureConfigFor(5), gestureConfigFor(1));
    assert.deepEqual(gestureConfigFor(-3), gestureConfigFor(0));
  });
});

describe("GestureController", () => {
  const output = (patch: Partial<GestureOutput>): GestureOutput => ({ tracked: true, handCount: 1, openness: 0.5, pan: { x: 0, y: 0 }, handsDistance: null, handsAngle: null, pinchPoint: null, palm: null, twoHandPinch: false, active: new Set(), events: [], ...patch });
  const settle = (controller: GestureController) => {
    let result = controller.step(0.016);
    for (let i = 0; i < 300; i += 1) result = controller.step(0.016);
    return result;
  };

  it("mano abierta expande y puño contrae", () => {
    const controller = new GestureController({ actions: {} });
    controller.ingest(output({ openness: 1 }));
    assert.ok(settle(controller).expansion > 0.9);
    controller.ingest(output({ openness: 0 }));
    assert.ok(settle(controller).expansion < -0.9);
  });

  it("mover la mano rota e inclina el núcleo", () => {
    const controller = new GestureController({ actions: {} });
    controller.ingest(output({ pan: { x: 1, y: 0 } }));
    assert.ok(settle(controller).yaw > 1);
    controller.ingest(output({ pan: { x: 0, y: 1 } }));
    const tilted = settle(controller);
    assert.ok(Math.abs(tilted.yaw) < 0.01);
    assert.ok(tilted.pitch < -0.5);
  });

  it("con dos manos manda la separación", () => {
    const controller = new GestureController({ actions: {} });
    controller.ingest(output({ handCount: 2, handsDistance: 0.8, openness: 0 }));
    assert.ok(settle(controller).expansion > 0.9, "separadas: expande aunque estén cerradas");
    controller.ingest(output({ handCount: 2, handsDistance: 0.2, openness: 1 }));
    assert.ok(settle(controller).expansion < -0.5);
  });

  it("sin manos vuelve gradualmente al estado automático", () => {
    const controller = new GestureController({ actions: {} });
    controller.ingest(output({ openness: 1, pan: { x: 1, y: 0 } }));
    settle(controller);
    controller.ingest(output({ tracked: false, handCount: 0 }));
    const soon = controller.step(0.1);
    assert.ok(soon.strength > 0.5, "no cae de golpe");
    assert.ok(settle(controller).strength < 0.01);
  });

  it("respeta los gestos desactivados", () => {
    const controller = new GestureController({ actions: {} });
    controller.setEnabled({ open_hand: false, swirl: false }, false);
    controller.ingest(output({ openness: 1, pan: { x: 1, y: 1 }, active: new Set<GestureName>(["swirl"]) }));
    const result = settle(controller);
    assert.equal(result.expansion, 0);
    assert.equal(result.yaw, 0);
    assert.equal(result.vortex, 0);
  });

  it("dispara la acción al confirmarse el gesto, no antes", () => {
    const calls: GestureAction[] = [];
    const controller = new GestureController({ actions: { explode: () => calls.push("explode") } });
    controller.ingest(output({ events: [{ gesture: "burst", phase: "detected", timestamp: 0 }] }));
    assert.deepEqual(calls, []);
    controller.ingest(output({ events: [{ gesture: "burst", phase: "confirmed", timestamp: 1 }] }));
    assert.deepEqual(calls, ["explode"]);
  });

  it("una acción sensible nunca se ejecuta sin confirmación", () => {
    let executed = 0;
    const event = output({ events: [{ gesture: "pinch", phase: "confirmed", timestamp: 0 }] });
    const bindings = { pinch: { action: "run_tool", sensitive: true } };

    const unattended = new GestureController({ actions: { run_tool: () => (executed += 1) }, bindings });
    unattended.ingest(event);
    assert.equal(executed, 0, "sin confirmador se descarta");

    let pending: (() => void) | null = null;
    const guarded = new GestureController({ actions: { run_tool: () => (executed += 1) }, bindings, confirm: (_action, _payload, proceed) => (pending = proceed) });
    guarded.ingest(event);
    assert.equal(executed, 0, "espera a la confirmación");
    assert.ok(pending);
    (pending as () => void)();
    assert.equal(executed, 1);
  });
});

describe("agarrar y girar el núcleo", () => {
  const output = (patch: Partial<GestureOutput>): GestureOutput => ({ tracked: true, handCount: 1, openness: 0.5, pan: { x: 0, y: 0 }, handsDistance: null, handsAngle: null, pinchPoint: null, palm: null, twoHandPinch: false, active: new Set(), events: [], ...patch });
  /** Arrastra la pinza de `from` a `to` en pasos de 50 ms y devuelve el instante final. */
  const drag = (controller: GestureController, from: [number, number], to: [number, number], steps = 10, start = 0) => {
    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps;
      const point = { x: from[0] + (to[0] - from[0]) * t, y: from[1] + (to[1] - from[1]) * t };
      controller.ingest(output({ pinchPoint: point, palm: point }), start + i * 50);
    }
    return start + steps * 50;
  };

  it("arrastrar la pinza gira el núcleo en el sentido de la mano", () => {
    const controller = new GestureController({ actions: {} });
    drag(controller, [-0.5, 0], [0.5, 0]);
    const turned = controller.step(0.016);
    assert.ok(turned.spinYaw > 2, `guiñada ${turned.spinYaw}`);
    assert.ok(Math.abs(turned.spinPitch) < 1e-9);
    assert.equal(turned.grabbing, true);

    const vertical = new GestureController({ actions: {} });
    drag(vertical, [0, -0.2], [0, 0.2]);
    assert.ok(vertical.step(0.016).spinPitch > 0.8);
  });

  it("el giro se acumula entre agarres y permite dar la vuelta completa", () => {
    const controller = new GestureController({ actions: {} });
    let t = 0;
    for (let i = 0; i < 4; i += 1) {
      t = drag(controller, [-0.5, 0], [0.5, 0], 10, t) + 50;
      // Soltar y volver al punto de partida sin pinza no deshace el giro.
      controller.ingest(output({ pinchPoint: null }), t);
      t += 50;
    }
    assert.ok(controller.step(0).spinYaw > Math.PI * 2);
  });

  it("al soltar sigue girando por inercia y acaba parándose", () => {
    const controller = new GestureController({ actions: {} });
    const end = drag(controller, [-0.5, 0], [0.5, 0]);
    const held = controller.step(0).spinYaw;
    controller.ingest(output({ pinchPoint: null }), end + 50);
    let state = controller.step(0.016);
    assert.equal(state.grabbing, false);
    for (let i = 0; i < 30; i += 1) state = controller.step(0.016);
    assert.ok(state.spinYaw > held + 0.3, "la inercia lo lleva más allá");
    for (let i = 0; i < 600; i += 1) state = controller.step(0.016);
    const rest = state.spinYaw;
    for (let i = 0; i < 60; i += 1) state = controller.step(0.016);
    assert.equal(state.spinYaw, rest, "termina deteniéndose");
  });

  it("la orientación se conserva cuando las manos salen de cámara", () => {
    const controller = new GestureController({ actions: {} });
    // Arrastre lento y parada antes de soltar: sin inercia que confunda la medida.
    const end = drag(controller, [-0.3, 0], [0.3, 0]);
    controller.ingest(output({ pinchPoint: { x: 0.3, y: 0 }, palm: { x: 0.3, y: 0 } }), end + 500);
    controller.ingest(output({ pinchPoint: { x: 0.3, y: 0 }, palm: { x: 0.3, y: 0 } }), end + 1000);
    const before = controller.step(0).spinYaw;
    controller.ingest(output({ tracked: false, handCount: 0 }), end + 1050);
    let state = controller.step(0.016);
    for (let i = 0; i < 600; i += 1) state = controller.step(0.016);
    assert.ok(state.strength < 0.01);
    assert.ok(Math.abs(state.spinYaw - before) < 0.05, "no vuelve sola a la posición inicial");
  });

  it("limita el cabeceo para que el núcleo no se dé la vuelta", () => {
    const controller = new GestureController({ actions: {} });
    let t = 0;
    for (let i = 0; i < 6; i += 1) t = drag(controller, [0, -0.8], [0, 0.8], 10, t) + 50;
    assert.ok(controller.step(0).spinPitch <= 1.35 + 1e-9);
  });

  it("dos manos como un volante ladean el núcleo en el mismo sentido", () => {
    const controller = new GestureController({ actions: {} });
    const grip = { pinchPoint: { x: 0, y: 0 }, palm: { x: 0, y: 0 }, twoHandPinch: true, handCount: 2, handsDistance: 0.4 };
    for (let i = 0; i <= 10; i += 1) controller.ingest(output({ ...grip, handsAngle: (i / 10) * 0.8 }), i * 50);
    // Ángulo creciente con y hacia abajo = sentido horario en pantalla = alabeo negativo.
    assert.ok(Math.abs(controller.step(0).roll + 0.8) < 1e-9);
  });

  it("ignora el salto de ángulo cuando las manos se cruzan", () => {
    const controller = new GestureController({ actions: {} });
    const grip = { pinchPoint: { x: 0, y: 0 }, palm: { x: 0, y: 0 }, twoHandPinch: true, handCount: 2, handsDistance: 0.4 };
    controller.ingest(output({ ...grip, handsAngle: 1.4 }), 0);
    controller.ingest(output({ ...grip, handsAngle: -1.4 }), 50);
    assert.equal(controller.step(0).roll, 0);
  });

  it("recolocar devuelve la orientación original y desactivar la rotación la bloquea", () => {
    const controller = new GestureController({ actions: {} });
    drag(controller, [-0.5, 0], [0.5, 0]);
    controller.resetOrientation();
    const reset = controller.step(0.5);
    assert.equal(reset.spinYaw, 0);

    const locked = new GestureController({ actions: {} });
    locked.setEnabled({}, false);
    drag(locked, [-0.5, 0], [0.5, 0]);
    assert.equal(locked.step(0.016).spinYaw, 0);
  });
});

describe("ángulo entre manos", () => {
  it("es 0 con las manos a la misma altura y no depende de cuál es la principal", () => {
    const recognizer = new GestureRecognizer(config());
    const level = recognizer.update(frameOf(0, { cx: 0.3, cy: 0.5, open: 0.5 }, { cx: 0.7, cy: 0.5, open: 0.5 }));
    assert.ok(level.handsAngle !== null && Math.abs(level.handsAngle) < 0.05);
    const tilted = recognizer.update(frameOf(50, { cx: 0.7, cy: 0.7, open: 0.5 }, { cx: 0.3, cy: 0.3, open: 0.5 }));
    assert.ok(tilted.handsAngle !== null && Math.abs(tilted.handsAngle - Math.PI / 4) < 0.05);
    assert.equal(recognizer.update(frameOf(100, { cx: 0.5, cy: 0.5, open: 0.5 })).handsAngle, null);
  });
});

describe("agarre: defectos vistos con cámara real", () => {
  const output = (patch: Partial<GestureOutput>): GestureOutput => ({ tracked: true, handCount: 1, openness: 0.5, pan: { x: 0, y: 0 }, handsDistance: null, handsAngle: null, pinchPoint: null, palm: null, twoHandPinch: false, active: new Set(), events: [], ...patch });

  it("el respingo de la mano al abrir los dedos no lanza el núcleo", () => {
    const controller = new GestureController({ actions: {} });
    // Agarre quieto durante 600 ms y, en el último fotograma, un salto brusco.
    for (let i = 0; i <= 12; i += 1) controller.ingest(output({ pinchPoint: { x: 0, y: 0 }, palm: { x: 0, y: 0 } }), i * 50);
    controller.ingest(output({ pinchPoint: { x: 0, y: 0.3 }, palm: { x: 0, y: 0.3 } }), 650);
    controller.ingest(output({ palm: { x: 0, y: 0.3 } }), 700);
    const released = controller.step(0).spinPitch;
    let state = controller.step(0.016);
    for (let i = 0; i < 120; i += 1) state = controller.step(0.016);
    assert.ok(Math.abs(state.spinPitch - released) < 0.05, `deriva ${state.spinPitch - released}`);
  });

  it("el giro sigue a la palma, no al punto de pinza", () => {
    const controller = new GestureController({ actions: {} });
    // Los dedos tiemblan (el punto de pinza se mueve) pero la mano no.
    for (let i = 0; i <= 10; i += 1) controller.ingest(output({ pinchPoint: { x: i % 2 ? 0.2 : -0.2, y: 0 }, palm: { x: 0, y: 0 } }), i * 50);
    assert.equal(controller.step(0).spinYaw, 0);
  });

  it("dos manos a la vista sin pinza no ladean el núcleo", () => {
    const controller = new GestureController({ actions: {} });
    for (let i = 0; i <= 10; i += 1) controller.ingest(output({ handCount: 2, handsDistance: 0.5, handsAngle: (i / 10) * 0.8, palm: { x: 0, y: 0 } }), i * 50);
    assert.equal(controller.step(0).roll, 0);
  });

  it("con el volante a dos manos no se cuela giro de una mano", () => {
    const controller = new GestureController({ actions: {} });
    for (let i = 0; i <= 10; i += 1) {
      const palm = { x: i / 20, y: 0 };
      controller.ingest(output({ handCount: 2, handsDistance: 0.4, twoHandPinch: true, pinchPoint: palm, palm, handsAngle: i / 20 }), i * 50);
    }
    const state = controller.step(0);
    assert.equal(state.spinYaw, 0);
    assert.ok(state.roll < -0.4);
  });

  it("una pinza ya agarrada aguanta aunque el resto de la mano se cierre", () => {
    const recognizer = new GestureRecognizer(gestureConfigFor(0.5, 1));
    let last = recognizer.update(frameOf(0, { cx: 0.5, cy: 0.5, open: 1, pinch: true }));
    for (let i = 1; i < 8; i += 1) last = recognizer.update(frameOf(i * 50, { cx: 0.5, cy: 0.5, open: 1, pinch: true }));
    assert.ok(last.active.has("pinch"));
    // Durante el arrastre los demás dedos se ven medio cerrados.
    for (let i = 8; i < 20; i += 1) last = recognizer.update(frameOf(i * 50, { cx: 0.5 + (i - 8) * 0.02, cy: 0.5, open: 0.25, pinch: true }));
    assert.ok(last.active.has("pinch"), "sigue agarrado");
    assert.ok(last.palm && last.palm.x > 0.2);
  });
});
