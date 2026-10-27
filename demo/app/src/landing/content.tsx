import type { LandingContent } from "./Landing";
import { StoryPanes } from "./Scrollytelling";

const dot = (c: string) => ({ "--c": c }) as React.CSSProperties;
const SOURCES: [string, string][] = [["Warehouse", "stock on hand and committed units"], ["Suppliers", "inbound purchase orders and track record"], ["Analytics", "channel demand and confidence"], ["Rules", "guardrails and locked SKUs"], ["Orders", "four channel order systems"]];
const SCORES: [string, string, number][] = [["DTC", "$24 x 0.9", 21.6], ["Amazon", "$16 x 1.0", 16], ["Etsy", "$13 x 0.8", 10.4], ["Walmart", "$10 x 0.9", 9]];
const RAILS: [string, number, number][] = [["DTC", 0, 35], ["Amazon", 1, 28], ["Etsy", 0, 6], ["Walmart", 2, 14]];

/** The pinned view: one allocation cycle, shown in the state of the current step. */
function CycleView({ step }: { step: number }) {
  return (
    <>
      <div className="pv-window-bar"><span>MUG-001, Ember Ceramic Mug</span><span>Cycle step {step + 1} of 4</span></div>
      <StoryPanes step={step}>
        {[
          <>{SOURCES.map(([n, w]) => <div className="pv-row" key={n}><span>{n}</span><span className="muted">{w}</span><span className="pv-dot" style={dot("var(--ds-success)")}>Read</span></div>)}</>,
          <>{SCORES.map(([c, f, s]) => <div className="pv-row" key={c}><span>{c}</span><span className="pv-rail"><i style={{ width: `${(s / 21.6) * 100}%` }} /></span><span className="pv-n">{f} = {s}</span></div>)}</>,
          <>{RAILS.map(([c, taken, cap]) => <div className="pv-row" key={c}><span>{c}</span><span className="pv-rail"><i style={{ width: `${Math.max(6, (cap / 35) * 100)}%` }} /></span><span className="pv-n">{taken} of {cap}</span></div>)}
            <pre className="pv-code">sellable 97 = on hand 100 - committed 3{"\n"}days of cover 3.2</pre></>,
          <>
            <div className="pv-head"><span className="pv-title">Move cap from Etsy to DTC<span className="pv-sub">Over the 25% change limit</span></span><span className="pv-dot" style={dot("var(--ds-warn)")}>Waiting for you</span></div>
            <div className="pv-row"><span>Without</span><span className="muted">The fastest channel sells out the pool first</span><span className="pv-n" /></div>
            <div className="pv-row"><span>With</span><span className="muted">Caps follow margin times demand confidence</span><span className="pv-n" /></div>
            <div className="pv-row"><span>You</span><span className="muted">Approve, or deny with a reason the agent reads next run</span><span className="pv-n" /></div>
          </>,
        ]}
      </StoryPanes>
    </>
  );
}

export const content: LandingContent = {
  product: "OmniSmartAlloc",
  tagline: "Inventory allocation agent",
  headline: <>Share <em>one</em> stock pool across every sales channel.</>,
  lede: "The agent reads warehouse, supplier, channel and rules data through Zetaris, then sets how many units DTC, Amazon, Etsy and Walmart may each sell. Big moves wait for your approval.",
  scene: "pool",
  accent: "#4CC9EE",
  heroLabel: "A sphere of points circled by four rings, each lit to one sales channel's share of stock",
  heroCaption: "The stock pool is a sphere of points; each of the four channels is a ring, lit to the share of stock it may sell.",
  facts: [
    { title: "Reads through Zetaris", body: "Warehouse, supplier portal, channel analytics, business rules and four channel order systems, in one federated query." },
    { title: "Reasons with NVIDIA Nemotron", body: "Through NVIDIA NIM or the Meterless runtime." },
    { title: "You approve the big moves", body: "Changes above the guardrails wait for approval before anything is written." },
  ],
  capsTitle: "Five jobs, every cycle.",
  capsLede: "Each allocation cycle runs the same steps and leaves a record you can check.",
  capabilities: [
    { title: "Read every system", body: "Stock on hand, inbound purchase orders, supplier track record, channel demand and business rules." },
    { title: "Rank the channels", body: "Score is unit margin times demand confidence. Higher scores get stock first." },
    { title: "Set channel caps", body: "How many units DTC, Amazon, Etsy and Walmart may each sell, inside your guardrails." },
    { title: "Hold the big moves", body: "Changes above the guardrails wait for approval, with the savings maths in view." },
    { title: "Flag what is coming", body: "Late inbound shipments and tight stock show up before they cost a sale." },
  ],
  why: "Stock sits in one warehouse, but four channels sell it at once. Without a referee the fastest channel wins and the most profitable one runs dry. OmniSmartAlloc decides who gets what, and shows its working.",
  storyTitle: "One cycle, step by step.",
  story: [
    { title: "Read every system", body: "Five sources are read through Zetaris in a single read-only query." },
    { title: "Rank the channels", body: "Each channel scores unit margin times demand confidence; higher scores get stock first." },
    { title: "Set the caps", body: "Each channel gets a cap, and the rail shows how much of it open orders already hold." },
    { title: "Hold the big move", body: "A change above the guardrails stops and waits for you, with the cost of doing nothing beside it." },
  ],
  storyView: (step) => <CycleView step={step} />,
  closing: "Give every unit a reason to be where it is.",
  footer: "OmniSmartAlloc. Built on Zetaris, Meterless and NVIDIA Nemotron for the Open Agent Hackathon 2026.",
};
