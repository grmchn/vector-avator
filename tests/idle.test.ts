import { describe, expect, it } from "vitest";
import { Idler } from "../src/core/idle";
import { DEFAULT_FACE } from "../src/core/face";
import { quatFromEulerDeg, quatAngleDeg } from "../src/core/math";

describe("idle micro-motion", () => {
  it("is deterministic, small and moves", () => {
    const a = new Idler({ seed: 3 }), b = new Idler({ seed: 3 });
    let lo = 1, hi = -1;
    for (let t = 0; t < 20; t += 0.05) {
      const d = a.at(t);
      expect(d).toEqual(b.at(t));
      expect(Math.abs(d.x)).toBeLessThanOrEqual(0.008 + 1e-9);
      expect(Math.abs(d.roll)).toBeLessThanOrEqual(2);
      lo = Math.min(lo, d.x); hi = Math.max(hi, d.x);
    }
    expect(hi - lo).toBeGreaterThan(0.008);
  });
  it("raises the hip over the supporting leg and leans the head the other way", () => {
    const i = new Idler({ seed: 5 });
    const pose = { bones: {}, hips: [0, 0, 0] as [number, number, number] };
    for (const t of [0.3, 1.7, 4.2]) {
      const d = i.at(t);
      const r = i.apply(pose, DEFAULT_FACE, t);
      expect(Math.sign(d.roll)).toBe(Math.sign(d.x));
      expect(Math.sign(r.face.roll)).toBe(-Math.sign(d.x));
      expect(r.pose.hips[0]).toBeCloseTo(d.x, 12);
      expect(quatAngleDeg(r.pose.bones.hips, quatFromEulerDeg(0, 0, d.roll))).toBeLessThan(1e-6);
      expect(pose.hips[0]).toBe(0);
    }
  });
});
