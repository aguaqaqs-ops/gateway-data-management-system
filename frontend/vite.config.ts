import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const backendOrigin = process.env.GATEWAY_FRONTEND_BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/v1": { target: backendOrigin, changeOrigin: true },
      "/healthz": { target: backendOrigin, changeOrigin: true },
      "/readyz": { target: backendOrigin, changeOrigin: true },
      "/openapi.json": { target: backendOrigin, changeOrigin: true }
    }
  },
  test: {
    clearMocks: true,
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"]
  }
});
