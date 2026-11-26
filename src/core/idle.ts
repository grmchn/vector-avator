// Idle micro-motion: a sign of life layered over any motion, like blink.ts and
// saccade.ts. The weight shifts slowly from foot to foot (motion-rules M1: the hips move
// sideways and the hip over the supporting leg rises), and the head leans a little the other
// way (M3). Two mixed slow waves with seeded phases, so it never looks mechanical and captures
// are reproducible. Breathing is drawn by the renderer (method V: vBreath).
import { mulberry32 } from "./blink";
import { quatFromEulerDeg, quatMul, IDENTITY } from "./math";
import type { Pose } from "./pose";
import type { FaceState } from "./face";

export interface IdleOptions {
  seed?: number;
  /** Sideways hips shift (m, peak). */
  sway?: number;
  /** Hips roll per metre of shift (deg/m): 0.008 m -> about 1.6 deg. */
  rollPerM?: number;
  /** Head lean against the hips (fraction of the hips roll). */
  headLean?: number;
  /** Main period (s). */
  period?: number;
}

export interface IdleOffset { x: number; roll: number; headRoll: number }

export class Idler {
  private ph: [number, number];
  constructor(private opt: IdleOptions = {}) {
    const r = mulberry32(opt.seed ?? 23);
    this.ph = [2 * Math.PI * r(), 2 * Math.PI * r()];
  }

  at(t: number): IdleOffset {
    const T = this.opt.period ?? 3.6, A = this.opt.sway ?? 0.008;
    const w = 0.72 * Math.sin((2 * Math.PI * t) / T + this.ph[0]) + 0.28 * Math.sin((2 * Math.PI * t) / (T * 2.37) + this.ph[1]);
    const x = A * w;
    const roll = x * (this.opt.rollPerM ?? 200);
    return { x, roll, headRoll: -roll * (this.opt.headLean ?? 0.5) };
  }

  /** The pose and face with the idle offset added (new objects; the inputs are not changed). */
  apply(pose: Pose, face: FaceState, t: number): { pose: Pose; face: FaceState } {
    const d = this.at(t);
    const hips = quatMul(quatFromEulerDeg(0, 0, d.roll), pose.bones.hips ?? IDENTITY);
    return {
      pose: { ...pose, bones: { ...pose.bones, hips }, hips: [pose.hips[0] + d.x, pose.hips[1], pose.hips[2]] },
      face: { ...face, roll: face.roll + d.headRoll },
    };
  }
}
