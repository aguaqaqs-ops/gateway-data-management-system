import { useEffect, useState, lazy, Suspense } from "react";
import { DesignSystemPage } from "./pages/DesignSystemPage";
import { ComparisonPage } from "./pages/ComparisonPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

const DevelopmentIdentityControl = import.meta.env.DEV
  ? lazy(() => import("./features/dev/DevIdentityControl").then((module) => ({ default: module.DevIdentityControl })))
  : null;

function currentPage(): "workspace" | "compare" | "design-system" {
  const params = new URLSearchParams(window.location.search);
  if (params.has("design-system")) return "design-system";
  return params.get("page") === "compare" ? "compare" : "workspace";
}

export function App() {
  const [sessionGeneration, setSessionGeneration] = useState(0);
  useEffect(() => { const changed = () => setSessionGeneration((value) => value + 1); window.addEventListener("gateway-session-change", changed); return () => window.removeEventListener("gateway-session-change", changed); }, []);
  const key = sessionGeneration;
  const identityControl = DevelopmentIdentityControl
    ? <Suspense fallback={null}><DevelopmentIdentityControl /></Suspense>
    : undefined;
  const page = currentPage();
  if (page === "design-system") return <DesignSystemPage />;
  if (page === "compare") return <ComparisonPage key={key} identityControl={identityControl} />;
  return <WorkbenchPage key={key} identityControl={identityControl} />;
}
