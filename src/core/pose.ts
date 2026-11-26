// Pose = local rotations of bones in the normalized humanoid space (see skeleton.ts).
import { IDENTITY, quatFromEulerDeg, quatNormalize, quatSlerp, vecLerp, type Quat, type Vec3 } from "./math";
import { isKnownBone } from "./skeleton";

export type HandShape = "open" | "point" | "fist" | "palm" | "palm_up" | "peace" | "thumbs_up";
export const HAND_SHAPES: HandShape[] = ["open", "point", "fist", "palm", "palm_up", "peace", "thumbs_up"];

/** What to draw when a character has no drawing for a shape (docs/vector-parts.md §4.3):
 *  the first available entry of [shape, ...HAND_FALLBACK[shape]] is used. */
export const HAND_FALLBACK: Record<HandShape, HandShape[]> = {
  open: [],
  palm: ["open"],
  palm_up: ["palm", "open"],
  point: ["open"],
  fist: ["open"],
  peace: ["point", "open"],
  thumbs_up: ["fist", "open"],
};

/** The first shape of the fallback chain that `has` accepts; `want` itself when nothing matches. */
export function resolveHandShape(want: HandShape, has: (s: HandShape) => boolean): HandShape {
  if (has(want)) return want;
  for (const s of HAND_FALLBACK[want]) if (has(s)) return s;
  return want;
}

export interface Pose {
  bones: Record<string, Quat>;
  /** Hips translation from the rest position, in metres of the normalized space. */
  hips: Vec3;
  /** Optional hand shapes (used by renderers that swap hand drawings, e.g. method V). */
  hands?: { L?: HandShape; R?: HandShape };
  /**
   * Optional whole-body vertical squash & stretch (1 = none, <1 squashed, >1 stretched).
   * Renderers scale about the feet and widen by 1/sqrt(squash) (volume kept).
   */
  squash?: number;
  /**
   * Optional IK reach of the wrists: the wrist goes toward a point given in the
   * renderer's view (u, v = 0..1 of the canvas width and height, may lie outside), blended
   * over the keyed arm by w (0 = keyed arm, 1 = IK arm). Solved by the renderer (core/ik.ts).
   */
  reach?: { L?: ReachTarget; R?: ReachTarget };
}

export interface ReachTarget { u: number; v: number; w: number }

/** JSON form: each bone is either Euler degrees [x, y, z] (XYZ) or {"q": [x, y, z, w]}. */
export type BoneRotationJson = [number, number, number] | { q: [number, number, number, number] };
export interface PoseJson {
  name?: string;
  description?: string;
  bones: Record<string, BoneRotationJson>;
  hips?: Vec3;
}

export function emptyPose(): Pose {
  return { bones: {}, hips: [0, 0, 0] };
}

export function parseRotation(r: BoneRotationJson): Quat {
  if (Array.isArray(r)) return quatFromEulerDeg(r[0], r[1], r[2]);
  return quatNormalize(r.q);
}

export function parsePose(json: PoseJson): Pose {
  const bones: Record<string, Quat> = {};
  for (const [name, r] of Object.entries(json.bones ?? {})) {
    if (!isKnownBone(name)) throw new Error(`unknown bone "${name}"`);
    bones[name] = parseRotation(r);
  }
  return { bones, hips: json.hips ?? [0, 0, 0] };
}

export function getRotation(p: Pose, bone: string): Quat {
  return p.bones[bone] ?? IDENTITY;
}

export function blendPose(a: Pose, b: Pose, t: number): Pose {
  const names = new Set([...Object.keys(a.bones), ...Object.keys(b.bones)]);
  const bones: Record<string, Quat> = {};
  for (const n of names) bones[n] = quatSlerp(getRotation(a, n), getRotation(b, n), t);
  return { bones, hips: vecLerp(a.hips, b.hips, t) };
}
