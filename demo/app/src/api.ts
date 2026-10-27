// Typed client for demo/server.py. Every call matches what the original pages sent; no API changes.

export type Channel = "DTC" | "Amazon" | "Etsy" | "Walmart";
export type OrderStatus = "open" | "partial" | "fulfilled" | "cancelled";
export type StockState = "Abundant" | "Balanced" | "Tight" | "Critical";

export interface Sku {
  sku: string; title: string; price: number | null;
  on_hand: number; committed: number; unputaway: number;
  state: StockState | null; sellable_units: number | null; buffer_units: number | null; days_of_cover: number | null;
  allocation: Record<string, number> | null; open_by_channel: Record<string, number>; locked: boolean;
  /** Units each channel's orders drew from its allocation since it was written (not cancelled). */
  used_by_channel?: Record<string, number>;
}
export interface ChannelInfo { name: Channel; color: string; source: { type: string; location: string } }
export interface Economics { sku: string; channel: Channel; unit_margin: number; demand_confidence: number; v7: number; v30: number; v90: number }
export interface Inbound { po: string; sku: string; qty: number; eta_days: number; status: string; supplier: string; arrival_date: string; projected_date: string; on_time_rate: number | null }
export interface PartialShipment { ts: string; qty: number; reason: string }
export interface Order {
  id: string; ts: string; sku: string; qty: number; fulfilled_qty: number; status: OrderStatus; channel: Channel;
  partial_shipments: PartialShipment[]; remaining: number; source: { type: string; location: string };
}
export interface Alert { ts: string; sku: string; problem: string; recommended_action: string; risk_of_inaction: string; deadline: string }
export interface Decision { ts: string; sku: string; record: { state?: string; allocation?: Record<string, number>; write_result?: string; reasoning?: string[] } }
export interface AgentStep { n: number; tool: string; ok: boolean; sources: string[]; text: string; error: string | null }
export interface AgentJob { running: boolean; tail: string; ok: boolean | null; steps: AgentStep[] }
export interface Totals {
  orders: number; units_ordered: number; units_awaiting: number; units_shipped: number; units_cancelled: number; skus: number;
  status_counts: Record<OrderStatus, number>; closed_units: Record<string, Record<string, number>>;
}
export interface AppState {
  skus: Sku[]; channels: ChannelInfo[]; economics: Economics[]; inbound: Inbound[];
  orders: Order[]; alerts: Alert[]; decisions: Decision[]; agent: AgentJob; totals: Totals;
  /** True when the server re-runs the agent by itself after orders, approvals and scenarios. */
  agent_auto?: boolean;
  /** Every allocation the agent wrote, oldest first (the last 200). */
  alloc_log?: { ts: string; sku: string; allocation: Record<string, number>; reason: string }[];
}

export interface EventChannel {
  channel: Channel; cap_from: number; cap_to: number; kind: "pause" | "increase" | "decrease"; reason: string;
  score: number; conf: number; margin: number; savings: string; calc: string[]; row_approval: string;
}
export interface AgentEvent {
  id: string; ts: string; sku: string; status: "auto" | "pending" | "approved" | "denied"; approval: string;
  without_change: { lines: string[]; total: number }; with_change: { lines: string[]; total: number };
  net_savings: number; channels: EventChannel[]; moves: { reduce: { channel: Channel; units: number }[]; add: { channel: Channel; units: number }[] };
  why: string[] | string; approval_id: string | null; deny_reason: string | null; approved_ts: string | null;
  /** Stock was sold or committed and caps were trimmed to match; nothing moved between channels. */
  stock_sync?: boolean;
  /** Past human approvals/denials for this SKU recalled from the H-MEM engine when the proposal was made. */
  recalled_memories?: RecalledMemory[];
}

export interface RecalledMemory {
  memory_id: string; decision: "approved" | "denied" | null; content: string; approval_id: string | null;
  relevance: number; confidence: number; learned_at: number;
}

/** Projected savings of the allocations now in force (auto-applied or approved), per SKU. */
export interface Savings { total: number; count: number; by_sku: Record<string, number> }

export interface Federated {
  ok: boolean; sql: string; ms?: number; error?: string;
  rows?: { channel: string; source_system: string; orders: number; units_ordered: number; units_shipped: number; units_open: number }[];
}
export interface ScenarioResult {
  summary: { orders_total: number; on_hand: number; sellable: number };
  checks: { name: string; ok: boolean | null; detail?: string }[]; passed: number; failed: number;
}

/** POST/GET returning parsed JSON plus the HTTP status; network failures throw. */
async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<{ ok: boolean; status: number; data: T }> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { ok: res.ok, status: res.status, data: (await res.json()) as T };
}

export const api = {
  state: () => call<AppState>("GET", "/api/state"),
  agentLog: () => call<{ events: AgentEvent[]; savings?: Savings }>("GET", "/api/agent-log"),
  agentStatus: () => call<AgentJob>("GET", "/api/agent/status"),
  federated: () => call<Federated>("GET", "/api/federated"),
  runAgent: () => call<{ started?: string; error?: string }>("POST", "/api/agent/run", { scope: "all" }),
  placeOrder: (channel: Channel, sku: string, qty: number) =>
    call<{ order?: Order; error?: string; stored_in?: { type: string; location: string } }>("POST", "/api/order", { channel, sku, qty }),
  settle: (id: string, action: "fulfill" | "partial" | "cancel", body?: { qty?: number; reason?: string }) =>
    call<{ order?: Order; error?: string }>("POST", `/api/order/${id}/${action}`, body ?? {}),
  approve: (id: string) => call<{ error?: string }>("POST", `/api/approvals/${id}/approve`, {}),
  deny: (id: string, reason: string) => call<{ error?: string }>("POST", `/api/approvals/${id}/deny`, { reason }),
  scenario1: () => call<ScenarioResult>("POST", "/api/scenario/1", {}),
  history: () => call<{ generated: number; by_channel: Record<string, number> }>("POST", "/api/history", { days: 90 }),
  reset: () => call<{ reset: boolean; orders_restored?: number; error?: string }>("POST", "/api/reset", {}),
  setAutoRun: (enabled: boolean) => call<{ agent_auto: boolean }>("POST", "/api/agent/auto", { enabled }),
};
