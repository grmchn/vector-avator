// Face state shared by all renderers.
export type EyeState = "open" | "half" | "closed";
export type MouthShape = "sil" | "a" | "i" | "u" | "e" | "o";
export type Expression = "neutral" | "smile" | "surprised" | "troubled";

export const EYE_STATES: EyeState[] = ["open", "half", "closed"];
export const MOUTH_SHAPES: MouthShape[] = ["sil", "a", "i", "u", "e", "o"];
export const EXPRESSIONS: Expression[] = ["neutral", "smile", "surprised", "troubled"];

export const EYE_LABEL: Record<EyeState, string> = { open: "開", half: "半閉", closed: "閉" };
export const MOUTH_LABEL: Record<MouthShape, string> = { sil: "無音", a: "あ", i: "い", u: "う", e: "え", o: "お" };
export const EXPRESSION_LABEL: Record<Expression, string> = { neutral: "通常", smile: "笑顔", surprised: "驚き", troubled: "困り" };

export interface FaceState {
  /** Head yaw in degrees, + = the character turns to its left (viewer's right). Target range ±45. */
  yaw: number;
  /** Head pitch in degrees, + = looks up. */
  pitch: number;
  /** Head roll (tilt) in degrees, + = tilts toward its left shoulder. */
  roll: number;
  eye: EyeState;
  /** Optional per-eye override (winks). */
  eyeL?: EyeState;
  eyeR?: EyeState;
  mouth: MouthShape;
  expression: Expression;
  /** Gaze offset in degrees (x: + = look to its left, y: + = up). */
  gazeX: number;
  gazeY: number;
  /** A prop shown over the head (the character's parts of group "prop", e.g. "question",
   *  "idea"); "none" or absent = no prop. Discrete: held from the earlier key while it grows or
   *  shrinks. */
  prop?: string;
  /** How much of the prop is shown, 0..1 (interpolated: keys 0 -> 1 make it pop in). */
  propAmt?: number;
}

export const DEFAULT_FACE: FaceState = {
  yaw: 0, pitch: 0, roll: 0, eye: "open", mouth: "sil", expression: "neutral", gazeX: 0, gazeY: 0,
};

export function parseFace(json: Partial<FaceState> | undefined, base: FaceState = DEFAULT_FACE): FaceState {
  const f = { ...base, ...(json ?? {}) };
  if (!EYE_STATES.includes(f.eye)) throw new Error(`unknown eye state ${f.eye}`);
  if (!MOUTH_SHAPES.includes(f.mouth)) throw new Error(`unknown mouth shape ${f.mouth}`);
  if (!EXPRESSIONS.includes(f.expression)) throw new Error(`unknown expression ${f.expression}`);
  return f;
}

/** Numeric fields interpolate; discrete fields switch at the next key (hold). */
export function lerpFace(a: FaceState, b: FaceState, t: number): FaceState {
  const n = (x: number, y: number) => x + (y - x) * t;
  return {
    ...a,
    yaw: n(a.yaw, b.yaw), pitch: n(a.pitch, b.pitch), roll: n(a.roll, b.roll),
    gazeX: n(a.gazeX, b.gazeX), gazeY: n(a.gazeY, b.gazeY),
    ...(a.prop !== undefined || b.prop !== undefined ? {
      // the prop that is growing or shrinking: the earlier key's, or the next one's when none
      prop: a.prop && a.prop !== "none" ? a.prop : b.prop,
      propAmt: n(a.propAmt ?? (a.prop && a.prop !== "none" ? 1 : 0), b.propAmt ?? (b.prop && b.prop !== "none" ? 1 : 0)),
    } : {}),
  };
}

export function eyeFor(face: FaceState, side: "L" | "R"): EyeState {
  return (side === "L" ? face.eyeL : face.eyeR) ?? face.eye;
}

/** Apply an automatic blink state to the face. Every eye that is open blinks: the shared
 *  `eye`, and an eye set open on its own (`eyeL` / `eyeR`, e.g. reopened after a wink). Before
 *  this, a motion that reopened one eye after a wink kept that eye open through every later blink,
 *  so only the other eye blinked. A closed or half eye (a wink in progress) is left as it is. */
export function withBlink(face: FaceState, blink: EyeState): FaceState {
  const f = { ...face };
  if (f.eye === "open") f.eye = blink;
  if (f.eyeL === "open") f.eyeL = blink;
  if (f.eyeR === "open") f.eyeR = blink;
  return f;
}
