import { useRef, useState } from "react";
import { NUDGE, T_BASE } from "../motion";
import { AnimatePresence, m } from "motion/react";
import { Button } from "../ui/Button";
import { Check, ChevronDown, SlidersHorizontal, X, TrendingDown, TrendingUp } from "lucide-react";
import type { AgentEvent } from "../api";
import { chanColor, money, when } from "../format";
import { useStore } from "../store";
import { Card, CardHead, ChanTag, ChartBox, Empty, Pill, Segmented, Spinner } from "../ui/kit";
import { AgentRunCard } from "./shared";

type Group = "all" | "Auto-apply" | "Needs approval" | "Approved" | "Denied" | "Stock sync";
const group = (e: AgentEvent): Exclude<Group, "all"> =>
  ({ pending: "Needs approval", approved: "Approved", denied: "Denied" } as const)[e.status as "pending"] ?? (e.stock_sync ? "Stock sync" : "Auto-apply");

export function Agent() {
  const { s, events, savings, agent, runAgent } = useStore();
  const [filter, setFilter] = useState<Group>("all");
  const root = useRef<HTMLDivElement>(null);
  if (!s) return null;

  const groups: Exclude<Group, "all">[] = ["Auto-apply", "Needs approval", "Approved", "Denied", "Stock sync"];
  const rows = events.filter((e) => filter === "all" || group(e) === filter);

  return (
    <div ref={root} className="stack">
      <div className="page-head">
        <div>
          <h1>Smart Allocation</h1>
          <p>The allocation agent reads every source through Zetaris, scores each channel, and moves caps within guardrails. Big or risky moves wait for you.</p>
        </div>
      </div>

      <AgentRunCard job={agent} pending={events.filter((e) => e.status === "pending").length} onRetry={runAgent} />

      <div className="grid g-2">
        <SavingsCard total={savings?.total ?? 0} count={savings?.count ?? 0} bySku={savings?.by_sku ?? {}}
          pending={events.filter((e) => e.status === "pending").reduce((a, e) => a + (e.net_savings || 0), 0)} />
        <ScoreCard />
      </div>

      <Card>
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

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h2 className="section-title" style={{ margin: 0 }}>Decisions</h2>
        <Segmented<Group> label="Filter decisions" value={filter} onChange={setFilter}
          options={[{ value: "all", label: "All", count: events.length }, ...groups.map((g) => ({ value: g, label: g, count: events.filter((e) => group(e) === g).length }))]} />
      </div>

      <div className="stack" style={{ gap: 16 }}>
        <AnimatePresence initial={false} mode="popLayout">
          {rows.map((e) => <m.div key={e.id} layout initial={{ opacity: 0, y: NUDGE }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={T_BASE}><EventCard e={e} /></m.div>)}
        </AnimatePresence>
        {!rows.length && (
          <Card><Empty icon={SlidersHorizontal} title={events.length ? "No decisions in this group" : "No agent decisions yet"}>
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
  const tone = g === "Needs approval" ? "warn" : g === "Approved" || g === "Auto-apply" ? "ok" : g === "Denied" ? "bad" : "info";
  const why = Array.isArray(e.why) ? e.why : [e.why];
  return (
    <Card style={g === "Needs approval" ? { borderColor: "var(--warn)", boxShadow: "0 0 0 3px var(--warn-bg)" } : undefined}>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <h2 style={{ fontSize: "var(--ds-t-heading)" }}>{e.sku}</h2>
          <Pill tone={tone}>{e.approval}</Pill>
          {e.channels.map((c) => <ChanTag key={c.channel} name={c.channel} />)}
        </div>
        <span className="tiny muted">{when(e.ts)}</span>
      </div>
      <div className="card-body stack" style={{ gap: 16 }}>
        {e.stock_sync ? (
          <div className="card-pad" style={{ background: "var(--fill)", borderRadius: 12, padding: 14 }}>
            <div style={{ fontWeight: 600 }}>Stock sync: no reallocation decision</div>
            <div className="small muted" style={{ marginTop: 4 }}>Stock was sold or committed, so channel limits were trimmed to match what is actually available. Nothing moved between channels: the removed units no longer exist to sell.</div>
          </div>
        ) : (
        <div className="grid g-3" style={{ gap: 12 }}>
          <div className="card-pad" style={{ background: "var(--fill)", borderRadius: 12, padding: 14 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>Without this change</div>
            <div className="small" style={{ margin: "6px 0" }}>{e.without_change.lines.map((l) => <div key={l}>{l}</div>)}</div>
            <div className="num" style={{ fontSize: "var(--ds-t-figure)", fontWeight: 600 }}>{money(e.without_change.total)}</div>
          </div>
          <div className="card-pad" style={{ background: "var(--fill)", borderRadius: 12, padding: 14 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>With this change</div>
            <div className="small" style={{ margin: "6px 0" }}>{e.with_change.lines.map((l) => <div key={l}>{l}</div>)}</div>
            <div className="num" style={{ fontSize: "var(--ds-t-figure)", fontWeight: 600 }}>{money(e.with_change.total)}</div>
          </div>
          <div className="card-pad" style={{ background: e.net_savings >= 0 ? "var(--ok-bg)" : "var(--bad-bg)", borderRadius: 12, padding: 14 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>Projected savings</div>
            <div className="num" style={{ fontSize: "var(--ds-t-metric)", fontWeight: 700, color: e.net_savings >= 0 ? "var(--ok)" : "var(--bad)", marginTop: 6 }}>
              {e.net_savings >= 0 ? "+" : "−"}{money(Math.abs(e.net_savings))}
            </div>
            <div className="tiny muted">assumes the units sell on whichever channel gets them</div>
          </div>
        </div>
        )}

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
                  <div className="grow num" style={{ fontSize: "var(--ds-t-heading)", fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                    {c.cap_from} <span className="muted">to</span> {c.cap_to}
                    <span className={`pill ${d > 0 ? "ok" : "bad"}`}>{d > 0 ? "+" : ""}{d}</span>
                  </div>
                  <span className="small muted">{c.savings}</span>
                  <Button variant="tertiary" aria-expanded={!!open[k]} aria-controls={`calc-${k}`} onClick={() => setOpen((o) => ({ ...o, [k]: !o[k] }))}>
                    How it's calculated<ChevronDown size={14} style={{ transform: open[k] ? "rotate(180deg)" : undefined, transition: "transform .2s" }} aria-hidden />
                  </Button>
                </div>
                {open[k] && <div id={`calc-${k}`} className="small muted" style={{ padding: "0 20px 12px 128px" }}>{c.calc.map((l) => <div key={l}>{l}</div>)}</div>}
              </div>
            );
          })}
        </div>

        {e.status === "pending" && e.approval_id && (
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <Button variant="secondary" disabled={working} onClick={async () => { setWorking(true); await approve(e.approval_id!); setWorking(false); }}>{working ? <Spinner /> : <Check size={15} aria-hidden />}Approve</Button>
            <Button variant="secondary" danger disabled={working} onClick={() => deny(e.approval_id!)}><X size={15} aria-hidden />Deny</Button>
            <span className="small muted">Nothing is written until you approve. Your decision applies the whole {e.sku} proposal.</span>
          </div>
        )}
        {e.status === "approved" && <div className="small" style={{ color: "var(--ok)", fontWeight: 600 }}>Approved{e.approved_ts ? ` ${when(e.approved_ts)}` : ""}: allocation written</div>}
        {e.status === "denied" && <div className="small" style={{ color: "var(--bad)", fontWeight: 600 }}>Denied{e.approved_ts ? ` ${when(e.approved_ts)}` : ""}{e.deny_reason ? `: ${e.deny_reason}` : ""}. The agent sees this reason on its next run.</div>}
      </div>
    </Card>
  );
}

/** Projected savings of the allocations in force: one figure per SKU from its latest applied change. */
function SavingsCard({ total, count, bySku, pending }: { total: number; count: number; bySku: Record<string, number>; pending: number }) {
  const rows = Object.entries(bySku);
  return (
    <Card>
      <CardHead title="Overall savings from smart allocation" sub={`From ${count} applied change${count === 1 ? "" : "s"} now in force`} />
      <div className="card-body" style={{ display: "flex", gap: 32, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          <div className="num" style={{ fontSize: "var(--ds-t-metric)", fontWeight: 700, color: "var(--ok)", lineHeight: 1.1 }}>+{money(total)}</div>
          {pending > 0 && <div className="small" style={{ color: "var(--warn)", marginTop: 6 }}>+{money(pending)} more awaiting approval</div>}
        </div>
        <div className="grow" style={{ minWidth: 220 }}>
          {rows.length ? rows.map(([sku, v]) => (
            <div key={sku} className="small" style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderTop: "1px solid var(--separator)" }}>
              <span className="mono">{sku}</span><b style={{ color: "var(--ok)" }}>+{money(v)}</b>
            </div>
          )) : <div className="small muted">No profitable reallocation applied yet.</div>}
        </div>
      </div>
    </Card>
  );
}

/** How a channel's score is built, worked through for the first SKU (as on the IMS Smart Allocation tab). */
function ScoreCard() {
  const { s } = useStore();
  if (!s) return null;
  const sku = s.skus[0]?.sku;
  const rows = s.economics.filter((r) => r.sku === sku)
    .map((r) => ({ c: r.channel, m: r.unit_margin, d: r.demand_confidence, score: +(r.unit_margin * r.demand_confidence).toFixed(1) }))
    .sort((a, b) => b.score - a.score);
  return (
    <Card>
      <CardHead title="How the score is calculated" sub="score = unit margin × demand confidence" />
      <div className="card-body small">
        <div className="muted" style={{ marginBottom: 6 }}>{sku} example</div>
        {rows.map((r, i) => (
          <div key={r.c} className="num" style={{ display: "grid", gridTemplateColumns: "84px 1fr 32px", gap: 8, padding: "3px 0" }}>
            <span style={{ color: chanColor(r.c), fontWeight: 600 }}>{r.c}</span>
            <span>${r.m} × {r.d} = <b>{r.score}</b></span>
            <span style={{ color: chanColor(r.c) }}>#{i + 1}</span>
          </div>
        ))}
        <p className="muted" style={{ margin: "10px 0 0" }}>A channel's score is its profit per unit multiplied by how reliably it sells. High margin with weak demand scores low, and the reverse too: the product of both decides who gets stock first.</p>
      </div>
    </Card>
  );
}
