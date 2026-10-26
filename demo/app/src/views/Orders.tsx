import { useMemo, useRef, useState } from "react";
import { Search, Inbox, Check, X } from "lucide-react";
import type { OrderStatus } from "../api";
import { num } from "../format";
import { useStore } from "../store";
import { Card, CardHead, Empty, Kpi, Segmented, Spinner } from "../ui/kit";
import { enter, useGSAP } from "../motion";
import { OrderRow } from "./shared";

type Filter = "all" | OrderStatus;

export function Orders() {
  const { s, settleAllOpen, busy } = useStore();
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => enter(".reveal"), { scope: root });

  const { open, settled } = useMemo(() => {
    const term = q.trim().toLowerCase();
    const hit = (o: { sku: string; channel: string; id: string }) => !term || `${o.sku} ${o.channel} ${o.id}`.toLowerCase().includes(term);
    const orders = (s?.orders ?? []).filter(hit);
    const match = (st: OrderStatus) => filter === "all" || filter === st;
    return {
      open: orders.filter((o) => o.status === "open" && (filter === "all" || filter === "open")),
      settled: orders.filter((o) => o.status !== "open" && match(o.status)),
    };
  }, [s, filter, q]);
  if (!s) return null;
  const c = s.totals.status_counts;
  const showOpen = filter === "all" || filter === "open";
  const showSettled = filter !== "open";

  return (
    <div ref={root} className="stack">
      <div className="page-head reveal">
        <div>
          <h1>Orders</h1>
          <p>Every order from the four channel systems in one queue. Fulfil, split or cancel; stock updates in the warehouse system immediately.</p>
        </div>
      </div>

      <div className="kpis reveal" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <Kpi label="Open" value={c.open} onClick={() => setFilter(filter === "open" ? "all" : "open")} pressed={filter === "open"} />
        <Kpi label="Partially fulfilled" value={c.partial} onClick={() => setFilter(filter === "partial" ? "all" : "partial")} pressed={filter === "partial"} />
        <Kpi label="Fulfilled" value={c.fulfilled} onClick={() => setFilter(filter === "fulfilled" ? "all" : "fulfilled")} pressed={filter === "fulfilled"} />
        <Kpi label="Cancelled" value={c.cancelled} onClick={() => setFilter(filter === "cancelled" ? "all" : "cancelled")} pressed={filter === "cancelled"} />
      </div>

      <div className="reveal" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
        <Segmented<Filter> label="Filter orders by status" value={filter} onChange={setFilter} options={[
          { value: "all", label: "All", count: s.totals.orders },
          { value: "open", label: "Open", count: c.open },
          { value: "partial", label: "Partial", count: c.partial },
          { value: "fulfilled", label: "Fulfilled", count: c.fulfilled },
          { value: "cancelled", label: "Cancelled", count: c.cancelled },
        ]} />
        <div className="search" style={{ width: "min(320px, 100%)" }}>
          <Search size={15} aria-hidden />
          <input className="input" type="search" placeholder="Search SKU, channel or order #" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search orders" />
        </div>
      </div>

      {showOpen && (
        <Card className="reveal">
          <CardHead title="Open orders" sub={`${num(open.length)} shown`}>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn sm" onClick={() => settleAllOpen("fulfill")} disabled={busy.bulk || !c.open}>{busy.bulk ? <Spinner /> : <Check size={14} aria-hidden />}Fulfill all open</button>
              <button className="btn sm danger" onClick={() => settleAllOpen("cancel")} disabled={busy.bulk || !c.open}><X size={14} aria-hidden />Cancel all open</button>
            </div>
          </CardHead>
          <div className="list" style={{ paddingTop: 8 }}>
            {open.map((o) => <OrderRow key={o.id} o={o} />)}
            {!open.length && <Empty icon={Inbox} title={q ? "No open orders match" : "No open orders"}>{q ? "Try another search." : "Everything has shipped."}</Empty>}
          </div>
        </Card>
      )}

      {showSettled && (
        <Card className="reveal">
          <CardHead title={filter === "all" ? "Settled orders" : `${filter[0].toUpperCase()}${filter.slice(1)} orders`} sub={`${num(settled.length)} shown, partial orders can still be fulfilled`} />
          <div className="list" style={{ paddingTop: 8 }}>
            {settled.map((o) => <OrderRow key={o.id} o={o} />)}
            {!settled.length && <Empty icon={Inbox} title="Nothing here">{q ? "No orders match this search." : "No orders in this state."}</Empty>}
          </div>
        </Card>
      )}

      {s.totals.orders > s.orders.length && (
        <p className="tiny muted reveal" style={{ textAlign: "center", margin: 0 }}>
          Lists show the latest {num(s.orders.length)} orders; counts cover all {num(s.totals.orders)}.
        </p>
      )}
    </div>
  );
}
