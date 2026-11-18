// Record a video of the minimal viewer (vviewer.html): one character, one motion, optional
// lip-sync track and audio. The clock is frozen per frame, so the result does not depend on the
// machine speed. Needs a running dev server (npm run dev), Playwright's Chromium and ffmpeg.
//
// Usage:
//   node tools/vector/record.mjs --out out/explain --motion explain
//   node tools/vector/record.mjs --out out/hello --motion talk_demo --lipsync line.json --audio line.wav
// Options:
//   --out <prefix>      output <prefix>.mp4 (frames are written to <prefix>_frames/ and removed)
//   --motion <name>     motion name (data/motions/*.json "name"); none = static pose
//   --seconds <s>       length (default: the lip-sync track, else the motion, else 3 s)
//   --fps <n>           frame rate (default 24)
//   --lipsync <json>    lip-sync JSON (tools/lipsync/lipsync.py)
//   --audio <file>      audio muxed into the video (not used for timing)
//   --query <q>         extra viewer query, e.g. "expr=smile&yaw=10&bg=ffd3e0&vHand=4"
//   --width / --height  viewport size (default 1280 x 1000); the preview canvas is captured
//   --scale <n>         device scale factor (default 2: the 16:9 preview is about 1520 x 856)
//   --keep-frames       keep the PNG frames
// Env: VIEWER_URL (default http://127.0.0.1:5280/)
import { chromium } from "playwright";
import { mkdirSync, rmSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname } from "node:path";

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(`--${k}`); return i >= 0 ? args[i + 1] : d; };
const out = opt("out");
if (!out) { console.error("--out is required (see the header of this file)"); process.exit(2); }
const fps = Number(opt("fps", "24"));
const motion = opt("motion", "");
const lipsync = opt("lipsync") ? JSON.parse(readFileSync(opt("lipsync"), "utf8")) : null;
const audio = opt("audio");
const base = process.env.VIEWER_URL ?? "http://127.0.0.1:5280/";
const q = new URLSearchParams(opt("query", ""));
if (motion) q.set("motion", motion);
q.set("t", "0");  // start with a frozen clock

const frameDir = `${out}_frames`;
rmSync(frameDir, { recursive: true, force: true });
mkdirSync(frameDir, { recursive: true });
mkdirSync(dirname(out), { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: Number(opt("width", "1280")), height: Number(opt("height", "1000")) },
  deviceScaleFactor: Number(opt("scale", "2")),
});
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(`${base}?${q}`, { waitUntil: "networkidle" });
await page.waitForFunction(() => window.__viewer?.ready === true, null, { timeout: 90000 });
if (lipsync) await page.evaluate((j) => window.__viewer.setLipsync(j), lipsync);
const motionLen = await page.evaluate(() => window.__viewer.motionDuration());
const secs = Number(opt("seconds", String(lipsync?.duration ?? (motionLen || 3))));
const n = Math.round(fps * secs);
const el = page.locator("#preview canvas").first();
await el.scrollIntoViewIfNeeded();
const box = await el.boundingBox();
const clip = { x: box.x, y: box.y, width: box.width, height: box.height };
for (let i = 0; i < n; i++) {
  await page.evaluate((t) => window.__viewer.setTime(t), i / fps);
  await page.screenshot({ path: `${frameDir}/f${String(i).padStart(5, "0")}.png`, clip });
}
await browser.close();

const ff = ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", `${frameDir}/f%05d.png`];
if (audio) ff.push("-i", audio, "-c:a", "aac", "-b:a", "128k", "-shortest");
ff.push("-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-crf", "20", `${out}.mp4`);
execFileSync("ffmpeg", ff);
if (!args.includes("--keep-frames")) rmSync(frameDir, { recursive: true, force: true });
console.log(`${n} frames (${secs.toFixed(2)} s, ${fps} fps) -> ${out}.mp4`);
if (errors.length) { console.log("page errors:\n" + errors.join("\n")); process.exitCode = 1; }
