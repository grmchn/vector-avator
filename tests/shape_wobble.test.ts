// Wobble of the flat-colour shapes: the part data stays as it is; the outline points are
// displaced by a smooth field that depends only on the position (and the boil step).
import { describe, expect, it } from "vitest";
import {
  SHAPE_PRESETS, emitWobbled, frameWobbleMap, shapeFromQuery, shapeSeed, shapeWobbleMap, wobbleMulti, wobbleRing, type ShapeWobble,
} from "../src/renderers/vector/wobble";
import type { Cmd, Pt } from "../src/renderers/vector/vdata";

const S: ShapeWobble = { ...SHAPE_PRESETS.mid };
const square: Pt[] = [[0, 0], [100, 0], [100, 100], [0, 100]];

describe("shapeFromQuery", () => {
  it("is off by default and reads names, numbers and overrides", () => {
    expect(shapeFromQuery(new URLSearchParams(""))).toBeNull();
    expect(shapeFromQuery(new URLSearchParams("vShape=0"))).toBeNull();
    expect(shapeFromQuery(new URLSearchParams("vShape=off"))).toBeNull();
    expect(shapeFromQuery(new URLSearchParams("vShape=1"))).toEqual(SHAPE_PRESETS.weak);
    expect(shapeFromQuery(new URLSearchParams("vShape=strong"))).toEqual(SHAPE_PRESETS.strong);
    const o = shapeFromQuery(new URLSearchParams("vShape=mid&vShapeAmp=3&vShapeWave=20&vShapeBoil=8&vShapeSeed=5"))!;
    expect(o).toMatchObject({ amp: 3, wave: 20, boil: 8, seed: 5 });
  });
  it("gets stronger from weak to strong", () => {
    expect(SHAPE_PRESETS.weak.amp).toBeLessThan(SHAPE_PRESETS.mid.amp);
    expect(SHAPE_PRESETS.mid.amp).toBeLessThan(SHAPE_PRESETS.strong.amp);
  });
});

describe("shapeWobbleMap", () => {
  it("is null for no wobble and deterministic otherwise", () => {
    expect(shapeWobbleMap(null)).toBeNull();
    expect(shapeWobbleMap({ ...S, amp: 0 })).toBeNull();
    const a = shapeWobbleMap(S, 0)!, b = shapeWobbleMap(S, 0)!;
    expect(a([12.3, 45.6])).toEqual(b([12.3, 45.6]));
  });

  it("stays within the amplitude and varies smoothly", () => {
    const f = shapeWobbleMap(S)!;
    for (let x = 0; x < 300; x += 3.7) {
      const p = f([x, 40]), q = f([x + 0.5, 40]);
      expect(Math.abs(p[0] - x)).toBeLessThanOrEqual(S.amp + 1e-9);
      expect(Math.abs(p[1] - 40)).toBeLessThanOrEqual(S.amp + 1e-9);
      expect(Math.hypot(q[0] - p[0] - 0.5, q[1] - p[1])).toBeLessThan(0.15);
    }
  });

  it("is the same at every time without a boil, and changes with the boil steps", () => {
    const p: Pt = [80, 120];
    expect(shapeWobbleMap(S, 0)!(p)).toEqual(shapeWobbleMap(S, 7.3)!(p));
    const B = { ...S, boil: 8 };
    expect(shapeSeed(B, 0.01)).toBe(shapeSeed(B, 0.1));
    expect(shapeSeed(B, 0.01)).not.toBe(shapeSeed(B, 0.13));
    expect(shapeWobbleMap(B, 0.01)!(p)).toEqual(shapeWobbleMap(B, 0.1)!(p));
    expect(shapeWobbleMap(B, 0.01)!(p)).not.toEqual(shapeWobbleMap(B, 0.13)!(p));
  });

  it("moves two parts that touch at one point to the same place (no gaps)", () => {
    // the field depends on the position only: the shared corner of two parts maps equally
    const f = shapeWobbleMap(S)!;
    const left = wobbleRing([[0, 0], [100, 0], [100, 100], [0, 100]], f, 4);
    const right = wobbleRing([[100, 0], [200, 0], [200, 100], [100, 100]], f, 4);
    // corners (100,0) and (100,100): left ring points 25 and 50, right ring points 0 and 75
    expect(right[0]).toEqual(left[25]);
    expect(right[75]).toEqual(left[50]);
  });
});

describe("wobbleRing / wobbleMulti", () => {
  it("cuts the outline into pieces and keeps a closing point closed", () => {
    const f = shapeWobbleMap(S)!;
    const r = wobbleRing(square, f, 4);
    expect(r.length).toBe(100); // 400 px of outline at 4 px
    const closed = wobbleRing([...square, square[0]], f, 4);
    expect(closed.length).toBe(101);
    expect(closed[closed.length - 1]).toEqual(closed[0]);
    // no piece is longer than the step plus the wobble difference
    for (let i = 0; i < r.length; i++) {
      const a = r[i], b = r[(i + 1) % r.length];
      expect(Math.hypot(b[0] - a[0], b[1] - a[1])).toBeLessThan(4 + 2 * Math.SQRT2 * S.amp * 0.5);
    }
  });

  it("with no displacement gives back the same shape, cut into pieces", () => {
    const r = wobbleRing(square, (p) => p, 10);
    expect(r[0]).toEqual([0, 0]);
    expect(r[10]).toEqual([100, 0]);
    expect(r.length).toBe(40);
  });

  it("maps every ring of a multipolygon", () => {
    const mp = wobbleMulti([[[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]], [[[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]]], (p) => [p[0] + 1, p[1]], 5);
    expect(mp.length).toBe(2);
    expect(mp[0][0][0]).toEqual([1, 0]);
    expect(mp[1][0][0]).toEqual([21, 0]);
  });
});

describe("frameWobbleMap", () => {
  it("carries the wobble along with a moving and turning frame", () => {
    const f = shapeWobbleMap(S)!;
    const m0 = frameWobbleMap(f, [100, 200], 0);
    const ang = 0.9, c = Math.cos(ang), s = Math.sin(ang), o: Pt = [-30, 55];
    const m1 = frameWobbleMap(f, o, ang);
    const rot = (p: Pt): Pt => [o[0] + c * (p[0] - 100) - s * (p[1] - 200), o[1] + s * (p[0] - 100) + c * (p[1] - 200)];
    for (const p of [[110, 230], [90, 260], [140, 205]] as Pt[]) {
      const a = rot(m0(p)), b = m1(rot(p));
      expect(b[0]).toBeCloseTo(a[0], 9);
      expect(b[1]).toBeCloseTo(a[1], 9);
    }
  });
});

describe("emitWobbled", () => {
  const calls: string[] = [];
  const pts: Pt[] = [];
  const stub = {
    moveTo: (x: number, y: number) => { calls.push("M"); pts.push([x, y]); },
    lineTo: (x: number, y: number) => { calls.push("L"); pts.push([x, y]); },
    closePath: () => calls.push("Z"),
  } as unknown as Path2D;

  it("emits short lines for lines and curves, keeps the subpath structure", () => {
    const cmds: Cmd[] = [
      { k: "M", p: [0, 0] }, { k: "L", p: [40, 0] }, { k: "C", p: [[60, 0], [80, 20], [80, 40]] }, { k: "Z" },
      { k: "M", p: [200, 0] }, { k: "L", p: [200, 8] }, { k: "Z" },
    ];
    emitWobbled(cmds, (p) => p, 4, stub);
    expect(calls.filter((c) => c === "M").length).toBe(2);
    expect(calls.filter((c) => c === "Z").length).toBe(2);
    expect(calls.filter((c) => c === "L").length).toBeGreaterThan(20);
    for (let i = 1; i < pts.length; i++) {
      if (calls[i] !== "L") continue;
      expect(Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])).toBeLessThanOrEqual(4.01 + 0.01);
    }
    // the curve ends at its end point
    const last = pts.findIndex((p, i) => calls[i] === "L" && p[0] === 80 && p[1] === 40);
    expect(last).toBeGreaterThan(0);
  });
});
