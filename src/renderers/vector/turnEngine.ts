// Turn engine for method V: the body and the head are drawn at any angle from key
// drawings 30 deg apart (front, 30, 60, 90 deg; mirrored for the other way) and in-betweens
// (morph.ts). One composed character (LoadedVector) is built per pair of drawing angles
// (body, head) and handed to one child renderer, which only swaps the shapes, landmarks and
// chain rests (VectorRenderer.swapVector): the canvas, the rig, the swing of the chains and
// the face state stay.
//
// Drawing angle of a yaw (deg):
// - |yaw| <= dead: the front drawing (the rest of the yaw is turned flat / by parallax, as
//   before the engine: small turns in gestures and idle sway keep the front drawing);
// - from dead to the first key the drawing angle runs 0 -> key, so it is continuous;
// - beyond, the drawing angle is the yaw;
// - all quantized to `step` deg and clamped to the keys.
import type { BodyViewDoc } from "./bodyView";
import { composeView, frontBodyView, frontHeadView } from "./bodyView";
import { DEFAULT_HEAD_TURN, DEFAULT_PARALLAX } from "./head";
import { morphPair, morphView, ringToD, type MorphPair } from "./morph";
import { parsePath, prepareVector, type LoadedVector, type VectorDoc, type VPart } from "./vdata";

export interface TurnOptions {
  /** quantization of the drawing angle (deg) */
  step: number;
  /** body / head yaw (deg) up to which the front drawing is kept */
  bodyDead: number;
  headDead: number;
  /** reproduce the first prototype: in-betweens go through path strings (for timing) */
  strings?: boolean;
}

const parseShapes = (parts: VPart[]): VPart[] => parts.map((p) => ({ ...p, shapes: p.shapes.map((s) => (s.cmds ? s : { ...s, cmds: parsePath(s.d), d: "" })) }));
const parseView = (v: BodyViewDoc): BodyViewDoc => ({ ...v, parts: parseShapes(v.parts) });
/** The in-between with its shapes as path strings again (the prototype's round trip). */
const stringView = (v: BodyViewDoc): BodyViewDoc => ({
  ...v,
  parts: v.parts.map((p) => ({ ...p, shapes: p.shapes.map((s) => (s.flat ? { name: s.name, fill: s.fill, d: s.flat.map(ringToD).join(" ") } : s)) })),
});

export class TurnEngine {
  readonly bodyAngles: number[];
  readonly headAngles: number[];
  private front: VectorDoc;
  private bodies = new Map<number, BodyViewDoc>();
  private heads = new Map<number, BodyViewDoc>();
  private pairs = new Map<string, MorphPair>();
  private cache = new Map<string, LoadedVector>();
  /** parts moved rigidly in the in-betweens (VPart.morph "rigid" on the front drawing) */
  private rigid: Set<string>;
  /** builds done (cache misses), for measurements */
  builds = 0;

  constructor(front: VectorDoc, bodies: Map<number, BodyViewDoc>, heads: Map<number, BodyViewDoc>, readonly opt: TurnOptions) {
    const s = !opt.strings;
    this.rigid = new Set(front.parts.filter((p) => p.morph === "rigid").map((p) => p.id));
    this.front = s ? { ...front, parts: parseShapes(front.parts) } : front;
    for (const [a, v] of bodies) this.bodies.set(a, s ? parseView(v) : v);
    this.bodies.set(0, s ? parseView(frontBodyView(front)) : frontBodyView(front));
    // head keys carry complete parallax / head-turn records so that they mix key by key
    const { reach: _r, ...ft } = front.headTurn ?? {};
    const full = (h: BodyViewDoc): BodyViewDoc => ({
      ...h,
      parallax: { ...DEFAULT_PARALLAX, ...(front.parallax ?? {}), ...(h.parallax ?? {}) },
      headTurn: { ...DEFAULT_HEAD_TURN, ...ft, ...(h.headTurn ?? {}) } as unknown as BodyViewDoc["headTurn"],
    });
    for (const [a, v] of heads) this.heads.set(a, full(s ? parseView(v) : v));
    this.heads.set(0, full(s ? parseView(frontHeadView(front)) : frontHeadView(front)));
    this.bodyAngles = [...this.bodies.keys()].sort((a, b) => a - b);
    this.headAngles = [...this.heads.keys()].sort((a, b) => a - b);
  }

  /** Drawing angle (deg) for a yaw (deg) over the given keys. */
  static drawAngle(yaw: number, keys: number[], dead: number, step: number): number {
    const sg = Math.sign(yaw), y = Math.abs(yaw);
    const first = Math.min(...keys.filter((k) => k * sg > 0).map(Math.abs), Infinity);
    let m: number;
    if (y <= dead || !isFinite(first)) m = 0;
    else if (y < first) m = (first * (y - dead)) / Math.max(1e-6, first - dead);
    else m = y;
    const q = step > 0 ? Math.round(m / step) * step : m;
    const lo = keys[0], hi = keys[keys.length - 1];
    return Math.max(lo, Math.min(hi, sg * q)) || 0;
  }

  bodyAngle(yaw: number): number { return TurnEngine.drawAngle(yaw, this.bodyAngles, this.opt.bodyDead, this.opt.step); }
  headAngle(yaw: number): number { return TurnEngine.drawAngle(yaw, this.headAngles, this.opt.headDead, this.opt.step); }

  /** The drawing at an angle (key or in-between). */
  private viewAt(kind: "body" | "head", deg: number): BodyViewDoc {
    const m = kind === "body" ? this.bodies : this.heads;
    const keys = kind === "body" ? this.bodyAngles : this.headAngles;
    const have = m.get(deg);
    if (have) return have;
    let i = 0;
    while (i + 1 < keys.length && keys[i + 1] <= deg) i++;
    const a = keys[i], b = keys[Math.min(i + 1, keys.length - 1)];
    const pk = `${kind}${a}|${b}`;
    let pair = this.pairs.get(pk);
    if (!pair) {
      pair = morphPair(m.get(a)!, m.get(b)!, { collapse: kind === "head", spacing: this.opt.strings ? 5 : 8, rigid: this.rigid });
      this.pairs.set(pk, pair);
    }
    const v = morphView(pair, (deg - a) / (b - a));
    return this.opt.strings ? stringView(v) : v;
  }

  /** The composed character for a body drawing angle and a head drawing angle (deg). */
  build(body: number, head: number): LoadedVector {
    const key = `${body}|${head}`;
    const have = this.cache.get(key);
    if (have) { this.cache.delete(key); this.cache.set(key, have); return have; }
    this.builds++;
    const lv = prepareVector(composeView(this.front, this.viewAt("body", body), this.viewAt("head", head)));
    this.cache.set(key, lv);
    while (this.cache.size > 48) this.cache.delete(this.cache.keys().next().value!);
    return lv;
  }
}
