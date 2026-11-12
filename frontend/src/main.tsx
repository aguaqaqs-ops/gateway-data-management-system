import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import { initializeGatewaySession } from "./features/session/handoff-session";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("缺少应用根节点 #root");
}

// The directory handoff fragment must be consumed before the first render;
// the fragment is cleared with replaceState inside the initializer.
initializeGatewaySession();

async function renderApp() {
  // Publish the initial development identity before scope-bound state reads.
  if (import.meta.env.DEV) await import("./features/dev/DevIdentityControl");
  createRoot(rootElement!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
  );
}
void renderApp();
