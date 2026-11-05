import { useState, type ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Blocks,
  ChevronLeft,
  ChevronRight,
  Command,
  GitCompareArrows,
  Layers3,
  Menu,
  RefreshCw,
  ShieldAlert,
  X,
  Zap,
  Server,
} from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { healthApi } from "../api/health";
import { apiBaseUrl } from "../api/client";
import { usePolling } from "../hooks/usePolling";
import { formatDate, StatusBadge } from "./ui";

const links = [
  { to: "/", label: "Overview", icon: BarChart3, end: true },
  { to: "/datasets", label: "Datasets", icon: Layers3 },
  { to: "/projects", label: "AI projects", icon: Server },
  { to: "/runs", label: "Evaluation runs", icon: Zap },
  { to: "/benchmarks", label: "Benchmarks", icon: Blocks },
  { to: "/observability", label: "Observability", icon: Activity },
  { to: "/compare", label: "Run comparison", icon: GitCompareArrows },
  { to: "/regressions", label: "Regression monitor", icon: ShieldAlert },
];

const titles: Array<[RegExp, string]> = [
  [/^\/$/, "Overview"],
  [/^\/datasets/, "Datasets"],
  [/^\/projects/, "AI projects"],
  [/^\/runs\/[^/]+$/, "Run details"],
  [/^\/runs/, "Evaluation runs"],
  [/^\/benchmarks/, "Benchmarks"],
  [/^\/observability/, "Observability"],
  [/^\/compare/, "Run comparison"],
  [/^\/regressions/, "Regression monitor"],
];

export default function Shell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const connection = usePolling(async (signal) => {
    try {
      const [live, ready] = await Promise.all([healthApi.live(signal), healthApi.ready(signal)]);
      return { status: live.status === "ok" && ready.status === "ready" ? "connected" : "reconnecting" };
    } catch {
      return { status: "disconnected" };
    }
  }, 10_000);
  const pageTitle = titles.find(([pattern]) => pattern.test(location.pathname))?.[1] ?? "ReliAI";

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      {mobileOpen && <button className="mobile-backdrop" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><span>R</span><i /></div>
          {!collapsed && <div className="brand-name"><strong>Reli<span>AI</span></strong><small>AI OPERATIONS</small></div>}
          <button className="sidebar-collapse icon-button" title={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => setCollapsed(!collapsed)}>
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
          <button className="mobile-close icon-button" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        {!collapsed && <div className="workspace-label">WORKSPACE <span className="workspace-dot" /> LOCAL DEV</div>}
        <nav className="side-nav" aria-label="Main navigation">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={label}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              onClick={() => setMobileOpen(false)}
            >
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {label === "Observability" && !collapsed && <span className="nav-live-dot" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          {!collapsed && (
            <div className="sidebar-promo">
              <div><Command size={15} /><span>Reliability workspace</span></div>
              <p>Observe. Evaluate. Improve.</p>
            </div>
          )}
          <button className="user-strip" onClick={() => navigate("/")} title="Local workspace">
            <span className="avatar">R</span>
            {!collapsed && <span className="user-info"><strong>Local workspace</strong><small>Developer mode</small></span>}
            {!collapsed && <ArrowUpRight size={15} className="user-arrow" />}
          </button>
        </div>
      </aside>

      <main className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={19} /></button>
            <div className="breadcrumb"><span>ReliAI</span><i>/</i><strong>{pageTitle}</strong></div>
          </div>
          <div className="topbar-tools">
            <label className="global-search">
              <Command size={14} />
              <input aria-label="Search runs" placeholder="Find a run…" onKeyDown={(event) => {
                if (event.key === "Enter") {
                  const query = event.currentTarget.value.trim();
                  navigate(query ? `/runs?q=${encodeURIComponent(query)}` : "/runs");
                }
              }} />
              <kbd>↵</kbd>
            </label>
            <div className="connection-indicator" title={`API status · updated ${connection.updatedAt ? formatDate(connection.updatedAt.toISOString()) : "not yet checked"}`}>
              <StatusBadge status={connection.data?.status ?? (connection.loading ? "reconnecting" : "disconnected")} />
              {connection.updatedAt && <span className="last-updated">Updated {connection.updatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
            </div>
            <button className={`icon-button refresh-button ${connection.refreshing ? "is-refreshing" : ""}`} title="Refresh data" aria-label="Refresh data" onClick={() => window.dispatchEvent(new Event("reliai:refresh"))}><RefreshCw size={16} /></button>
          </div>
        </header>
        <div className="page-content">{children}</div>
        <footer className="app-footer"><span>ReliAI · Observe. Evaluate. Improve.</span><span>API <code>{apiBaseUrl}</code></span></footer>
      </main>
    </div>
  );
}
