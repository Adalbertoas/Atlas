import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { AtlasVisualStateMachine, STATE_LABELS, STATE_PRIORITY, type AtlasVisualState } from "./AtlasVisualStateMachine.ts";
import { DEFAULT_SETTINGS, sanitizeSettings, SETTINGS_KEY, SettingsStore } from "./InteractionConfig.ts";

describe("AtlasVisualStateMachine", () => {
  it("empieza en IDLE y sigue las señales reales", () => {
    const machine = new AtlasVisualStateMachine();
    assert.equal(machine.update(0), "IDLE");
    machine.setSignal("THINKING", true);
    assert.equal(machine.update(1), "THINKING");
    machine.setSignal("THINKING", false);
    assert.equal(machine.update(2), "IDLE");
  });

  it("la voz activa tiene prioridad sobre pensar y sobre IDLE", () => {
    const machine = new AtlasVisualStateMachine();
    machine.setSignal("THINKING", true);
    machine.setSignal("LISTENING", true);
    assert.equal(machine.update(0), "LISTENING");
    machine.setSignal("SPEAKING", true);
    assert.equal(machine.update(1), "SPEAKING");
    machine.setSignal("SPEAKING", false);
    machine.setSignal("LISTENING", false);
    assert.equal(machine.update(2), "THINKING", "al acabar la voz reaparece el estado de fondo");
  });

  it("un error tiene prioridad sobre todo, pero es temporal", () => {
    const machine = new AtlasVisualStateMachine();
    machine.setSignal("SPEAKING", true);
    machine.pulse("ERROR", 2000, 0);
    assert.equal(machine.update(100), "ERROR");
    assert.equal(machine.update(1999), "ERROR");
    assert.equal(machine.update(2000), "SPEAKING");
  });

  it("el éxito es temporal y no tapa una nueva petición", () => {
    const machine = new AtlasVisualStateMachine();
    machine.pulse("SUCCESS", 1400, 0);
    assert.equal(machine.update(10), "SUCCESS");
    machine.setSignal("THINKING", true);
    assert.equal(machine.update(20), "THINKING");
    machine.setSignal("THINKING", false);
    assert.equal(machine.update(30), "SUCCESS");
    assert.equal(machine.update(1500), "IDLE");
  });

  it("el reposo cede ante cualquier actividad", () => {
    const machine = new AtlasVisualStateMachine();
    machine.setSignal("SLEEPING", true);
    assert.equal(machine.update(0), "SLEEPING");
    machine.setSignal("PROCESSING", true);
    assert.equal(machine.update(1), "PROCESSING");
  });

  it("repetir un pulso lo prolonga, nunca lo acorta", () => {
    const machine = new AtlasVisualStateMachine();
    machine.pulse("ERROR", 2000, 0);
    machine.pulse("ERROR", 500, 100);
    assert.equal(machine.update(1500), "ERROR");
    machine.pulse("ERROR", 2000, 1500);
    assert.equal(machine.update(3000), "ERROR");
    assert.equal(machine.update(3500), "IDLE");
  });

  it("notifica solo los cambios, con el estado anterior", () => {
    const machine = new AtlasVisualStateMachine();
    const seen: string[] = [];
    const unsubscribe = machine.subscribe((state, previous) => seen.push(`${previous}>${state}`));
    machine.setSignal("LISTENING", true);
    machine.update(0);
    machine.update(1);
    machine.setSignal("LISTENING", false);
    machine.update(2);
    unsubscribe();
    machine.setSignal("THINKING", true);
    machine.update(3);
    assert.deepEqual(seen, ["IDLE>LISTENING", "LISTENING>IDLE"]);
  });

  it("todas las prioridades son distintas y cada estado tiene etiqueta", () => {
    const states = Object.keys(STATE_PRIORITY) as AtlasVisualState[];
    assert.equal(states.length, 8);
    assert.equal(new Set(Object.values(STATE_PRIORITY)).size, states.length);
    for (const state of states) assert.ok(STATE_LABELS[state]);
  });
});

describe("preferencias de Neural Core", () => {
  const memoryStorage = (initial: Record<string, string> = {}) => {
    const data = new Map(Object.entries(initial));
    return { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => void data.set(key, value), data };
  };

  it("los valores predeterminados no encienden la cámara ni leen en voz alta", () => {
    assert.equal(DEFAULT_SETTINGS.debugCamera, false);
    assert.equal(DEFAULT_SETTINGS.debugLandmarks, false);
    assert.equal(DEFAULT_SETTINGS.speakReplies, false);
    assert.equal(DEFAULT_SETTINGS.listenOnStartup, false, "el micrófono no queda escuchando sin que se pida");
    assert.ok(!("handsFree" in DEFAULT_SETTINGS), "la escucha manos libres no se persiste encendida");
    assert.ok(!("handControl" in DEFAULT_SETTINGS), "el control por manos no se persiste");
  });

  it("sanea datos corruptos o manipulados", () => {
    assert.deepEqual(sanitizeSettings(null), DEFAULT_SETTINGS);
    assert.deepEqual(sanitizeSettings("basura"), DEFAULT_SETTINGS);
    const cleaned = sanitizeSettings({ quality: "ultra", gestureSensitivity: 9, intensity: Number.NaN, coreColor: "javascript:alert(1)", particles: "si", gestures: { burst: false, inventado: true } });
    assert.equal(cleaned.quality, "auto");
    assert.equal(cleaned.gestureSensitivity, 1);
    assert.equal(cleaned.intensity, DEFAULT_SETTINGS.intensity);
    assert.equal(cleaned.coreColor, null);
    assert.equal(cleaned.particles, true);
    assert.equal(cleaned.gestures.burst, false);
    assert.equal(cleaned.gestures.fist, true);
    assert.ok(!("inventado" in cleaned.gestures));
  });

  it("conserva los valores válidos", () => {
    const cleaned = sanitizeSettings({ quality: "low", coreColor: "#12abEF", intensity: 0.3, bloom: true });
    assert.equal(cleaned.quality, "low");
    assert.equal(cleaned.coreColor, "#12abEF");
    assert.equal(cleaned.intensity, 0.3);
    assert.equal(cleaned.bloom, true);
  });

  it("persiste los cambios, avisa a los suscriptores y restaura", () => {
    const storage = memoryStorage();
    const store = new SettingsStore(storage);
    let notified = 0;
    store.subscribe(() => (notified += 1));

    store.update({ quality: "high", intensity: 0.4 });
    assert.equal(notified, 1);
    assert.equal(store.get().quality, "high");
    assert.equal(new SettingsStore(storage).get().intensity, 0.4, "se recupera en la siguiente sesión");

    store.reset();
    assert.deepEqual(store.get(), DEFAULT_SETTINGS);
    assert.deepEqual(JSON.parse(storage.data.get(SETTINGS_KEY) ?? "null"), DEFAULT_SETTINGS);
  });

  it("funciona sin almacenamiento y con almacenamiento dañado", () => {
    assert.deepEqual(new SettingsStore(null).get(), DEFAULT_SETTINGS);
    assert.deepEqual(new SettingsStore(memoryStorage({ [SETTINGS_KEY]: "{no es json" })).get(), DEFAULT_SETTINGS);
    const failing = { getItem: () => null, setItem: () => { throw new Error("cuota"); } };
    const store = new SettingsStore(failing);
    store.update({ intensity: 0.2 });
    assert.equal(store.get().intensity, 0.2, "el cambio se aplica aunque no pueda guardarse");
  });
});
