import { useEffect, useState, type ReactNode } from "react";
import { Check, Copy, LoaderCircle, X } from "lucide-react";

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{children}</section>;
}

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="heading-action">{action}</div>}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  return (
    <button className={`button button-${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "completed" || status === "succeeded" || status === "connected" || status === "ready"
      ? "good"
      : status === "failed" || status === "disconnected"
        ? "bad"
        : status === "running" || status === "pending" || status === "reconnecting" || status === "partial"
          ? "warn"
          : "neutral";
  return <span className={`status-badge status-${tone}`}><i />{status.replaceAll("_", " ")}</span>;
}

export function Loading({ label = "Loading data" }: { label?: string }) {
  return <div className="state-box"><LoaderCircle className="spin" size={18} /><span>{label}</span></div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <strong>Could not load this data</strong>
      <span>{message}</span>
      {retry && <Button variant="secondary" onClick={retry}>Try again</Button>}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-mark">∅</div><strong>{title}</strong><p>{description}</p>{action}</div>;
}

export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="icon-button copy-button"
      aria-label="Copy identifier"
      title="Copy identifier"
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  icon,
  accent = "violet",
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: ReactNode;
  accent?: string;
}) {
  return (
    <Panel className="metric-card">
      <div className={`metric-icon ${accent}`}>{icon}</div>
      <div className="metric-copy"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
    </Panel>
  );
}

export function Modal({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <header><div><h2 id="modal-title">{title}</h2>{description && <p>{description}</p>}</div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={18} /></button></header>
        {children}
      </section>
    </div>
  );
}

export function ToastHost() {
  const [toast, setToast] = useState<{ message: string; kind: string; id: number } | null>(null);
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ message: string; kind?: string }>).detail;
      const id = Date.now();
      setToast({ message: detail.message, kind: detail.kind ?? "success", id });
      window.setTimeout(() => setToast((current) => current?.id === id ? null : current), 3500);
    };
    window.addEventListener("reliai:toast", handler);
    return () => window.removeEventListener("reliai:toast", handler);
  }, []);
  if (!toast) return null;
  return <div className={`toast toast-${toast.kind}`} role="status">{toast.kind === "error" ? <X size={16} /> : <Check size={16} />}{toast.message}</div>;
}

export function notify(message: string, kind: "success" | "error" = "success") {
  window.dispatchEvent(new CustomEvent("reliai:toast", { detail: { message, kind } }));
}

export function DataTable({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`table-wrap ${className}`}><table>{children}</table></div>;
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function shortId(value: string, chars = 8) {
  return `${value.slice(0, chars)}…${value.slice(-4)}`;
}

export function durationMs(start: string | null, end: string | null) {
  if (!start || !end) return null;
  const duration = new Date(end).getTime() - new Date(start).getTime();
  return Number.isFinite(duration) && duration >= 0 ? duration : null;
}

export function metricDisplay(value: number | null | undefined, percent = false) {
  if (value === null || value === undefined) return "Unavailable";
  return percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(3);
}
