import { useRef, type ReactNode } from "react";
import { Button } from "../ui/Button";
import { ArrowRight, ShoppingCart, Warehouse } from "lucide-react";
import type { Route } from "../App";
import { Card, CardHead } from "../ui/kit";
import { enter, useGSAP } from "../motion";

/** A step that names a screen gets a button that opens it. */
function Step({ children, to, go, label }: { children: ReactNode; to?: Route; go: (r: Route) => void; label?: string }) {
  return (
    <li style={{ margin: "8px 0", lineHeight: 1.55 }}>
      {children}
      {to && <Button variant="tertiary" style={{ marginInlineStart: 8 }} onClick={() => go(to)}>{label ?? "Open"}<ArrowRight size={13} aria-hidden /></Button>}
    </li>
  );
}

/** The guided demo: what the OMS and IMS screens are for, and two scenarios that make the agent act. */
export function Instructions({ go }: { go: (r: Route) => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => enter(".reveal"), { scope: root });
  return (
    <div ref={root} className="stack">
      <div className="page-head reveal">
        <div>
          <h1>Instructions</h1>
          <p>Two screens, two scenarios. Place orders in the OMS, fulfil them in the IMS, and watch the agent decide.</p>
        </div>
      </div>

      <div className="grid g-2 reveal">
        <Card>
          <CardHead title={<span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><ShoppingCart size={17} aria-hidden />Order Management System (OMS)</span>} sub="Where orders happen" />
          <div className="card-body small" style={{ lineHeight: 1.6 }}>
            Open <b>Storefronts</b>, pick a channel (DTC, Amazon, Etsy, Walmart), set a quantity and click <b>Place order</b>. Each channel writes to its own system. Fulfilment happens in the IMS.
            <div style={{ marginTop: 10 }}><Button variant="secondary" onClick={() => go("storefronts")}>Open Storefronts<ArrowRight size={13} aria-hidden /></Button></div>
          </div>
        </Card>
        <Card>
          <CardHead title={<span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><Warehouse size={17} aria-hidden />Inventory Management System (IMS)</span>} sub="Where the agent reports" />
          <div className="card-body small" style={{ lineHeight: 1.6 }}>
            <b>Orders</b> is where you fulfil orders. <b>Smart Allocation</b> shows what the agent decided: green <b>Auto-applied</b> cards it wrote itself, amber <b>Needs approval</b> cards waiting for a human.
            <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button variant="secondary" onClick={() => go("orders")}>Open Orders<ArrowRight size={13} aria-hidden /></Button>
              <Button variant="secondary" onClick={() => go("agent")}>Open Smart Allocation<ArrowRight size={13} aria-hidden /></Button>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid g-2 reveal">
        <Card style={{ borderColor: "var(--warn)" }}>
          <CardHead title={<span style={{ color: "var(--warn)" }}>Scenario A: needs approval</span>} sub="A big order forces a big move, so the agent asks first" />
          <div className="card-body small">
            <ol style={{ margin: 0, paddingInlineStart: 20 }}>
              <Step go={go} to="storefronts" label="Storefronts">In <b>Storefronts</b>, choose the <b>Amazon</b> channel.</Step>
              <Step go={go}>On <b>Ember Ceramic Mug (MUG-001)</b>, set the quantity to <b>30</b> and click <b>Place order</b>.</Step>
              <Step go={go} to="orders" label="Orders">Open <b>Orders</b>, find the new MUG-001 order under <b>Open orders</b> and click <b>Fulfill all</b>.</Step>
              <Step go={go}>Wait about <b>1 to 2 minutes</b>: with <b>Auto-run</b> on, the agent runs by itself after a fulfilment.</Step>
              <Step go={go} to="agent" label="Smart Allocation">Open <b>Smart Allocation</b>: the amber <b>Needs approval</b> card is there.</Step>
              <Step go={go}>Click <b>Approve</b> or <b>Deny</b> on the card to finish.</Step>
            </ol>
            <p className="muted" style={{ margin: "12px 0 0" }}>Why it asks: the order drains most of MUG-001's stock, so the fix moves more than 25% of a channel's units (or empties a channel). Big moves always need a human yes or no.</p>
          </div>
        </Card>
        <Card style={{ borderColor: "var(--ok)" }}>
          <CardHead title={<span style={{ color: "var(--ok)" }}>Scenario B: auto-applied</span>} sub="A clear win the agent makes on its own" />
          <div className="card-body small">
            <ol style={{ margin: 0, paddingInlineStart: 20 }}>
              <Step go={go} to="storefronts" label="Storefronts">In <b>Storefronts</b>, choose <b>DTC</b>. On <b>Aurora Desk Lamp (LAMP-002)</b>, set <b>20</b> and click <b>Place order</b>.</Step>
              <Step go={go}>Choose <b>Amazon</b>. On <b>LAMP-002</b>, set <b>20</b> and click <b>Place order</b>.</Step>
              <Step go={go} to="orders" label="Orders">Open <b>Orders</b> and click <b>Fulfill all</b> on both new LAMP-002 orders.</Step>
              <Step go={go}>Wait about <b>1 to 2 minutes</b> while the agent runs.</Step>
              <Step go={go} to="agent" label="Smart Allocation">Open <b>Smart Allocation</b>: the green <b>Auto-applied</b> card shows the units moved to the higher-margin channel and the dollars saved.</Step>
            </ol>
            <p className="muted" style={{ margin: "12px 0 0" }}>Why it just acts: DTC earns the most per LAMP-002 sale, so refilling it from slower channels is a clear win. No channel is emptied and no move is over 25%, so the agent applies it without asking.</p>
          </div>
        </Card>
      </div>

      <Card className="reveal">
        <CardHead title="Good to know" />
        <div className="card-body small">
          <ul style={{ margin: 0, paddingInlineStart: 20, lineHeight: 1.8 }}>
            <li>The agent wakes up after a <b>fulfilment</b>, not when an order is placed. Don't skip <b>Fulfill</b>.</li>
            <li>In the sidebar, <b>Orders</b> shows the open-order count and <b>Smart Allocation</b> the approvals waiting for you.</li>
            <li>No card after about 2 minutes? Click <b>Run allocation cycle</b> at the top right once.</li>
            <li>Want a clean slate? <b>Reset demo</b> in the sidebar restores stock, orders and allocations.</li>
          </ul>
        </div>
      </Card>
    </div>
  );
}
