import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development (npm run dev) Vite serves the UI on :5173 and forwards
// /api calls to the Python backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": process.env.RAVENQUILL_API || "http://127.0.0.1:8000" },
  },
});
