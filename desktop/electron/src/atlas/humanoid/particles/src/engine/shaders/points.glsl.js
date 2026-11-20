// ATLAS Fase 5B — render de partículas.
// Lee posición y normal del pase de skinning (un texel por partícula, gl_VertexID → texel).
// Profundidad real: tamaño en mundo (mm) con perspectiva, borde (rim) más brillante, atenuación con la distancia
// y oclusión opcional contra la malla dibujada sólo en el buffer de profundidad.
// 5E: tinte por estado y onda de energía desde el núcleo (uEnergy*). Con los valores por defecto (uTintMix = 0,
// uEnergyAmp = 0) el resultado es idéntico al de la 5B.

export const pointsVertexShader = /* glsl */`
precision highp float;
precision highp int;
precision highp sampler2D;

uniform sampler2D tPos;
uniform sampler2D tNrm;
uniform int partWidth;
uniform float pointSize;     // metros
uniform float pixelScale;    // alto_px / (2·tan(fov/2))
uniform float depthBias;     // metros hacia la cámara (evita que la oclusión se coma la cara visible)
uniform float regionScale[5];
uniform float brightness;
uniform vec3 uTint;          // 5E
uniform float uTintMix;
uniform vec3 uEnergyOrigin;
uniform float uEnergyRadius;
uniform float uEnergyWidth;
uniform float uEnergyAmp;
uniform vec3 uEnergyColor;

out vec3 vColor;
out float vAlpha;

void main() {
  int id = gl_VertexID;
  ivec2 c = ivec2(id % partWidth, id / partWidth);
  vec4 p = texelFetch(tPos, c, 0);
  vec4 n = texelFetch(tNrm, c, 0);
  vec4 mv = viewMatrix * vec4(p.xyz, 1.0);
  vec3 viewDir = normalize(-mv.xyz);
  vec3 nv = normalize((viewMatrix * vec4(n.xyz, 0.0)).xyz);
  float ndv = dot(nv, viewDir);
  float rim = 1.0 - abs(ndv);
  mv.xyz += viewDir * depthBias;
  gl_Position = projectionMatrix * mv;

  float seed = n.w;
  int region = int(p.w + 0.5);
  float s = pointSize * regionScale[region] * (0.7 + 0.6 * fract(seed * 13.37));
  gl_PointSize = clamp(s * pixelScale / max(0.05, -mv.z), 1.0, 48.0);

  // Paleta azul eléctrico → cian; el borde y una parte de las partículas tiran a cian.
  vec3 deep = vec3(0.04, 0.32, 1.0);
  vec3 cyan = vec3(0.30, 0.92, 1.0);
  float t = clamp(rim * 0.85 + fract(seed * 7.13) * 0.35, 0.0, 1.0);
  vColor = mix(deep, cyan, t);
  vColor = mix(vColor, uTint * (0.55 + 0.6 * t), uTintMix);
  float de = distance(p.xyz, uEnergyOrigin) - uEnergyRadius;
  float energy = uEnergyAmp * exp(-de * de / (uEnergyWidth * uEnergyWidth));
  vColor += uEnergyColor * energy;
  float back = ndv < 0.0 ? 0.45 : 1.0;          // cara trasera más tenue (si no hay oclusión)
  float fog = smoothstep(9.0, 2.0, -mv.z);
  vAlpha = brightness * (0.35 + 0.65 * rim + 0.25 * fract(seed * 3.1)) * back * fog * (1.0 + energy);
}
`;

export const pointsFragmentShader = /* glsl */`
precision highp float;
in vec3 vColor;
in float vAlpha;
out vec4 outColor;
void main() {
  vec2 d = gl_PointCoord - vec2(0.5);
  float r2 = dot(d, d);
  if (r2 > 0.25) discard;
  float core = exp(-r2 * 30.0);
  float halo = exp(-r2 * 9.0) * 0.35;
  outColor = vec4(vColor * (core + halo) * vAlpha, 1.0);
}
`;
