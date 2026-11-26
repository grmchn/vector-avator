// In-betweens of turned drawings for method V (id075 follow-up).
// Two neighbouring drawings (body drawings at 0 / 30 / 60 / 90 deg, or head drawings at the
// same angles) are blended shape by shape: every outline is resampled by arc length to the
// same number of points, the two rings are put in correspondence (same winding, the cyclic
// shift that overlays them best), and the points are mixed by the turn fraction t.
// Landmarks (skeleton), chain roots / tips, the head offset and (head drawings) the parallax /
// head-turn tunables are mixed the same way; draw order, arm attachment and part flags come
// from the nearer drawing (they switch at t = 0.5).
// Parts or shapes that exist on one side only:
// - body pairs (default): taken whole from the nearer drawing;
// - head pairs (collapse): squeezed to a vertical line at the part's edge on the side the
//   head turns toward (the far eye of the 60 deg head flattens into the profile on its way to
//   the side head, which has no far eye).
// The blended outlines are emitted as parsed commands (no path string round trip): the
// renderer consumes them directly (VShape.cmds / VShape.flat).
import type { BodyViewDoc } from "./bodyView";
import type { ChainDef, Cmd, Pt, VPart, VShape } from "./vdata";
import { flatten, mapCmds, parsePath } from "./vdata";

/** point spacing of the resampled outlines (drawing px) and the bounds of their point count:
 *  8 px keeps curves within a fraction of a pixel (Catmull-Rom through the points) and keeps
 *  the per-frame drawing and outline work close to the key drawings' */
let SPACING = 8, MIN_N = 40, MAX_N = 200;
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lerpPt = (a: Pt, b: Pt, t: number): Pt => [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];

/** Closed polyline resampled to n points evenly spaced along its length. */
export function resampleRing(ring: Pt[], n: number): Pt[] {
  const pts = ring.slice();
  const L: number[] = [0];
  for (let i = 1; i <= pts.length; i++) {
    const a = pts[i - 1], b = pts[i % pts.length];
    L.push(L[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1]));
  }
  const total = L[L.length - 1];
  const out: Pt[] = [];
  let j = 0;
  for (let k = 0; k < n; k++) {
    const s = (k / n) * total;
    while (j < pts.length - 1 && L[j + 1] < s) j++;
    const a = pts[j], b = pts[(j + 1) % pts.length];
    const seg = L[j + 1] - L[j];
    const u = seg > 1e-9 ? (s - L[j]) / seg : 0;
    out.push(lerpPt(a, b, u));
  }
  return out;
}

function area(r: Pt[]): number {
  let s = 0;
  for (let i = 0; i < r.length; i++) { const a = r[i], b = r[(i + 1) % r.length]; s += a[0] * b[1] - b[0] * a[1]; }
  return s / 2;
}

function perimeter(r: Pt[]): number {
  let s = 0;
  for (let i = 0; i < r.length; i++) { const a = r[i], b = r[(i + 1) % r.length]; s += Math.hypot(b[0] - a[0], b[1] - a[1]); }
  return s;
}

/** b rotated (cyclically) so that b[i] corresponds best to a[i], after removing each ring's
 *  centroid (so that a part that moved still matches by shape). Both rings: same length and
 *  winding. */
export function alignRing(a: Pt[], b: Pt[]): Pt[] {
  const n = a.length;
  const ca = a.reduce((s, p) => [s[0] + p[0] / n, s[1] + p[1] / n], [0, 0]);
  const cb = b.reduce((s, p) => [s[0] + p[0] / n, s[1] + p[1] / n], [0, 0]);
  let best = 0, bestErr = Infinity;
  for (let k = 0; k < n; k++) {
    let e = 0;
    for (let i = 0; i < n && e < bestErr; i++) {
      const p = a[i], q = b[(i + k) % n];
      const dx = p[0] - ca[0] - (q[0] - cb[0]), dy = p[1] - ca[1] - (q[1] - cb[1]);
      e += dx * dx + dy * dy;
    }
    if (e < bestErr) { bestErr = e; best = k; }
  }
  return a.map((_, i) => b[(i + best) % n]);
}

/** A closed ring as a smooth path (Catmull-Rom through the points, as cubic Beziers). */
export function ringToCmds(r: Pt[]): Cmd[] {
  const n = r.length;
  const P = (i: number) => r[((i % n) + n) % n];
  const out: Cmd[] = [{ k: "M", p: r[0] }];
  for (let i = 0; i < n; i++) {
    const p0 = P(i - 1), p1 = P(i), p2 = P(i + 1), p3 = P(i + 2);
    const c1: Pt = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: Pt = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    out.push({ k: "C", p: [c1, c2, p2] });
  }
  out.push({ k: "Z" });
  return out;
}

/** The same as a path string (tests, debugging). */
export function ringToD(r: Pt[]): string {
  const f = (v: number) => (Math.round(v * 100) / 100).toString();
  return ringToCmds(r).map((c) => (c.k === "Z" ? "Z" : c.k === "C" ? `C${c.p.map((q) => `${f(q[0])} ${f(q[1])}`).join(" ")}` : `${c.k}${f(c.p[0])} ${f(c.p[1])}`)).join(" ");
}

const cmdsOf = (s: VShape): Cmd[] => s.cmds ?? parsePath(s.d);
const ringsOf = (s: VShape): Pt[][] => flatten(cmdsOf(s), 16);

/** fade: the side (0 = a, 1 = b) where the shape is gone (it collapses and fades out) */
interface ShapePair { a: VShape; b: VShape; rings: [Pt[], Pt[]][] | null; fade?: 0 | 1 }
/** rigid: the boxes of a rigid part (VPart.morph "rigid") in a and b */
interface PartPair { a?: VPart; b?: VPart; shapes: ShapePair[]; rigid?: [Box, Box] }
type Box = [number, number, number, number];

/** Precomputed correspondence of two drawings (b is moved onto a's anchor: the hips for body
 *  drawings, the head pivot for head drawings). */
export interface MorphPair { a: BodyViewDoc; b: BodyViewDoc; parts: PartPair[] }

function ringPair(r0: Pt[], r1: Pt[]): [Pt[], Pt[]] {
  const n = Math.max(MIN_N, Math.min(MAX_N, Math.round(Math.max(perimeter(r0), perimeter(r1)) / SPACING)));
  let A = resampleRing(r0, n), B = resampleRing(r1, n);
  if (area(A) < 0) A = A.reverse();
  if (area(B) < 0) B = B.reverse();
  return [A, alignRing(A, B)];
}

function pairShape(sa: VShape, sb: VShape): ShapePair {
  const ra = ringsOf(sa), rb = ringsOf(sb);
  if (ra.length !== rb.length || !ra.length) return { a: sa, b: sb, rings: null };
  return { a: sa, b: sb, rings: ra.map((r0, i) => ringPair(r0, rb[i])) };
}

/** A shape that only one drawing has, paired with itself squeezed to the vertical line x = edge
 *  (`present` is a's shape when `aSide`, else b's). */
function collapseShape(s: VShape, edge: number, aSide: boolean): ShapePair {
  const rings = ringsOf(s).map((r0): [Pt[], Pt[]] => {
    let A = resampleRing(r0, Math.max(MIN_N, Math.min(MAX_N, Math.round(perimeter(r0) / SPACING))));
    if (area(A) < 0) A = A.reverse();
    const B = A.map((p): Pt => [edge, p[1]]);
    return aSide ? [A, B] : [B, A];
  });
  return { a: s, b: s, rings, fade: aSide ? 1 : 0 };
}

/** x range of a closed polyline along the row y (null when the row misses it). */
function rowSpan(r: Pt[], y: number): [number, number] | null {
  let x0 = Infinity, x1 = -Infinity;
  for (let i = 0; i < r.length; i++) {
    const a = r[i], b = r[(i + 1) % r.length];
    if ((a[1] - y) * (b[1] - y) > 0 || a[1] === b[1]) continue;
    const x = a[0] + ((y - a[1]) / (b[1] - a[1])) * (b[0] - a[0]);
    x0 = Math.min(x0, x); x1 = Math.max(x1, x);
  }
  return isFinite(x0) ? [x0, x1] : null;
}

/** The collapse line x kept inside an outline (the drawing that lacks the part): a part that
 *  vanishes behind the profile must not be left outside the head (the far eye, brow and
 *  the inner bands of the far ear stuck out of the side head at 80-90 deg). */
function inside(edge: number, y: number, outline: Pt[] | undefined, margin: number): number {
  const sp = outline && outline.length ? rowSpan(outline, y) : null;
  if (!sp || sp[1] - sp[0] < 2 * margin) return edge;
  return Math.max(sp[0] + margin, Math.min(sp[1] - margin, edge));
}

function box4(p: VPart): [number, number, number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const s of p.shapes) for (const r of ringsOf(s)) for (const q of r) { x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]); }
  return [x0, y0, x1, y1];
}
/** Nearest point of a closed polyline. */
function nearestOn(r: Pt[], p: Pt): Pt {
  let best: Pt = r[0], bd = Infinity;
  for (let i = 0; i < r.length; i++) {
    const a = r[i], b = r[(i + 1) % r.length];
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const l2 = dx * dx + dy * dy || 1;
    const u = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
    const q: Pt = [a[0] + dx * u, a[1] + dy * u];
    const d = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2;
    if (d < bd) { bd = d; best = q; }
  }
  return best;
}
/** The outer outline of a part (its ring of largest area). */
function outerRing(p: VPart): Pt[] {
  let best: Pt[] = [], ba = -1;
  for (const s of p.shapes) for (const r of ringsOf(s)) { const a = Math.abs(area(r)); if (a > ba) { ba = a; best = r; } }
  return best;
}

/** A part that only one drawing has, paired with itself carried along by a part of its group
 *  that both drawings have (box to box): the eye-white ring of the turned heads follows the
 *  eye white of the front head. */
function followShape(s: VShape, from: [number, number, number, number], to: [number, number, number, number], aSide: boolean, onto?: Pt[]): ShapePair {
  const sx = (to[2] - to[0]) / Math.max(1e-6, from[2] - from[0]), sy = (to[3] - to[1]) / Math.max(1e-6, from[3] - from[1]);
  const g = (p: Pt): Pt => [to[0] + (p[0] - from[0]) * sx, to[1] + (p[1] - from[1]) * sy];
  // ...and pressed onto the mate's outline there, so it has no area (it grows out of the
  // outline instead of being drawn as a second outline)
  const f = onto ? (p: Pt): Pt => nearestOn(onto, g(p)) : g;
  const rings = ringsOf(s).map((r0): [Pt[], Pt[]] => {
    let A = resampleRing(r0, Math.max(MIN_N, Math.min(MAX_N, Math.round(perimeter(r0) / SPACING))));
    if (area(A) < 0) A = A.reverse();
    const B = A.map(f);
    return aSide ? [A, B] : [B, A];
  });
  return { a: s, b: s, rings };
}

function moveView(v: BodyViewDoc, d: Pt): BodyViewDoc {
  if (!d[0] && !d[1]) return v;
  const f = (p: Pt): Pt => [p[0] + d[0], p[1] + d[1]];
  const skeleton: Record<string, Pt> = {};
  for (const [k, p] of Object.entries(v.skeleton)) skeleton[k] = k === "head_radius" ? p : f(p);
  const mapS = (s: VShape): VShape => (s.cmds
    ? { ...s, cmds: s.cmds.map((c): Cmd => (c.k === "Z" ? c : c.k === "C" ? { k: "C", p: [f(c.p[0]), f(c.p[1]), f(c.p[2])] } : { k: c.k, p: f(c.p) })) }
    : { ...s, cmds: parsePath(s.d).map((c): Cmd => (c.k === "Z" ? c : c.k === "C" ? { k: "C", p: [f(c.p[0]), f(c.p[1]), f(c.p[2])] } : { k: c.k, p: f(c.p) })), d: "" });
  return {
    ...v, skeleton,
    parts: v.parts.map((p) => ({ ...p, pivot: f(p.pivot), shapes: p.shapes.map(mapS) })),
    chains: v.chains?.map((c) => ({ ...c, root: f(c.root), tip: f(c.tip) })),
  };
}

export interface MorphOptions {
  /** squeeze parts / shapes that one drawing lacks instead of taking the nearer drawing whole
   *  (head drawings) */
  collapse?: boolean;
  /** point spacing of the resampled outlines (default 8 px; the first prototype used 5 px
   *  with 64..320 points) */
  spacing?: number;
  /** ids of parts moved rigidly (VPart.morph "rigid" given on the front drawing) */
  rigid?: Set<string>;
}

export function morphPair(a: BodyViewDoc, b0: BodyViewDoc, opt: MorphOptions = {}): MorphPair {
  const keep = [SPACING, MIN_N, MAX_N];
  if (opt.spacing && opt.spacing !== 8) [SPACING, MIN_N, MAX_N] = opt.spacing <= 5 ? [opt.spacing, 64, 320] : [opt.spacing, 40, 200];
  try { return pairDocs(a, b0, opt); } finally { [SPACING, MIN_N, MAX_N] = keep; }
}

function pairDocs(a: BodyViewDoc, b0: BodyViewDoc, opt: MorphOptions): MorphPair {
  // body drawings turn about the hips axis (x only); head drawings sit on their pivot
  const body = !!(a.skeleton.hips && b0.skeleton.hips);
  const d: Pt = body ? [a.skeleton.hips[0] - b0.skeleton.hips[0], 0] : [a.skeleton.head[0] - b0.skeleton.head[0], a.skeleton.head[1] - b0.skeleton.head[1]];
  const b = moveView(b0, d);
  // the side a part that one drawing lacks disappears to: the way the head turns toward the
  // drawing that lacks it (yaw < 0 = the face goes to screen left)
  const dirToB = Math.sign(b.yaw - a.yaw) || 1;
  const byB = new Map(b.parts.map((p) => [p.id, p]));
  const bAll = new Map(byB);
  const parts: PartPair[] = [];
  const collapsePart = (p: VPart, aSide: boolean): PartPair => {
    // carried along by a part of its group both drawings have (the eye white first)
    const mates = p.group ? a.parts.filter((x) => x.group === p.group && x.id !== p.id && bAll.has(x.id)) : [];
    const ref = mates.find((x) => x.id.endsWith("_white")) ?? mates.find((x) => x.visible) ?? mates[0];
    if (ref) {
      const refB = bAll.get(ref.id)!;
      const ra = box4(ref), rb = box4(refB);
      return { a: p, b: p, shapes: p.shapes.map((s) => (aSide ? followShape(s, ra, rb, true, outerRing(refB)) : followShape(s, rb, ra, false, outerRing(ref)))) };
    }
    const bx = box4(p);
    const miss = aSide ? bAll.get("head") : a.parts.find((x) => x.id === "head");
    const edge = inside((aSide ? dirToB : -dirToB) > 0 ? bx[2] : bx[0], (bx[1] + bx[3]) / 2, miss && outerRing(miss), Math.min(12, (bx[2] - bx[0]) / 2));
    return { a: p, b: p, shapes: p.shapes.map((s) => collapseShape(s, edge, aSide)) };
  };
  for (const pa of a.parts) {
    const pb = byB.get(pa.id);
    byB.delete(pa.id);
    if (!pb) { parts.push(opt.collapse ? collapsePart(pa, true) : { a: pa, shapes: [] }); continue; }
    if (pa.morph === "rigid" || pb.morph === "rigid" || opt.rigid?.has(pa.id)) { parts.push({ a: pa, b: pb, shapes: [], rigid: [box4(pa), box4(pb)] }); continue; }
    const named = pa.shapes.every((s) => pb.shapes.some((t) => t.name === s.name)) && pb.shapes.every((s) => pa.shapes.some((t) => t.name === s.name));
    let shapes: ShapePair[] = [];
    if (pa.shapes.length === pb.shapes.length && (named || !opt.collapse)) {
      shapes = pa.shapes.map((s, i) => pairShape(s, named ? pb.shapes.find((t) => t.name === s.name)! : pb.shapes[i]));
    } else if (opt.collapse) {
      // shapes matched by name; the others squeeze into the part's edge
      // a shape one side lacks (the inner bands of the far ear) collapses inside the part's
      // outline on the side that lacks it
      const ba = box4(pa), bb = box4(pb), oa = outerRing(pa), ob = outerRing(pb);
      const cy = (b4: Box) => (b4[1] + b4[3]) / 2;
      const ea = inside(dirToB > 0 ? ba[2] : ba[0], cy(ba), ob, 6), eb = inside(dirToB > 0 ? bb[0] : bb[2], cy(bb), oa, 6);
      const all = [...pa.shapes.map((s) => s.name), ...pb.shapes.map((s) => s.name).filter((n) => !pa.shapes.some((s) => s.name === n))];
      shapes = all.map((n) => {
        const sa = pa.shapes.find((s) => s.name === n), sb = pb.shapes.find((s) => s.name === n);
        if (sa && sb) return pairShape(sa, sb);
        return sa ? collapseShape(sa, ea, true) : collapseShape(sb!, eb, false);
      });
    }
    parts.push({ a: pa, b: pb, shapes });
  }
  for (const pb of byB.values()) parts.push(opt.collapse ? collapsePart(pb, false) : { b: pb, shapes: [] });
  return { a, b, parts };
}

const smooth = (x: number) => { const c = Math.max(0, Math.min(1, x)); return c * c * (3 - 2 * c); };
const lerpBox = (a: Box, b: Box, t: number): Box => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t), lerp(a[3], b[3], t)];

/** A rigid part: the nearer drawing's shape moved and uniformly scaled from its box `from` to
 *  the box `to` (centre to centre). */
function rigidPart(p: VPart, from: Box, to: Box): VPart {
  const k = (to[2] - to[0] + to[3] - to[1]) / Math.max(1e-6, from[2] - from[0] + from[3] - from[1]);
  const cf: Pt = [(from[0] + from[2]) / 2, (from[1] + from[3]) / 2], ct: Pt = [(to[0] + to[2]) / 2, (to[1] + to[3]) / 2];
  const f = (q: Pt): Pt => [ct[0] + (q[0] - cf[0]) * k, ct[1] + (q[1] - cf[1]) * k];
  return {
    ...p, pivot: f(p.pivot),
    shapes: p.shapes.map((s) => ({ ...s, d: "", cmds: mapCmds(cmdsOf(s), f), flat: s.flat?.map((r) => r.map(f)) })),
  };
}

/** Numeric records mixed key by key (a key one side lacks keeps the other side's value). */
function lerpRec<T extends Record<string, unknown>>(a: T | undefined, b: T | undefined, t: number): T | undefined {
  if (!a || !b) return (t < 0.5 ? a : b) ?? a ?? b;
  const out: Record<string, unknown> = { ...(t < 0.5 ? a : b) };
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const x = a[k], y = b[k];
    if (typeof x === "number" && typeof y === "number") out[k] = lerp(x, y, t);
  }
  return out as T;
}

/** `near` order with the ids only `other` lists put after their predecessor in `other`. */
function mergeOrder(near: string[] | undefined, other: string[] | undefined): string[] | undefined {
  if (!near || !other) return near;
  const out = near.slice();
  const has = new Set(out);
  other.forEach((id, i) => {
    if (has.has(id)) return;
    let j = -1;
    for (let k = i - 1; k >= 0 && j < 0; k--) j = out.indexOf(other[k]);
    out.splice(j + 1, 0, id);
    has.add(id);
  });
  return out;
}

/** The drawing in between: t = 0 is a, t = 1 is b. */
export function morphView(m: MorphPair, t: number): BodyViewDoc {
  const near = t < 0.5 ? m.a : m.b, far = t < 0.5 ? m.b : m.a;
  const skeleton: Record<string, Pt> = {};
  for (const [k, p] of Object.entries(m.a.skeleton)) skeleton[k] = m.b.skeleton[k] ? lerpPt(p, m.b.skeleton[k], t) : p;
  for (const [k, p] of Object.entries(m.b.skeleton)) if (!skeleton[k]) skeleton[k] = p;
  const parts: VPart[] = [];
  for (const pp of m.parts) {
    const base = (t < 0.5 ? pp.a ?? pp.b : pp.b ?? pp.a)!;
    if (!pp.a || !pp.b) { if ((pp.a && t < 0.5) || (pp.b && t >= 0.5)) parts.push(base); continue; }
    if (pp.rigid) { parts.push(rigidPart(base, pp.rigid[t < 0.5 ? 0 : 1], lerpBox(pp.rigid[0], pp.rigid[1], t))); continue; }
    if (!pp.shapes.length) { parts.push(base); continue; }
    const shapes: VShape[] = [];
    for (const sp of pp.shapes) {
      const s0 = t < 0.5 ? sp.a : sp.b;
      if (!sp.rings) { shapes.push(s0); continue; }
      // a collapsing shape fades out over the last part of its way (no hairline is left)
      const rest = sp.fade === undefined ? 1 : sp.fade === 1 ? 1 - t : t;
      const alpha = smooth((rest - 0.25) / 0.45);
      if (alpha <= 0.01) continue;
      const rings = sp.rings.map(([A, B]) => A.map((p, j) => lerpPt(p, B[j], t)));
      shapes.push({ name: s0.name, fill: s0.fill, d: "", cmds: rings.flatMap(ringToCmds), flat: rings, ...(alpha < 0.99 ? { alpha } : {}) });
    }
    if (!shapes.length) continue;
    parts.push({ ...base, pivot: lerpPt(pp.a.pivot, pp.b.pivot, t), shapes });
  }
  const chainsB = new Map((m.b.chains ?? []).map((c) => [c.id, c]));
  const chains: ChainDef[] | undefined = (near.chains ?? []).map((c) => {
    const ca = (m.a.chains ?? []).find((x) => x.id === c.id), cb = chainsB.get(c.id);
    return ca && cb ? { ...c, root: lerpPt(ca.root, cb.root, t), tip: lerpPt(ca.tip, cb.tip, t) } : c;
  });
  const ho = (v: BodyViewDoc): Pt => v.headOffset ?? [0, 0];
  const headOffset = lerpPt(ho(m.a), ho(m.b), t);
  const fw = (v: BodyViewDoc) => v.frontWeight ?? 0;
  const frontWeight = lerp(fw(m.a), fw(m.b), t);
  const out: BodyViewDoc = {
    ...near,
    view: `morph${Math.round(lerp(m.a.yaw, m.b.yaw, t) * 10) / 10}`,
    yaw: lerp(m.a.yaw, m.b.yaw, t),
    skeleton,
    parts,
    chains,
    order: mergeOrder(near.order, far.order),
    parallax: lerpRec(m.a.parallax, m.b.parallax, t),
    headTurn: lerpRec(m.a.headTurn, m.b.headTurn, t),
    ...(frontWeight ? { frontWeight } : {}),
  };
  if (headOffset[0] || headOffset[1]) out.headOffset = headOffset; else delete out.headOffset;
  if (!out.parallax) delete out.parallax;
  if (!out.headTurn) delete out.headTurn;
  if (!out.order) delete out.order;
  return out;
}
