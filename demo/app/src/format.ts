import type { Channel, OrderStatus, StockState } from "./api";

export const CHANNELS: Channel[] = ["DTC", "Amazon", "Etsy", "Walmart"];
const CH_VAR: Record<string, string> = { DTC: "--ch-dtc", Amazon: "--ch-amazon", Etsy: "--ch-etsy", Walmart: "--ch-walmart" };
const ST_VAR: Record<string, string> = { Abundant: "--st-abundant", Balanced: "--st-balanced", Tight: "--st-tight", Critical: "--st-critical" };

/** CSS var reference for a channel's data colour (for style props). */
export const chanVar = (c: string) => `var(${CH_VAR[c] ?? "--label-3"})`;
export const stateVar = (s: string | null) => `var(${(s && ST_VAR[s]) || "--label-3"})`;

/** Resolved colour values, for Chart.js which cannot read CSS variables. */
export function cssColor(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}
export const chanColor = (c: string) => cssColor(CH_VAR[c] ?? "--label-3");
export const stateColor = (s: string | null) => cssColor((s && ST_VAR[s]) || "--label-3");

export const STATUS_TONE: Record<OrderStatus, "warn" | "info" | "ok" | "bad"> = { open: "warn", partial: "info", fulfilled: "ok", cancelled: "bad" };
export const STATE_TONE: Record<StockState, "ok" | "info" | "warn" | "bad"> = { Abundant: "ok", Balanced: "info", Tight: "warn", Critical: "bad" };

export const CHANNEL_BLURB: Record<string, string> = {
  DTC: "Our own storefront",
  Amazon: "Marketplace — Buy Box and ranking at stake",
  Etsy: "Handmade and enthusiast marketplace",
  Walmart: "Big-box marketplace",
};

const nf = new Intl.NumberFormat("en-US");
export const num = (n: number | null | undefined) => (n == null ? "—" : nf.format(n));
export const money = (n: number | null | undefined) => (n == null ? "—" : `$${nf.format(n)}`);

/** "2026-10-25T18:05:50Z" → "Oct 25, 18:05 UTC" */
export function when(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }) + " UTC";
}

/** Relative time for recent events ("3 min ago"), absolute beyond a day. */
export function ago(ts: string): string {
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (!Number.isFinite(s)) return ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return when(ts);
}

export const plural = (n: number, one: string, many = `${one}s`) => `${num(n)} ${n === 1 ? one : many}`;

/** Units a channel's orders drew from its allocation since it was written (the server's rule); falls back to open units. */
export const usedUnits = (p: { used_by_channel?: Record<string, number>; open_by_channel: Record<string, number> }, c: string) =>
  p.used_by_channel ? p.used_by_channel[c] ?? 0 : p.open_by_channel[c] ?? 0;
