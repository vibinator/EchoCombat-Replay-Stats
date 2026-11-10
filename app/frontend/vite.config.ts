// @ts-expect-error Node's own module: this project has no Node type definitions (only this build file needs them)
import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** VERSION of the backend this site is built with (the Dockerfile copies version.py beside the frontend for this);
 *  "" when the file is not there: the pages then never compare versions (api.ts, site updates). */
function appVersion(): string {
  try {
    return /^VERSION = "([^"]+)"/m.exec(readFileSync(new URL("../backend/version.py", import.meta.url), "utf8"))?.[1] ?? "";
  } catch {
    return "";
  }
}

export default defineConfig({
  plugins: [react()],
  // answers saved in the browser (sessionStorage, api.ts) belong to one build: a new version never reads old ones
  define: { __BUILD_ID__: JSON.stringify(Date.now().toString(36)), __APP_VERSION__: JSON.stringify(appVersion()) },
  // the 3D playback chunk (three.js, ~620 kB) is loaded only when someone opens the 3D view
  build: { chunkSizeWarningLimit: 700 },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/achievements/custom": "http://127.0.0.1:8000" },
  },
});
