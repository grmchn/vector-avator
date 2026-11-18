import { defineConfig } from "vite";

function localStamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// The dev server listens on localhost:5280 (add --host to open it from another machine).
export default defineConfig({
  define: { __BUILD_ID__: JSON.stringify(localStamp()) },
  server: { port: 5280, strictPort: true },
  preview: { port: 5281, strictPort: true },
  // the motion data (JSON) is bundled into the viewer, so the chunk is large on purpose
  build: { outDir: "dist", sourcemap: true, chunkSizeWarningLimit: 4000 },
});
