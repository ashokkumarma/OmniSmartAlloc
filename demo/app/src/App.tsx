import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  LayoutGrid, Package, Boxes, SlidersHorizontal, Store, Database, Play, FlaskConical, History, RotateCcw, Search, CornerDownLeft, BookOpen, type LucideIcon,
  ExternalLink,
} from "lucide-react";
import { AnimatePresence, m } from "motion/react";
import { useStore } from "./store";
import { PAGE, SPRING } from "./motion";
import { CHANNELS } from "./format";
import { Landing } from "./landing/Landing";
import { content as landingContent } from "./landing/content";
import { ThemeButton } from "./theme";
import { Button } from "./ui/Button";
import { MenuSheet } from "./ui/MenuSheet";
import { Sheet } from "./ui/overlays";
import { PageSkeleton, Spinner } from "./ui/kit";
import { Overview } from "./views/Overview";
import { Orders } from "./views/Orders";
import { Inventory } from "./views/Inventory";
import { SkuDetail } from "./views/SkuDetail";
import { Agent } from "./views/Agent";
import { Storefronts } from "./views/Storefronts";
import { Sources } from "./views/Sources";
import { Instructions } from "./views/Instructions";

export type Route = "instructions" | "overview" | "orders" | "inventory" | "agent" | "storefronts" | "sources";
const PATHS: Record<Route, string> = { instructions: "/instructions", overview: "/app", orders: "/orders", inventory: "/inventory", agent: "/agent", storefronts: "/storefronts", sources: "/sources" };
const ALIASES: Record<string, Route> = { "/ops": "overview", "/dashboard": "overview", "/channels": "storefronts", "/smart-allocation": "agent" };
// Two systems, as in the guided demo: the OMS takes orders, the IMS fulfils them and shows the agent's decisions.
type Group = "oms" | "ims";
const GROUPS: { id: Group; label: string }[] = [{ id: "oms", label: "Order management (OMS)" }, { id: "ims", label: "Inventory management (IMS)" }];
const NAV: { route: Route; label: string; icon: LucideIcon; group: Group }[] = [
  { route: "instructions", label: "Instructions", icon: BookOpen, group: "oms" },
  { route: "storefronts", label: "Storefronts", icon: Store, group: "oms" },
  { route: "agent", label: "Smart Allocation", icon: SlidersHorizontal, group: "ims" },
  { route: "overview", label: "Dashboard", icon: LayoutGrid, group: "ims" },
  { route: "orders", label: "Orders", icon: Package, group: "ims" },
  { route: "inventory", label: "Inventory", icon: Boxes, group: "ims" },
  { route: "sources", label: "Data sources", icon: Database, group: "ims" },
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
  const [menu, setMenu] = useState(false);

  const go = useCallback((r: Route, to?: string) => {
    const path = r === "inventory" && to ? `/inventory/${to}` : PATHS[r];
    if (path !== location.pathname) history.pushState(null, "", path);
    setLoc({ route: r, sku: r === "inventory" && to ? to : null });
    window.scrollTo({ top: 0 });
  }, []);

  useEffect(() => {
    const onPop = () => setLoc(parsePath(location.pathname));
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("popstate", onPop);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("popstate", onPop);
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

  const navItems = (onPick?: () => void, group?: Group) => NAV.filter((n) => !group || n.group === group).map(({ route: r, label, icon: Icon }) => {
    const c = counts[r];
    return (
      <button key={r} className="nav-item" aria-current={route === r ? "page" : undefined} onClick={() => { go(r); onPick?.(); }}>
        {route === r && <m.span layoutId="nav-ind" className="nav-ind" transition={SPRING} />}
        <Icon size={17} aria-hidden />
        <span>{label}</span>
        {c && c.n > 0 && <span className={`count ${c.alert ? "alert" : ""}`} aria-label={`${c.n} ${c.alert ? "awaiting approval" : "open"}`}>{c.n}</span>}
      </button>
    );
  });

  let view: ReactNode;
  if (!s) view = <div className={offline ? "empty" : undefined} style={{ marginTop: offline ? 80 : 0 }}>{offline ? <><b>Cannot reach the demo server</b>Start it with <span className="mono">scripts/start_demo.py</span>.</> : <PageSkeleton />}</div>;
  else if (route === "instructions") view = <Instructions go={go} />;
  else if (route === "overview") view = <Overview go={go} />;
  else if (route === "orders") view = <Orders />;
  else if (route === "inventory") view = sku ? <SkuDetail sku={sku} go={go} /> : <Inventory go={go} />;
  else if (route === "agent") view = <Agent />;
  else if (route === "storefronts") view = <Storefronts />;
  else view = <Sources />;

  const autoRun = (
    <label className="auto-run" title="Re-run the agent automatically after orders ship, approvals change or a scenario loads">
      <input type="checkbox" checked={store.s?.agent_auto !== false} onChange={(e) => store.setAutoRun(e.target.checked)} />
      Auto-run
    </label>
  );

  const openPath = (to: string) => { history.pushState(null, "", to); setLoc(parsePath(to)); window.scrollTo({ top: 0 }); };
  if (loc.landing) {
    // the orbit in the hero is drawn from the first SKU that has caps
    const alloc = s?.skus.find((p) => p.allocation)?.allocation;
    return <Landing c={landingContent} open={openPath} data={alloc ? CHANNELS.map((c) => alloc[c] ?? 0) : undefined} />;
  }

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Main">
        <div className="brand">
          <a className="wordmark" href="/" onClick={(e) => { e.preventDefault(); openPath("/"); }}>OmniSmartAlloc</a>
          <small>Inventory allocation</small>
        </div>
        <button className="nav-item search-item" onClick={() => setPalette(true)}>
          <Search size={17} aria-hidden /><span>Search</span><span className="kbd">⌘K</span>
        </button>
        {GROUPS.map((g) => (
          <div key={g.id}>
            <div className="nav-label">{g.label}</div>
            <nav className="nav" aria-label={g.label}>{navItems(undefined, g.id)}</nav>
          </div>
        ))}
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
        <header className="appbar">
          <div className="appbar-in">
            <a className="wordmark" href="/" onClick={(e) => { e.preventDefault(); openPath("/"); }}>OmniSmartAlloc</a>
            <span className="spacer" />
            <div className="appbar-end">
              {autoRun}
              <ThemeButton className="theme-switch" />
              <button type="button" className="menu-toggle" aria-expanded={menu} onClick={() => setMenu(true)}>Menu</button>
              <Button variant="primary" onClick={store.runAgent} disabled={busy.agent}>
                {busy.agent && <Spinner />}
                {busy.agent ? "Agent running…" : <span>Run <span className="hide-sm">allocation </span>cycle</span>}
              </Button>
            </div>
          </div>
        </header>
        <AnimatePresence>
        {menu && (
          <MenuSheet title="OmniSmartAlloc" onClose={() => setMenu(false)}
            links={NAV.map((n) => ({ label: n.label, href: PATHS[n.route], current: route === n.route, onSelect: () => go(n.route) }))}>
            <Button onClick={() => { setMenu(false); setPalette(true); }}>Search</Button>
            <Button onClick={store.scenario1} disabled={busy.scenario}>{busy.scenario ? "Loading scenario…" : "Load Scenario 1"}</Button>
            <Button onClick={store.history} disabled={busy.history}>{busy.history ? "Generating…" : "Generate history"}</Button>
            <Button onClick={store.reset} disabled={busy.reset}>{busy.reset ? "Resetting…" : "Reset demo"}</Button>
            {autoRun}
            <ThemeButton />
            <a className="btn btn-tertiary" href="/oms">OMS (classic)</a>
            <a className="btn btn-tertiary" href="/ims">IMS (classic)</a>
          </MenuSheet>
        )}
        </AnimatePresence>
        <m.main className="content" key={s ? `${route}/${sku ?? ""}` : "loading"} {...PAGE}>{view}</m.main>
      </div>

      <AnimatePresence>{palette && <Palette close={() => setPalette(false)} go={go} />}</AnimatePresence>
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
