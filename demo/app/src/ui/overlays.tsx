import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, m } from "motion/react";
import { Button } from "./Button";
import { CheckCircle2, AlertCircle, X } from "lucide-react";
import { NUDGE, SPRING, T_BASE, T_FAST } from "../motion";

interface Toast { id: number; msg: string; ok: boolean }
interface ConfirmOpts { title: string; body?: ReactNode; confirmLabel?: string; destructive?: boolean }
interface PromptOpts extends ConfirmOpts { label: string; placeholder?: string; required?: string }
type Dialog =
  | ({ kind: "confirm"; resolve: (v: boolean) => void } & ConfirmOpts)
  | ({ kind: "prompt"; resolve: (v: string | null) => void } & PromptOpts);

interface Overlays {
  toast: (msg: string, ok?: boolean) => void;
  confirm: (o: ConfirmOpts) => Promise<boolean>;
  prompt: (o: PromptOpts) => Promise<string | null>;
}
const Ctx = createContext<Overlays | null>(null);
export const useOverlays = () => useContext(Ctx)!;

export function OverlayProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const seq = useRef(0);

  const toast = useCallback((msg: string, ok = true) => {
    const id = ++seq.current;
    setToasts((t) => [...t.slice(-3), { id, msg, ok }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ok ? 5000 : 8000);
  }, []);
  const confirm = useCallback((o: ConfirmOpts) => new Promise<boolean>((resolve) => setDialog({ kind: "confirm", resolve, ...o })), []);
  const prompt = useCallback((o: PromptOpts) => new Promise<string | null>((resolve) => setDialog({ kind: "prompt", resolve, ...o })), []);

  return (
    <Ctx.Provider value={{ toast, confirm, prompt }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <ToastItem key={t.id} t={t} onClose={() => setToasts((x) => x.filter((y) => y.id !== t.id))} />
          ))}
        </AnimatePresence>
      </div>
      <AnimatePresence>{dialog && <DialogSheet dialog={dialog} close={() => setDialog(null)} />}</AnimatePresence>
    </Ctx.Provider>
  );
}

function ToastItem({ t, onClose }: { t: Toast; onClose: () => void }) {
  return (
    <m.div layout className={`toast ${t.ok ? "ok" : "err"}`} initial={{ opacity: 0, y: NUDGE }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={T_BASE}>
      {t.ok ? <CheckCircle2 size={18} aria-hidden /> : <AlertCircle size={18} aria-hidden />}
      <span>{t.msg}</span>
      <button onClick={onClose} aria-label="Dismiss"><X size={16} /></button>
    </m.div>
  );
}

/** Modal sheet: focus moves in, Escape cancels, focus returns to the opener. */
export function Sheet({ title, children, onClose, labelledBy, className = "" }: { title?: string; children: ReactNode; onClose: () => void; labelledBy?: string; className?: string }) {
  const scrim = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  // read during the first render: autoFocus inside the sheet moves focus before any effect runs
  const [opener] = useState(() => document.activeElement as HTMLElement | null);
  useEffect(() => {
    // once per opening: move focus in, give it back to the opener on close
    const first = panel.current?.querySelector<HTMLElement>("[autofocus], input, textarea, button");
    first?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeRef.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  return (
    <m.div ref={scrim} className="scrim" onMouseDown={(e) => e.target === scrim.current && onClose()} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={T_BASE}>
      <m.div ref={panel} className={`sheet ${className}`} role="dialog" aria-modal="true" aria-label={labelledBy ? undefined : title} aria-labelledby={labelledBy}
        initial={{ opacity: 0, scale: 0.97, y: NUDGE }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ ...SPRING, opacity: T_FAST }}>
        {children}
      </m.div>
    </m.div>
  );
}

function DialogSheet({ dialog, close }: { dialog: Dialog; close: () => void }) {
  const [value, setValue] = useState("");
  const [err, setErr] = useState("");
  const cancel = () => {
    if (dialog.kind === "confirm") dialog.resolve(false);
    else dialog.resolve(null);
    close();
  };
  const accept = () => {
    if (dialog.kind === "confirm") dialog.resolve(true);
    else {
      if (dialog.required && !value.trim()) return setErr(dialog.required);
      dialog.resolve(value);
    }
    close();
  };
  return (
    <Sheet onClose={cancel} labelledBy="dlg-title">
      <h2 id="dlg-title">{dialog.title}</h2>
      {dialog.body && <p>{dialog.body}</p>}
      {dialog.kind === "prompt" && (
        <div className="field">
          <label htmlFor="dlg-input">{dialog.label}</label>
          <textarea id="dlg-input" className="textarea" rows={3} maxLength={300} value={value} placeholder={dialog.placeholder}
            onChange={(e) => { setValue(e.target.value); setErr(""); }} aria-invalid={!!err} aria-describedby={err ? "dlg-err" : undefined} />
          {err && <span id="dlg-err" className="small" style={{ color: "var(--bad)" }}>{err}</span>}
        </div>
      )}
      <div className="acts">
        <Button variant="secondary" onClick={cancel}>Cancel</Button>
        <Button variant="primary" danger={!!dialog.destructive} onClick={accept} autoFocus={dialog.kind === "confirm"}>
          {dialog.confirmLabel ?? "OK"}
        </Button>
      </div>
    </Sheet>
  );
}
