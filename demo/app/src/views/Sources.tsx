import { useRef } from "react";
import { Button } from "../ui/Button";
import { Database, Globe, Server, SlidersHorizontal, Workflow, RefreshCw, DatabaseZap, ArrowRight } from "lucide-react";
import { CHANNELS, chanColor, chanVar, num } from "../format";
import { useStore } from "../store";
import { axes, Card, CardHead, ChartBox, ChanTag, Empty, Pill, Spinner } from "../ui/kit";
import { enter, useGSAP } from "../motion";

const BACK_OFFICE = [
  { name: "WMS", holds: "Stock on hand, inbound POs" },
  { name: "SUPPLIER_PORTAL", holds: "On-time rate, lane delays" },
  { name: "CHANNEL_ANALYTICS", holds: "Margin, velocity, demand confidence" },
  { name: "RULES_ENGINE", holds: "Locked SKUs, floors, promos" },
];

export function Sources() {
  const { s, fed, fedLoading, loadFederated } = useStore();
  const root = useRef<HTMLDivElement>(null);
  const live = !!fed?.ok;

  useGSAP(() => enter(".reveal"), { scope: root });

  if (!s) return null;
  const openOrders = (c: string) => s.orders.filter((o) => o.channel === c && (o.status === "open" || o.status === "partial")).length;
  const openUnits = (c: string) => s.skus.reduce((a, p) => a + (p.open_by_channel[c] ?? 0), 0);
  const pg = s.channels.filter((c) => c.source.type.startsWith("Postgres"));
  const rest = s.channels.filter((c) => !c.source.type.startsWith("Postgres"));
  const inbound = s.inbound.reduce((a, x) => a + x.qty, 0);
  const rows = CHANNELS.map((c) => fed?.rows?.find((r) => r.channel === c) ?? { channel: c, source_system: `${s.channels.find((x) => x.name === c)?.source.type} (no rows yet)`, orders: 0, units_ordered: 0, units_shipped: 0, units_open: 0 });

  return (
    <div ref={root} className="stack">
      <div className="page-head reveal">
        <div>
          <h1>Data sources</h1>
          <p>Orders, stock, supplier performance, channel economics and business rules each live in their own system. Zetaris federates them so the agent queries one SQL endpoint; no data is copied.</p>
        </div>
        <Pill tone={live ? "ok" : "warn"}>{live ? "Zetaris connected" : "Zetaris not connected"}</Pill>
      </div>

      <Card className="reveal card-pad">
        <div className="flow">
          <div className="flow-col">
            <div className="flow-label">Sources</div>
            <div className="node group">
              <div className="node-title"><Database size={15} aria-hidden />Channel order DB <span className="muted">Postgres (JDBC)</span></div>
              <div className="node-grid">
                {pg.map((c) => (
                  <div key={c.name} className="node sub" style={{ borderColor: chanVar(c.name) }}>
                    <ChanTag name={c.name} />
                    <div className="tiny muted mono">{c.source.location}</div>
                    <div className="tiny"><b className="num">{openOrders(c.name)}</b> open, <b className="num">{openUnits(c.name)}</b> units</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="node group">
              <div className="node-title"><Globe size={15} aria-hidden />Marketplace API <span className="muted">REST</span></div>
              {rest.map((c) => (
                <div key={c.name} className="node sub" style={{ borderColor: chanVar(c.name) }}>
                  <ChanTag name={c.name} />
                  <div className="tiny muted mono">{c.source.location}</div>
                  <div className="tiny"><b className="num">{openOrders(c.name)}</b> open, <b className="num">{openUnits(c.name)}</b> units</div>
                </div>
              ))}
            </div>
            <div className="node group">
              <div className="node-title"><Server size={15} aria-hidden />Back-office systems <span className="muted">REST</span></div>
              {BACK_OFFICE.map((b) => <div key={b.name} className="tiny"><span className="mono" style={{ fontWeight: 600 }}>{b.name}</span> <span className="muted">{b.holds}</span></div>)}
            </div>
          </div>

          <Connector />

          <div className="flow-col center">
            <div className="flow-label">Federation</div>
            <div className="node hero" style={{ borderColor: "var(--accent)" }}>
              <div className="node-title"><DatabaseZap size={16} style={{ color: "var(--accent)" }} aria-hidden />Zetaris <span className={`dot ${live ? "ok" : "warn"}`} style={{ marginInlineStart: "auto" }} aria-label={live ? "connected" : "not connected"} /></div>
              <ul className="node-list">
                <li>1 JDBC datasource (CHANNEL_DB, 3 tables)</li>
                <li>5 Lightning REST databases</li>
                <li>6 schema views (omnismart.*)</li>
                <li>Live SQL across every system</li>
                <li>No data copied or moved</li>
              </ul>
            </div>
          </div>

          <Connector />

          <div className="flow-col center">
            <div className="flow-label">Decision</div>
            <div className="node hero">
              <div className="node-title"><SlidersHorizontal size={16} style={{ color: "var(--accent)" }} aria-hidden />Nemotron agent</div>
              <ul className="node-list">
                <li>compute_allocation per SKU</li>
                <li>Guardrailed set_channel_allocation</li>
                <li>Alerts and decision log</li>
              </ul>
              <div className="tiny" style={{ marginTop: 8 }}><b className="num">{s.alerts.length}</b> alerts, <b className="num">{s.decisions.length}</b> decisions</div>
            </div>
          </div>

          <Connector />

          <div className="flow-col center">
            <div className="flow-label">Action</div>
            <div className="node hero">
              <div className="node-title"><Workflow size={16} style={{ color: "var(--accent)" }} aria-hidden />Actions</div>
              <ul className="node-list">
                <li>Channel allocation caps</li>
                <li>Fulfilment and cancellation</li>
              </ul>
              <div className="tiny" style={{ marginTop: 8 }}><b className="num">{num(inbound)}</b> inbound units pending</div>
            </div>
          </div>
        </div>
      </Card>

      <Card className="reveal">
        <CardHead title="Live federated query" sub="One Lightning SQL statement that unions three Postgres tables with a REST API">
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {fed?.ok && <span className="tiny muted">{fed.rows?.length ?? 0} source rows, {fed.ms} ms, via Zetaris JDBC</span>}
            <Button variant="secondary" onClick={loadFederated} disabled={fedLoading}>{fedLoading ? <Spinner /> : <RefreshCw size={14} aria-hidden />}{fed?.ok ? "Refresh" : "Retry"}</Button>
          </div>
        </CardHead>
        <div className="card-body grid g-2" style={{ gap: 20 }}>
          <pre className="code">{fed?.sql || "Loading…"}</pre>
          <div>
            {fed?.ok ? (
              <>
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>Channel</th><th>Source system</th><th className="num">Orders</th><th className="num">Ordered</th><th className="num">Shipped</th><th className="num">Open</th></tr></thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.channel}>
                          <td><ChanTag name={r.channel} /></td>
                          <td className="small muted">{r.source_system}</td>
                          <td className="num">{num(r.orders)}</td><td className="num">{num(r.units_ordered ?? 0)}</td>
                          <td className="num">{num(r.units_shipped ?? 0)}</td><td className="num"><b>{num(r.units_open ?? 0)}</b></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <ChartBox size="sm" label="Open and shipped units by channel from the federated query" deps={[JSON.stringify(rows)]} make={() => ({
                  type: "bar",
                  data: { labels: rows.map((r) => r.channel), datasets: [
                    { label: "Open", data: rows.map((r) => +r.units_open || 0), backgroundColor: rows.map((r) => chanColor(r.channel)), borderRadius: 4 },
                    { label: "Shipped", data: rows.map((r) => +r.units_shipped || 0), backgroundColor: rows.map((r) => chanColor(r.channel) + "55"), borderRadius: 4 },
                  ] },
                  options: { scales: axes(), plugins: { legend: { display: true, labels: { usePointStyle: true, pointStyle: "rectRounded" } } } },
                })} />
              </>
            ) : (
              <Empty icon={DatabaseZap} title={fed ? "Zetaris is not connected" : "Querying Zetaris…"}>
                {fed && <>This live query runs when Zetaris is up. Start it, then choose Retry.<div className="tiny muted" style={{ marginTop: 8 }} title={fed.error}>{fed.error?.slice(0, 140)}</div></>}
              </Empty>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

/** Line between two flow columns; dots travel along it while data is flowing. */
function Connector() {
  return (
    <div className="flow-link" aria-hidden>
      <span className="flow-line" />
      <ArrowRight size={16} className="flow-arrow" />
    </div>
  );
}
