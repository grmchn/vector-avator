// Wobble of the flat-colour shapes themselves (derived from id053). The part data is not
// changed: when a part is drawn, its outline is cut into short pieces and every point is moved a
// little by a smooth noise field. The field depends only on the position in the part's rest
// coordinates, so two parts that touch at rest keep touching (no gaps), and a moving part carries
// its wobble along (it does not swim).
import type { MultiPolygon } from "./pc";
import { fbm2 } from "./outline";
import type { Cmd, Pt } from "./vdata";

export interface ShapeWobble {
  amp: number;   // drawing px: largest displacement of an outline point
  wave: number;  // drawing px: wavelength of the noise
  boil: number;  // re-rolls of the field per second (0 = still, no flicker)
  seed: number;
  step: number;  // drawing px: spacing of the points the outline is cut into
}

export type ShapePreset = "weak" | "mid" | "strong";
export const SHAPE_PRESETS: Record<ShapePreset, ShapeWobble> = {
  weak: { amp: 0.8, wave: 46, boil: 0, seed: 1, step: 4 },
  mid: { amp: 1.5, wave: 38, boil: 0, seed: 1, step: 4 },
  strong: { amp: 2.4, wave: 30, boil: 0, seed: 1, step: 4 },
};

/** URL: vShape=0|1|2|3 (off, weak, mid, strong) or off|weak|mid|strong (default: off), then the
 *  overrides vShapeAmp, vShapeWave, vShapeBoil and vShapeSeed. */
export function shapeFromQuery(p: URLSearchParams): ShapeWobble | null {
  const v = p.get("vShape");
  const names: (ShapePreset | null)[] = [null, "weak", "mid", "strong"];
  const name = v == null ? null : (names[Number(v)] ?? (v in SHAPE_PRESETS ? (v as ShapePreset) : null));
  if (!name) return null;
  const s = { ...SHAPE_PRESETS[name] };
  const ov: [string, keyof ShapeWobble][] = [["vShapeAmp", "amp"], ["vShapeWave", "wave"], ["vShapeBoil", "boil"], ["vShapeSeed", "seed"]];
  for (const [k, f] of ov) if (p.has(k) && isFinite(Number(p.get(k)))) s[f] = Number(p.get(k));
  return s;
}

/** Seed of the current frame: changes `boil` times per second, constant when boil = 0. */
export function shapeSeed(s: ShapeWobble, clock = 0): number {
  return (s.seed | 0) + (s.boil > 0 ? Math.floor(clock * s.boil + 1e-6) * 6007 : 0);
}

/** The displaced position of a point (rest coordinates in, rest coordinates out). */
export function shapeWobbleMap(s: ShapeWobble | null | undefined, clock = 0): ((p: Pt) => Pt) | null {
  if (!s || !(s.amp > 0) || !(s.wave > 0)) return null;
  const sd = shapeSeed(s, clock) + 401, f = s.wave;
  return ([x, y]) => [x + s.amp * fbm2(x / f, y / f, sd), y + s.amp * fbm2(x / f + 7.7, y / f - 2.9, sd + 83)];
}

/** The same field in the frame of a moving object (origin and rotation): the arm carries its
 *  wobble along instead of sliding through a fixed pattern. */
export function frameWobbleMap(field: (p: Pt) => Pt, origin: Pt, angle: number): (p: Pt) => Pt {
  const c = Math.cos(angle), s = Math.sin(angle);
  return (p) => {
    const dx = p[0] - origin[0], dy = p[1] - origin[1];
    const lx = c * dx + s * dy, ly = -s * dx + c * dy; // into the frame
    const q = field([lx, ly]);
    const ex = q[0] - lx, ey = q[1] - ly;               // displacement in the frame
    return [p[0] + c * ex - s * ey, p[1] + s * ex + c * ey];
  };
}

/** Points between a and b (excluding a, including b) at spacing of at most `step`. */
function between(a: Pt, b: Pt, step: number): Pt[] {
  const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / step));
  const out: Pt[] = [];
  for (let i = 1; i <= n; i++) { const t = i / n; out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]); }
  return out;
}

/** Closed ring cut into pieces of at most `step`, every point mapped. A repeated closing point
 *  (polygon-clipping rings) is kept as a repeated point. */
export function wobbleRing(ring: Pt[], f: (p: Pt) => Pt, step: number): Pt[] {
  if (ring.length < 2) return ring.map(f);
  const closed = Math.abs(ring[0][0] - ring[ring.length - 1][0]) < 1e-9 && Math.abs(ring[0][1] - ring[ring.length - 1][1]) < 1e-9;
  const pts = closed ? ring.slice(0, -1) : ring;
  const out: Pt[] = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    out.push(f(a));
    const mid = between(a, b, step);
    mid.pop(); // b is the next ring point
    for (const m of mid) out.push(f(m));
  }
  if (closed) out.push(out[0]);
  return out;
}

export function wobbleMulti(mp: MultiPolygon, f: (p: Pt) => Pt, step: number): MultiPolygon {
  return mp.map((poly) => poly.map((ring) => wobbleRing(ring as Pt[], f, step)));
}

/** Path commands as a path made of short lines with every point mapped by `f` (the shape's own
 *  point map is applied by the caller inside `f`, after the wobble). */
export function emitWobbled(cmds: Cmd[], f: (p: Pt) => Pt, step: number, path: Path2D = new Path2D()): Path2D {
  let last: Pt = [0, 0], start: Pt = [0, 0];
  const line = (to: Pt) => { for (const p of between(last, to, step)) { const q = f(p); path.lineTo(q[0], q[1]); } last = to; };
  for (const c of cmds) {
    if (c.k === "M") { const q = f(c.p); path.moveTo(q[0], q[1]); last = c.p; start = c.p; }
    else if (c.k === "L") line(c.p);
    else if (c.k === "C") {
      const [a, b, e] = c.p;
      const len = Math.hypot(a[0] - last[0], a[1] - last[1]) + Math.hypot(b[0] - a[0], b[1] - a[1]) + Math.hypot(e[0] - b[0], e[1] - b[1]);
      const n = Math.max(2, Math.ceil(len / step));
      const p0 = last;
      for (let i = 1; i <= n; i++) {
        const t = i / n, u = 1 - t;
        const x = u * u * u * p0[0] + 3 * u * u * t * a[0] + 3 * u * t * t * b[0] + t * t * t * e[0];
        const y = u * u * u * p0[1] + 3 * u * u * t * a[1] + 3 * u * t * t * b[1] + t * t * t * e[1];
        const q = f([x, y]);
        path.lineTo(q[0], q[1]);
      }
      last = e;
    } else { path.closePath(); last = start; }
  }
  return path;
}
