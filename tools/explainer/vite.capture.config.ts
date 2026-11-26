// Dev server for explainer captures (from the G12 one): no file watching and no HMR, so
// edits made while a capture runs do not reload the page. The motions are read when the server
// starts, so tools/explainer/capserver.sh restarts it before each capture.
import { defineConfig, mergeConfig } from "vite";
import base from "../../vite.config";

const port = Number(process.env.CAPTURE_PORT ?? 5285);
export default mergeConfig(base, defineConfig({
  root: new URL("../..", import.meta.url).pathname,
  server: { host: "127.0.0.1", port, strictPort: true, hmr: false, watch: null },
}));
