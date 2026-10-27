import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./foundation.css";
import "./ui/controls.css";
import "./theme.css";
import "./motion";
import App from "./App";
import { OverlayProvider } from "./ui/overlays";
import { StoreProvider } from "./store";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OverlayProvider>
      <StoreProvider>
        <App />
      </StoreProvider>
    </OverlayProvider>
  </StrictMode>,
);
