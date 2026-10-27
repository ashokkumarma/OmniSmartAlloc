import { useRef } from "react";
import { Button } from "../ui/Button";
import type { Route } from "../App";
import { Warehouse, Lock, PackageCheck, Truck, Layers, Gauge, AlertTriangle, ClipboardList } from "lucide-react";
import { CHANNELS, chanColor, chanVar, num, plural, STATE_TONE, stateColor, when, usedUnits } from "../format";
import { useStore } from "../store";
import { axes, Card, CardHead, ChartBox, Empty, Kpi, Legend, Meter, Pill } from "../ui/kit";

export function Inventory({ go }: { go: (r: Route, sku?: string) => void }) {
  const { s } = useStore();
  const root = useRef<HTMLDivElement>(null);
  if (!s) return null;

  const onHand = s.skus.reduce((a, p) => a + p.on_hand, 0);
  const committed = s.skus.reduce((a, p) => a + p.committed, 0);
  const sellable = s.skus.reduce((a, p) => a + (p.sellable_units ?? 0), 0);
  const inbound = s.inbound.reduce((a, x) => a + x.qty, 0);
  const skuLabels = s.skus.map((p) => p.sku);

  return (
    <div ref={root} className="stack">
      <div className="page-head">
        <div>
          <h1>Inventory</h1>
          <p>One warehouse pool shared by every channel. Sellable stock is on hand minus committed; the agent caps how much each channel may sell.</p>
        </div>
      </div>

      <div className="kpis">
        <Kpi label="On hand" icon={Warehouse} value={onHand} hint="units in the warehouse" />
        <Kpi label="Reserved" icon={Lock} value={committed} hint="committed to open orders" />
        <Kpi label="Allocatable" icon={PackageCheck} value={sellable} hint="sellable now" />
        <Kpi label="Inbound units" icon={Truck} value={inbound} hint="pending delivery" />
        <Kpi label="Inbound shipments" icon={Layers} value={s.inbound.length} hint="purchase orders" />
      </div>

      <Card>
        <CardHead title="Stock by SKU" sub="On hand, reserved in open orders, and what each channel may still sell" />
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table className="table">
            <thead><tr><th>Product</th><th>State</th><th className="num">On hand</th><th>Reserved</th><th className="num">Allocatable</th><th className="num">Cover</th><th style={{ minWidth: 220 }}>Channel allocation <span className="muted">(used / allocated)</span></th></tr></thead>
            <tbody>
              {s.skus.map((p) => {
                const reserved = Object.values(p.open_by_channel).reduce((a, b) => a + b, 0);
                return (
                  <tr key={p.sku}>
                    <td>
                      <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}><Button variant="tertiary" onClick={() => go("inventory", p.sku)}>{p.title}</Button>{p.locked && <Lock size={13} aria-label="Locked by business rules" style={{ color: "var(--label-2)" }} />}</div>
                      <div className="tiny muted mono">{p.sku}</div>
                    </td>
                    <td>{p.state ? <Pill tone={STATE_TONE[p.state]}>{p.state}</Pill> : <span className="muted">—</span>}</td>
                    <td className="num"><b>{num(p.on_hand)}</b></td>
                    <td className="num">{num(p.committed)} <span className="tiny muted">({reserved} in open orders)</span></td>
                    <td className="num">{num(p.sellable_units)}</td>
                    <td className="num">{p.days_of_cover != null ? `${p.days_of_cover} d` : "—"}</td>
                    <td>
                      {p.allocation ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                          {CHANNELS.map((c) => {
                            const a = p.allocation?.[c] ?? 0, o = usedUnits(p, c);
                            return (
                              <div className="alloc-row" key={c}>
                                <span>{c}</span>
                                <Meter pct={a ? (o / a) * 100 : 0} color={chanVar(c)} label={`${c}: ${o} used of ${a} allocated`} />
                                <span className="v">{o}/{a}</span>
                              </div>
                            );
                          })}
                        </div>
                      ) : <span className="muted small">No allocation yet</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <CardHead title="Incoming inventory" sub="Inbound purchase orders, with arrival adjusted for each supplier's track record" />
        <div className="table-wrap" style={{ marginTop: 8 }}>
          {s.inbound.length ? (
            <table className="table">
              <thead><tr><th>PO</th><th>SKU</th><th className="num">Qty</th><th>Supplier</th><th>Status</th><th>Promised</th><th>Projected</th><th className="num">Supplier on time</th></tr></thead>
              <tbody>
                {s.inbound.map((x) => {
                  const late = x.projected_date > x.arrival_date;
                  return (
                    <tr key={x.po}>
                      <td className="mono small">{x.po}</td>
                      <td><b>{x.sku}</b></td>
                      <td className="num">{num(x.qty)}</td>
                      <td>{x.supplier}</td>
                      <td><Pill tone={x.status === "in_transit" ? "info" : undefined}>{x.status.replace("_", " ")}</Pill></td>
                      <td className="num">{x.arrival_date} <span className="tiny muted">({x.eta_days} d)</span></td>
                      <td className="num" style={late ? { color: "var(--warn)", fontWeight: 600 } : undefined}>
                        {x.projected_date}{late && <AlertTriangle size={13} aria-label="projected late" style={{ marginInlineStart: 6, verticalAlign: -2 }} />}
                      </td>
                      <td className="num">{x.on_time_rate != null ? `${Math.round(x.on_time_rate * 100)}%` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : <Empty icon={Truck} title="No inbound shipments" />}
        </div>
      </Card>

      <div className="grid g-2">
        <Card>
          <CardHead title="Allocation vs consumed" sub="Solid: allocated, light: used by orders since the allocation">
            <Legend items={CHANNELS.map((c) => ({ label: c, color: chanVar(c) }))} />
          </CardHead>
          <div className="card-body">
            <ChartBox size="lg" label="Allocation versus consumed units by SKU and channel" deps={[JSON.stringify(s.skus.map((p) => [p.allocation, p.used_by_channel]))]} make={() => ({
              type: "bar",
              data: {
                labels: skuLabels,
                datasets: [
                  ...CHANNELS.map((c) => ({ label: `${c} allocated`, data: s.skus.map((p) => p.allocation?.[c] ?? 0), backgroundColor: chanColor(c), stack: "a", borderRadius: 3, maxBarThickness: 36 })),
                  ...CHANNELS.map((c) => ({ label: `${c} used`, data: s.skus.map((p) => usedUnits(p, c)), backgroundColor: chanColor(c) + "4d", borderColor: chanColor(c), borderWidth: 1, stack: "c", borderRadius: 3, maxBarThickness: 36 })),
                ],
              },
              options: { scales: axes(true) },
            })} />
          </div>
        </Card>
        <Card>
          <CardHead title="Days of cover" sub="How long sellable stock lasts at current demand" />
          <div className="card-body">
            <ChartBox size="lg" label="Days of cover by SKU" deps={[s.skus.map((p) => `${p.days_of_cover}${p.state}`).join()]} make={() => ({
              type: "bar",
              data: { labels: skuLabels, datasets: [{ label: "Days of cover", data: s.skus.map((p) => p.days_of_cover ?? 0), backgroundColor: s.skus.map((p) => stateColor(p.state)), borderRadius: 6, maxBarThickness: 44 }] },
              options: { scales: axes() },
            })} />
          </div>
        </Card>
      </div>

      <Card>
        <CardHead title="Allocated units per channel" sub="The agent's latest cap for each channel">
          <Legend items={CHANNELS.map((c) => ({ label: c, color: chanVar(c) }))} />
        </CardHead>
        <div className="card-body">
          <ChartBox label="Allocated units per channel and SKU" deps={[JSON.stringify(s.skus.map((p) => p.allocation))]} make={() => ({
            type: "bar",
            data: { labels: skuLabels, datasets: CHANNELS.map((c) => ({ label: c, data: s.skus.map((p) => p.allocation?.[c] ?? 0), backgroundColor: chanColor(c), borderRadius: 4, barPercentage: 0.9, categoryPercentage: 0.6 })) },
            options: { scales: axes(false, "allocated units") },
          })} />
        </div>
      </Card>

      <Card>
        <CardHead title="Agent activity" sub={`${plural(s.alerts.length, "alert")}, ${plural(s.decisions.length, "decision")}`} />
        <div className="list" style={{ paddingTop: 8 }}>
          {s.alerts.slice(0, 6).map((a) => (
            <div className="row" key={`a${a.ts}${a.sku}`}>
              <AlertTriangle size={18} style={{ color: "var(--warn)" }} aria-hidden />
              <div className="grow">
                <div><b>{a.sku}</b>, {a.recommended_action}</div>
                <div className="meta">{a.problem}, {a.deadline}</div>
              </div>
              <span className="tiny muted">{when(a.ts)}</span>
            </div>
          ))}
          {s.decisions.slice(0, 6).map((d) => (
            <div className="row" key={`d${d.ts}${d.sku}`}>
              <ClipboardList size={18} style={{ color: "var(--accent)" }} aria-hidden />
              <div className="grow">
                <div><b>{d.sku}</b> {d.record.state && <>{d.record.state}</>}</div>
                <div className="meta">Allocated {Object.entries(d.record.allocation ?? {}).map(([c, n]) => `${c} ${n}`).join(", ") || "—"}</div>
              </div>
              <span className="tiny muted">{when(d.ts)}</span>
            </div>
          ))}
          {!s.alerts.length && !s.decisions.length && <Empty icon={Gauge} title="The agent has not run yet">Run an allocation cycle to see its alerts and decisions here.</Empty>}
          {s.agent.running && <div className="row muted small">The agent is running…</div>}
        </div>
      </Card>
    </div>
  );
}
