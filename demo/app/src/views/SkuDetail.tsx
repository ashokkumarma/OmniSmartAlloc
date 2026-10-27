import { useRef } from "react";
import { Button } from "../ui/Button";
import { Lock, PackageCheck, Truck, Warehouse, Gauge, Boxes } from "lucide-react";
import type { Route } from "../App";
import { CHANNELS, chanVar, money, num, plural, STATE_TONE, when } from "../format";
import { useStore } from "../store";
import { Card, CardHead, ChanTag, Empty, Kpi, Meter, Pill } from "../ui/kit";
import { enter, useGSAP } from "../motion";
import { OrderRow } from "./shared";

/** One product: its stock, how much each channel may sell (cap rails), what is inbound and the orders that hold stock. */
export function SkuDetail({ sku, go }: { sku: string; go: (r: Route, sku?: string) => void }) {
  const { s } = useStore();
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => enter(".reveal"), { scope: root, dependencies: [sku] });
  if (!s) return null;

  const crumbs = (
    <nav className="crumbs" aria-label="Breadcrumb">
      <button onClick={() => go("inventory")}>Inventory</button>
      <span aria-hidden>/</span>
      <span aria-current="page" className="mono">{sku}</span>
    </nav>
  );
  const p = s.skus.find((x) => x.sku === sku);
  if (!p) {
    return (
      <div className="stack">
        {crumbs}
        <Card><Empty icon={Boxes} title={`No product with the SKU ${sku}`}><Button variant="secondary" style={{ marginTop: 12 }} onClick={() => go("inventory")}>Back to inventory</Button></Empty></Card>
      </div>
    );
  }

  const inbound = s.inbound.filter((x) => x.sku === sku);
  const orders = s.orders.filter((o) => o.sku === sku).sort((a, b) => b.ts.localeCompare(a.ts));
  const open = orders.filter((o) => o.status === "open" || o.status === "partial");
  const shown = open.length ? open.slice(0, 8) : orders.slice(0, 8);
  const alerts = [...new Map(s.alerts.filter((a) => a.sku === sku).reverse().map((a) => [a.recommended_action + a.problem, a])).values()].slice(0, 3);
  const decision = [...s.decisions].reverse().find((d) => d.sku === sku);
  const reserved = Object.values(p.open_by_channel).reduce((a, b) => a + b, 0);

  return (
    <div ref={root} className="stack">
      {crumbs}
      <div className="page-head reveal">
        <div>
          <h1>{p.title}</h1>
          <p className="mono" style={{ fontSize: "var(--t-footnote)" }}>
            {p.sku}{p.price != null && `  ${money(p.price)} per unit`}
          </p>
        </div>
        <div className="page-actions">
          {p.state && <Pill tone={STATE_TONE[p.state]}>{p.state}</Pill>}
          {p.locked && <Pill><Lock size={12} aria-hidden />Locked by business rules</Pill>}
        </div>
      </div>

      <div className="kpis four reveal">
        <Kpi label="On hand" icon={Warehouse} value={p.on_hand} hint="units in the warehouse" />
        <Kpi label="Reserved" icon={Lock} value={p.committed} hint={`${num(reserved)} in open orders`} />
        <Kpi label="Allocatable" icon={PackageCheck} value={p.sellable_units ?? 0} hint="sellable now" />
        <Kpi label="Days of cover" icon={Gauge} value={p.days_of_cover ?? 0} hint={p.days_of_cover == null ? "no sales history" : "at the 30-day rate"} />
      </div>

      <Card className="reveal">
        <CardHead title="What each channel may sell" sub="The bar is the cap the agent set. The filled part is already taken by open orders." />
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {p.allocation ? CHANNELS.map((c) => {
            const cap = p.allocation?.[c] ?? 0, taken = p.open_by_channel[c] ?? 0;
            const e = s.economics.find((x) => x.sku === sku && x.channel === c);
            return (
              <div key={c} className="cap-row">
                <ChanTag name={c} />
                <Meter pct={cap ? Math.min(100, (taken / cap) * 100) : 0} color={chanVar(c)} label={`${c}: ${taken} of ${cap} taken`} />
                <span className="num cap-n"><b>{taken}</b> of {cap}</span>
                <span className="tiny muted cap-e">{e ? `margin ${money(e.unit_margin)}, confidence ${Math.round(e.demand_confidence * 100)}%` : ""}</span>
              </div>
            );
          }) : <p className="muted" style={{ margin: 0 }}>No allocation yet. Run an allocation cycle to set a cap per channel.</p>}
        </div>
      </Card>

      <div className="grid g-2 reveal">
        <Card>
          <CardHead title="Inbound" sub={plural(inbound.length, "purchase order")} />
          {inbound.length ? (
            <div className="list" style={{ marginTop: 8 }}>
              {inbound.map((x) => (
                <div className="row" key={x.po}>
                  <div className="grow">
                    <div><b className="num">{num(x.qty)}</b> units from {x.supplier}</div>
                    <div className="meta"><span className="mono">{x.po}</span>, due {x.arrival_date}, projected {x.projected_date}</div>
                  </div>
                  <Pill tone={x.projected_date > x.arrival_date ? "warn" : x.status === "in_transit" ? "info" : undefined}>{x.projected_date > x.arrival_date ? "Late" : x.status.replace("_", " ")}</Pill>
                </div>
              ))}
            </div>
          ) : <Empty icon={Truck} title="Nothing inbound for this product" />}
        </Card>

        <Card>
          <CardHead title="Agent notes" sub={decision ? `Last decision ${when(decision.ts)}` : "No decision yet"} />
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {alerts.map((a) => (
              <div key={a.ts + a.problem}>
                <div><b>{a.recommended_action}</b></div>
                <div className="small muted">{a.problem}. {a.risk_of_inaction.replace(/\.?$/, ".")} Deadline: {a.deadline}.</div>
              </div>
            ))}
            {decision?.record.reasoning?.map((r, i) => <div key={i} className="small">{r}</div>)}
            {!alerts.length && !decision?.record.reasoning?.length && <p className="muted" style={{ margin: 0 }}>The agent has nothing to flag for this product.</p>}
          </div>
        </Card>
      </div>

      <Card className="reveal">
        <CardHead title={open.length ? "Open orders" : "Recent orders"} sub={open.length ? `${plural(open.length, "order")} holding stock` : `${plural(orders.length, "order")} in total`} />
        <div className="list" style={{ marginTop: 8 }}>
          {shown.length ? shown.map((o) => <OrderRow key={o.id} o={o} />) : <Empty icon={PackageCheck} title="No orders for this product yet" />}
        </div>
      </Card>
    </div>
  );
}
