// Eye part selection for method V.
// An expression may use its own eye drawing (e.g. smile = closed arcs). Blinks (automatic or
// keyed) must not swap that drawing for the plain half / closed eye for a few frames: that reads
// as a flash of the neutral face, or as the eyes opening for an instant. How an expression's
// eyes take the blink states is set by `blink` in vector.json `expressions.<key>`:
//   "full"   - half and closed are shown (default for eye "open")
//   "closed" - only closed is shown; half keeps the expression's eyes (default for other eyes)
//   "none"   - the expression's eyes are kept (default for eye "smile": it is already closed)
import type { EyeState } from "../../core/face";

export type BlinkMode = "full" | "closed" | "none";

export function blinkMode(ex: { eye?: string; blink?: string }): BlinkMode {
  if (ex.blink === "full" || ex.blink === "closed" || ex.blink === "none") return ex.blink;
  const v = ex.eye ?? "open";
  return v === "open" ? "full" : v === "smile" ? "none" : "closed";
}

/** Variant name of an eye group for an expression and an eye state. */
export function eyeVariant(ex: { eye?: string; blink?: string }, state: EyeState, has: (v: string) => boolean): string {
  const mode = blinkMode(ex);
  if (mode !== "none" && state === "closed" && has("closed")) return "closed";
  if (mode === "full" && state === "half" && has("half")) return "half";
  const v = ex.eye ?? "open";
  return has(v) ? v : "open";
}
