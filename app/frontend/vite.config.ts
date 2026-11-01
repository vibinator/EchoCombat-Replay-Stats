import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // answers saved in the browser (sessionStorage, api.ts) belong to one build: a new version never reads old ones
  define: { __BUILD_ID__: JSON.stringify(Date.now().toString(36)) },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/achievements/custom": "http://127.0.0.1:8000" },
  },
});
