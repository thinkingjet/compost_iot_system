import { DashboardPage } from "./pages/DashboardPage";
import { BinsPage, DevicesPage } from "./pages/ListingPages";
import { AssignDevicesPage, BinSetupPage, DeviceSetupPage } from "./pages/OnboardingPages";
import { DetailPage } from "./pages/DetailPage";
import { useLocation } from "./router";

export default function App() {
  const { pathname } = useLocation();
  const pages = {
    "/": <DeviceSetupPage />,
    "/dashboard": <DashboardPage />,
    "/bins": <BinsPage />,
    "/devices": <DevicesPage />,
    "/setup/device": <DeviceSetupPage />,
    "/setup/bin": <BinSetupPage />,
    "/setup/assign": <AssignDevicesPage />,
  };
  if (/^\/(bin|device)\/(live|maintenance|history|devices|settings)$/.test(pathname)) return <DetailPage />;
  return pages[pathname] ?? <DashboardPage />;
}
