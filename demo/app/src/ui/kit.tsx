import { useEffect, useRef, useState, type ReactNode } from "react";
import { Minus, Plus, Loader2, type LucideIcon } from "lucide-react";
import { Chart, registerables, type ChartConfiguration } from "chart.js";
import { chanVar, cssColor } from "../format";
import { countTo, gsap, reducedMotion, useGSAP } from "../motion";

Chart.register(...registerables);

export function Card({ children, className = "", ...rest }: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLElement>) {
  return <section className={`card ${className}`} {...rest}>{children}</section>;
}

export function CardHead({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="card-head">
      <div>
        <h2>{title}</h2>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {children}
    </div>
  );
}

export function Pill({ tone, children, title }: { tone?: "ok" | "warn" | "bad" | "info"; children: ReactNode; title?: string }) {
  return <span className={`pill ${tone ?? ""}`} title={title}>{children}</span>;
}

export function ChanTag({ name, plain }: { name: string; plain?: boolean }) {
  return (
    <span className="chan" style={plain ? undefined : { color: chanVar(name) }}>
      <i style={{ background: chanVar(name) }} aria-hidden />
      <span style={plain ? undefined : { color: "var(--label)" }}>{name}</span>
    </span>
  );
}

const groupDigits = (n: number) => n.toLocaleString("en-US");

/** A KPI whose number counts up to each new value. */
export function Kpi({ label, value, format = groupDigits, hint, icon: Icon, onClick, pressed }: {
  label: string; value: number; format?: (n: number) => string; hint?: ReactNode; icon?: LucideIcon; onClick?: () => void; pressed?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const prev = useRef(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const tween = countTo(el, prev.current, value, format);
    prev.current = value;
    return () => {
      tween?.kill();
      el.textContent = format(value);
    };
  }, [value, format]);
  const body = (
    <>
      <div className="label">{Icon && <Icon size={14} aria-hidden />}{label}</div>
      <div className="value" ref={ref} aria-label={`${label}: ${format(value)}`}>{format(value)}</div>
      {hint && <div className="hint">{hint}</div>}
    </>
  );
  return onClick
    ? <button type="button" className="card kpi" onClick={onClick} aria-pressed={pressed}>{body}</button>
    : <div className="card kpi">{body}</div>;
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; count?: number }[]; label: string;
}) {
  return (
    <div className="segmented" role="tablist" aria-label={label}
      onKeyDown={(e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        const i = options.findIndex((o) => o.value === value);
        const next = options[(i + (e.key === "ArrowRight" ? 1 : options.length - 1)) % options.length];
        onChange(next.value);
        (e.currentTarget.querySelectorAll("button")[options.indexOf(next)] as HTMLButtonElement)?.focus();
      }}>
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} tabIndex={o.value === value ? 0 : -1} onClick={() => onChange(o.value)}>
          {o.label}{o.count !== undefined && <span className="n">{o.count.toLocaleString("en-US")}</span>}
        </button>
      ))}
    </div>
  );
}

export function Empty({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Icon size={28} aria-hidden />
      <b>{title}</b>
      {children}
    </div>
  );
}

/** A thin progress bar that grows in from the left once (transform only). */
export function Meter({ pct, color, label }: { pct: number; color: string; label?: string }) {
  const bar = useRef<HTMLElement>(null);
  useGSAP(() => {
    if (!reducedMotion()) gsap.from(bar.current, { scaleX: 0, duration: 0.7, ease: "power2.out" });
  }, []);
  const p = Math.max(0, Math.min(100, pct));
  return (
    <div className="meter" role="img" aria-label={label ?? `${Math.round(p)}%`}>
      <i ref={bar} style={{ width: `${p}%`, background: color }} />
    </div>
  );
}

export function Stepper({ value, min, max, onChange, label }: { value: number; min: number; max: number; onChange: (n: number) => void; label: string }) {
  const clamp = (n: number) => Math.max(min, Math.min(Math.max(min, max), n));
  return (
    <div className="stepper">
      <button type="button" onClick={() => onChange(clamp(value - 1))} aria-label={`Decrease ${label}`} disabled={value <= min}><Minus size={14} /></button>
      <input type="number" inputMode="numeric" value={value} min={min} max={max} aria-label={label}
        onChange={(e) => onChange(clamp(Math.round(Number(e.target.value) || min)))} />
      <button type="button" onClick={() => onChange(clamp(value + 1))} aria-label={`Increase ${label}`} disabled={value >= max}><Plus size={14} /></button>
    </div>
  );
}

export const Spinner = ({ size = 14 }: { size?: number }) => <Loader2 size={size} className="spin" aria-hidden />;

/** Re-render charts when the OS or the in-app switch changes light/dark, so their colours follow the theme. */
function useColorScheme() {
  const [n, setN] = useState(0);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setN((v) => v + 1);
    mq.addEventListener("change", on);
    window.addEventListener("themechange", on);
    return () => { mq.removeEventListener("change", on); window.removeEventListener("themechange", on); };
  }, []);
  return n;
}

/** Chart.js canvas. `make` builds the config; it re-runs when `deps` or the colour scheme change. */
export function ChartBox({ make, deps, size = "", label }: { make: () => ChartConfiguration; deps: unknown[]; size?: "" | "sm" | "lg"; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const dark = useColorScheme();
  useEffect(() => {
    const text = cssColor("--chart-text"), grid = cssColor("--chart-grid");
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
    Chart.defaults.color = text;
    Chart.defaults.borderColor = grid;
    const cfg = make();
    cfg.options = {
      responsive: true, maintainAspectRatio: false,
      animation: reducedMotion() ? false : { duration: 600, easing: "easeOutQuart" },
      ...cfg.options,
      plugins: { legend: { display: false }, ...cfg.options?.plugins,
        tooltip: { backgroundColor: cssColor("--surface"), titleColor: cssColor("--label"), bodyColor: cssColor("--label"), borderColor: grid, borderWidth: 1, padding: 10, cornerRadius: 8, boxPadding: 4, ...cfg.options?.plugins?.tooltip } },
    };
    const chart = new Chart(canvas.current!, cfg);
    return () => chart.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, dark]);
  return <div className={`chart-box ${size}`}><canvas ref={canvas} role="img" aria-label={label} /></div>;
}

/** Common bar-chart axes in the theme. */
export function axes(stacked = false, yTitle?: string) {
  return {
    x: { stacked, grid: { display: false }, border: { display: false } },
    y: { stacked, beginAtZero: true, grid: { color: cssColor("--chart-grid") }, border: { display: false }, ticks: { precision: 0 },
      title: yTitle ? { display: true, text: yTitle } : undefined },
  };
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="legend">
      {items.map((i) => <span key={i.label}><i style={{ background: i.color }} />{i.label}</span>)}
    </div>
  );
}

/** Placeholder with the Overview's layout while the first load runs. Pulses; no shimmer. */
export function PageSkeleton() {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading">
      <div><div className="sk" style={{ height: 30, width: 180 }} /><div className="sk" style={{ height: 14, width: "52%", marginTop: 12 }} /></div>
      <div className="kpis">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="card kpi"><div className="sk" style={{ height: 12, width: "55%" }} /><div className="sk" style={{ height: 28, width: "40%", marginTop: 12 }} /></div>)}</div>
      <div className="grid g-main"><div className="card sk-card" /><div className="card sk-card" /></div>
    </div>
  );
}
