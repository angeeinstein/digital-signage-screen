import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// In development, run the Flask backend on :5000 (python app.py) and
// `npm run dev` here; API and static icon requests are proxied.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5000",
      "/static": "http://127.0.0.1:5000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Chromium on Raspberry Pi OS is current, but stay conservative.
    target: "es2020",
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
