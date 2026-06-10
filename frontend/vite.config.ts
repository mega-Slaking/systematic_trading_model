import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server config (spec §8). The proxy forwards `/api` -> the FastAPI service
// on :8000, so in dev the SPA and API look same-origin and CORS never bites.
// CORSMiddleware on the API still covers the non-proxied / prod case.
export default defineConfig({
  plugins: [react()],
  // Pre-bundle the Plotly stack. react-plotly.js (CommonJS) + plotly.js/dist are
  // pulled in only via a dynamic `React.lazy` import (ReturnsScatter), which Vite
  // doesn't always discover for dep pre-bundling -- leaving the lazy chunk to fail
  // evaluating in dev. Forcing them here resolves it. (Restart dev after changing.)
  optimizeDeps: {
    include: ["react-plotly.js", "plotly.js"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
