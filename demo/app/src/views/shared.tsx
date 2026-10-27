import { useEffect, useRef, useState } from "react";
import { Button } from "../ui/Button";
import { Check, X, SplitSquareHorizontal, CheckCircle2, XCircle, SlidersHorizontal } from "lucide-react";
import type { AgentJob, Order } from "../api";
import { STATUS_TONE, when } from "../format";
import { useStore } from "../store";
import { Sheet } from "../ui/overlays";
import { Card, CardHead, ChanTag, Pill, Spinner } from "../ui/kit";
import { gsap, reducedMotion, useGSAP } from "../motion";

/** One order with its status and, when it is still open or partial, the fulfilment actions. */
export function OrderRow({ o, actions = true }: { o: Order; actions?: boolean }) {
  const { settle } = useStore();
  const [partial, setPartial] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const run = async (a: "fulfill" | "cancel") => {
    setWorking(a);
    await settle(o.id, a);
    setWorking(null);
  };
  const last = (o.partial_shipments || []).filter((p) => p.reason).slice(-1)[0];
  const canAct = actions && (o.status === "open" || o.status === "partial");
  return (
    <div className="row">
      <div style={{ width: 96 }}><ChanTag name={o.channel} /></div>
      <div className="grow">
        <div><b className="num">{o.qty}×</b> {o.sku} <span className="muted tiny mono">#{o.id}</span></div>
        <div className="meta">
          {when(o.ts)}
          {o.fulfilled_qty > 0 && <>, shipped {o.fulfilled_qty}/{o.qty}</>}
          {last && <>, partial reason: {last.reason}</>}
        </div>
      </div>
      <Pill tone={STATUS_TONE[o.status]}>{o.status}</Pill>
      {canAct && (
        <div className="acts">
          <Button variant="secondary" onClick={() => run("fulfill")} disabled={!!working}>{working === "fulfill" ? <Spinner /> : <Check size={14} aria-hidden />}Fulfill all</Button>
          {o.remaining > 1 && <Button variant="secondary" onClick={() => setPartial(true)} disabled={!!working}><SplitSquareHorizontal size={14} aria-hidden />Partial</Button>}
          <Button variant="secondary" danger onClick={() => run("cancel")} disabled={!!working}>{working === "cancel" ? <Spinner /> : <X size={14} aria-hidden />}Cancel</Button>
        </div>
      )}
      {partial && <PartialSheet o={o} close={() => setPartial(false)} />}
    </div>
  );
}

/** Ship part of an order now. Same rules as the server: 1 to remaining − 1 units. */
function PartialSheet({ o, close }: { o: Order; close: () => void }) {
  const { settle } = useStore();
  const [qty, setQty] = useState("1");
  const [reason, setReason] = useState("");
  const q = Number(qty);
  const ok = Number.isInteger(q) && q >= 1 && q < o.remaining;
  const submit = async () => {
    if (!ok) return;
    close();
    await settle(o.id, "partial", { qty: q, reason });
  };
  return (
    <Sheet onClose={close} labelledBy="pm-title">
      <div>
        <h2 id="pm-title">Partial fulfilment</h2>
        <p style={{ marginTop: 4 }}><ChanTag name={o.channel} />, {o.qty}× {o.sku} <span className="mono tiny">#{o.id}</span></p>
      </div>
      <form className="stack" style={{ gap: 16 }} onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <div className="field">
          <label htmlFor="pm-qty">Quantity to ship now</label>
          <input id="pm-qty" className="input" type="number" min={1} max={o.remaining - 1} step={1} value={qty} autoFocus
            onChange={(e) => setQty(e.target.value)} aria-invalid={!ok} aria-describedby="pm-help" />
          <span id="pm-help" className="small" style={{ color: ok ? "var(--label-2)" : "var(--bad)" }}>
            {ok
              ? <>Ordered {o.qty}. Filled {o.fulfilled_qty}, will be <b>{o.fulfilled_qty + q}</b>. Unfulfilled {o.remaining}, will be <b>{o.remaining - q}</b>.</>
              : <>Enter a quantity between 1 and {o.remaining - 1}. Use Fulfill all to ship everything.</>}
          </span>
        </div>
        <div className="field">
          <label htmlFor="pm-reason">Reason <span className="muted">(optional)</span></label>
          <textarea id="pm-reason" className="textarea" rows={2} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. damaged units in bin, customer asked to split the shipment" />
        </div>
        <div className="acts" style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button onClick={close}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={!ok}>Ship {ok ? q : ""} {q === 1 ? "unit" : "units"}</Button>
        </div>
      </form>
    </Sheet>
  );
}

type RunState = "queued" | "running" | "waiting" | "done" | "failed";
const RUN_LABEL: Record<RunState, string> = { queued: "Queued", running: "Running", waiting: "Waiting for you", done: "Done", failed: "Failed" };

/** Live trace of the allocation agent: status, elapsed time, one row per tool call, and a lamp for each system it has read. */
export function AgentRunCard({ job, pending = 0, onRetry }: { job: AgentJob | null; pending?: number; onRetry?: () => void }) {
  const list = useRef<HTMLOListElement>(null);
  const seen = useRef(0);
  const started = useRef<number | null>(null);
  const [secs, setSecs] = useState(0);
  const steps = job?.steps ?? [];
  useGSAP(() => {
    const rows = list.current?.querySelectorAll("li") ?? [];
    const fresh = Array.from(rows).slice(seen.current);
    seen.current = rows.length;
    if (fresh.length && !reducedMotion()) gsap.from(fresh, { opacity: 0, duration: 0.2, clearProps: "opacity" });
    if (job?.running && list.current) list.current.scrollTop = list.current.scrollHeight;
  }, { dependencies: [steps.length] });
  const running = !!job?.running;
  useEffect(() => {
    if (!running) { started.current = null; return; }
    started.current ??= Date.now();
    const t = window.setInterval(() => setSecs(Math.floor((Date.now() - (started.current ?? Date.now())) / 1000)), 500);
    return () => window.clearInterval(t);
  }, [running]);
  if (!job || (!job.running && !steps.length)) return null;

  const state: RunState = job.running ? (steps.length ? "running" : "queued") : job.ok === false ? "failed" : pending > 0 ? "waiting" : "done";
  const sources = [...new Set(steps.flatMap((x) => x.sources))].sort();
  const lastSources = new Set(job.running ? steps[steps.length - 1]?.sources ?? [] : []);
  const reason = job.ok === false ? job.tail.trim().split("\n").filter(Boolean).pop() : undefined;
  return (
    <Card aria-live="polite" className="reveal">
      <CardHead
        title={<span style={{ display: "inline-flex", gap: 10, alignItems: "center" }}><SlidersHorizontal size={16} style={{ color: "var(--accent-text)" }} aria-hidden />Agent run<span className={`run-status ${state}`} role="status"><i aria-hidden />{RUN_LABEL[state]}</span></span>}
        sub={`${steps.length} ${steps.length === 1 ? "step" : "steps"}${secs > 0 || job.running ? `, ${secs} s` : ""}${state === "waiting" ? `, ${pending} ${pending === 1 ? "change waits" : "changes wait"} for your approval` : ""}`}>
        {job.running && <Spinner size={16} />}
      </CardHead>
      <div className="card-body">
        {state === "failed" && (
          <div className="inline-error" role="alert">
            <div><b>The run did not finish.</b>{reason && <span className="small"> {reason.slice(0, 300)}</span>}</div>
            {onRetry && <Button variant="secondary" onClick={onRetry}>Run again</Button>}
          </div>
        )}
        {steps.length ? (
          <ol ref={list} style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 280, overflow: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
            {steps.map((st) => (
              <li key={st.n} style={{ display: "grid", gridTemplateColumns: "24px 20px minmax(0,1fr) auto", gap: 8, alignItems: "baseline", padding: "6px 0", borderTop: "1px solid var(--separator)" }}>
                <span className="muted tiny num">{st.n}</span>
                {st.ok ? <CheckCircle2 size={15} style={{ color: "var(--ok)", alignSelf: "center" }} aria-label="ok" /> : <XCircle size={15} style={{ color: "var(--bad)", alignSelf: "center" }} aria-label="failed" />}
                <span>{st.text}{st.error && <span className="small" style={{ display: "block", color: "var(--bad)" }}>{st.error}</span>}</span>
                <span style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>{st.sources.map((x) => <Pill key={x} tone="info">{x}</Pill>)}</span>
              </li>
            ))}
          </ol>
        ) : <p className="muted" style={{ margin: 0 }}>Starting the agent...</p>}
        {sources.length > 0 && (
          <div className="lamps" aria-label="Systems the agent has read">
            <span className="small muted">Read so far</span>
            {sources.map((x) => <span key={x} className={`lamp ${lastSources.has(x) ? "live" : ""}`}><i aria-hidden />{x}</span>)}
          </div>
        )}
      </div>
    </Card>
  );
}
