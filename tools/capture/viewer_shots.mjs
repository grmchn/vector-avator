// Capture the viewer preview for a list of conditions.
// Usage: node tools/capture/viewer_shots.mjs <outDir> <name>=<query> [<name>=<query> ...]
//   e.g. usagi_attention="char=usagi&renderer=raw&pose=attention"
// Env: VIEWER_URL (default http://127.0.0.1:5280/), VIEWPORT_W/VIEWPORT_H, DSF (device scale factor).
// Each shot is retried with a fresh browser when the page dies (headless renderer crashes under load).
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const [outDir, ...specs] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const base = process.env.VIEWER_URL ?? "http://127.0.0.1:5280/";
const errors = [];
let browser = null, page = null;

async function open() {
  if (browser) await browser.close().catch(() => {});
  browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  page = await browser.newPage({ viewport: { width: Number(process.env.VIEWPORT_W ?? 1280), height: Number(process.env.VIEWPORT_H ?? 900) }, deviceScaleFactor: Number(process.env.DSF ?? 1) });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
}

async function shot(name, query) {
  await page.goto(`${base}?${query}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__viewer?.ready === true, null, { timeout: 180000 });
  await page.waitForTimeout(400);
  const loc = page.locator(query.includes("renderer=grid") ? "#preview" : "#preview canvas").first();
  await loc.scrollIntoViewIfNeeded();
  const box = await loc.boundingBox();
  await page.screenshot({ path: `${outDir}/${name}.png`, clip: { x: box.x, y: box.y, width: box.width, height: box.height }, timeout: 120000 });
}

await open();
for (const spec of specs) {
  const i = spec.indexOf("=");
  const name = spec.slice(0, i), query = spec.slice(i + 1);
  for (let k = 0; ; k++) {
    try { await shot(name, query); break; }
    catch (e) {
      if (k >= 3) throw e;
      console.log("retry", name, String(e.message ?? e).split("\n")[0]);
      await open();
    }
  }
  console.log("shot", name);
}
await browser.close();
if (errors.length) { console.log("ERRORS:\n" + errors.join("\n")); process.exitCode = 1; }
