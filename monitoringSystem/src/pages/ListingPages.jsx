import { useNavigate } from "../router";
import { AppShell } from "../components/Layout";
import { BinCard, Button, DeviceCard, PageHeader } from "../components/ui";
import { bins, devices } from "../data/mockData";

export function BinsPage() {
  const navigate = useNavigate();
  return <AppShell><PageHeader eyebrow="Management" title="Compost bins" description="Monitor active batches and manage every compost location." action={<Button icon="plus" onClick={() => navigate("/setup/bin")}>Create bin</Button>} /><div className="grid grid-3">{bins.map((bin) => <BinCard key={bin.id} bin={bin} />)}</div></AppShell>;
}

export function DevicesPage() {
  const navigate = useNavigate();
  return <AppShell><PageHeader eyebrow="Hardware" title="Devices" description="Connected sensors across all compost locations." action={<Button icon="plus" onClick={() => navigate("/setup/device")}>Add device</Button>} /><div className="grid grid-3">{devices.map((device) => <DeviceCard key={device.id} device={device} />)}</div></AppShell>;
}
