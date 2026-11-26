// Capture a frame sequence of the viewer at a fixed frame rate (clock is frozen per
// frame via window.__viewer.setTime) and encode it to MP4 with ffmpeg.
// Usage: node tools/capture/sequence.mjs <outPrefix> "<query>" [fps=12] [seconds=3] [selector]
// Env: VIEWER_URL, VIEWPORT_W, VIEWPORT_H, DSF, OUT_FPS (frame rate of the MP4, default 24),
//      T0 (start time in seconds, default 0; the clock is first stepped from 0 to T0 at the
//      capture rate without screenshots, so springs reach the state they have in a loop;
//      T0_WARM = seconds of that stepping before T0, default all of it: slow characters can use 1)
//      ALPHA=1: keep the frames as transparent PNGs read straight from the canvas (use with bg=none;
//      no MP4; the frames stay in <outPrefix>_frames/f0000.png ...)
import { chromium } from "playwright";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname } from "node:path";

const [outPrefix, query, fpsArg = "12", secArg = "3", selArg] = process.argv.slice(2);
const fps = Number(fpsArg), secs = Number(secArg);
const frameDir = `${outPrefix}_frames`;
rmSync(frameDir, { recursive: true, force: true });
mkdirSync(frameDir, { recursive: true });
mkdirSync(dirname(outPrefix), { recursive: true });
const base = process.env.VIEWER_URL ?? "http://127.0.0.1:5280/";
const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: Number(process.env.VIEWPORT_W ?? 1600), height: Number(process.env.VIEWPORT_H ?? 1100) }, deviceScaleFactor: Number(process.env.DSF ?? 1) });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(`${base}?${query}`, { waitUntil: "networkidle" });
await page.waitForFunction(() => window.__viewer?.ready === true, null, { timeout: 90000 });
await page.waitForTimeout(500);
const sel = selArg ?? (query.includes("renderer=grid") ? "#preview" : "#preview canvas");
const n = Math.round(fps * secs);
// a fixed clip rectangle is faster and does not wait for "stable" elements under load
await page.locator(sel).first().scrollIntoViewIfNeeded();
const box = await page.locator(sel).first().boundingBox();
const clip = { x: box.x, y: box.y, width: box.width, height: box.height };
const t0 = Number(process.env.T0 ?? 0);
if (t0 > 0) {
  const warm = Math.min(t0, Number(process.env.T0_WARM ?? t0));
  await page.evaluate(([t0, fps, warm]) => { for (let i = Math.round((t0 - warm) * fps); i < Math.round(t0 * fps); i++) window.__viewer.setTime(i / fps); }, [t0, fps, warm]);
}
for (let i = 0; i < n; i++) {
  await page.evaluate((t) => window.__viewer.setTime(t), t0 + i / fps);
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => r(null))));
  if (process.env.ALPHA) {
    const url = await page.evaluate((s) => document.querySelector(s).toDataURL("image/png"), sel);
    writeFileSync(`${frameDir}/f${String(i).padStart(4, "0")}.png`, Buffer.from(url.split(",")[1], "base64"));
    continue;
  }
  for (let k = 0; ; k++) {  // retry: captureScreenshot fails now and then under load
    try { await page.screenshot({ path: `${frameDir}/f${String(i).padStart(4, "0")}.png`, clip, timeout: 120000 }); break; }
    catch (e) { if (k >= 3) throw e; await page.waitForTimeout(500); }
  }
}
await browser.close();
if (process.env.ALPHA) {
  console.log("frames", n, "->", frameDir);
  if (errors.length) { console.log("ERRORS\n" + errors.join("\n")); process.exitCode = 1; }
  process.exit();
}
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", `${frameDir}/f%04d.png`,
  "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-r", process.env.OUT_FPS ?? "24", `${outPrefix}.mp4`]);
console.log("frames", n, "->", `${outPrefix}.mp4`);
if (errors.length) { console.log("ERRORS\n" + errors.join("\n")); process.exitCode = 1; }
