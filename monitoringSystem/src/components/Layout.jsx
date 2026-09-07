import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "../router";
import { Icon } from "./Icon";
import { useApp } from "../context/AppContext";

export function Brand() {
  return <div className="brand"><span className="brand-mark"><Icon name="leaf" /></span>CompostIQ</div>;
}

const navGroups = [
  { label: "Workspace", items: [{ to: "/dashboard", icon: "home", label: "Overview" }, { to: "/bins", icon: "bin", label: "Compost bins" }, { to: "/devices", icon: "device", label: "Devices" }] },
  { label: "Quick actions", items: [{ to: "/setup/device", icon: "plus", label: "Add device" }, { to: "/setup/bin", icon: "plus", label: "Create bin" }] },
];

function Sidebar({ open, onClose }) {
  return (
    <aside className={`sidebar ${open ? "open" : ""}`}>
      <Brand />
      {navGroups.map((group) => <div key={group.label}>
        <div className="nav-label">{group.label}</div>
        {group.items.map((item) => <NavLink key={item.to} to={item.to} onClick={onClose} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}><Icon name={item.icon} /><span>{item.label}</span></NavLink>)}
      </div>)}
      <div className="sidebar-footer"><div className="account"><span className="avatar">GU</span><span className="account-copy"><strong>UNRAM Pilot</strong><span>Administrator</span></span></div></div>
    </aside>
  );
}

function routeTitle(pathname) {
  if (pathname.includes("device")) return pathname === "/devices" ? "Devices" : "Outer Sensor";
  if (pathname.includes("bin")) return pathname === "/bins" ? "Compost bins" : "Bin 1";
  return "Overview";
}

export function AppShell({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { pathname } = useLocation();
  const { showToast } = useApp();
  return (
    <div className="shell">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      {sidebarOpen && <button className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}
      <main className="main">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Icon name="menu" /></button>
          <div className="crumb"><span>CompostIQ</span><span>/</span><strong>{routeTitle(pathname)}</strong></div>
          <div className="top-actions"><span className="status-pill"><i className="dot" /> All systems online</span><button className="icon-btn" onClick={() => showToast("No new notifications")} aria-label="Notifications"><Icon name="bell" /></button></div>
        </header>
        {children}
      </main>
    </div>
  );
}

export function DetailNavigation({ type, current }) {
  const navigate = useNavigate();
  const items = type === "bin" ? [["live", "Live telemetry"], ["maintenance", "Maintenance"], ["history", "Historical stats"], ["devices", "Devices"], ["settings", "Settings"]] : [["live", "Live telemetry"], ["history", "Historical stats"], ["settings", "Settings"]];
  return <nav className="card detail-tabs" aria-label={`${type} sections`}>{items.map(([key, label]) => <button key={key} className={current === key ? "active" : ""} onClick={() => navigate(`/${type}/${key}`)}>{label}</button>)}</nav>;
}
