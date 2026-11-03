import { DesignSystemPage } from "./pages/DesignSystemPage";
import { ComparisonPage } from "./pages/ComparisonPage";

export function App() {
  return new URLSearchParams(window.location.search).has("design-system")
    ? <DesignSystemPage />
    : <ComparisonPage />;
}
