import { useState } from "react";
import { useNavigate, useParams } from "../router";
import { AppShell, DetailNavigation } from "../components/Layout";
import { Button, DeviceCard, Field, PageHeader, RangeControl, SectionHeader } from "../components/ui";
import { HealthChart, PhaseHistoryChart, SparklineChart, TelemetryChart } from "../components/charts/PlotlyCharts";
import { devices, historical, maintenanceTasks, metrics, telemetry } from "../data/mockData";
import { useApp } from "../context/AppContext";

function SensorChip({ label, value, unit, values, color }) {
  return <article className="card sensor-chip"><span>{label}</span><strong>{value} <small>{unit}</small></strong><SparklineChart values={values} color={color} className="tiny-line" /></article>;
}

function SensorStrip() {
  return <div className="sensor-strip"><SensorChip label="Temperature" value="54.2" unit="°C" values={telemetry.temperature} color="red" /><SensorChip label="Moisture" value="50.7" unit="%" values={telemetry.moisture} color="blue" /><SensorChip label="Oxygen" value="20.4" unit="%" values={telemetry.oxygen} color="green" /><SensorChip label="Maturation" value="Day 18" unit="of 28" values={historical.health} color="lime" /></div>;
}

function LivePanel({ isBin }) {
  const [range, setRange] = useState("24h");
  return <><SensorStrip /><article className="card chart-card"><div className="chart-toolbar"><div><p className="eyebrow">Live data</p><h2>{isBin ? "Environmental telemetry" : "Sensor readings"}</h2><p>Updated 14 seconds ago</p></div><RangeControl value={range} onChange={setRange} /></div><TelemetryChart range={range} /></article></>;
}

function MaintenancePanel() {
  const { showToast } = useApp();
  return <><SensorStrip /><article className="card card-pad"><div className="section-head"><div><p className="eyebrow">Smart schedule</p><h2>Estimated next tasks</h2></div><Button onClick={() => showToast("Predictions refreshed")}>Generate predictions</Button></div><div className="task-list">{maintenanceTasks.map((task, index) => <div className="task" key={task.title}><span className="task-num">{String(index + 1).padStart(2, "0")}</span><div><strong>{task.title}</strong><p>{task.detail}</p></div><time>{task.time}</time></div>)}</div></article></>;
}

function HistoryPanel() {
  const [range, setRange] = useState("24h");
  return <><SensorStrip /><div className="grid grid-2"><article className="card chart-card"><div className="chart-toolbar"><div><p className="eyebrow">Phase analysis</p><h2>Temperature over time</h2></div><RangeControl value={range} onChange={setRange} /></div><PhaseHistoryChart /></article><article className="card chart-card"><div className="chart-toolbar"><div><p className="eyebrow">Quality score</p><h2>Compost health</h2></div><span className="tag">Last 30 days</span></div><HealthChart /></article></div></>;
}

function DevicesPanel() {
  const navigate = useNavigate();
  return <article className="card card-pad"><SectionHeader title="Devices monitoring Bin 1" /><div className="panel-actions"><Button icon="plus" onClick={() => navigate("/setup/device")}>Add device</Button></div><div className="grid grid-2 device-panel-grid">{devices.slice(0, 2).map((device) => <DeviceCard key={device.id} device={device} />)}</div></article>;
}

function SettingsPanel({ isBin }) {
  const { showToast } = useApp();
  return <article className="card settings"><div className="settings-block"><p className="eyebrow">General</p><h2>{isBin ? "Bin settings" : "Device settings"}</h2><p>Update how this {isBin ? "compost batch" : "sensor"} appears across CompostIQ.</p><div className="form-grid"><Field label="Name"><input defaultValue={isBin ? "Bin 1" : "Outer Sensor"} /></Field><Field label="Location"><select defaultValue="UNRAM"><option>UNRAM</option><option>Primary School</option><option>Mataram</option></select></Field>{isBin && <><Field label="Compost method"><select defaultValue="Takakura"><option>Takakura</option><option>Tumbler</option></select></Field><Field label="Capacity"><input defaultValue="240 L" /></Field></>}</div><div className="settings-save"><Button onClick={() => showToast("Settings saved")}>Save changes</Button></div></div><div className="settings-block"><p className="eyebrow">System information</p><h2>{isBin ? "Assigned devices" : "Device details"}</h2><div className="details-table">{isBin ? <><DetailRow label="Outer Sensor" value="Monitoring · Online" /><DetailRow label="Inner Sensor" value="Monitoring · Online" /></> : <><DetailRow label="UUID" value="CMP-IQ-ESP32-01-84BF" /><DetailRow label="MAC address" value="84:F7:03:A1:2D:90" /><DetailRow label="Firmware" value="v2.4.1 · Up to date" /><DetailRow label="Created" value="18 August 2026" /></>}</div></div></article>;
}

function DetailRow({ label, value }) { return <div className="detail-row"><span>{label}</span><strong>{value}</strong></div>; }

export function DetailPage() {
  const { type, tab } = useParams();
  const { showToast } = useApp();
  const isBin = type === "bin";
  const safeTab = isBin ? ["live", "maintenance", "history", "devices", "settings"].includes(tab) ? tab : "live" : ["live", "history", "settings"].includes(tab) ? tab : "live";
  const panel = safeTab === "live" ? <LivePanel isBin={isBin} /> : safeTab === "maintenance" ? <MaintenancePanel /> : safeTab === "history" ? <HistoryPanel /> : safeTab === "devices" ? <DevicesPanel /> : <SettingsPanel isBin={isBin} />;
  return <AppShell><PageHeader eyebrow={isBin ? "Compost bin" : "Monitoring device"} title={isBin ? "Bin 1" : "Outer Sensor"} description={isBin ? "UNRAM · Peak decomposition" : "Bin 1 · ESP32-C3"} action={<Button variant="secondary" onClick={() => showToast("Report exported")}>Export report</Button>} /><div className="detail-page"><DetailNavigation type={type} current={safeTab} /><section className="content-panel">{panel}</section></div></AppShell>;
}
