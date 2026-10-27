import { useRef } from "react";
import { NUDGE, T_BASE } from "../motion";
import { AnimatePresence, m } from "motion/react";
import { Button } from "../ui/Button";
import { AlertTriangle, CheckCircle2, Clock, PackageCheck, PackageOpen, ShoppingBag, Truck, Warehouse, SlidersHorizontal, DatabaseZap, Lock } from "lucide-react";
import type { Route } from "../App";
import { CHANNELS, chanColor, chanVar, money, num, plural, STATE_TONE, stateColor, stateVar, when, usedUnits } from "../format";
import { useStore } from "../store";
import { axes, Card, CardHead, ChartBox, Kpi, Legend, Meter, Pill, Empty } from "../ui/kit";
import { AgentRunCard, OrderRow } from "./shared";

interface Attention { id: string; tone: "bad" | "warn" | "info"; icon: typeof AlertTriangle; title: string; detail?: string; action: string; to: Route; sku?: string }

export function Overview({ go }: { go: (r: Route, sku?: string) => void }) {
  const { s, events, fed, agent, runAgent, reset, busy } = useStore();
  const root = useRef<HTMLDivElement>(null);
  if (!s) return null;

  const T = s.totals;
  const sellable = s.skus.reduce((a, p) => a + (p.sellable_units ?? 0), 0);
  const inboundUnits = s.inbound.reduce((a, x) => a + x.qty, 0);
  const pending = events.filter((e) => e.status === "pending");

  const attention: Attention[] = [];
  const late = s.inbound.filter((x) => x.projected_date > x.arrival_date);
  if (pending.length) attention.push({ id: "approvals", tone: "warn", icon: SlidersHorizontal, title: `${plural(pending.length, "allocation change")} ${pending.length === 1 ? "needs" : "need"} your approval`, detail: pending.map((e) => e.sku).join(", "), action: "Review", to: "agent" });
  for (const p of [...s.skus].filter((p) => p.state === "Critical" || p.state === "Tight").sort((a, b) => (a.state === "Critical" ? -1 : 1) - (b.state === "Critical" ? -1 : 1)))
    attention.push({ id: `sku-${p.sku}`, tone: p.state === "Critical" ? "bad" : "warn", icon: AlertTriangle, title: `${p.title} is ${p.state?.toLowerCase()}`, detail: `${p.sku}, ${num(p.sellable_units)} sellable, ${p.days_of_cover ?? "—"} days of cover`, action: "View stock", to: "inventory", sku: p.sku });
  if (fed && !fed.ok)
    attention.push({ id: "zetaris", tone: "info", icon: DatabaseZap, title: "Zetaris is not connected", detail: "Agent runs and the live federated query need it.", action: "Data sources", to: "sources" });
  if (late.length)
    attention.push({ id: "late", tone: "info", icon: Truck, title: `${plural(late.length, "inbound line")} likely to arrive late`, detail: [...new Set(late.map((x) => `${x.po} (${x.supplier}, ${x.on_time_rate != null ? Math.round(x.on_time_rate * 100) + "% on time" : "no history"})`))].join(", "), action: "Inbound", to: "inventory" });
  for (const a of s.alerts.slice(0, 2))
    attention.push({ id: `al-${a.ts}-${a.sku}`, tone: "warn", icon: AlertTriangle, title: `${a.sku}: ${a.recommended_action}`, detail: `${a.problem}, ${a.deadline}`, action: "Inventory", to: "inventory" });
  if (T.status_counts.open + T.status_counts.partial > 0)
    attention.push({ id: "ship", tone: "info", icon: PackageOpen, title: `${plural(T.status_counts.open + T.status_counts.partial, "order")} waiting to ship`, detail: `${num(T.units_awaiting)} units reserved`, action: "Orders", to: "orders" });

  const margins = CHANNELS.map((c) => {
    const pcts = s.economics.filter((e) => e.channel === c).map((e) => {
      const pr = s.skus.find((p) => p.sku === e.sku)?.price;
      return pr ? Math.round((e.unit_margin / pr) * 100) : 0;
    }).filter((v) => v > 0);
    return pcts.length ? Math.round(pcts.reduce((a, b) => a + b, 0) / pcts.length) : 0;
  });

  return (
    <div ref={root} className="stack">
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>One stock pool across four sales channels. Data is read live through Zetaris; the agent decides how much each channel may sell.</p>
        </div>
      </div>

      <AgentRunCard job={agent} pending={pending.length} onRetry={runAgent} />

      {T.orders === 0 && (
        <Card>
          <Empty icon={ShoppingBag} title="No orders yet">
            Load the demo data to see four channels sharing one stock pool.
            <div style={{ marginTop: 12 }}><Button variant="secondary" onClick={reset} disabled={busy.reset}>{busy.reset ? "Loading..." : "Load demo data"}</Button></div>
          </Empty>
        </Card>
      )}

      <div className="kpis">
        <Kpi label="Total orders" icon={ShoppingBag} value={T.orders} hint={`${num(T.status_counts.open + T.status_counts.partial)} open`} />
        <Kpi label="Awaiting shipment" icon={Clock} value={T.units_awaiting} hint="units reserved" />
        <Kpi label="Units shipped" icon={PackageCheck} value={T.units_shipped} hint={`${num(T.units_cancelled)} cancelled`} />
        <Kpi label="Sellable stock" icon={Warehouse} value={sellable} hint={`across ${s.skus.length} SKUs`} />
        <Kpi label="Inbound units" icon={Truck} value={inboundUnits} hint={plural(s.inbound.length, "shipment")} />
      </div>

      <div className="grid g-main">
        <Card>
          <CardHead title="Needs attention" sub={attention.length ? plural(attention.length, "item") : "Nothing waiting on you"} />
          {attention.length ? (
            <div className="list" style={{ paddingTop: 8 }}>
              <AnimatePresence initial={false} mode="popLayout">
              {attention.slice(0, 7).map((a) => (
                <m.div layout className="row" key={a.id} initial={{ opacity: 0, y: NUDGE }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={T_BASE}>
                  <span style={{ color: `var(--${a.tone === "bad" ? "bad" : a.tone === "warn" ? "warn" : "info"})`, display: "grid" }}><a.icon size={18} aria-hidden /></span>
                  <div className="grow">
                    <div style={{ fontWeight: 500 }}>{a.title}</div>
                    {a.detail && <div className="meta">{a.detail}</div>}
                  </div>
                  <Button variant="tertiary" onClick={() => go(a.to, a.sku)}>{a.action}</Button>
                </m.div>
              ))}
              </AnimatePresence>
            </div>
          ) : <Empty icon={CheckCircle2} title="All clear">No approvals, stock risks or late shipments.</Empty>}
        </Card>
        <Card>
          <CardHead title="On hand per channel" sub="What each channel can still sell: allocation minus units used">
            <Legend items={CHANNELS.map((c) => ({ label: c, color: chanVar(c) }))} />
          </CardHead>
          <div className="card-body">
            <ChartBox label="On hand units per channel and SKU" deps={[JSON.stringify(s.skus.map((p) => [p.allocation, p.used_by_channel]))]} make={() => ({
              type: "bar",
              data: { labels: s.skus.map((p) => p.sku), datasets: CHANNELS.map((c) => ({ label: c, data: s.skus.map((p) => (p.allocation ? Math.max(0, (p.allocation[c] ?? 0) - usedUnits(p, c)) : 0)), backgroundColor: chanColor(c), borderRadius: 4, maxBarThickness: 28 })) },
              options: { scales: axes(false, "units") },
            })} />
          </div>
        </Card>
        <Card>
          <CardHead title="Margin by channel" sub="Average unit margin as % of price" />
          <div className="card-body">
            <ChartBox label="Profit margin percent by channel" deps={[margins.join()]} make={() => ({
              type: "bar",
              data: { labels: CHANNELS, datasets: [{ data: margins, backgroundColor: CHANNELS.map(chanColor), borderRadius: 6, maxBarThickness: 44 }] },
              options: { scales: { ...axes(), y: { ...axes().y, max: 100, ticks: { callback: (v) => `${v}%` } } }, plugins: { tooltip: { callbacks: { label: (c) => ` margin ${c.raw}%` } } } },
            })} />
          </div>
        </Card>
      </div>

      <section>
        <h2 className="section-title">Stock health</h2>
        <div className="grid g-4">
          {s.skus.map((p) => (
            <Card key={p.sku} className="card-pad">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{p.title}</div>
                  <div className="muted tiny mono">{p.sku}{p.price != null && `, ${money(p.price)}`}</div>
                </div>
                {p.state ? <Pill tone={STATE_TONE[p.state]}>{p.state}</Pill> : <Pill>no run yet</Pill>}
              </div>
              <div style={{ display: "flex", gap: 20, margin: "14px 0 12px" }}>
                <div><div className="tiny muted">Sellable</div><div className="num" style={{ fontSize: "var(--ds-t-figure)", fontWeight: 600 }}>{num(p.sellable_units)}</div></div>
                <div><div className="tiny muted">On hand</div><div className="num" style={{ fontSize: "var(--ds-t-figure)", fontWeight: 600 }}>{num(p.on_hand)}</div></div>
                <div><div className="tiny muted">Cover</div><div className="num" style={{ fontSize: "var(--ds-t-figure)", fontWeight: 600, color: stateVar(p.state) }}>{p.days_of_cover ?? "—"}<span className="tiny muted"> d</span></div></div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {p.allocation ? CHANNELS.map((c) => {
                  const a = p.allocation?.[c] ?? 0, o = usedUnits(p, c);
                  return (
                    <div className="alloc-row" key={c}>
                      <span style={{ color: "var(--label-2)" }}>{c}</span>
                      <Meter pct={a ? (o / a) * 100 : 0} color={chanVar(c)} label={`${c}: ${o} used of ${a} allocated`} />
                      <span className="v">{o}/{a}</span>
                    </div>
                  );
                }) : <span className="muted small">No allocation yet</span>}
              </div>
              {p.locked && <div className="tiny muted" style={{ marginTop: 10, display: "flex", gap: 4, alignItems: "center" }}><Lock size={12} aria-hidden />Locked by business rules</div>}
            </Card>
          ))}
        </div>
      </section>

      <div className="grid g-2">
        <Card>
          <CardHead title="Open units by channel" sub="Units still to ship, per SKU">
            <Legend items={CHANNELS.map((c) => ({ label: c, color: chanVar(c) }))} />
          </CardHead>
          <div className="card-body">
            <ChartBox label="Open units by channel and SKU" deps={[JSON.stringify(s.skus.map((p) => p.open_by_channel))]} make={() => ({
              type: "bar",
              data: { labels: s.skus.map((p) => p.sku), datasets: CHANNELS.map((c) => ({ label: c, data: s.skus.map((p) => p.open_by_channel[c] ?? 0), backgroundColor: chanColor(c), stack: "o", borderRadius: 4, maxBarThickness: 40 })) },
              options: { scales: axes(true) },
            })} />
          </div>
        </Card>
        <Card>
          <CardHead title="Order status mix" sub="All orders, in units" />
          <div className="card-body">
            <ChartBox label="Order status mix in units" deps={[T.units_awaiting, T.units_shipped, T.units_cancelled]} make={() => ({
              type: "doughnut",
              data: { labels: ["Awaiting shipment", "Shipped", "Cancelled"], datasets: [{ data: [T.units_awaiting, T.units_shipped, T.units_cancelled], backgroundColor: [chanColor("Amazon"), stateColor("Abundant"), stateColor("Critical")], borderWidth: 0 }] },
              options: { cutout: "68%", plugins: { legend: { display: true, position: "right", labels: { usePointStyle: true, pointStyle: "circle", padding: 14 } } } },
            })} />
          </div>
        </Card>
      </div>

      <Card>
        <CardHead title="Recent orders" sub={`Latest 10 of ${num(T.orders)}`}>
          <Button variant="tertiary" onClick={() => go("orders")}>All orders</Button>
        </CardHead>
        <div className="list" style={{ paddingTop: 8 }}>
          {s.orders.slice(0, 10).map((o) => <OrderRow key={o.id} o={o} />)}
          {!s.orders.length && <Empty icon={ShoppingBag} title="No orders yet">Place one from Storefronts, or load Scenario 1.</Empty>}
        </div>
      </Card>
      <p className="tiny muted" style={{ textAlign: "center", margin: 0 }}>Last updated {when(new Date().toISOString())}, refreshes every 10 seconds</p>
    </div>
  );
}

