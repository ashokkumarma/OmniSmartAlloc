import { useRef } from "react";
import { ArrowRight } from "lucide-react";
import type { Route } from "../App";
import { Card, CardHead } from "../ui/kit";
import { enter, useGSAP } from "../motion";

const COVERAGE: { area: string; how: string; see: string; to: Route }[] = [
  { area: "Fragmented data sources", how: "Six systems that were never designed to work together: a Postgres order database (DTC, Etsy, Walmart), an Amazon REST API, a warehouse system, a supplier portal, channel analytics and a rules engine. No single one can answer \"where should stock go?\".", see: "Data sources", to: "sources" },
  { area: "Federation across source types", how: "Zetaris Lightning SQL exposes the Postgres tables (JDBC) and the REST APIs as one queryable layer, so one SQL statement can combine a Postgres table with a REST response. The agent never talks to the sources one by one.", see: "Data sources", to: "sources" },
  { area: "LLM reasoning and tool use", how: "A NVIDIA Nemotron ReAct agent, called through an OpenAI-compatible endpoint, decides which tool to use next: discover sources, run a query, compute an allocation, apply it, raise an alert, log the decision.", see: "Smart Allocation (agent run)", to: "agent" },
  { area: "Deterministic, explainable maths", how: "The model does not do arithmetic. A deterministic engine computes sellable stock (on hand minus committed), credits reliable inbound supply, classifies the supply state and ranks channels by margin and demand. The same inputs always give the same allocation.", see: "Smart Allocation", to: "agent" },
  { area: "Guardrails enforced in code", how: "SQL is read-only. A write is refused if projected savings are zero or negative, or if the stock or margin data is stale. A move over 25% of a channel's units, or to zero, is never auto-applied. The model cannot talk its way past these checks.", see: "Smart Allocation", to: "agent" },
  { area: "Human in the loop", how: "Risky moves become amber Needs approval cards. A person approves or denies, and only an approval writes the full target.", see: "Smart Allocation", to: "agent" },
  { area: "Transparency and audit", how: "Every card shows the units moved, the reasons, the channels read and the projected dollars saved. Allocations, alerts, approvals and decisions are written to an append-only log.", see: "Smart Allocation", to: "agent" },
  { area: "Autonomous, event-driven operation", how: "The agent wakes up when an order is fulfilled, because that is when physical stock changes. It looks only at the SKU that changed. A manual run covers every SKU.", see: "Orders", to: "orders" },
  { area: "Reproducible demo", how: "Reset demo restores the baseline in one click, and two scripted scenarios (needs approval, auto-applied) let anyone reproduce the behaviour. The test suite runs offline with fake connectors.", see: "Instructions", to: "instructions" },
];

const REAL_WORLD: { title: string; problem: string; fix: string }[] = [
  { title: "Stock stranded in the wrong channel", problem: "A seller splits inventory across their own store, Amazon, Etsy and Walmart. One channel sells out while another sits on units that barely move, and nobody notices until a customer is turned away.", fix: "The agent compares sales velocity and demand confidence per channel and moves units to where they will actually sell." },
  { title: "Blind to margin", problem: "The same unit earns very different profit by channel. In this demo DTC earns 75%, Amazon 50%, Etsy 40% and Walmart 30%. Splitting stock evenly, or by habit, quietly gives profit away.", fix: "Allocation is ranked by margin as well as demand, and every move shows the dollars it is projected to save." },
  { title: "Slow, manual rebalancing", problem: "Teams rebalance with spreadsheets and exports from five different tools. By the time the numbers are joined, they are out of date.", fix: "The federated query reads every source live, and the agent reacts the moment stock physically changes." },
  { title: "Automation nobody trusts", problem: "A black box that moves stock on its own is a risk. Emptying a channel by mistake means lost sales and angry marketplace metrics.", fix: "Small, clearly profitable moves are applied automatically. Big moves wait for a person. Everything is explained and logged." },
];

/** Where the project sits against the hackathon track, and why it matters outside the demo. */
export function HackathonContext({ go }: { go: (r: Route) => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => enter(".reveal"), { scope: root });
  return (
    <div ref={root} className="stack">
      <div className="page-head reveal">
        <div>
          <h1>Hackathon Context</h1>
          <p>Open Agent Hackathon 2026, Track 1: Solving Fragmented Intelligence. OmniSmartAlloc is an agent that makes one allocation decision from data that lives in six separate systems.</p>
        </div>
      </div>

      <Card className="reveal">
        <CardHead title="The idea in one paragraph" />
        <div className="card-body small" style={{ lineHeight: 1.65 }}>
          A multi-channel seller's inventory truth is scattered: orders in one database per channel, stock in the warehouse, supplier reliability in a portal, margins in analytics and business rules in yet another tool. OmniSmartAlloc treats none of them as the authority. It federates them through Zetaris, lets a Nemotron agent decide what to look at, computes the allocation with deterministic and explainable maths, and enforces the safety rules in code before anything is written. The result is a decision no single system could have made, with a human approving the risky ones.
        </div>
      </Card>

      <Card className="reveal">
        <CardHead title="Technical coverage" sub="How the project covers each part of the Track 1 brief" />
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Area</th><th>How OmniSmartAlloc covers it</th><th>See it</th></tr></thead>
            <tbody>
              {COVERAGE.map((r) => (
                <tr key={r.area}>
                  <td style={{ fontWeight: 600, minWidth: 190 }}>{r.area}</td>
                  <td style={{ lineHeight: 1.55, minWidth: 340 }}>{r.how}</td>
                  <td><button className="btn sm plain" onClick={() => go(r.to)}>{r.see}<ArrowRight size={13} aria-hidden /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="reveal">
        <h2 style={{ margin: "8px 0 12px" }}>Why it matters in the real world</h2>
        <div className="grid g-2">
          {REAL_WORLD.map((r) => (
            <Card key={r.title}>
              <CardHead title={r.title} />
              <div className="card-body small" style={{ lineHeight: 1.6 }}>
                <p style={{ margin: 0 }}><span className="pill warn">Problem</span> {r.problem}</p>
                <p style={{ margin: "10px 0 0" }}><span className="pill ok">What the agent does</span> {r.fix}</p>
              </div>
            </Card>
          ))}
        </div>
      </div>

      <Card className="reveal">
        <CardHead title="Who benefits" />
        <div className="card-body small">
          <ul style={{ margin: 0, paddingInlineStart: 20, lineHeight: 1.8 }}>
            <li><b>Operations teams</b> stop rebalancing by hand and only review the moves that need a decision.</li>
            <li><b>Finance and merchandising</b> see the projected savings for each move, with the reasons behind it.</li>
            <li><b>Customers</b> are less likely to hit a sold-out channel while stock sits unused elsewhere.</li>
          </ul>
          <p className="muted" style={{ margin: "12px 0 0" }}>Scope note: the sources in this demo are mock APIs and a local Postgres database that stand in for real marketplace, warehouse and analytics systems. The federation, agent, engine and guardrails are the same pieces a real deployment would use, pointed at real endpoints.</p>
        </div>
      </Card>
    </div>
  );
}
