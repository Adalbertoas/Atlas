// ATLAS Fase 5B — pase de skinning en GPU.
// Un texel por partícula. Cada partícula guarda los 3 vértices de su triángulo y sus baricéntricas;
// el shader deforma esos 3 vértices con los huesos reales del GLB (misma fórmula LBS que
// THREE.SkinnedMesh: bindMatrixInverse · Σ wᵢ · boneMatrixᵢ · bindMatrix · v) y los interpola.
// MODE 0 → posición mundial (xyz) + región (w).  MODE 1 → normal del triángulo deformado (xyz) + semilla (w).

export const skinVertexShader = /* glsl */`
void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

export const skinFragmentShader = /* glsl */`
precision highp float;
precision highp int;
precision highp sampler2D;

uniform sampler2D boneTexture;     // THREE.Skeleton.boneTexture (4 texels por hueso)
uniform sampler2D tVertPos;        // posición de reposo (espacio de la malla)
uniform sampler2D tVertSkinIndex;  // 4 índices de hueso
uniform sampler2D tVertSkinWeight; // 4 pesos (normalizados por GLTFLoader)
uniform sampler2D tPartTri;        // i0, i1, i2, región
uniform sampler2D tPartBary;       // u (peso de i1), v (peso de i2), semilla, 0
uniform mat4 bindMatrix;
uniform mat4 bindMatrixInverse;
uniform mat4 meshMatrixWorld;
uniform int vertWidth;
uniform int mode;

out vec4 outColor;

mat4 boneMatrix(float fi) {
  int j = int(fi + 0.5) * 4;
  int size = textureSize(boneTexture, 0).x;
  int x = j % size;
  int y = j / size;
  return mat4(texelFetch(boneTexture, ivec2(x, y), 0), texelFetch(boneTexture, ivec2(x + 1, y), 0),
              texelFetch(boneTexture, ivec2(x + 2, y), 0), texelFetch(boneTexture, ivec2(x + 3, y), 0));
}

vec3 skinVertex(float fv) {
  int i = int(fv + 0.5);
  ivec2 c = ivec2(i % vertWidth, i / vertWidth);
  vec3 p = texelFetch(tVertPos, c, 0).xyz;
  vec4 si = texelFetch(tVertSkinIndex, c, 0);
  vec4 sw = texelFetch(tVertSkinWeight, c, 0);
  vec4 sv = bindMatrix * vec4(p, 1.0);
  vec4 s = boneMatrix(si.x) * sv * sw.x + boneMatrix(si.y) * sv * sw.y
         + boneMatrix(si.z) * sv * sw.z + boneMatrix(si.w) * sv * sw.w;
  return (meshMatrixWorld * (bindMatrixInverse * s)).xyz;
}

void main() {
  ivec2 pc = ivec2(gl_FragCoord.xy);
  vec4 tri = texelFetch(tPartTri, pc, 0);
  vec4 b = texelFetch(tPartBary, pc, 0);
  vec3 a = skinVertex(tri.x);
  vec3 bb = skinVertex(tri.y);
  vec3 c = skinVertex(tri.z);
  if (mode == 0) {
    float w = 1.0 - b.x - b.y;
    outColor = vec4(a * w + bb * b.x + c * b.y, tri.w);
  } else {
    vec3 n = cross(bb - a, c - a);
    float l = length(n);
    outColor = vec4(l > 0.0 ? n / l : vec3(0.0, 1.0, 0.0), b.z);
  }
}
`;
