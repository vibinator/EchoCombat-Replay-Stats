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

/** Lists every page's files in index.html (a JSON data block: the Content-Security-Policy allows no inline script),
 *  so public/early.js can ask for the opened page's file while the main script is still downloading. */
function pageFiles() {
  return {
    name: "page-files",
    transformIndexHtml: {
      order: "post" as const,
      handler(html: string, ctx: { bundle?: Record<string, { type: string; name?: string; isDynamicEntry?: boolean; fileName: string; imports?: string[] }> }) {
        if (!ctx.bundle) return html; // the dev server: pages are not separate files there
        const main = new Set<string>();
        for (const c of Object.values(ctx.bundle)) if (c.type === "chunk" && !c.isDynamicEntry && html.includes(c.fileName)) [c.fileName, ...(c.imports ?? [])].forEach((f) => main.add(f));
        const pages: Record<string, string[]> = {};
        for (const c of Object.values(ctx.bundle)) {
          if (c.type !== "chunk" || !c.isDynamicEntry || !c.name?.endsWith("Page")) continue;
          pages[c.name] = [c.fileName, ...(c.imports ?? [])].filter((f) => !main.has(f)).map((f) => `/${f}`);
        }
        // before early.js in the page, so that script (async: it must not wait for the stylesheet) always finds it
        const block = `<script type="application/json" id="page-files">${JSON.stringify(pages)}</script>`;
        const early = html.indexOf("<script async src=\"/early.js\">");
        return early < 0 ? html.replace("</head>", `  ${block}
  </head>`) : `${html.slice(0, early)}${block}
    ${html.slice(early)}`;
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), pageFiles()],
  // answers saved in the browser (sessionStorage, api.ts) belong to one build: a new version never reads old ones
  define: { __BUILD_ID__: JSON.stringify(Date.now().toString(36)), __APP_VERSION__: JSON.stringify(appVersion()) },
  // the 3D playback chunk (three.js, ~620 kB) is loaded only when someone opens the 3D view
  build: { chunkSizeWarningLimit: 700 },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/achievements/custom": "http://127.0.0.1:8000" },
  },
});
