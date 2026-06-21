import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": resolve(__dirname, "src") } },
  server: {
    port: 5173,
    // Proxy API calls to the FastAPI gateway in dev.
    proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" },
  },
  test: { environment: "jsdom", globals: true },
});
