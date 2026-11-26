// Automatic hand shape for method V: used when the pose does not name one. Pure functions
// (no DOM) so the thresholds can be tested.
import type { HandShape } from "../../core/pose";
import type { Vec3 } from "../../core/math";

/** Thresholds on the palm normal (world, +y up, +z toward the viewer). Entering needs more than
 *  staying, so a hand hovering near a boundary does not flicker between drawings. */
export const AUTO_HAND = {
  palmEnter: 0.55, palmStay: 0.4,
  upEnter: 0.6, upStay: 0.45,
} as const;

/** Shape for a hand whose palm normal is `n` (it points down in the T-pose). `prev` is the shape
 *  chosen last frame (hysteresis). `hasPalmUp` is false for characters without a palm-up drawing:
 *  they keep the old behaviour (palm toward the viewer, otherwise open). */
export function autoHandShape(n: Vec3, prev: HandShape, hasPalmUp: boolean): HandShape {
  const A = AUTO_HAND;
  if (hasPalmUp) {
    if (prev === "palm_up" && n[1] > A.upStay) return "palm_up";
    if (prev === "palm" && n[2] > A.palmStay && n[2] >= n[1]) return "palm";
    const up = n[1] > A.upEnter, pal = n[2] > A.palmEnter;
    if (up && pal) return n[1] > n[2] ? "palm_up" : "palm";
    if (up) return "palm_up";
    if (pal) return "palm";
    return "open";
  }
  if (prev === "palm" && n[2] > A.palmStay) return "palm";
  return n[2] > A.palmEnter ? "palm" : "open";
}

/** How well a mirrored-or-not drawing puts its feature (the index finger of `point`, the thumb of
 *  `thumbs_up`) on the preferred side: > 0 good, < 0 the drawing should be mirrored.
 *  `sig` is the local x side of the feature in the drawing (+1 / -1), `a` the hand's rotation
 *  (the drawing points down at a = 0), `tb` the screen side of the body (+1 right, -1 left).
 *  point: the index finger goes to the body side when the hand points down, at the viewer or up,
 *  and to the top when it points sideways. thumbs_up: the thumb goes to the top. */
export function mirrorDot(shape: HandShape, sig: number, a: number, tb: number): number {
  if (shape === "thumbs_up") return sig * -Math.sin(a);
  const gl = Math.hypot(tb * 0.8, 1);
  return sig * ((Math.cos(a) * tb * 0.8) / gl + (Math.sin(a) * -1) / gl);
}

/** Local x side (+1 / -1, 0 = unknown) the thumb sticks out to in a thumbs-up drawing: the side the
 *  silhouette reaches farther from the wrist pivot. */
export function thumbUpSide(rings: [number, number][][], pivotX: number): number {
  let pos = 0, neg = 0;
  for (const r of rings) for (const q of r) { const d = q[0] - pivotX; if (d > pos) pos = d; if (-d > neg) neg = -d; }
  const w = pos + neg;
  return w > 0 && Math.abs(pos - neg) > 0.06 * w ? Math.sign(pos - neg) : 0;
}

/** Thresholds for flat hands named in motions, on the z (toward the viewer) component of
 *  the palm normal after the body turn: the palm (or the back) is shown while it faces the viewer
 *  within ~50 deg (cos 50 = 0.64) and kept up to ~60 deg (cos 60 = 0.5); in between, the hand is
 *  seen from its edge. Entering needs more than staying, so the drawing does not flicker. */
export const BODY_HAND = { faceEnter: 0.64, faceStay: 0.5 } as const;

/** Drawing for `palm` named in a motion, read as seen from the front of the body: the
 *  palm faces where the body faces. The body turn `bodyYaw` (radians about the vertical axis,
 *  chest) decides which side the camera sees: the palm drawing (side: palm), the back drawing
 *  (`open`, side: back) or the edge drawing (`palm_up`, side: edge) when the character has one.
 *  `prev` is the drawing chosen last frame by this function (hysteresis). Every other shape,
 *  `open` included, passes through: the relaxed hand keeps its back drawing whatever the body
 *  turn. */
export function bodyHandShape(label: HandShape, bodyYaw: number, prev: HandShape, hasEdge: boolean): HandShape {
  if (label !== "palm") return label;
  const nz = Math.cos(bodyYaw);
  const A = BODY_HAND;
  if (nz > A.faceEnter || (prev === "palm" && nz > A.faceStay)) return "palm";
  if (nz < -A.faceEnter || (prev === "open" && nz < -A.faceStay)) return "open";
  if (hasEdge) return "palm_up";
  // without an edge drawing: the nearer face, switching at 90 deg (the previous one in between)
  if (Math.abs(nz) < 0.05 && (prev === "palm" || prev === "open")) return prev;
  return nz >= 0 ? "palm" : "open";
}
