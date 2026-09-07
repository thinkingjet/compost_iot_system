import { useNavigate } from "../router";
import { AppShell } from "../components/Layout";
import { AlertCard, BinCard, Button, DeviceCard, MetricCard, PageHeader, SectionHeader } from "../components/ui";
import { bins, devices, metrics } from "../data/mockData";
import { useApp } from "../context/AppContext";

export function DashboardPage() {
  const navigate = useNavigate();
  const { setup, showToast } = useApp();
  return <AppShell>
    <PageHeader eyebrow="Monday · 7 September" title="Good morning, UNRAM" description="Here’s what’s happening across your compost system." action={<Button icon="plus" onClick={() => navigate("/setup/device")}>Add device</Button>} />
    <section className="grid grid-4">{metrics.map((metric) => <MetricCard key={metric.label} metric={metric} />)}</section>
    <section className="section"><SectionHeader title="Needs attention" actionLabel="Review all" onAction={() => showToast("All alerts marked as reviewed")} /><div className="grid grid-2"><AlertCard type="hot" title="Temperature is running high" detail={`${setup.binName} · Turn compost within 2 hours`} priority="High" /><AlertCard type="dry" title="Moisture is trending low" detail="Primary School · Add approximately 3L water" priority="Medium" /></div></section>
    <section className="section"><SectionHeader title="Compost bins" actionLabel="View all" onAction={() => navigate("/bins")} /><div className="grid grid-3">{bins.map((bin) => <BinCard key={bin.id} bin={bin} />)}</div></section>
    <section className="section"><SectionHeader title="Devices" actionLabel="View all" onAction={() => navigate("/devices")} /><div className="grid grid-3">{devices.map((device) => <DeviceCard key={device.id} device={device} />)}</div></section>
  </AppShell>;
}
