import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { STATE_PRIORITY, type AtlasVisualState } from "../interaction/AtlasVisualStateMachine.ts";
import { AtlasVisualStateMachine } from "../interaction/AtlasVisualStateMachine.ts";
import { DEFAULT_SETTINGS, sanitizeSettings } from "../interaction/InteractionConfig.ts";
import { VISUAL_PRESETS } from "../particle-core/ParticlePresets.ts";
import { audioDrivesHumanoid, humanoidQuality, humanoidState, toLandmarkerResult } from "./humanoidBridge.ts";

describe("humanoide: estados", () => {
  it("cada estado visual de ATLAS tiene un estado del contrato de Atlas3D", () => {
    const expected: Record<AtlasVisualState, string> = {
      IDLE: "idle", SLEEPING: "idle", SUCCESS: "idle", LISTENING: "listening", THINKING: "thinking",
      PROCESSING: "thinking", EXECUTING: "executing", SPEAKING: "speaking", ERROR: "error",
    };
    for (const state of Object.keys(STATE_PRIORITY) as AtlasVisualState[]) assert.equal(humanoidState(state), expected[state], state);
  });

  it("EXECUTING solo dura mientras la herramienta está en curso y vuelve a THINKING", () => {
    const machine = new AtlasVisualStateMachine();
    machine.setSignal("THINKING", true);
    assert.equal(machine.update(0), "THINKING");
    machine.setSignal("EXECUTING", true);
    assert.equal(machine.update(1), "EXECUTING");
    machine.setSignal("EXECUTING", false);
    assert.equal(machine.update(2), "THINKING");
  });

  it("hablar y escuchar tienen prioridad sobre ejecutar", () => {
    assert.ok(STATE_PRIORITY.SPEAKING > STATE_PRIORITY.EXECUTING);
    assert.ok(STATE_PRIORITY.LISTENING > STATE_PRIORITY.EXECUTING);
    assert.ok(STATE_PRIORITY.EXECUTING > STATE_PRIORITY.THINKING);
  });

  it("el núcleo anterior también tiene preset para EXECUTING", () => {
    assert.ok(VISUAL_PRESETS.executing);
  });

  it("el audio solo anima al humanoide al escuchar y al hablar", () => {
    assert.deepEqual(["idle", "listening", "thinking", "executing", "speaking", "error"].filter((s) => audioDrivesHumanoid(s as never)), ["listening", "speaking"]);
  });
});

describe("humanoide: calidad y ajustes", () => {
  it("las calidades se traducen sin reducir partículas", () => {
    assert.equal(humanoidQuality("low"), "LOW");
    assert.equal(humanoidQuality("medium"), "MEDIUM");
    assert.equal(humanoidQuality("high"), "HIGH");
  });

  it("el humanoide es la figura por defecto y los ajustes inválidos se corrigen", () => {
    assert.equal(DEFAULT_SETTINGS.avatar, "humanoid");
    assert.equal(DEFAULT_SETTINGS.avatarBloom, true);
    assert.equal(sanitizeSettings({ avatar: "otro", avatarBloom: "si" }).avatar, "humanoid");
    assert.equal(sanitizeSettings({ avatar: "core" }).avatar, "core");
    assert.equal(sanitizeSettings({ avatarBloom: false }).avatarBloom, false);
    // Preferencias guardadas antes de la integración: aparece el humanoide.
    assert.equal(sanitizeSettings({ particles: true, quality: "high" }).avatar, "humanoid");
  });
});

describe("humanoide: manos", () => {
  it("deshace el espejo y conserva la etiqueta de MediaPipe", () => {
    const landmarks = Array.from({ length: 21 }, (_, i) => ({ x: 0.25, y: i / 21, z: -0.01 }));
    const result = toLandmarkerResult({ timestamp: 10, hands: [{ landmarks, handedness: "Left" }, { landmarks, handedness: null }] });
    assert.equal(result.landmarks.length, 2);
    assert.equal(result.landmarks[0][0].x, 0.75);
    assert.equal(result.landmarks[0][5].y, 5 / 21);
    assert.deepEqual(result.handedness[0], [{ categoryName: "Left", score: 1 }]);
    assert.deepEqual(result.handedness[1], []);
  });

  it("sin manos, un fotograma vacío (para que el seguimiento suelte los gestos)", () => {
    assert.deepEqual(toLandmarkerResult({ timestamp: 1, hands: [] }), { landmarks: [], handedness: [] });
  });
});
