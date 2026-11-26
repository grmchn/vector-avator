import { describe, expect, it } from "vitest";
import { IDENTITY, quatFromEulerDeg, quatMul, quatRotate, type Quat, type Vec3 } from "../src/core/math";
import { DEFAULT_ARM_LIMITS, limitDirection, solveArm, screenTarget } from "../src/core/ik";

const dist = (a: Vec3, b: Vec3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const unit = (v: Vec3): Vec3 => { const l = Math.hypot(...v); return [v[0] / l, v[1] / l, v[2] / l]; };

/** Wrist from forward kinematics of the returned local rotations (independent of the solver). */
function fkWrist(side: "L" | "R", shoulder: Vec3, parent: Quat, up: Quat, lo: Quat, a: number, b: number): { elbow: Vec3; wrist: Vec3 } {
  const s = side === "L" ? 1 : -1;
  const wu = quatMul(parent, up), wl = quatMul(wu, lo);
  const e = quatRotate(wu, [s * a, 0, 0]);
  const elbow: Vec3 = [shoulder[0] + e[0], shoulder[1] + e[1], shoulder[2] + e[2]];
  const f = quatRotate(wl, [s * b, 0, 0]);
  return { elbow, wrist: [elbow[0] + f[0], elbow[1] + f[1], elbow[2] + f[2]] };
}

describe("two-bone arm IK", () => {
  const sh: Vec3 = [60, 200, 0];
  const a = 70, b = 58;

  it("puts the wrist on a reachable target (both sides, rotated parent)", () => {
    for (const side of ["L", "R"] as const) {
      const s = side === "L" ? 1 : -1;
      for (const parent of [IDENTITY, quatFromEulerDeg(5, -12, 8)]) {
        const target: Vec3 = [sh[0] + s * 60, sh[1] + 40, 50];
        const r = solveArm({ side, shoulder: sh, parentRot: parent, upperLen: a, foreLen: b, target });
        expect(r.reached).toBe(true);
        const fk = fkWrist(side, sh, parent, r.upper, r.lower, a, b);
        expect(dist(fk.wrist, target)).toBeLessThan(1e-6 * 1000);
        expect(dist(r.wrist, target)).toBeLessThan(1e-3);
        expect(dist(fk.elbow, sh)).toBeCloseTo(a, 6);
      }
    }
  });

  it("stretches toward an unreachable target", () => {
    const target: Vec3 = [sh[0] + 900, sh[1] + 200, 80];
    const r = solveArm({ side: "L", shoulder: sh, parentRot: IDENTITY, upperLen: a, foreLen: b, target });
    expect(r.reached).toBe(false);
    expect(r.bend).toBeLessThan(1);
    const fk = fkWrist("L", sh, IDENTITY, r.upper, r.lower, a, b);
    expect(dist(fk.wrist, sh)).toBeCloseTo(a + b, 1);
    const want = unit([900, 200, 80]), got = unit([fk.wrist[0] - sh[0], fk.wrist[1] - sh[1], fk.wrist[2] - sh[2]]);
    expect(want[0] * got[0] + want[1] * got[1] + want[2] * got[2]).toBeGreaterThan(0.9999);
  });

  it("bends the elbow toward the pole (down by default)", () => {
    const target: Vec3 = [sh[0] + 80, sh[1], 0];
    const r = solveArm({ side: "L", shoulder: sh, parentRot: IDENTITY, upperLen: a, foreLen: b, target });
    const fk = fkWrist("L", sh, IDENTITY, r.upper, r.lower, a, b);
    expect(fk.elbow[1]).toBeLessThan(sh[1]);
    expect(r.bend).toBeGreaterThan(30);
  });

  it("keeps the range of motion", () => {
    // straight up, behind and across are clamped
    for (const [side, d] of [["L", [0, 1, 0]], ["L", [0.2, 0, -1]], ["R", [1, 0, 0.1]], ["L", [-1, -0.2, 0.3]]] as const) {
      const v = limitDirection(side, d as unknown as Vec3);
      const s = side === "L" ? 1 : -1;
      expect(Math.asin(v[1]) * 180 / Math.PI).toBeLessThanOrEqual(DEFAULT_ARM_LIMITS.maxUp + 1e-6);
      expect(Math.asin(-v[2]) * 180 / Math.PI).toBeLessThanOrEqual(DEFAULT_ARM_LIMITS.maxBack + 1e-6);
      expect(Math.asin(-s * v[0]) * 180 / Math.PI).toBeLessThanOrEqual(DEFAULT_ARM_LIMITS.maxCross + 1e-6);
      expect(Math.hypot(...v)).toBeCloseTo(1, 9);
    }
    // the elbow never folds past maxBend, even for a target at the shoulder
    const r = solveArm({ side: "R", shoulder: sh, parentRot: IDENTITY, upperLen: a, foreLen: b, target: [sh[0] - 5, sh[1], 0] });
    expect(r.bend).toBeLessThanOrEqual(DEFAULT_ARM_LIMITS.maxBend + 1e-6);
    expect(r.reached).toBe(false);
  });

  it("matches the hand-keyed convention: a straight left arm down to the side is [0,0,-90]", () => {
    const r = solveArm({ side: "L", shoulder: sh, parentRot: IDENTITY, upperLen: a, foreLen: b, target: [sh[0], sh[1] - 500, 0], limits: { maxCross: 90 } });
    const e = quatRotate(r.upper, [1, 0, 0]);
    expect(e[1]).toBeCloseTo(-1, 4);
    const key = quatFromEulerDeg(0, 0, -90);
    const k = quatRotate(key, [1, 0, 0]);
    expect(dist(e, k)).toBeLessThan(1e-2);
  });

  it("screenTarget leans the arm a little toward the viewer", () => {
    const t = screenTarget(sh, sh[0] + 100, sh[1], 8);
    expect(t[2]).toBeCloseTo(100 * Math.tan(8 * Math.PI / 180), 9);
  });
});
