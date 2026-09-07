import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AppProvider } from "./context/AppContext";
import { RouterProvider } from "./router";

ReactDOM.createRoot(document.getElementById("app")).render(
  <React.StrictMode>
    <RouterProvider>
      <AppProvider><App /></AppProvider>
    </RouterProvider>
  </React.StrictMode>,
);
