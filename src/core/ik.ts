// Two-bone arm IK: solve the upper/lower arm rotations that put the wrist on a target.
// Works in the normalized humanoid space (docs/data-format.md §1): +Y up, the character faces
// +Z, its left is +X; at rest (T-pose) the left arm points along +X and the right arm along -X.
// The elbow bends about the upper arm's local Z axis (like the hand-keyed motions: a left
// forearm flexes with +Z, a right forearm with -Z), so the forearm folds toward the upper
// arm's local +Y. Renderer-independent: callers give world positions in any consistent unit.
import { quatConj, quatFromBasis, quatFromEulerDeg, quatMul, quatRotate, type Quat, type Vec3 } from "./math";

export type Side = "L" | "R";

export interface ArmLimits {
  /** Largest elbow flexion (deg). */
  maxBend: number;
  /** Highest direction of the arm, measured from the horizontal (deg). */
  maxUp: number;
  /** How far the arm may point behind the frontal plane (deg). */
  maxBack: number;
  /** How far the arm may point across the body's midline (deg). */
  maxCross: number;
}

export const DEFAULT_ARM_LIMITS: ArmLimits = { maxBend: 140, maxUp: 40, maxBack: 15, maxCross: 25 };

export interface ArmIKInput {
  side: Side;
  /** World position of the upper-arm joint (the shoulder). */
  shoulder: Vec3;
  /** World rotation of the upper arm's parent bone (the shoulder bone). */
  parentRot: Quat;
  upperLen: number;
  foreLen: number;
  /** World target of the wrist. */
  target: Vec3;
  /** World direction the elbow should point to (default: down and a little back). */
  pole?: Vec3;
  limits?: Partial<ArmLimits>;
}

export interface ArmIKResult {
  /** Local rotations to put in the pose. */
  upper: Quat;
  lower: Quat;
  /** World wrist position of the solution. */
  wrist: Vec3;
  /** Elbow flexion (deg). */
  bend: number;
  /** True when the (limited) target is within reach. */
  reached: boolean;
}

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k];
const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a: Vec3) => Math.hypot(a[0], a[1], a[2]);
const unit = (a: Vec3): Vec3 => { const l = norm(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const DEG = Math.PI / 180;

/** Keep a unit direction inside the arm's range of motion (see ArmLimits). */
export function limitDirection(side: Side, d: Vec3, lim: ArmLimits = DEFAULT_ARM_LIMITS): Vec3 {
  const s = side === "L" ? 1 : -1;
  let v: Vec3 = unit(d);
  // set one component, rescale the other two so the vector stays unit length
  const pin = (v: Vec3, i: number, val: number): Vec3 => {
    const o = [0, 1, 2].filter((k) => k !== i);
    const rest = Math.hypot(v[o[0]], v[o[1]]);
    const want = Math.sqrt(Math.max(0, 1 - val * val));
    const out: Vec3 = [...v] as Vec3;
    out[i] = val;
    if (rest > 1e-9) { out[o[0]] = (v[o[0]] / rest) * want; out[o[1]] = (v[o[1]] / rest) * want; }
    else { out[o[0]] = want; out[o[1]] = 0; }
    return out;
  };
  for (let it = 0; it < 3; it++) {
    if (v[1] > Math.sin(lim.maxUp * DEG)) v = pin(v, 1, Math.sin(lim.maxUp * DEG));
    if (v[2] < -Math.sin(lim.maxBack * DEG)) v = pin(v, 2, -Math.sin(lim.maxBack * DEG));
    if (s * v[0] < -Math.sin(lim.maxCross * DEG)) v = pin(v, 0, -s * Math.sin(lim.maxCross * DEG));
  }
  return unit(v);
}

/** A target for pointing at something on the screen plane: the arm also leans `forwardDeg`
 *  toward the viewer (+Z), so it does not lie flat in the body plane (motion-rules M5: keep it
 *  small, about 10 deg, so a sideways arm is still drawn behind the shoulder). */
export function screenTarget(shoulder: Vec3, x: number, y: number, forwardDeg = 8): Vec3 {
  const dx = x - shoulder[0], dy = y - shoulder[1];
  return [x, y, shoulder[2] + Math.tan(forwardDeg * DEG) * Math.hypot(dx, dy)];
}

export function solveArm(inp: ArmIKInput): ArmIKResult {
  const lim: ArmLimits = { ...DEFAULT_ARM_LIMITS, ...(inp.limits ?? {}) };
  const s = inp.side === "L" ? 1 : -1;
  const a = inp.upperLen, b = inp.foreLen;
  const raw = sub(inp.target, inp.shoulder);
  const dist = norm(raw);
  const t = limitDirection(inp.side, dist > 1e-9 ? raw : [s, 0, 0], lim);
  // reachable distances: fully stretched .. folded to maxBend
  const dMax = a + b;
  const dMin = Math.sqrt(Math.max(0, a * a + b * b + 2 * a * b * Math.cos(lim.maxBend * DEG)));
  const d = Math.min(dMax * 0.99999, Math.max(dMin, dist));
  const reached = dist <= dMax + 1e-6 && dist >= dMin - 1e-6;
  // pole: the part of the requested elbow direction that is perpendicular to the target line
  let pole: Vec3 = inp.pole ? unit(inp.pole) : unit([0, -1, -0.35]);
  let pp = sub(pole, mul(t, dot(pole, t)));
  if (norm(pp) < 1e-4) { pole = [0, 0, -1]; pp = sub(pole, mul(t, dot(pole, t))); }
  if (norm(pp) < 1e-4) { pole = [0, -1, 0]; pp = sub(pole, mul(t, dot(pole, t))); }
  pp = unit(pp);
  // law of cosines: angle between the upper arm and the target line, and the elbow flexion
  const cosA = Math.max(-1, Math.min(1, (a * a + d * d - b * b) / (2 * a * d)));
  const alpha = Math.acos(cosA);
  const cosE = Math.max(-1, Math.min(1, (a * a + b * b - d * d) / (2 * a * b)));
  const bend = Math.PI - Math.acos(cosE);
  // upper arm direction (elbow pushed toward the pole) and its flexion side (local +Y)
  const u = add(mul(t, Math.cos(alpha)), mul(pp, Math.sin(alpha)));
  const y = unit(sub(mul(t, Math.sin(alpha)), mul(pp, Math.cos(alpha))));
  const ex = mul(u, s); // the bone runs along local +X (left) or -X (right)
  const ez = cross(ex, y);
  const world = quatFromBasis(ex, y, ez);
  const upper = quatMul(quatConj(inp.parentRot), world);
  const lower = quatFromEulerDeg(0, 0, s * bend / DEG);
  const elbow = add(inp.shoulder, mul(u, a));
  const fore = quatRotate(quatMul(world, lower), [s, 0, 0]);
  const wrist = add(elbow, mul(fore, b));
  return { upper, lower, wrist, bend: bend / DEG, reached };
}
