import { useRef, useState } from "react";
import { ShoppingCart, Database, Globe, ShoppingBag, ChevronDown } from "lucide-react";
import type { Channel } from "../api";
import { CHANNELS, CHANNEL_BLURB, chanColor, chanVar, money, num, STATUS_TONE, when } from "../format";
import { useStore } from "../store";
import { axes, Card, CardHead, ChartBox, Empty, Pill, Segmented, Spinner, Stepper } from "../ui/kit";
import { enter, gsap, reducedMotion, useGSAP } from "../motion";

export function Storefronts() {
  const { s, placeOrder } = useStore();
  const [ch, setCh] = useState<Channel>("DTC");
  const [qty, setQty] = useState<Record<string, number>>({});
  const [buying, setBuying] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => enter(".reveal"), { scope: root, dependencies: [ch], revertOnUpdate: true });
  if (!s) return null;

  const info = s.channels.find((c) => c.name === ch)!;
  const er = s.economics.find((e) => e.channel === ch);
  const price = s.skus.find((p) => p.sku === er?.sku)?.price;
  const marginPct = er && price ? Math.round((er.unit_margin / price) * 100) : null;
  const orders = s.orders.filter((o) => o.channel === ch);
  const shown = expanded ? orders : orders.slice(0, 6);
  const isPg = info.source.type.startsWith("Postgres");

  const buy = async (sku: string, btn: HTMLButtonElement) => {
    const n = qty[`${ch}_${sku}`] ?? 1;
    setBuying(sku);
    const ok = await placeOrder(ch, sku, n);
    setBuying(null);
    if (ok && !reducedMotion()) gsap.fromTo(btn, { scale: 0.94 }, { scale: 1, duration: 0.5, ease: "back.out(3)" });
  };

  return (
    <div ref={root} className="stack">
      <div className="page-head reveal">
        <div>
          <h1>Storefronts</h1>
          <p>Place test orders as a shopper would. Each channel writes to its own system, exactly like production, and the agent sees it on the next run.</p>
        </div>
        <Segmented<Channel> label="Channel" value={ch} onChange={(c) => { setCh(c); setExpanded(false); }}
          options={CHANNELS.map((c) => ({ value: c, label: <><i style={{ width: 8, height: 8, borderRadius: 4, background: chanVar(c), display: "inline-block" }} aria-hidden />{c}</> }))} />
      </div>

      <Card className="reveal card-pad" style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: chanVar(ch), display: "grid", placeItems: "center", color: "#fff", flex: "none" }} aria-hidden>
          <ShoppingBag size={22} />
        </div>
        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{ fontSize: 20, fontWeight: 600 }}>{ch}</div>
          <div className="muted">{CHANNEL_BLURB[ch]}</div>
        </div>
        <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
          <div><div className="tiny muted">Margin</div><div className="num" style={{ fontSize: 20, fontWeight: 600 }}>{marginPct != null ? `${marginPct}%` : "—"}</div></div>
          <div><div className="tiny muted">Orders stored in</div><div style={{ display: "flex", gap: 6, alignItems: "center", fontWeight: 500 }}>{isPg ? <Database size={15} aria-hidden /> : <Globe size={15} aria-hidden />}{info.source.type}</div><div className="tiny muted mono">{info.source.location}</div></div>
        </div>
      </Card>

      <section className="reveal">
        <h2 className="section-title">Catalog</h2>
        <div className="grid g-4">
          {s.skus.map((p) => {
            const free = p.on_hand - p.committed;
            const cap = p.allocation ? p.allocation[ch] ?? 0 : null;
            const open = p.open_by_channel[ch] ?? 0;
            const used = p.used_by_channel ? p.used_by_channel[ch] ?? 0 : open;
            const left = cap === null ? null : Math.max(0, cap - used);
            const key = `${ch}_${p.sku}`;
            return (
              <Card key={p.sku} className="card-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{p.title}</div>
                  <div className="tiny muted mono">{p.sku}</div>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span className="num" style={{ fontSize: 22, fontWeight: 600 }}>{money(p.price)}</span>
                  {cap !== null && <span className="small muted">{left} of {cap} left{used ? ` (${used} used${open ? `, ${open} open` : ""})` : ""}</span>}
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: "auto" }}>
                  <Stepper label={`Quantity of ${p.title}`} value={qty[key] ?? 1} min={1} max={Math.max(1, free)} onChange={(n) => setQty((q) => ({ ...q, [key]: n }))} />
                  <button className="btn primary" style={{ flex: 1 }} disabled={buying === p.sku} onClick={(e) => buy(p.sku, e.currentTarget)}>
                    {buying === p.sku ? <Spinner /> : <ShoppingCart size={15} aria-hidden />}Buy
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      <div className="grid g-main reveal">
        <Card>
          <CardHead title="Order feed" sub={`${num(orders.length)} recent ${ch} orders`} />
          <div className="list" style={{ paddingTop: 8 }}>
            {shown.map((o) => (
              <div className="row" key={o.id}>
                <div className="grow">
                  <div><b className="num">{o.qty}×</b> {o.sku} {o.fulfilled_qty > 0 && <span className="small muted">shipped {o.fulfilled_qty}/{o.qty}</span>}</div>
                  <div className="meta">{when(o.ts)}, <span className="mono">#{o.id}</span></div>
                </div>
                <Pill tone={STATUS_TONE[o.status]}>{o.status}</Pill>
              </div>
            ))}
            {!orders.length && <Empty icon={ShoppingBag} title={`No ${ch} orders yet`}>Buy something above to create one.</Empty>}
          </div>
          {orders.length > 6 && (
            <div style={{ padding: "0 20px 14px" }}>
              <button className="btn sm plain" onClick={() => setExpanded((x) => !x)} aria-expanded={expanded}>
                {expanded ? "Show less" : `Show ${orders.length - 6} more`}<ChevronDown size={14} style={{ transform: expanded ? "rotate(180deg)" : undefined }} aria-hidden />
              </button>
            </div>
          )}
        </Card>
        <div className="stack" style={{ gap: 16 }}>
          <Card>
            <CardHead title="Open orders" sub="Units still to ship" />
            <div className="card-body">
              <ChartBox size="sm" label={`${ch} open units by SKU`} deps={[ch, JSON.stringify(s.skus.map((p) => p.open_by_channel[ch]))]} make={() => ({
                type: "bar",
                data: { labels: s.skus.map((p) => p.sku), datasets: [{ data: s.skus.map((p) => p.open_by_channel[ch] ?? 0), backgroundColor: chanColor(ch), borderRadius: 6, maxBarThickness: 40 }] },
                options: { scales: axes() },
              })} />
            </div>
          </Card>
          <Card>
            <CardHead title="Closed orders" sub="Units shipped, all time" />
            <div className="card-body">
              <ChartBox size="sm" label={`${ch} closed units by SKU`} deps={[ch, JSON.stringify(s.totals.closed_units[ch])]} make={() => ({
                type: "bar",
                data: { labels: s.skus.map((p) => p.sku), datasets: [{ data: s.skus.map((p) => s.totals.closed_units[ch]?.[p.sku] ?? 0), backgroundColor: chanColor(ch) + "99", borderRadius: 6, maxBarThickness: 40 }] },
                options: { scales: axes() },
              })} />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
