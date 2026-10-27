import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Color, Float32BufferAttribute, BufferGeometry, MathUtils, ShaderMaterial, TorusGeometry, type Group, type Mesh } from "three";
import { MESH_VERT, RIM_FN } from "./glsl";
import type { SceneProps } from "./hero-types";

/** The stock pool is a sphere of points; each sales channel is a ring around it, lit for the share of stock that channel may sell.
 *  Scrolling widens the rings and lengthens the lit arcs. */
const LOOP = 30; // seconds for one idle turn
const RADII = [1.25, 1.5, 1.75, 2.0];
const DEMO_CAPS = [44, 33, 7, 16];
const POINTS = 3800;

const POOL_VERT = /* glsl */ `
uniform float uTime;
uniform float uPx;
varying float vRim;
varying float vFace;
void main() {
  vec3 p = position;
  float w = sin(p.y * 4.0 + uTime * 0.6) * 0.5 + sin(p.x * 5.0 - uTime * 0.45) * 0.5;
  p *= 0.95 * (1.0 + 0.025 * w);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vec3 n = normalize(normalMatrix * position);
  float f = dot(n, normalize(-mv.xyz));
  vRim = pow(1.0 - max(f, 0.0), 2.0);
  vFace = 0.5 + 0.5 * f;
  gl_PointSize = 17.0 * uPx / -mv.z;
  gl_Position = projectionMatrix * mv;
}`;
const POOL_FRAG = /* glsl */ `
uniform vec3 uBase;
uniform vec3 uAccent;
varying float vRim;
varying float vFace;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  float a = smoothstep(0.5, 0.15, d);
  vec3 col = mix(uBase, uAccent, 0.25 + vRim * 0.75);
  gl_FragColor = vec4(col, a * mix(0.28, 1.0, vFace));
  #include <colorspace_fragment>
}`;
const RING_FRAG = /* glsl */ `
uniform float uCap;
uniform float uSpin;
uniform vec3 uAccent;
uniform vec3 uDim;
varying vec3 vNormal;
varying vec3 vView;
varying vec2 vUv;
${RIM_FN}
void main() {
  float t = fract(vUv.x - uSpin);
  float lit = step(t, uCap);
  float head = smoothstep(uCap - 0.07, uCap, t) * lit;
  vec3 col = mix(uDim, uAccent * 0.8, lit);
  col += uAccent * head * 0.7;
  col += uAccent * rim(vNormal, vView, 2.0) * 0.2 * lit;
  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`;

const fibonacci = (n: number) => {
  const a = new Float32Array(n * 3);
  const g = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), t = g * i;
    a[i * 3] = Math.cos(t) * r; a[i * 3 + 1] = y; a[i * 3 + 2] = Math.sin(t) * r;
  }
  return a;
};

export function HeroScene({ accent, data, progress, pointer }: SceneProps) {
  const group = useRef<Group>(null);
  const rings = useRef<(Mesh | null)[]>([]);
  const caps = useMemo(() => {
    const c = data?.length === 4 ? data : DEMO_CAPS;
    const max = Math.max(1, ...c);
    return c.map((v) => 0.16 + 0.74 * (v / max));
  }, [data]);

  const pool = useMemo(() => {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(fibonacci(POINTS), 3));
    const material = new ShaderMaterial({
      vertexShader: POOL_VERT, fragmentShader: POOL_FRAG, transparent: true, depthWrite: false,
      uniforms: { uTime: { value: 0 }, uPx: { value: 1 }, uBase: { value: new Color("#5b6672") }, uAccent: { value: new Color(accent) } },
    });
    return { geometry, material };
  }, [accent]);

  const ring = useMemo(() => RADII.map((r) => ({
    geometry: new TorusGeometry(r, 0.014, 10, 240),
    material: new ShaderMaterial({
      vertexShader: MESH_VERT, fragmentShader: RING_FRAG,
      uniforms: { uCap: { value: 0 }, uSpin: { value: 0 }, uAccent: { value: new Color(accent) }, uDim: { value: new Color("#2a3038") } },
    }),
  })), [accent]);

  useFrame((state, dt) => {
    const g = group.current;
    if (!g) return;
    const t = state.clock.elapsedTime, p = progress.get(), px = pointer.current.x, py = pointer.current.y;
    pool.material.uniforms.uTime.value = t;
    pool.material.uniforms.uPx.value = state.gl.getPixelRatio();
    g.rotation.y = (t / LOOP) * Math.PI * 2 + px * 0.25;
    g.rotation.x = MathUtils.damp(g.rotation.x, 0.3 + py * 0.18, 4, dt);
    g.position.x = MathUtils.damp(g.position.x, px * 0.18, 4, dt);
    g.position.y = MathUtils.damp(g.position.y, py * 0.12, 4, dt);
    ring.forEach((r, i) => {
      r.material.uniforms.uCap.value = caps[i] * (0.55 + 0.45 * p);
      r.material.uniforms.uSpin.value = (t / LOOP) * (0.6 + i * 0.25);
      rings.current[i]?.scale.setScalar(1 + p * 0.16 * (i + 1) / 4);
    });
  });

  return (
    <group ref={group}>
      <points geometry={pool.geometry} material={pool.material} />
      {ring.map((r, i) => (
        <mesh key={i} ref={(el) => { rings.current[i] = el; }} geometry={r.geometry} material={r.material} rotation={[1.1 + i * 0.22, i * 0.5, i * 0.35]} />
      ))}
    </group>
  );
}
