import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to FastAPI, so the browser sees one origin (no CORS setup).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
