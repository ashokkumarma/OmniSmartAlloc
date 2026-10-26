import type { LandingContent } from "./Landing";

const RAILS: [string, number, number][] = [["DTC", 0, 35], ["Amazon", 1, 28], ["Etsy", 0, 6], ["Walmart", 2, 14]];

export const content: LandingContent = {
  product: "OmniSmartAlloc",
  eyebrow: "Inventory allocation agent",
  cycle: ["Read", "Rank", "Supply"],
  rest: " every channel from one stock pool.",
  statement: "The agent reads warehouse, supplier, channel and rules systems through Zetaris, then sets how many units each sales channel may sell. Big moves wait for your approval.",
  facts: [
    { title: "Reads through Zetaris", body: "Warehouse, supplier portal, channel analytics, business rules and four channel order systems, in one federated query." },
    { title: "Nemotron on Meterless", body: "The agent reasons with NVIDIA Nemotron, served by Meterless Nightshift." },
    { title: "You approve the big moves", body: "Changes above the guardrails wait for approval before anything is written." },
  ],
  capsEyebrow: "What it does",
  capsTitle: "Five jobs, every cycle.",
  capsLede: "Each allocation cycle runs the same steps and leaves a record you can check.",
  capabilities: [
    { title: "Read every system", body: "Stock on hand, inbound purchase orders, supplier track record, channel demand and business rules." },
    { title: "Rank the channels", body: "Score is unit margin times demand confidence. Higher scores get stock first." },
    { title: "Set channel caps", body: "How many units DTC, Amazon, Etsy and Walmart may each sell, inside your guardrails." },
    { title: "Hold the big moves", body: "Changes above the guardrails wait for approval, with the savings maths in view." },
    { title: "Flag what is coming", body: "Late inbound shipments and tight stock show up before they cost a sale." },
  ],
  interludeEyebrow: "Why it exists",
  interlude: "Stock sits in one warehouse, but four channels sell it at once. Without a referee the fastest channel wins and the most profitable one runs dry. OmniSmartAlloc decides who gets what, and shows its working.",
  pillarsEyebrow: "The product",
  pillarsTitle: "One pool, four channels, one record.",
  pillars: [
    {
      title: "Cap rails", body: "Each channel's cap, and how much of it open orders already hold.",
      preview: (
        <>
          <div className="pv-head"><span className="pv-title">MUG-001, Ember Ceramic Mug</span><span className="pv-dot" style={{ "--c": "var(--ds-warn)" } as React.CSSProperties}>Tight</span></div>
          {RAILS.map(([c, taken, cap]) => (
            <div className="pv-row" key={c}><span>{c}</span><span className="pv-rail"><i style={{ width: `${Math.max(6, (cap / 35) * 100)}%` }} /></span><span className="pv-n">{taken} of {cap}</span></div>
          ))}
          <pre className="pv-code">sellable 97 = on hand 100 - committed 3{"\n"}days of cover 3.2</pre>
        </>
      ),
    },
    {
      title: "Decisions you approve", body: "Large moves stop and wait, with the cost of doing nothing next to the change.",
      preview: (
        <>
          <div className="pv-head"><span className="pv-title">Move cap from Etsy to DTC</span><span className="pv-dot" style={{ "--c": "var(--ds-warn)" } as React.CSSProperties}>Waiting for you</span></div>
          <div className="pv-row"><span>Without</span><span className="muted">The fastest channel sells out the pool first</span><span className="pv-n" /></div>
          <div className="pv-row"><span>With</span><span className="muted">Caps follow margin times demand confidence</span><span className="pv-n" /></div>
          <div className="pv-row"><span>You</span><span className="muted">Approve, or deny with a reason the agent reads next run</span><span className="pv-n" /></div>
        </>
      ),
    },
    {
      title: "Every source, one query", body: "Postgres tables and REST services, joined by Zetaris in a single read-only statement.",
      preview: (
        <>
          <div className="pv-head"><span className="pv-title">Federated read</span><span className="pv-dot" style={{ "--c": "var(--ds-success)" } as React.CSSProperties}>Read only</span></div>
          <pre className="pv-code">{"SELECT channel, SUM(qty) AS units_open\nFROM channel_db.dtc_orders\nUNION ALL ... amazon_api.orders\nUNION ALL ... etsy_orders, walmart_orders\nGROUP BY channel;"}</pre>
          <div className="pv-row"><span>Sources</span><span className="muted">WMS, supplier portal, analytics, rules</span><span className="pv-n">8</span></div>
        </>
      ),
    },
  ],
  closing: "Give every unit a reason to be where it is.",
  scene: "orbit",
  footer: "OmniSmartAlloc. Built on Zetaris, Meterless and NVIDIA Nemotron for the Open Agent Hackathon 2026.",
};
