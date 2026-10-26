import { useRef, useState } from "react";
import { Check, ChevronDown, Sparkles, X, TrendingDown, TrendingUp } from "lucide-react";
import type { AgentEvent } from "../api";
import { chanColor, money, when } from "../format";
import { useStore } from "../store";
import { Card, CardHead, ChanTag, ChartBox, Empty, Pill, Segmented, Spinner } from "../ui/kit";
import { enter, useGSAP } from "../motion";
import { AgentRunCard } from "./shared";

type Group = "all" | "Auto-apply" | "Needs approval" | "Approved" | "Denied";
const group = (e: AgentEvent): Exclude<Group, "all"> => ({ pending: "Needs approval", approved: "Approved", denied: "Denied" } as const)[e.status as "pending"] ?? "Auto-apply";

export function Agent() {
  const { s, events, agent, runAgent } = useStore();
  const [filter, setFilter] = useState<Group>("all");
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => enter(".reveal"), { scope: root });
  if (!s) return null;

  const groups: Exclude<Group, "all">[] = ["Auto-apply", "Needs approval", "Approved", "Denied"];
  const rows = events.filter((e) => filter === "all" || group(e) === filter);

  return (
    <div ref={root} className="stack">
      <div className="page-head reveal">
        <div>
          <h1>Agent</h1>
          <p>The allocation agent reads every source through Zetaris, scores each channel, and moves caps within guardrails. Big or risky moves wait for you.</p>
        </div>
      </div>

      <AgentRunCard job={agent} pending={events.filter((e) => e.status === "pending").length} onRetry={runAgent} />

      <Card className="reveal">
        <CardHead title="How channels are ranked" sub="Score = unit margin × demand confidence. Higher scores get stock first." />
        <div className="card-body grid g-4" style={{ gap: 20 }}>
          {s.skus.map((p) => {
            const ev = events.find((e) => e.sku === p.sku);
            const chans = (ev ? ev.channels.map((c) => ({ channel: c.channel, conf: c.conf, margin: c.margin, score: c.score }))
              : s.economics.filter((r) => r.sku === p.sku).map((r) => ({ channel: r.channel, conf: r.demand_confidence, margin: r.unit_margin, score: +(r.unit_margin * r.demand_confidence).toFixed(1) })))
              .sort((a, b) => b.score - a.score);
            const xs = chans.map((c) => c.conf);
            return (
              <div key={p.sku}>
                <div style={{ fontWeight: 600 }}>{p.sku}</div>
                <div className="tiny" style={{ display: "flex", flexWrap: "wrap", gap: "2px 6px", margin: "2px 0 6px" }}>
                  {chans.map((c, i) => <span key={c.channel}><span className="muted">{i + 1}.</span> <span style={{ color: "var(--label)", fontWeight: 600 }}>{c.channel}</span>{i < chans.length - 1 && <span className="muted"> ›</span>}</span>)}
                </div>
                <ChartBox size="sm" label={`Channel ranking for ${p.sku}`} deps={[JSON.stringify(chans)]} make={() => ({
                  type: "scatter",
                  data: { datasets: [{ data: chans.map((c, i) => ({ x: c.conf, y: c.margin, c: c.channel, s: c.score, rank: i + 1 })), pointRadius: 7, pointHoverRadius: 9, backgroundColor: chans.map((c) => chanColor(c.channel)), borderColor: "transparent" }] },
                  options: {
                    layout: { padding: { right: 8 } },
                    scales: {
                      x: { min: xs.length ? Math.max(0, Math.floor(Math.min(...xs) * 10 - 1) / 10) : 0, max: xs.length ? Math.ceil(Math.max(...xs) * 10 + 2) / 10 : 1, title: { display: true, text: "demand confidence" }, border: { display: false } },
                      y: { title: { display: true, text: "margin $/unit" }, ticks: { callback: (v) => `$${v}` }, border: { display: false } },
                    },
                    plugins: { tooltip: { callbacks: { label: (pt) => { const r = pt.raw as { rank: number; c: string; y: number; x: number; s: number }; return ` #${r.rank} ${r.c}: margin $${r.y}, confidence ${r.x}, score ${r.s}`; } } } },
                  },
                })} />
              </div>
            );
          })}
        </div>
      </Card>

      <div className="reveal" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h2 className="section-title" style={{ margin: 0 }}>Decisions</h2>
        <Segmented<Group> label="Filter decisions" value={filter} onChange={setFilter}
          options={[{ value: "all", label: "All", count: events.length }, ...groups.map((g) => ({ value: g, label: g, count: events.filter((e) => group(e) === g).length }))]} />
      </div>

      <div className="stack reveal" style={{ gap: 16 }}>
        {rows.map((e) => <EventCard key={e.id} e={e} />)}
        {!rows.length && (
          <Card><Empty icon={Sparkles} title={events.length ? "No decisions in this group" : "No agent decisions yet"}>
            {events.length ? "Choose another filter." : "Run an allocation cycle. Every change the agent proposes or applies shows up here."}
          </Empty></Card>
        )}
      </div>
    </div>
  );
}

function EventCard({ e }: { e: AgentEvent }) {
  const { approve, deny } = useStore();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [working, setWorking] = useState(false);
  const g = group(e);
  const tone = g === "Needs approval" ? "warn" : g === "Approved" ? "ok" : g === "Denied" ? "bad" : "info";
  const why = Array.isArray(e.why) ? e.why : [e.why];
  return (
    <Card style={g === "Needs approval" ? { borderColor: "var(--warn)", boxShadow: "0 0 0 3px var(--warn-bg)" } : undefined}>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <h2 style={{ fontSize: 17 }}>{e.sku}</h2>
          <Pill tone={tone}>{e.approval}</Pill>
          {e.channels.map((c) => <ChanTag key={c.channel} name={c.channel} />)}
        </div>
        <span className="tiny muted">{when(e.ts)}</span>
      </div>
      <div className="card-body stack" style={{ gap: 16 }}>
        <div className="grid g-3" style={{ gap: 12 }}>
          <div className="card-pad" style={{ background: "var(--fill)", borderRadius: 12, padding: 14 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>Without this change</div>
            <div className="small" style={{ margin: "6px 0" }}>{e.without_change.lines.map((l) => <div key={l}>{l}</div>)}</div>
            <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>{money(e.without_change.total)}</div>
          </div>
          <div className="card-pad" style={{ background: "var(--fill)", borderRadius: 12, padding: 14 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>With this change</div>
            <div className="small" style={{ margin: "6px 0" }}>{e.with_change.lines.map((l) => <div key={l}>{l}</div>)}</div>
            <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>{money(e.with_change.total)}</div>
          </div>
          <div className="card-pad" style={{ background: e.net_savings >= 0 ? "var(--ok-bg)" : "var(--bad-bg)", borderRadius: 12, padding: 14 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>Projected savings</div>
            <div className="num" style={{ fontSize: 28, fontWeight: 700, color: e.net_savings >= 0 ? "var(--ok)" : "var(--bad)", marginTop: 6 }}>
              {e.net_savings >= 0 ? "+" : "−"}{money(Math.abs(e.net_savings))}
            </div>
            <div className="tiny muted">assumes the units sell on whichever channel gets them</div>
          </div>
        </div>

        <div>
          <div className="tiny muted" style={{ fontWeight: 600, marginBottom: 4 }}>Why this change</div>
          <ul style={{ margin: 0, paddingInlineStart: 18 }}>{why.map((b) => <li key={b} style={{ margin: "3px 0" }}>{b}</li>)}</ul>
        </div>

        {(e.moves.reduce.length > 0 || e.moves.add.length > 0) && (
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }} className="small">
            {e.moves.reduce.length > 0 && <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><TrendingDown size={15} style={{ color: "var(--bad)" }} aria-hidden /><b>Reduce</b> {e.moves.reduce.map((m) => `${m.channel} −${m.units}`).join(", ")}</span>}
            {e.moves.add.length > 0 && <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><TrendingUp size={15} style={{ color: "var(--ok)" }} aria-hidden /><b>Add</b> {e.moves.add.map((m) => `${m.channel} +${m.units}`).join(", ")}</span>}
          </div>
        )}

        <div style={{ border: "1px solid var(--separator)", borderRadius: 12 }}>
          {e.channels.map((c, i) => {
            const d = c.cap_to - c.cap_from, k = `${e.id}-${c.channel}`;
            return (
              <div key={c.channel} style={{ borderTop: i ? "1px solid var(--separator)" : 0 }}>
                <div className="row" style={{ borderTop: 0 }}>
                  <div style={{ width: 96 }}><ChanTag name={c.channel} /></div>
                  <div className="grow num" style={{ fontSize: 17, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                    {c.cap_from} <span className="muted">to</span> {c.cap_to}
                    <span className={`pill ${d > 0 ? "ok" : "bad"}`}>{d > 0 ? "+" : ""}{d}</span>
                  </div>
                  <span className="small muted">{c.savings}</span>
                  <button className="btn sm plain" aria-expanded={!!open[k]} aria-controls={`calc-${k}`} onClick={() => setOpen((o) => ({ ...o, [k]: !o[k] }))}>
                    How it's calculated<ChevronDown size={14} style={{ transform: open[k] ? "rotate(180deg)" : undefined, transition: "transform .2s" }} aria-hidden />
                  </button>
                </div>
                {open[k] && <div id={`calc-${k}`} className="small muted" style={{ padding: "0 20px 12px 128px" }}>{c.calc.map((l) => <div key={l}>{l}</div>)}</div>}
              </div>
            );
          })}
        </div>

        {e.status === "pending" && e.approval_id && (
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn primary" disabled={working} onClick={async () => { setWorking(true); await approve(e.approval_id!); setWorking(false); }}>{working ? <Spinner /> : <Check size={15} aria-hidden />}Approve</button>
            <button className="btn danger" disabled={working} onClick={() => deny(e.approval_id!)}><X size={15} aria-hidden />Deny</button>
            <span className="small muted">Nothing is written until you approve. Your decision applies the whole {e.sku} proposal.</span>
          </div>
        )}
        {e.status === "approved" && <div className="small" style={{ color: "var(--ok)", fontWeight: 600 }}>Approved{e.approved_ts ? ` ${when(e.approved_ts)}` : ""}: allocation written</div>}
        {e.status === "denied" && <div className="small" style={{ color: "var(--bad)", fontWeight: 600 }}>Denied{e.approved_ts ? ` ${when(e.approved_ts)}` : ""}{e.deny_reason ? `: ${e.deny_reason}` : ""}. The agent sees this reason on its next run.</div>}
      </div>
    </Card>
  );
}
