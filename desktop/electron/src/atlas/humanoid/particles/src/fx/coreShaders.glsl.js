// ATLAS Fase 5E — shaders del núcleo de energía. Todo el movimiento se calcula en la GPU a partir de fases que la CPU
// acumula (orbitPhase, flowPhase, noiseT, ringPhase): así un cambio de velocidad nunca provoca un salto de posición.

export const NOISE = /* glsl */`
float hash3(vec3 p) { p = fract(p * 0.3183099 + vec3(0.11, 0.17, 0.23)); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vnoise(vec3 x) {
  vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z);
}
vec3 vnoise3(vec3 p) { return vec3(vnoise(p), vnoise(p + vec3(31.4, 7.1, 2.7)), vnoise(p + vec3(5.2, 47.3, 13.9))) * 2.0 - 1.0; }
mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c); }
mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c); }
`;

// uniforms comunes (un mismo objeto compartido por todos los materiales del núcleo)
export const COMMON = /* glsl */`
uniform float uTime, uNoiseT, uOrbitPhase, uFlowPhase, uPulse, uAudio, uTurb, uIntensity, uBrightness, uScale, uFlow, uPixelScale, uAudioGain;
uniform vec3 uColor, uColor2, uFlowDir;
`;

// --- envoltura del núcleo (esfera deformada con brillo de borde) ---
export const shellVS = NOISE + COMMON + /* glsl */`
out vec3 vN; out vec3 vV; out float vD;
void main() {
  vec3 n = normalize(position);
  float d = (vnoise(n * 3.0 + uNoiseT * 0.9) - 0.5) * (0.12 + uTurb * 0.55) + uPulse * 0.22 + uAudio * uAudioGain * 0.25;
  vec3 p = position * (1.0 + d) * uScale;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vN = normalize(normalMatrix * n); vV = normalize(-mv.xyz); vD = d;
  gl_Position = projectionMatrix * mv;
}`;
export const shellFS = COMMON + /* glsl */`
in vec3 vN; in vec3 vV; in float vD;
out vec4 outColor;
void main() {
  float ndv = abs(dot(normalize(vN), normalize(vV)));
  float fres = pow(1.0 - ndv, 2.4);
  vec3 c = mix(uColor, uColor2, clamp(vD * 2.0 + 0.3, 0.0, 1.0));
  vec3 col = c * (0.18 + 1.9 * fres) * (0.7 + 0.6 * uPulse) * uIntensity * uBrightness;
  outColor = vec4(col, 1.0);
}`;

// --- núcleo interior muy brillante ---
export const kernelFS = COMMON + /* glsl */`
in vec3 vN; in vec3 vV; in float vD;
out vec4 outColor;
void main() {
  float ndv = abs(dot(normalize(vN), normalize(vV)));
  vec3 col = mix(uColor, vec3(1.0), 0.65) * pow(ndv, 1.6) * (1.1 + 1.2 * uPulse + uAudio * uAudioGain) * uIntensity * uBrightness;
  outColor = vec4(col, 1.0);
}`;

// --- partículas: plasma interior, órbitas/flujo y campo ---
const POINT_OUT = /* glsl */`
out vec3 vColor; out float vAlpha;
void emit(vec3 local, float sizeM, vec3 col, float alpha) {
  vec4 mv = modelViewMatrix * vec4(local, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = clamp(sizeM * uPixelScale / max(0.05, -mv.z), 1.0, 24.0);
  vColor = col; vAlpha = alpha;
}`;
export const pointFS = /* glsl */`
in vec3 vColor; in float vAlpha;
out vec4 outColor;
void main() {
  vec2 d = gl_PointCoord - 0.5; float r2 = dot(d, d);
  if (r2 > 0.25) discard;
  outColor = vec4(vColor * (exp(-r2 * 28.0) + 0.25 * exp(-r2 * 8.0)) * vAlpha, 1.0);
}`;

export const plasmaVS = NOISE + COMMON + POINT_OUT + /* glsl */`
in vec4 aSeed;
void main() {
  vec3 dir = normalize(aSeed.xyz * 2.0 - 1.0 + 1e-4);
  float r = 0.048 * pow(aSeed.w, 0.333) * (1.0 + uPulse * 0.25 + uAudio * uAudioGain * 0.3);
  vec3 p = dir * r;
  p += vnoise3(p * 30.0 + uNoiseT * 1.6 + aSeed.w * 10.0) * (0.006 + 0.016 * uTurb);
  p = rotY(uOrbitPhase * (0.6 + aSeed.w) * 1.7) * p;
  vec3 col = mix(uColor, vec3(1.0), 0.45 + 0.4 * aSeed.y);
  emit(p * uScale, 0.0042 * (0.6 + aSeed.x), col * uIntensity * uBrightness, 0.55 + 0.45 * uPulse);
}`;

export const orbitVS = NOISE + COMMON + POINT_OUT + /* glsl */`
in vec4 aOrbit;   // radio, inclinación, nodo, fase
in vec2 aSpeed;   // velocidad relativa, semilla
void main() {
  float rad = aOrbit.x * (1.0 + uAudio * uAudioGain * 0.22 + uPulse * 0.06);
  float a = aOrbit.w + uOrbitPhase * aSpeed.x;
  vec3 o = rotY(aOrbit.z) * rotX(aOrbit.y) * vec3(cos(a) * rad, 0.0, sin(a) * rad);
  o += vnoise3(o * 12.0 + uNoiseT) * 0.008 * uTurb;
  // flujo direccional (EXECUTING): las partículas salen del núcleo en hélice a lo largo de uFlowDir
  float t = fract(aSpeed.y * 7.31 + uFlowPhase * (0.6 + 0.5 * aSpeed.x));
  vec3 fd = normalize(uFlowDir), side = normalize(cross(fd, vec3(0.0, 0.0, 1.0)) + 1e-4), up = cross(side, fd);
  float sa = aOrbit.w * 3.0 + t * 18.0;
  vec3 f = fd * (0.03 + t * 0.55) + (side * cos(sa) + up * sin(sa)) * (0.012 + 0.05 * t * (1.0 - t) * 4.0 * 0.25);
  vec3 p = mix(o, f, uFlow);
  float fade = mix(1.0, smoothstep(0.0, 0.08, t) * (1.0 - t), uFlow);
  vec3 col = mix(uColor, uColor2, aSpeed.y) * uIntensity * uBrightness;
  emit(p * uScale, 0.0036 * (0.7 + aSpeed.y * 0.8), col, (0.55 + 0.3 * uPulse) * fade);
}`;

export const fieldVS = NOISE + COMMON + POINT_OUT + /* glsl */`
in vec4 aSeed;          // posición base en una caja alrededor del avatar (xyz) + semilla
uniform vec3 uCore;     // posición del núcleo (en el espacio del campo)
uniform float uFieldSwirl;
void main() {
  vec3 b = aSeed.xyz;
  vec3 p = b + vnoise3(b * 0.9 + uNoiseT * 0.12) * 0.18;
  p = rotY(uFieldSwirl * (0.3 + aSeed.w * 0.7) * 0.15) * (p - vec3(uCore.x, 0.0, uCore.z)) + vec3(uCore.x, 0.0, uCore.z);
  vec3 toP = p - uCore; float d = length(toP);
  p += toP / max(d, 1e-3) * (uAudio * uAudioGain * 0.16 + uPulse * 0.025) * exp(-d * 0.9);
  vec3 col = mix(uColor, uColor2, aSeed.w) * uBrightness;
  float a = (0.10 + 0.12 * aSeed.w) * (0.6 + 0.6 * uIntensity) * (1.0 + uAudio * uAudioGain * 0.8);
  emit(p, 0.0045 * (0.5 + aSeed.w), col, a);
}`;

// --- anillos de energía: toro fino con pulsos que recorren el anillo ---
export const ringVS = COMMON + /* glsl */`
out float vU;
void main() { vU = uv.x; gl_Position = projectionMatrix * modelViewMatrix * vec4(position * uScale * (1.0 + uPulse * 0.05 + uAudio * uAudioGain * 0.08), 1.0); }`;
export const ringFS = COMMON + /* glsl */`
in float vU; uniform float uRingPhase, uRingDash; uniform vec3 uRingColor;
out vec4 outColor;
void main() {
  float s = fract(vU * uRingDash - uRingPhase);
  float dash = smoothstep(0.0, 0.08, s) * (1.0 - smoothstep(0.35, 0.6, s));
  vec3 col = uRingColor * (0.25 + 1.4 * dash) * uIntensity * uBrightness;
  outColor = vec4(col, 1.0);
}`;

// --- ondas: esfera que se expande (emisión) o se contrae (recepción), brillo en el borde ---
export const waveVS = /* glsl */`
uniform float uR;
out vec3 vN; out vec3 vV;
void main() { vec4 mv = modelViewMatrix * vec4(position * uR, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`;
export const waveFS = /* glsl */`
uniform float uA; uniform vec3 uC;
in vec3 vN; in vec3 vV;
out vec4 outColor;
void main() { float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 4.0); outColor = vec4(uC * f * uA, 1.0); }`;

// --- destellos: chispas que salen del núcleo y se apagan ---
export const sparkVS = /* glsl */`
in vec4 aDir;   // dirección (xyz) + velocidad
uniform float uAge, uPixelScale, uScale; uniform vec3 uSparkColor;
out vec3 vColor; out float vAlpha;
void main() {
  float d = aDir.w * (1.0 - exp(-uAge * 3.2)) * 0.32;
  vec4 mv = modelViewMatrix * vec4(normalize(aDir.xyz) * d * uScale, 1.0);
  gl_Position = projectionMatrix * mv;
  float life = exp(-uAge * 2.6);
  gl_PointSize = clamp(0.006 * (0.4 + life) * uPixelScale / max(0.05, -mv.z), 1.0, 20.0);
  vColor = mix(uSparkColor, vec3(1.0), 0.35 * life); vAlpha = life * step(0.0, uAge) * step(uAge, 2.5);
}`;
