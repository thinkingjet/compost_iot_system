import { useNavigate } from "../router";
import { Icon } from "./Icon";
import { SparklineChart } from "./charts/PlotlyCharts";

export function Button({ children, variant = "primary", icon, type = "button", onClick, className = "" }) {
  return <button type={type} className={`btn btn-${variant} ${className}`} onClick={onClick}>{icon && <Icon name={icon} />}{children}</button>;
}

export function PageHeader({ eyebrow, title, description, action }) {
  return <div className="page-head"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}

export function SectionHeader({ title, actionLabel, onAction }) {
  return <div className="section-head"><h2>{title}</h2>{actionLabel && <button className="text-action" onClick={onAction}>{actionLabel}</button>}</div>;
}

export function Field({ label, children }) {
  return <div className="field"><label>{label}</label>{children}</div>;
}

export function MetricCard({ metric }) {
  return <article className="card card-pad metric"><div className="metric-top"><span>{metric.label}</span><i className="metric-icon"><Icon name={metric.icon} /></i></div><div className="metric-value">{metric.value} <small>{metric.unit}</small></div><div className="metric-delta"><b>{metric.delta}</b> · last 24 hours</div><SparklineChart values={metric.values} color={metric.color} /></article>;
}

export function BinCard({ bin }) {
  const navigate = useNavigate();
  return <article className="card unit-card" onClick={() => navigate("/bin/live")} role="button" tabIndex="0" onKeyDown={(event) => event.key === "Enter" && navigate("/bin/live")}>
    <div className={`unit-visual ${bin.variant ?? ""}`}><div className="unit-head"><div><strong>{bin.name}</strong><div className="unit-location">{bin.location} · {bin.devices} {bin.devices === 1 ? "device" : "devices"}</div></div><span className="phase-orb"><Icon name="leaf" /></span></div><SparklineChart values={[48, 51, 50, 56, 54, 60, 63, 61, 68]} color="green" className="mini-chart" /></div>
    <div className="unit-body"><div className="unit-row"><span className="phase">{bin.phase}</span><span className="tag"><i className="dot" /> Online</span></div><div className="unit-row"><span className="health">Health score <span className="health-bar"><i style={{ width: `${bin.health}%` }} /></span></span><strong>{bin.health}%</strong></div></div>
  </article>;
}

export function DeviceCard({ device }) {
  const navigate = useNavigate();
  return <article className="card card-pad unit-card" onClick={() => navigate("/device/live")} role="button" tabIndex="0" onKeyDown={(event) => event.key === "Enter" && navigate("/device/live")}><div className="unit-row"><span className="device-icon"><Icon name="device" /></span><span className="tag"><i className="dot" /> Online</span></div><h3 className="device-title">{device.name}</h3><p className="device-location">Monitoring {device.location} · {device.model}</p><div className="unit-row"><span className="metric-value device-reading">{device.reading}</span><span className="view-link">View telemetry →</span></div></article>;
}

export function AlertCard({ type, title, detail, priority }) {
  return <article className="card alert-card"><span className={`alert-icon ${type}`}><Icon name={type === "hot" ? "flame" : "drop"} /></span><span className="alert-copy"><strong>{title}</strong><p>{detail}</p></span><span className="tag">{priority}</span></article>;
}

export function RangeControl({ value, onChange }) {
  return <div className="segmented">{["6h", "24h", "7d"].map((range) => <button key={range} className={value === range ? "active" : ""} onClick={() => onChange(range)}>{range}</button>)}</div>;
}
