import { describe, expect, it } from "vitest";
import { quatAngleDeg, quatFromEulerDeg, quatMul } from "../src/core/math";
import { parseMotion, samplePose, sampleFace } from "../src/core/motion";

describe("motion reach track", () => {
  const m = parseMotion({
    name: "r", duration: 2, loop: false,
    keys: [
      { t: 0, reach: { L: [1.2, 0.3, 0] } },
      { t: 1, ease: "linear", reach: { L: [1.2, 0.3, 1] } },
      { t: 2, reach: { L: [1.0, 0.5, 1] } },
    ],
  });
  it("is absent while the weight is 0", () => {
    expect(samplePose(m, 0).reach).toBeUndefined();
  });
  it("interpolates the target and the weight", () => {
    const r = samplePose(m, 0.5).reach!.L!;
    expect(r.u).toBeCloseTo(1.2, 9);
    expect(r.w).toBeGreaterThan(0.2);
    expect(r.w).toBeLessThan(0.8);
    const e = samplePose(m, 2).reach!.L!;
    expect([e.u, e.v, e.w]).toEqual([1.0, 0.5, 1]);
  });
});

describe("additive layer", () => {
  const m = parseMotion({
    name: "a", duration: 2, loop: false,
    keys: [{ t: 0, bones: { head: [0, 20, 0] }, face: { yaw: 10, expression: "smile" } }],
    additive: [
      { t: 0.5, bones: { head: [0, 0, 0] }, face: { pitch: 0 } },
      { t: 1, bones: { head: [5, 0, 0] }, face: { pitch: -4 } },
      { t: 1.5, bones: { head: [0, 0, 0] }, face: { pitch: 0 } },
    ],
  });
  it("multiplies bone rotations on top of the sampled pose", () => {
    const p = samplePose(m, 1);
    const want = quatMul(quatFromEulerDeg(0, 20, 0), quatFromEulerDeg(5, 0, 0));
    expect(quatAngleDeg(p.bones.head, want)).toBeLessThan(1e-6);
    expect(quatAngleDeg(samplePose(m, 1.6).bones.head, quatFromEulerDeg(0, 20, 0))).toBeLessThan(1e-6);
  });
  it("adds the numeric face fields and keeps the discrete ones", () => {
    const f = sampleFace(m, 1);
    expect(f.pitch).toBeCloseTo(-4, 9);
    expect(f.yaw).toBeCloseTo(10, 9);
    expect(f.expression).toBe("smile");
  });
});
