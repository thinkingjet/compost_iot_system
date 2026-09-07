import { createContext, useContext, useMemo, useState } from "react";

const AppContext = createContext(null);

const initialSetup = {
  deviceName: "Outer Sensor",
  location: "Bin 1 · UNRAM",
  binName: "Bin 1",
  compostType: "Takakura",
  material: "Food scraps + dry leaves",
  capacity: "240",
  assigned: ["outer"],
};

export function AppProvider({ children }) {
  const [setup, setSetup] = useState(initialSetup);
  const [toast, setToast] = useState("");

  const showToast = (message) => {
    setToast(message);
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => setToast(""), 2600);
  };

  const value = useMemo(() => ({ setup, setSetup, showToast }), [setup]);
  return (
    <AppContext.Provider value={value}>
      {children}
      <div id="toast-root" aria-live="polite">{toast && <div className="toast">{toast}</div>}</div>
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used inside AppProvider");
  return context;
}
