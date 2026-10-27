import type { Scene } from "./hero-types";

/** Static still of the hero object: shown first, and instead of the WebGL scene on low-power devices and with reduced motion. */
export function Poster({ accent }: { scene: Scene; accent: string }) {
  const dots = Array.from({ length: 150 }, (_, i) => {
    const y = 1 - (i / 149) * 2, r = Math.sqrt(1 - y * y), t = i * 2.39996;
    return { x: 200 + Math.cos(t) * r * 74, y: 200 + y * 74, z: Math.sin(t) };
  });
  const rings = [[96, 28, -0.4, 0.62], [116, 34, -0.2, 0.5], [136, 40, 0, 0.18], [156, 46, 0.2, 0.34]];
  return (
    <svg viewBox="0 0 400 400" aria-hidden="true">
      {rings.map(([rx, ry, rot, lit], i) => (
        <g key={i} transform={`rotate(${rot * 57 + i * 24} 200 200)`}>
          <ellipse cx="200" cy="200" rx={rx * 1.2} ry={ry * 1.5} fill="none" stroke="#2a3038" strokeWidth="1.5" />
          <ellipse cx="200" cy="200" rx={rx * 1.2} ry={ry * 1.5} fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" pathLength="100" strokeDasharray={`${lit * 100} 100`} />
        </g>
      ))}
      {dots.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r="1.6" fill={d.z > 0 ? accent : "#5b6672"} opacity={d.z > 0 ? 0.85 : 0.35} />)}
    </svg>
  );
}
