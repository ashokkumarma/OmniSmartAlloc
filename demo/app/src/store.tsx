import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type AgentEvent, type AgentJob, type AppState, type Channel, type Federated, type Savings } from "./api";
import { useOverlays } from "./ui/overlays";

type Busy = "scenario" | "history" | "reset" | "agent" | "bulk";

interface Store {
  s: AppState | null;
  events: AgentEvent[];
  savings: Savings | null;
  fed: Federated | null;
  fedLoading: boolean;
  offline: boolean;
  busy: Partial<Record<Busy, boolean>>;
  agent: AgentJob | null;
  refresh: () => Promise<void>;
  loadFederated: () => Promise<void>;
  runAgent: () => Promise<void>;
  placeOrder: (channel: Channel, sku: string, qty: number) => Promise<boolean>;
  settle: (id: string, action: "fulfill" | "partial" | "cancel", body?: { qty?: number; reason?: string }) => Promise<void>;
  settleAllOpen: (action: "fulfill" | "cancel") => Promise<void>;
  approve: (id: string) => Promise<void>;
  deny: (id: string) => Promise<void>;
  scenario1: () => Promise<void>;
  history: () => Promise<void>;
  reset: () => Promise<void>;
  setAutoRun: (enabled: boolean) => Promise<void>;
}
const Ctx = createContext<Store | null>(null);
export const useStore = () => useContext(Ctx)!;

const POLL_MS = 10_000;

export function StoreProvider({ children }: { children: ReactNode }) {
  const { toast, confirm, prompt } = useOverlays();
  const [s, setS] = useState<AppState | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [savings, setSavings] = useState<Savings | null>(null);
  const [fed, setFed] = useState<Federated | null>(null);
  const [fedLoading, setFedLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState<Partial<Record<Busy, boolean>>>({});
  const [agent, setAgent] = useState<AgentJob | null>(null);
  const agentTimer = useRef<number>(0);

  const refresh = useCallback(async () => {
    try {
      const [st, log] = await Promise.all([api.state(), api.agentLog()]);
      setS(st.data);
      setEvents(log.data.events);
      setSavings(log.data.savings ?? null);
      setAgent((a) => (a?.running ? a : st.data.agent));
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  const loadFederated = useCallback(async () => {
    setFedLoading(true);
    try {
      setFed((await api.federated()).data);
    } catch {
      setFed({ ok: false, sql: "", error: "Could not reach the demo server" });
    } finally {
      setFedLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    loadFederated();
    const t = window.setInterval(() => document.visibilityState === "visible" && refresh(), POLL_MS);
    const f = window.setInterval(() => document.visibilityState === "visible" && loadFederated(), 30_000);
    return () => {
      window.clearInterval(t);
      window.clearInterval(f);
      window.clearInterval(agentTimer.current);
    };
  }, [refresh, loadFederated]);

  /** Disable the action while it runs; a network failure becomes a toast. */
  const withBusy = useCallback(async (key: Busy, fn: () => Promise<void>) => {
    setBusy((b) => ({ ...b, [key]: true }));
    try {
      await fn();
    } catch (e) {
      toast(`Could not reach the demo server: ${(e as Error).message}`, false);
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
  }, [toast]);

  const runAgent = useCallback(async () => {
    setBusy((b) => ({ ...b, agent: true }));
    try {
      const r = await api.runAgent();
      if (!r.ok) {
        toast(r.data.error ?? "Could not start the agent", false);
        setBusy((b) => ({ ...b, agent: false }));
        return;
      }
    } catch (e) {
      toast(`Could not reach the demo server: ${(e as Error).message}`, false);
      setBusy((b) => ({ ...b, agent: false }));
      return;
    }
    setAgent({ running: true, steps: [], tail: "", ok: null });
    window.clearInterval(agentTimer.current);
    agentTimer.current = window.setInterval(async () => {
      try {
        const j = (await api.agentStatus()).data;
        setAgent(j);
        if (!j.running) {
          window.clearInterval(agentTimer.current);
          setBusy((b) => ({ ...b, agent: false }));
          await refresh();
          if (j.ok === false) {
            const last = (j.tail || "").trim().split("\n").filter(Boolean).pop() || "no output";
            toast(`The agent run did not finish: ${last.slice(0, 300)}`, false);
          } else {
            toast(`Allocation cycle finished: ${j.steps.length} steps`, true);
          }
        }
      } catch {
        /* keep polling; a transient failure should not end the run view */
      }
    }, 1500);
  }, [refresh, toast]);

  const placeOrder = useCallback(async (channel: Channel, sku: string, qty: number) => {
    try {
      const r = await api.placeOrder(channel, sku, qty);
      toast(r.ok && r.data.stored_in ? `Order placed: ${qty}× ${sku} on ${channel}, saved to ${r.data.stored_in.type} ${r.data.stored_in.location}` : r.data.error ?? "Order failed", r.ok);
      await refresh();
      return r.ok;
    } catch (e) {
      toast(`Could not reach the demo server: ${(e as Error).message}`, false);
      return false;
    }
  }, [refresh, toast]);

  const settle = useCallback(async (id: string, action: "fulfill" | "partial" | "cancel", body?: { qty?: number; reason?: string }) => {
    try {
      const r = await api.settle(id, action, body);
      if (!r.ok) toast(r.data.error ?? "Action failed", false);
      else toast({ fulfill: "Order fulfilled", partial: "Partial shipment recorded", cancel: "Order cancelled" }[action], true);
    } catch (e) {
      toast(`Could not reach the demo server: ${(e as Error).message}`, false);
    }
    await refresh();
  }, [refresh, toast]);

  const settleAllOpen = useCallback(async (action: "fulfill" | "cancel") => {
    if (!s) return;
    const open = s.orders.filter((o) => o.status === "open");
    if (!open.length) return toast("There are no open orders.", true);
    const ok = await confirm({
      title: action === "fulfill" ? `Fulfill ${open.length} open orders?` : `Cancel ${open.length} open orders?`,
      body: action === "fulfill" ? "Ships every remaining unit and updates on-hand stock." : "Releases every reserved unit back to stock.",
      confirmLabel: action === "fulfill" ? "Fulfill all" : "Cancel all", destructive: action === "cancel",
    });
    if (!ok) return;
    await withBusy("bulk", async () => {
      for (const o of open) await api.settle(o.id, action);
      toast(`${open.length} orders ${action === "fulfill" ? "fulfilled" : "cancelled"}`, true);
      await refresh();
    });
  }, [s, confirm, withBusy, toast, refresh]);

  const approve = useCallback(async (id: string) => {
    const r = await api.approve(id);
    toast(r.ok ? "Approved: the allocation is written" : r.data.error ?? "Approve failed", r.ok);
    await refresh();
  }, [refresh, toast]);

  const deny = useCallback(async (id: string) => {
    const reason = await prompt({
      title: "Deny this change?", body: "The agent reads your reason on its next run.", label: "Reason", confirmLabel: "Deny change",
      placeholder: "e.g. Amazon promo starts Friday, keep its allocation", required: "A reason is required to deny.", destructive: true,
    });
    if (reason === null) return;
    const r = await api.deny(id, reason);
    toast(r.ok ? "Denied: nothing was written" : r.data.error ?? "Deny failed", r.ok);
    await refresh();
  }, [prompt, refresh, toast]);

  const scenario1 = useCallback(async () => {
    const ok = await confirm({
      title: "Load Scenario 1?",
      body: "LAMP-002: DTC selling ahead of forecast while Amazon lags. This replaces all LAMP-002 orders, stock, inbound, margins and allocation; other SKUs are untouched.",
      confirmLabel: "Load scenario",
    });
    if (!ok) return;
    await withBusy("scenario", async () => {
      const r = (await api.scenario1()).data;
      const bad = r.checks.filter((c) => c.ok === false);
      const info = r.checks.filter((c) => c.ok === null && c.name.startsWith("engine preview"));
      toast(`Scenario 1 loaded for LAMP-002: ${r.summary.orders_total} orders, on hand ${r.summary.on_hand}, sellable ${r.summary.sellable}.\n`
        + `Checks: ${r.passed} passed, ${r.failed} failed` + (bad.length ? `\n– ${bad.map((c) => c.name).join("\n– ")}` : "")
        + (info.length ? `\n\n${info.map((c) => `${c.name}: ${c.detail}`).join("\n")}` : ""), r.failed === 0);
      await refresh();
      await loadFederated();
    });
  }, [confirm, withBusy, toast, refresh, loadFederated]);

  const history = useCallback(() => withBusy("history", async () => {
    const r = (await api.history()).data;
    toast(`Generated ${r.generated} orders: ${Object.entries(r.by_channel).map(([c, n]) => `${c} ${n}`).join(", ")}`, true);
    await refresh();
  }), [withBusy, toast, refresh]);

  const reset = useCallback(async () => {
    const ok = await confirm({
      title: "Reset the demo?", body: "This wipes all orders and restores the baseline stock, allocation split and channel margins.",
      confirmLabel: "Reset demo", destructive: true,
    });
    if (!ok) return;
    await withBusy("reset", async () => {
      const r = (await api.reset()).data;
      toast(r.reset ? `Demo reset: ${r.orders_restored} orders restored` : r.error ?? "Reset failed", !!r.reset);
      await refresh();
    });
  }, [confirm, withBusy, toast, refresh]);

  const setAutoRun = useCallback(async (enabled: boolean) => {
    try {
      const r = await api.setAutoRun(enabled);
      setS((st) => (st ? { ...st, agent_auto: r.data.agent_auto } : st));
      toast(r.data.agent_auto ? "Auto-run on: the agent re-runs after orders ship and approvals change" : "Auto-run off: run the allocation cycle yourself", true);
    } catch (e) {
      toast(`Could not reach the demo server: ${(e as Error).message}`, false);
    }
  }, [toast]);

  return (
    <Ctx.Provider value={{ s, events, savings, fed, fedLoading, offline, busy, agent, refresh, loadFederated, runAgent, placeOrder, settle, settleAllOpen, approve, deny, scenario1, history, reset, setAutoRun }}>
      {children}
    </Ctx.Provider>
  );
}
