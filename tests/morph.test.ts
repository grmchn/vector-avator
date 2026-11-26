import { describe, expect, it } from "vitest";
import type { BodyViewDoc } from "../src/renderers/vector/bodyView";
import { alignRing, morphPair, morphView, resampleRing, ringToD } from "../src/renderers/vector/morph";
import { flatten, parsePath, type Cmd, type Pt, type VPart } from "../src/renderers/vector/vdata";
import { TurnEngine } from "../src/renderers/vector/turnEngine";
import { composeView, frontHeadView } from "../src/renderers/vector/bodyView";
import { SpringChain } from "../src/renderers/vector/spring";

const box = (x0: number, y0: number, x1: number, y1: number) => `M${x0} ${y0} L${x1} ${y0} L${x1} ${y1} L${x0} ${y1} Z`;
const part = (id: string, d: string): VPart => ({ id, label: id, parent: null, pivot: [0, 0], visible: true, coverage: "", bone: "hips", layer: "body", shapes: [{ name: "a", d, fill: "#fff" }] });
const view = (yaw: number, hipsX: number, d: string): BodyViewDoc => ({
  format: "so-chara-vector-view/1", yaw, skeleton: { hips: [hipsX, 100], head: [hipsX, 0] }, parts: [part("torso", d)],
});
const ringOf = (s: { d: string; cmds?: Cmd[] }) => flatten(s.cmds ?? parsePath(s.d), 16)[0];
const cx = (r: Pt[]) => r.reduce((s, p) => s + p[0], 0) / r.length;

describe("body in-betweens (morph.ts)", () => {
  it("resamples a ring to evenly spaced points on its outline", () => {
    const r = resampleRing([[0, 0], [10, 0], [10, 10], [0, 10]], 8);
    expect(r).toHaveLength(8);
    expect(r[1][0]).toBeCloseTo(5); expect(r[2][0]).toBeCloseTo(10);
  });
  it("aligns the start of a ring to the best matching point", () => {
    const a = resampleRing([[0, 0], [10, 0], [10, 10], [0, 10]], 8);
    const b = [...a.slice(3), ...a.slice(0, 3)];
    expect(alignRing(a, b)).toEqual(a);
  });
  it("gives the end drawings at t = 0 and 1 and the middle shape in between", () => {
    const m = morphPair(view(-15, 50, box(0, 0, 100, 100)), view(-30, 50, box(20, 0, 80, 100)));
    const w = (t: number) => { const r = ringOf(morphView(m, t).parts[0].shapes[0]); return Math.max(...r.map((p) => p[0])) - Math.min(...r.map((p) => p[0])); };
    // the smooth re-emitted outline rounds sharp corners by about a pixel
    expect(Math.abs(w(0) - 100)).toBeLessThan(2);
    expect(Math.abs(w(1) - 60)).toBeLessThan(2);
    expect(Math.abs(w(0.5) - 80)).toBeLessThan(2);
    expect(morphView(m, 0.5).yaw).toBeCloseTo(-22.5);
  });
  it("puts the second drawing on the first one's hips before blending", () => {
    const m = morphPair(view(-15, 50, box(0, 0, 100, 100)), view(-30, 70, box(20, 0, 120, 100)));
    const r = ringOf(morphView(m, 0.5).parts[0].shapes[0]);
    expect(cx(r)).toBeCloseTo(50, 0);
    expect(morphView(m, 0.5).skeleton.hips[0]).toBeCloseTo(50);
  });
  it("emits a closed smooth path through the points", () => {
    const d = ringToD([[0, 0], [10, 0], [10, 10], [0, 10]]);
    expect(d.startsWith("M0 0")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
    expect(parsePath(d).filter((c) => c.k === "C")).toHaveLength(4);
  });
});

const head = (yaw: number, parts: VPart[], hx = 50): BodyViewDoc => ({
  format: "so-chara-vector-view/1", kind: "head", yaw, skeleton: { head: [hx, 100], head_center: [hx, 50], head_radius: [40, 40] }, parts,
});
const hpart = (id: string, d: string, layer = "feature"): VPart => ({ ...part(id, d), bone: "head", layer });
const xs = (r: Pt[]) => r.map((p) => p[0]);

describe("head in-betweens (morph.ts)", () => {
  it("squeezes a part one drawing lacks into its edge on the side the head turns to", () => {
    // the far eye exists at -60 deg and not at -90 deg: on the way to -90 it flattens to its left edge
    const m = morphPair(head(-90, [hpart("head", box(0, 0, 100, 100), "head")]), head(-60, [hpart("head", box(0, 0, 100, 100), "head"), hpart("eye_R_white", box(10, 40, 30, 60))]), { collapse: true });
    const eye = (t: number) => morphView(m, t).parts.find((p) => p.id === "eye_R_white")!;
    const r1 = ringOf(eye(1).shapes[0]);
    expect(Math.min(...xs(r1))).toBeCloseTo(10, 0);
    expect(Math.max(...xs(r1))).toBeCloseTo(30, 0);
    // gone (faded out) on the side that lacks it; half way it is half as wide and fading
    expect(eye(0)).toBeUndefined();
    const sh = eye(0.5).shapes[0];
    const rh = ringOf(sh);
    expect(Math.max(...xs(rh)) - Math.min(...xs(rh))).toBeCloseTo(10, 0);
    expect(Math.min(...xs(rh))).toBeCloseTo(10, 0);
    expect(sh.alpha).toBeGreaterThan(0.3);
    expect(sh.alpha).toBeLessThan(1);
  });
  it("puts the second head on the first one's pivot and mixes the tunables", () => {
    const a = { ...head(0, [hpart("head", box(0, 0, 100, 100), "head")]), parallax: { head: 0.4 } };
    const b = { ...head(-30, [hpart("head", box(20, 10, 120, 110), "head")], 70), parallax: { head: 0.6 } };
    const v = morphView(morphPair(a, b, { collapse: true }), 0.5);
    expect(cx(ringOf(v.parts[0].shapes[0]))).toBeCloseTo(50, 0);
    expect(v.skeleton.head[0]).toBeCloseTo(50);
    expect(v.parallax!.head).toBeCloseTo(0.5);
  });
});

describe("collapse inside the outline and rigid parts", () => {
  it("keeps a vanishing part inside the head outline of the drawing that lacks it", () => {
    // the far eye sits right of where the side head's outline ends: it collapses inside it
    const m = morphPair(head(-90, [hpart("head", box(0, 0, 60, 100), "head")]), head(-60, [hpart("head", box(0, 0, 100, 100), "head"), hpart("eye_R_white", box(70, 40, 90, 60))]), { collapse: true });
    const r = ringOf(morphView(m, 0.45).parts.find((p) => p.id === "eye_R_white")!.shapes[0]);
    expect(Math.max(...xs(r))).toBeLessThan(90);
  });
  it("moves a rigid part without blending its shape", () => {
    const tail = (x: number, w: number): VPart => ({ ...part("tail", box(x, 0, x + w, w)), morph: "rigid" });
    const a = { ...view(-30, 50, box(0, 0, 10, 10)), parts: [tail(0, 20)] }, b = { ...view(-60, 50, box(0, 0, 10, 10)), parts: [tail(40, 20)] };
    const r = ringOf(morphView(morphPair(a, b), 0.25).parts[0].shapes[0]);
    expect(Math.min(...xs(r))).toBeCloseTo(10, 0);
    expect(Math.max(...xs(r)) - Math.min(...xs(r))).toBeCloseTo(20, 0);
  });
});

describe("turn engine drawing angles (turnEngine.ts)", () => {
  const keys = [-90, -60, -30, 0, 30, 60, 90];
  it("keeps the front drawing for small turns and runs continuously to the first key", () => {
    expect(TurnEngine.drawAngle(5, keys, 7.5, 3)).toBe(0);
    expect(TurnEngine.drawAngle(-7.5, keys, 7.5, 3)).toBe(0);
    expect(TurnEngine.drawAngle(18.75, keys, 7.5, 0)).toBeCloseTo(15);
    expect(TurnEngine.drawAngle(30, keys, 7.5, 3)).toBe(30);
    expect(TurnEngine.drawAngle(-44, keys, 7.5, 3)).toBe(-45);
    expect(TurnEngine.drawAngle(120, keys, 7.5, 3)).toBe(90);
    expect(TurnEngine.drawAngle(10, [0, 60, 90], 0, 3)).toBe(9);
  });
});

describe("front head as a view", () => {
  it("composes like the front character itself", () => {
    const front = {
      format: "x", character: "c", width: 100, height: 200,
      parts: [part("torso", box(0, 100, 100, 200)), hpart("head", box(0, 0, 100, 100), "head"), hpart("nose", box(40, 40, 60, 60))],
      skeleton: { hips: [50, 150], head: [50, 100], head_center: [50, 50], head_radius: [50, 50], shoulder_L: [80, 110], elbow_L: [90, 130], wrist_L: [95, 150], shoulder_R: [20, 110], elbow_R: [10, 130], wrist_R: [5, 150] },
      arms: {} as never, expressions: {},
    } as never;
    const body = { format: "so-chara-vector-view/1", yaw: -30, skeleton: { hips: [50, 150], head: [55, 100] }, parts: [part("torso", box(10, 100, 90, 200))], headOffset: [4, 0] } as BodyViewDoc;
    const a = composeView(front, body), b = composeView(front, body, frontHeadView(front));
    expect(b.parts.map((p) => p.id)).toEqual(a.parts.map((p) => p.id));
    expect(b.skeleton.head_center).toEqual(a.skeleton.head_center);
    expect(b.parts[1].shapes[0].d).toBe(a.parts[1].shapes[0].d);
  });
});

describe("chain rebase (spring.ts)", () => {
  it("keeps the swing when the rest moves", () => {
    const def = { id: "ear", bone: "head", parts: [], root: [0, 0] as Pt, tip: [0, -100] as Pt, segments: 3, stiffness: 0.5, damping: 0.5, gravity: 0 };
    const c = new SpringChain(def);
    c.step(0, [0, 0], 0);
    c.step(1 / 60, [30, 0], 0);
    c.step(1 / 60, [40, 0], 0);
    const th = [...c.state.th];
    c.rebase({ ...def, root: [5, 0], tip: [5, -90] });
    expect(c.state.th).toEqual(th);
    expect(c.segLen).toBeCloseTo(30);
  });
});
