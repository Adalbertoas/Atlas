// Shaders GLSL del núcleo. Toda la animación por partícula ocurre en GPU; la CPU
// solo envía un puñado de uniforms por fotograma (ver ParticleAnimator).

const simplexNoise = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.0-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;vec4 s1=floor(b1)*2.0+1.0;vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
`;

export const particleVertexShader = /* glsl */ `
uniform float uTime;
uniform float uExpansion;
uniform vec3 uRotation;          // x = guiñada (Y), y = cabeceo (X), z = alabeo (Z)
uniform float uGestureStrength;
uniform float uAudioLevel;
uniform float uAudioBass;
uniform float uAudioMid;
uniform float uAudioTreble;
uniform float uEmotion;          // turbulencia del estado actual
uniform vec3 uInteractionPoint;
uniform float uInteractionStrength;
uniform float uExplosionProgress;
uniform float uPulse;            // -1 inactivo, 0..1 avance de la onda de choque
uniform float uRing;
uniform float uCloud;
uniform float uVortex;
uniform float uVortexPhase;
uniform float uWavePhase;
uniform float uWaveStrength;
uniform float uJitter;
uniform float uSize;
uniform float uScale;

attribute vec3 aRing;
attribute vec3 aCloud;
attribute vec4 aSeed;
attribute float aSize;

varying float vMix;
varying float vGlow;
varying float vAlpha;

#ifdef USE_SIMPLEX
${simplexNoise}
#endif

// Campo de flujo barato y continuo: suficiente para el movimiento orgánico.
vec3 flow(vec3 p, float t) {
  return 0.5 * vec3(
    sin(p.y * 1.7 + t) + sin(p.z * 1.3 - t * 0.7),
    sin(p.z * 1.9 + t * 1.1) + sin(p.x * 1.5 + t * 0.6),
    sin(p.x * 1.6 - t * 0.9) + sin(p.y * 1.4 + t * 0.8)
  );
}

void main() {
  // 1. Forma: mezcla continua esfera -> anillo -> nube (reversible).
  vec3 p = mix(position, aRing, uRing);
  p = mix(p, aCloud, uCloud);

  float r = length(p);
  vec3 dir = r > 0.0001 ? p / r : vec3(0.0, 1.0, 0.0);

  // 2. Movimiento orgánico y deformación por ruido.
  p += flow(p * 1.4 + aSeed.xyz * 3.0, uTime * 0.35) * (0.03 + uEmotion * 0.1);
  #ifdef USE_SIMPLEX
  p += dir * snoise(dir * 1.8 + vec3(uTime * 0.15)) * (0.035 + uEmotion * 0.09);
  #endif

  // 3. Respiración, ondas, audio y onda de choque, todo a lo largo del radio.
  float breathe = sin(uTime * 0.9 + aSeed.w * 6.2832) * 0.012;
  float wave = sin(r * 9.0 - uWavePhase + aSeed.x) * uWaveStrength * (0.25 + uAudioMid * 0.9);
  float audioPush = uAudioLevel * 0.1 + uAudioBass * 0.14 * (0.5 + aSeed.y);
  float shell = 0.0;
  if (uPulse >= 0.0) {
    float shellRadius = uPulse * 2.4;
    float d = (r - shellRadius) * 4.5;
    shell = exp(-d * d) * (1.0 - uPulse);
  }
  p += dir * (breathe + wave * 0.06 + audioPush * r + shell * 0.22);
  p *= uExpansion;

  // 4. Torbellino: giro diferencial alrededor de Y y perfil de embudo.
  float radial = length(p.xz);
  float swirl = uVortexPhase * (0.6 + aSeed.z * 0.8) / (0.4 + radial);
  float cs = cos(swirl); float sn = sin(swirl);
  p.xz = mat2(cs, -sn, sn, cs) * p.xz;
  p.xz *= mix(1.0, 0.35 + 1.1 * smoothstep(-1.0, 1.0, p.y), uVortex);

  // 5. Vibración controlada (error).
  p += vec3(
    sin(uTime * 61.0 + aSeed.x * 40.0),
    sin(uTime * 53.0 + aSeed.y * 40.0),
    sin(uTime * 47.0 + aSeed.z * 40.0)
  ) * uJitter * 0.02;

  // 6. Explosión / reconstrucción: el mismo parámetro en ambos sentidos.
  p += dir * uExplosionProgress * (1.5 + aSeed.y * 3.5);
  p += (aSeed.xyz - 0.5) * uExplosionProgress * 1.2;

  // 7. Rotación del núcleo.
  float cy = cos(uRotation.x); float sy = sin(uRotation.x);
  p.xz = mat2(cy, -sy, sy, cy) * p.xz;
  float cx = cos(uRotation.y); float sx = sin(uRotation.y);
  p.yz = mat2(cx, -sx, sx, cx) * p.yz;
  float cz = cos(uRotation.z); float sz = sin(uRotation.z);
  p.xy = vec2(cz * p.x - sz * p.y, sz * p.x + cz * p.y);

  // 8. Punto de interacción (pinza): atrae las partículas cercanas.
  vec3 toPoint = uInteractionPoint - p;
  float pull = uInteractionStrength * exp(-dot(toPoint, toPoint) * 3.0);
  p += toPoint * pull * 0.6;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;

  float sparkle = 1.0 + uAudioTreble * aSeed.z * 0.9 + shell * 1.5 + pull * 1.2;
  gl_PointSize = clamp(uSize * aSize * sparkle * uScale / max(-mv.z, 0.1), 1.0, 72.0);

  vMix = clamp(r * 0.75 + aSeed.w * 0.35, 0.0, 1.0);
  vGlow = 1.0 + shell * 1.6 + uAudioLevel * 0.5 + uGestureStrength * 0.15 + pull;
  // Las partículas del fondo se atenúan: refuerza la sensación de profundidad.
  vAlpha = mix(0.35, 1.0, smoothstep(-6.5, -3.0, mv.z));
}
`;

export const particleFragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uBrightness;

varying float vMix;
varying float vGlow;
varying float vAlpha;

void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d = length(c);
  // Descarta las esquinas del sprite: nunca se ve el cuadrado del punto.
  if (d > 0.5) discard;

  float soft = smoothstep(0.5, 0.0, d);
  float core = exp(-d * d * 38.0);

  vec3 color = mix(uColorA, uColorB, vMix) + vec3(core * 0.55);
  float alpha = (soft * soft * 0.55 + core * 0.6) * vAlpha * uBrightness * vGlow;
  gl_FragColor = vec4(color, alpha);
}
`;

export const haloVertexShader = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

export const haloFragmentShader = /* glsl */ `
precision highp float;
uniform vec3 uColor;
uniform float uIntensity;
varying vec2 vUv;
void main() {
  float d = length(vUv - 0.5) * 2.0;
  float glow = pow(max(1.0 - d, 0.0), 2.6);
  gl_FragColor = vec4(uColor, glow * uIntensity);
}
`;
