import react from "@vitejs/plugin-react";
import { realpathSync } from "node:fs";
import { defineConfig } from "vitest/config";

export default defineConfig(({ command }) => ({
  root: command === "build" ? realpathSync(process.cwd()) : undefined,
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000"
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"]
  }
}));
