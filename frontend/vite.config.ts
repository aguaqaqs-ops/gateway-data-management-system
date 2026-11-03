import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const backendOrigin = process.env.GATEWAY_FRONTEND_BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const productionModuleManifest: Plugin = {
  name: "production-module-manifest",
  apply: "build" as const,
  async writeBundle(_options, bundle) {
    const modules = [...new Set(Object.values(bundle).flatMap((output) =>
      output.type === "chunk"
        ? Object.entries(output.modules)
            .filter(([, module]) => module.renderedLength > 0)
            .map(([id]) => id.replaceAll("\\", "/"))
        : []
    ))];
    const directory = resolve(process.cwd(), "node_modules", ".cache", "frontend-build");
    await mkdir(directory, { recursive: true });
    await writeFile(resolve(directory, "production-modules.json"), JSON.stringify(modules, null, 2) + "\n");
  },
};

export default defineConfig({
  plugins: [react(), productionModuleManifest],
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
