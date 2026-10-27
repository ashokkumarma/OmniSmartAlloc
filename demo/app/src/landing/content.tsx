import type { LandingContent } from "./Landing";
import { CHAPTERS, FilmScene } from "./film-scene";

export const content: LandingContent = {
  product: "OmniSmartAlloc",
  tagline: "Inventory allocation agent",
  headline: <>Share <em>one</em> stock pool across every sales channel.</>,
  lede: "The agent reads warehouse, supplier, channel and rules data through Zetaris, then sets how many units DTC, Amazon, Etsy and Walmart may each sell. Big moves wait for your approval.",
  scene: "pool",
  accent: "#4CC9EE",
  heroLabel: "A sphere of points circled by four rings, each lit to one sales channel's share of stock",
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
  filmLabel: "One allocation cycle, scrolled",
  chapters: CHAPTERS,
  film: (p) => <FilmScene p={p} />,
  closing: "Give every unit a reason to be where it is.",
  footer: "OmniSmartAlloc. Built on Zetaris, Meterless and NVIDIA Nemotron for the Open Agent Hackathon 2026.",
};
