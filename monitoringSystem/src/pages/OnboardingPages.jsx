import { useNavigate } from "../router";
import { Brand } from "../components/Layout";
import { Button, Field } from "../components/ui";
import { Icon } from "../components/Icon";
import { useApp } from "../context/AppContext";

function OnboardingLayout({ step, children }) {
  return <div className="onboarding"><section className="onboard-side"><Brand /><div className="onboard-hero"><p className="eyebrow">Smart composting</p><h1>Better compost, backed by data.</h1><p>Connect your sensors, monitor every batch, and know exactly when your compost needs attention.</p><div className="feature-list">{["Live environmental telemetry", "Actionable maintenance alerts", "Automatic phase detection"].map((feature) => <span className="feature" key={feature}><i>✓</i>{feature}</span>)}</div></div><div className="onboard-art"><div className="soil" /><div className="bin-illustration" /></div></section><section className="onboard-main"><div className="wizard"><div className="wizard-top"><span className="step-label">Setup · <b>Step {step} of 3</b></span><span className="progress"><i style={{ width: `${step / 3 * 100}%` }} /></span></div>{children}</div></section></div>;
}

export function DeviceSetupPage() {
  const navigate = useNavigate();
  const { setup, setSetup } = useApp();
  const submit = (event) => { event.preventDefault(); navigate("/setup/bin"); };
  return <OnboardingLayout step={1}><p className="eyebrow">Connect hardware</p><h1>Add your first device</h1><p>Give the sensor a recognisable name. You can update these details at any time.</p><form className="wizard-form" onSubmit={submit}><Field label="Device name"><input required value={setup.deviceName} placeholder="e.g. Outer Sensor" onChange={(event) => setSetup({ ...setup, deviceName: event.target.value })} /></Field><Field label="Initial location"><select value={setup.location} onChange={(event) => setSetup({ ...setup, location: event.target.value })}><option>Unassigned</option><option>Bin 1 · UNRAM</option><option>Primary School</option></select></Field><div className="wizard-actions"><Button variant="ghost" onClick={() => navigate("/dashboard")}>Skip for now</Button><Button type="submit">Continue <Icon name="arrow" /></Button></div></form></OnboardingLayout>;
}

export function BinSetupPage() {
  const navigate = useNavigate();
  const { setup, setSetup } = useApp();
  const update = (key) => (event) => setSetup({ ...setup, [key]: event.target.value });
  const submit = (event) => { event.preventDefault(); navigate("/setup/assign"); };
  return <OnboardingLayout step={2}><p className="eyebrow">Compost profile</p><h1>Create a compost bin</h1><p>Add the details we’ll use to calibrate insights and phase predictions.</p><form className="wizard-form" onSubmit={submit}><div className="form-grid"><Field label="Bin name"><input required value={setup.binName} onChange={update("binName")} /></Field><Field label="Capacity (litres)"><input type="number" value={setup.capacity} onChange={update("capacity")} /></Field><Field label="Compost method"><select value={setup.compostType} onChange={update("compostType")}><option>Takakura</option><option>Tumbler</option><option>Hot compost</option></select></Field><Field label="Primary material"><select value={setup.material} onChange={update("material")}><option>Food scraps + dry leaves</option><option>Garden waste</option><option>Mixed organics</option></select></Field></div><div className="wizard-actions"><Button variant="ghost" onClick={() => navigate("/setup/device")}>Back</Button><Button type="submit">Continue <Icon name="arrow" /></Button></div></form></OnboardingLayout>;
}

const availableDevices = [{ id: "outer", name: "Outer Sensor", detail: "ESP32 · Online · Added just now" }, { id: "inner", name: "Inner Sensor", detail: "ESP32 · Online · Available" }];

export function AssignDevicesPage() {
  const navigate = useNavigate();
  const { setup, setSetup, showToast } = useApp();
  const toggle = (id) => setSetup({ ...setup, assigned: setup.assigned.includes(id) ? setup.assigned.filter((device) => device !== id) : [...setup.assigned, id] });
  const complete = () => { localStorage.setItem("compostiq-setup", "complete"); navigate("/dashboard"); window.setTimeout(() => showToast("Bin and devices added successfully"), 100); };
  return <OnboardingLayout step={3}><p className="eyebrow">Device assignment</p><h1>Connect devices to {setup.binName}</h1><p>Select the sensors that will monitor this compost batch.</p><div className="wizard-form">{availableDevices.map((device) => { const selected = setup.assigned.includes(device.id); return <button type="button" key={device.id} className={`device-option ${selected ? "selected" : ""}`} onClick={() => toggle(device.id)}><span className="device-icon"><Icon name="device" /></span><span className="device-copy"><strong>{device.id === "outer" ? setup.deviceName : device.name}</strong><span>{device.detail}</span></span><span className="check"><Icon name="check" /></span></button>; })}<div className="wizard-actions"><Button variant="ghost" onClick={() => navigate("/setup/bin")}>Back</Button><Button onClick={complete}>Finish setup <Icon name="check" /></Button></div></div></OnboardingLayout>;
}
