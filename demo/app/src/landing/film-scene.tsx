import { m, useTransform } from "motion/react";
import { lerp, useSeg, useVis, type P } from "./film-kit";

/** One allocation cycle, drawn as it happens. Chapters: read five systems into the stock pool, rank the channels, pour the pool into capped
 *  channels, hold a big move for approval. Every element below is a transform of the scroll progress `p`. */
export const CHAPTERS = [["Read every", "system."], ["Rank every", "channel."], ["Cap every", "unit."], ["You approve", "big moves."]];

const CHANNELS = ["DTC", "Amazon", "Etsy", "Walmart"];
const CAPS = [44, 33, 7, 16];
const SCORES = [21.6, 16, 10.4, 9];
const SOURCES = ["Warehouse", "Suppliers", "Analytics", "Rules", "Orders"];
const POOL = { x: 230, y: 290, r: 90 };
const BX = 520, BW = 290, BH = 92;
const by = (i: number) => 40 + i * 118;

// 100 stock units: where each sits in the pool, and which channel slot it ends in
const UNITS = (() => {
  const out: { from: [number, number]; to: [number, number] }[] = [];
  const g = Math.PI * (3 - Math.sqrt(5));
  const used = [0, 0, 0, 0];
  for (let j = 0; j < 100; j++) {
    const r = Math.sqrt((j + 0.5) / 100) * POOL.r, a = j * g;
    const bi = j < 44 ? 0 : j < 77 ? 1 : j < 84 ? 2 : 3;
    const k = used[bi]++;
    out.push({ from: [POOL.x + Math.cos(a) * r, POOL.y + Math.sin(a) * r], to: [BX + 16 + (k % 24) * 11, by(bi) + 56 + Math.floor(k / 24) * 11] });
  }
  return out;
})();

function Unit({ p, j }: { p: P; j: number }) {
  const u = UNITS[j];
  const appear = useSeg(p, j * 0.0012, j * 0.0012 + 0.04);
  const t = useSeg(p, 0.5 + j * 0.0014, 0.5 + j * 0.0014 + 0.12);
  const x = useTransform(t, (v) => lerp(u.from[0], u.to[0], v));
  const y = useTransform(t, (v) => lerp(u.from[1], u.to[1], v) - Math.sin(Math.PI * v) * 46);
  const o = useTransform(t, [0, 0.2], [0.5, 1]);
  const s = useTransform([appear, t], (v: number[]) => v[0] * (1 + Math.sin(Math.PI * v[1]) * 0.5));
  return <m.circle r="3.4" className="f-acc" style={{ x, y, scale: s, opacity: o }} />;
}

function Source({ p, k }: { p: P; k: number }) {
  const ang = ([-155, -125, -90, -55, -25][k] * Math.PI) / 180;
  const nx = POOL.x + Math.cos(ang) * 178, ny = POOL.y + Math.sin(ang) * 178;
  const px = POOL.x + Math.cos(ang) * (POOL.r + 4), py = POOL.y + Math.sin(ang) * (POOL.r + 4);
  const a = k * 0.022;
  const o = useSeg(p, a, a + 0.05);
  const line = useSeg(p, a + 0.02, a + 0.12);
  return (
    <m.g style={{ opacity: o }}>
      <m.path d={`M${nx} ${ny} L${px} ${py}`} className="f-link" style={{ pathLength: line }} />
      <circle cx={nx} cy={ny} r="5" className="f-acc" />
      <text x={nx} y={ny - 14} textAnchor="middle" className="f-t f-dim">{SOURCES[k]}</text>
    </m.g>
  );
}

function PoolLayer({ p }: { p: P }) {
  const src = useTransform(p, [0.24, 0.34], [1, 0]);
  const label = useVis(p, 0.0, 0.5, 0.05);
  return (
    <>
      <m.g style={{ opacity: src }}>{SOURCES.map((s, k) => <Source key={s} p={p} k={k} />)}</m.g>
      <m.text x={POOL.x} y="420" textAnchor="middle" className="f-t f-dim" style={{ opacity: label }}>100 units in stock, read through Zetaris</m.text>
    </>
  );
}

function Bucket({ p, i }: { p: P; i: number }) {
  const e = 0.25 + i * 0.012;
  const enter = useSeg(p, e, e + 0.08);
  const x = useTransform(enter, [0, 1], [90, 0]);
  const score = useTransform(p, [0.3, 0.46], [0, SCORES[i]]);
  const scoreText = useTransform(score, (v) => `score ${v.toFixed(1)}`);
  const scoreO = useTransform(p, [0.47, 0.52], [1, 0]);
  const rail = useSeg(p, 0.32, 0.46, 0, SCORES[i] / 21.6);
  const count = useTransform(p, [0.5, 0.74], [0, CAPS[i]]);
  const countText = useTransform(count, (v) => `${Math.round(v)} units`);
  const countO = useSeg(p, 0.5, 0.55);
  const hot = useSeg(p, 0.78, 0.86);
  const hotO = i === 0 || i === 2 ? hot : 0;
  return (
    <m.g style={{ opacity: enter, x }}>
      <rect x={BX} y={by(i)} width={BW} height={BH} rx="12" className="f-card" />
      <m.rect x={BX} y={by(i)} width={BW} height={BH} rx="12" className="f-acc-line" style={{ opacity: hotO }} />
      <text x={BX + 16} y={by(i) + 30} className="f-t f-bold">{CHANNELS[i]}</text>
      <m.text x={BX + BW - 16} y={by(i) + 30} textAnchor="end" className="f-t f-dim" style={{ opacity: scoreO }}>{scoreText}</m.text>
      <m.text x={BX + BW - 16} y={by(i) + 30} textAnchor="end" className="f-t f-acc-t f-bold" style={{ opacity: countO }}>{countText}</m.text>
      <m.rect x={BX + 16} y={by(i) + 40} width={BW - 32} height="5" rx="2.5" className="f-mute fl" style={{ scaleX: rail, opacity: scoreO }} />
    </m.g>
  );
}

function HoldLayer({ p }: { p: P }) {
  const arrow = useSeg(p, 0.77, 0.86);
  const head = useSeg(p, 0.85, 0.87);
  const card = useSeg(p, 0.82, 0.88);
  const cardY = useTransform(card, [0, 1], [60, 0]);
  const press = useTransform(p, [0.92, 0.935, 0.95], [1, 0.94, 1]);
  const approve = useSeg(p, 0.93, 0.95);
  const check = useSeg(p, 0.95, 0.98);
  const waiting = useTransform(p, [0.94, 0.96], [1, 0]);
  const done = useSeg(p, 0.97, 1);
  const ey = by(2) + 46, dy = by(0) + 46;
  return (
    <>
      <m.path d={`M${BX - 10} ${ey} C ${BX - 90} ${ey}, ${BX - 90} ${dy}, ${BX - 12} ${dy}`} className="f-link f-link-hot" style={{ pathLength: arrow }} />
      <m.path d={`M${BX - 22} ${dy - 8} L${BX - 10} ${dy} L${BX - 22} ${dy + 8}`} className="f-link f-link-hot" style={{ pathLength: head, opacity: head }} />
      <m.g style={{ opacity: card, y: cardY }}>
        <rect x="40" y="392" width="330" height="120" rx="14" className="f-card" />
        <text x="60" y="424" className="f-t f-bold">Move cap from Etsy to DTC</text>
        <text x="60" y="446" className="f-t f-dim">Over the 25% change limit</text>
        <m.g style={{ opacity: waiting }}><circle cx="300" cy="418" r="4" className="f-warn" /><text x="310" y="423" className="f-t f-dim">Waiting for you</text></m.g>
        <m.g style={{ scale: press }} className="fc">
          <rect x="60" y="464" width="112" height="36" rx="8" className="f-btn" />
          <m.rect x="60" y="464" width="112" height="36" rx="8" className="f-acc-fill" style={{ opacity: approve }} />
          <text x="116" y="487" textAnchor="middle" className="f-t f-bold">Approve</text>
        </m.g>
        <rect x="184" y="464" width="96" height="36" rx="8" className="f-btn f-btn-danger" />
        <text x="232" y="487" textAnchor="middle" className="f-t f-bold f-danger-t">Deny</text>
        <m.path d="M296 483 l8 9 l17 -19" className="f-check" style={{ pathLength: check, opacity: check }} />
        <m.text x="330" y="492" textAnchor="end" className="f-t f-dim" style={{ opacity: done }} />
      </m.g>
      <m.text x="60" y="376" className="f-t f-acc-t f-bold" style={{ opacity: done }}>Approved. Allocation written.</m.text>
    </>
  );
}

export function FilmScene({ p }: { p: P }) {
  return (
    <svg viewBox="0 0 840 540" className="film-svg" role="img" aria-label="One allocation cycle: five systems read into a stock pool, ranked, poured into capped channels, and a big move held for approval">
      <PoolLayer p={p} />
      {CHANNELS.map((c, i) => <Bucket key={c} p={p} i={i} />)}
      {UNITS.map((_, j) => <Unit key={j} p={p} j={j} />)}
      <HoldLayer p={p} />
    </svg>
  );
}
