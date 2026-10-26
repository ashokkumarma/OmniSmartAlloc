import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  LayoutGrid, Package, Boxes, Sparkles, Store, Database, Play, FlaskConical, History, RotateCcw, Search, CornerDownLeft, type LucideIcon,
  ExternalLink,
} from "lucide-react";
import { useStore } from "./store";
import { CHANNELS } from "./format";
import { Landing } from "./landing/Landing";
import { content as landingContent } from "./landing/content";
import { ThemeButton } from "./theme";
import { Sheet } from "./ui/overlays";
import { PageSkeleton, Spinner } from "./ui/kit";
import { Overview } from "./views/Overview";
import { Orders } from "./views/Orders";
import { Inventory } from "./views/Inventory";
import { SkuDetail } from "./views/SkuDetail";
import { Agent } from "./views/Agent";
import { Storefronts } from "./views/Storefronts";
import { Sources } from "./views/Sources";

export type Route = "overview" | "orders" | "inventory" | "agent" | "storefronts" | "sources";
const PATHS: Record<Route, string> = { overview: "/app", orders: "/orders", inventory: "/inventory", agent: "/agent", storefronts: "/storefronts", sources: "/sources" };
const ALIASES: Record<string, Route> = { "/ops": "overview", "/channels": "storefronts" };
const NAV: { route: Route; label: string; icon: LucideIcon }[] = [
  { route: "overview", label: "Overview", icon: LayoutGrid },
  { route: "orders", label: "Orders", icon: Package },
  { route: "inventory", label: "Inventory", icon: Boxes },
  { route: "agent", label: "Agent", icon: Sparkles },
  { route: "storefronts", label: "Storefronts", icon: Store },
  { route: "sources", label: "Data sources", icon: Database },
];

/** The section a URL belongs to; /inventory/<SKU> is a product page inside Inventory. */
function parsePath(path: string): { route: Route; sku: string | null; landing?: boolean } {
  const p = path.replace(/\/+$/, "") || "/";
  if (p === "/") return { route: "overview", sku: null, landing: true };
  const m = /^\/inventory\/([A-Za-z0-9-]{1,32})$/.exec(p);
  if (m) return { route: "inventory", sku: m[1] };
  return { route: ALIASES[p] ?? (Object.entries(PATHS).find(([, v]) => v === p)?.[0] as Route) ?? "overview", sku: null };
}

export default function App() {
  const store = useStore();
  const [loc, setLoc] = useState(() => parsePath(location.pathname));
  const { route, sku } = loc;
  const [palette, setPalette] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  const go = useCallback((r: Route, to?: string) => {
    const path = r === "inventory" && to ? `/inventory/${to}` : PATHS[r];
    if (path !== location.pathname) history.pushState(null, "", path);
    setLoc({ route: r, sku: r === "inventory" && to ? to : null });
    window.scrollTo({ top: 0 });
  }, []);

  useEffect(() => {
    const onPop = () => setLoc(parsePath(location.pathname));
    const onScroll = () => setScrolled(window.scrollY > 8);
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("popstate", onPop);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    document.title = loc.landing ? "OmniSmartAlloc: inventory allocation agent" : `${sku ?? NAV.find((n) => n.route === route)?.label} | OmniSmartAlloc`;
  }, [route, sku, loc.landing]);

  const { s, events, busy, fed, offline } = store;
  const pending = new Set(events.filter((e) => e.status === "pending").map((e) => e.approval_id)).size;
  const openOrders = s ? s.totals.status_counts.open + s.totals.status_counts.partial : 0;
  const counts: Partial<Record<Route, { n: number; alert?: boolean }>> = { orders: { n: openOrders }, agent: { n: pending, alert: pending > 0 } };
  const title = NAV.find((n) => n.route === route)!.label;

  const navItems = (onPick?: () => void) => NAV.map(({ route: r, label, icon: Icon }) => {
    const c = counts[r];
    return (
      <button key={r} className="nav-item" aria-current={route === r ? "page" : undefined} onClick={() => { go(r); onPick?.(); }}>
        <Icon size={17} aria-hidden />
        <span>{label}</span>
        {c && c.n > 0 && <span className={`count ${c.alert ? "alert" : ""}`} aria-label={`${c.n} ${c.alert ? "awaiting approval" : "open"}`}>{c.n}</span>}
      </button>
    );
  });

  let view: ReactNode;
  if (!s) view = <div className={offline ? "empty" : undefined} style={{ marginTop: offline ? 80 : 0 }}>{offline ? <><b>Cannot reach the demo server</b>Start it with <span className="mono">scripts/start_demo.py</span>.</> : <PageSkeleton />}</div>;
  else if (route === "overview") view = <Overview go={go} />;
  else if (route === "orders") view = <Orders />;
  else if (route === "inventory") view = sku ? <SkuDetail sku={sku} go={go} /> : <Inventory go={go} />;
  else if (route === "agent") view = <Agent />;
  else if (route === "storefronts") view = <Storefronts />;
  else view = <Sources />;

  const openPath = (to: string) => { history.pushState(null, "", to); setLoc(parsePath(to)); window.scrollTo({ top: 0 }); };
  if (loc.landing) {
    // the orbit in the hero is drawn from the first SKU that has caps
    const alloc = s?.skus.find((p) => p.allocation)?.allocation;
    return <Landing c={landingContent} open={openPath} data={alloc ? CHANNELS.map((c) => alloc[c] ?? 0) : undefined} />;
  }

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Main">
        <a className="brand" href="/" onClick={(e) => { e.preventDefault(); openPath("/"); }}>
          <span className="brand-mark" aria-hidden><Boxes size={16} /></span>
          <span>OmniSmartAlloc<small>Inventory allocation</small></span>
        </a>
        <button className="btn sm" style={{ justifyContent: "flex-start", color: "var(--label-2)", margin: "0 4px 4px" }} onClick={() => setPalette(true)}>
          <Search size={14} aria-hidden /> Search <span style={{ marginInlineStart: "auto" }} className="kbd">⌘K</span>
        </button>
        <div className="nav-label">Operate</div>
        <nav className="nav" aria-label="Sections">{navItems()}</nav>
        <div className="nav-label">Demo data</div>
        <div className="nav">
          <button className="nav-item" onClick={store.scenario1} disabled={busy.scenario}>{busy.scenario ? <Spinner size={17} /> : <FlaskConical size={17} aria-hidden />}<span>{busy.scenario ? "Loading scenario…" : "Scenario 1"}</span></button>
          <button className="nav-item" onClick={store.history} disabled={busy.history}>{busy.history ? <Spinner size={17} /> : <History size={17} aria-hidden />}<span>{busy.history ? "Generating…" : "Generate history"}</span></button>
          <button className="nav-item" onClick={store.reset} disabled={busy.reset}>{busy.reset ? <Spinner size={17} /> : <RotateCcw size={17} aria-hidden />}<span>{busy.reset ? "Resetting…" : "Reset demo"}</span></button>
          {/* The original OMS and IMS pages: the guided demo walkthrough runs there. */}
          <a className="nav-item" href="/oms"><ExternalLink size={17} aria-hidden /><span>OMS (classic)</span></a>
          <a className="nav-item" href="/ims"><ExternalLink size={17} aria-hidden /><span>IMS (classic)</span></a>
        </div>
        <div className="sidebar-foot" aria-label="System status">
          <div className="status-row"><span className={`dot ${offline ? "bad" : "ok"}`} />Channel stores {offline ? "unreachable" : "connected"}</div>
          <div className="status-row" title={fed?.error}><span className={`dot ${fed?.ok ? "ok" : fed ? "warn" : ""}`} />Zetaris {fed?.ok ? "connected" : fed ? "not connected" : "checking…"}</div>
          <div className="status-row"><span className={`dot ${store.agent?.running ? "ok" : ""}`} />Agent {store.agent?.running ? "running" : "idle"}</div>
        </div>
      </aside>

      <div className="main">
        <header className={`toolbar ${scrolled ? "scrolled" : ""}`}>
          <span className="toolbar-title">{title}</span>
          <span className="spacer" />
          <ThemeButton />
          <label className="auto-run" title="Re-run the agent automatically after orders ship, approvals change or a scenario loads">
            <input type="checkbox" checked={store.s?.agent_auto !== false} onChange={(e) => store.setAutoRun(e.target.checked)} />
            Auto-run
          </label>
          <button className="btn primary" onClick={store.runAgent} disabled={busy.agent}>
            {busy.agent ? <Spinner /> : <Play size={14} aria-hidden fill="currentColor" />}
            {busy.agent ? "Agent running…" : "Run allocation cycle"}
          </button>
        </header>
        <nav className="mobile-nav" aria-label="Main">
          {navItems()}
          <span className="mobile-sep" aria-hidden />
          <button className="nav-item" onClick={() => setPalette(true)}><Search size={17} aria-hidden /><span>Search</span></button>
          <button className="nav-item" onClick={store.scenario1} disabled={busy.scenario}><FlaskConical size={17} aria-hidden /><span>Scenario 1</span></button>
          <button className="nav-item" onClick={store.history} disabled={busy.history}><History size={17} aria-hidden /><span>Generate history</span></button>
          <button className="nav-item" onClick={store.reset} disabled={busy.reset}><RotateCcw size={17} aria-hidden /><span>Reset demo</span></button>
        </nav>
        <main className="content" key={`${route}/${sku ?? ""}`}>{view}</main>
      </div>

      {palette && <Palette close={() => setPalette(false)} go={go} />}
    </div>
  );
}

interface Cmd { id: string; label: string; hint: string; icon: LucideIcon; run: () => void }

/** ⌘K / Ctrl+K: jump to a section, a SKU, or run a demo action. */
function Palette({ close, go }: { close: () => void; go: (r: Route, sku?: string) => void }) {
  const store = useStore();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const list = useRef<HTMLUListElement>(null);
  const cmds = useMemo<Cmd[]>(() => {
    const nav = NAV.map((n) => ({ id: n.route, label: n.label, hint: "Go to", icon: n.icon, run: () => go(n.route) }));
    const actions: Cmd[] = [
      { id: "run", label: "Run allocation cycle", hint: "Action", icon: Play, run: store.runAgent },
      { id: "scn", label: "Load Scenario 1", hint: "Demo data", icon: FlaskConical, run: store.scenario1 },
      { id: "hist", label: "Generate history orders", hint: "Demo data", icon: History, run: store.history },
      { id: "reset", label: "Reset demo", hint: "Demo data", icon: RotateCcw, run: store.reset },
    ];
    const skus = (store.s?.skus ?? []).map((p) => ({ id: p.sku, label: `${p.sku}, ${p.title}`, hint: "Product", icon: Boxes, run: () => go("inventory", p.sku) }));
    return [...nav, ...actions, ...skus];
  }, [store, go]);
  const shown = cmds.filter((c) => c.label.toLowerCase().includes(q.trim().toLowerCase()));
  const pick = (c?: Cmd) => { if (!c) return; close(); c.run(); };

  useEffect(() => setSel(0), [q]);
  useEffect(() => { list.current?.querySelector<HTMLElement>(`[data-i="${sel}"]`)?.scrollIntoView({ block: "nearest" }); }, [sel]);

  return (
    <Sheet onClose={close} title="Search" className="palette">
      <input className="input" autoFocus placeholder="Search sections, SKUs and actions" value={q} aria-label="Search" role="combobox" aria-expanded aria-controls="palette-list"
        aria-activedescendant={shown[sel] ? `cmd-${shown[sel].id}` : undefined}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setSel((i) => Math.min(shown.length - 1, i + 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setSel((i) => Math.max(0, i - 1)); }
          if (e.key === "Enter") pick(shown[sel]);
        }} />
      <ul ref={list} id="palette-list" role="listbox">
        {shown.map((c, i) => (
          <li key={c.id}>
            <button id={`cmd-${c.id}`} data-i={i} role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => pick(c)}>
              <c.icon size={16} aria-hidden />
              <span style={{ flex: 1 }}>{c.label}</span>
              <span className="muted tiny">{c.hint}</span>
              {i === sel && <CornerDownLeft size={14} aria-hidden />}
            </button>
          </li>
        ))}
        {!shown.length && <li className="empty small">No matches</li>}
      </ul>
    </Sheet>
  );
}
