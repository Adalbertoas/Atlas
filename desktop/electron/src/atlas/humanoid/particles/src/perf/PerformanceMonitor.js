// ATLAS Fase 5B — monitor de rendimiento: FPS, tiempo de frame, memoria (JS y estimación GPU), llamadas de dibujo.
// Sin asignaciones por frame: búfer circular de tiempos.
export class PerformanceMonitor {
  constructor(size = 120) {
    this.times = new Float32Array(size);
    this.i = 0; this.n = 0; this.last = 0;
  }
  frame(now = performance.now()) {
    if (this.last) { this.times[this.i] = now - this.last; this.i = (this.i + 1) % this.times.length; this.n = Math.min(this.n + 1, this.times.length); }
    this.last = now;
  }
  get frameMs() { if (!this.n) return 0; let s = 0; for (let k = 0; k < this.n; k++) s += this.times[k]; return s / this.n; }
  get fps() { const ms = this.frameMs; return ms ? 1000 / ms : 0; }
  get p95Ms() { if (!this.n) return 0; const a = Array.from(this.times.subarray(0, this.n)).sort((x, y) => x - y); return a[Math.floor(0.95 * (a.length - 1))]; }
  reset() { this.i = 0; this.n = 0; this.last = 0; }
  snapshot(renderer, engine) {
    const mem = performance.memory;
    return {
      fps: +this.fps.toFixed(1), frameMs: +this.frameMs.toFixed(2), p95Ms: +this.p95Ms.toFixed(2),
      drawCalls: renderer?.info.render.calls, points: renderer?.info.render.points,
      jsHeapMB: mem ? +(mem.usedJSHeapSize / 2 ** 20).toFixed(1) : null,
      gpu: engine?.memoryReport(), textures: renderer?.info.memory.textures, geometries: renderer?.info.memory.geometries,
    };
  }
}
