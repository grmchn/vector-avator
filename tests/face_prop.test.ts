// Props over the head: FaceState.prop / propAmt interpolation and the framing URL parser.
import { describe, expect, it } from "vitest";
import { DEFAULT_FACE, lerpFace } from "../src/core/face";
import { parseFraming } from "../src/core/renderer";

describe("face props", () => {
  it("grows the next key's prop when the earlier key has none", () => {
    const a = { ...DEFAULT_FACE, prop: "none", propAmt: 0 };
    const b = { ...DEFAULT_FACE, prop: "idea", propAmt: 1 };
    const m = lerpFace(a, b, 0.5);
    expect(m.prop).toBe("idea");
    expect(m.propAmt).toBeCloseTo(0.5);
  });
  it("keeps the shrinking prop until it is gone", () => {
    const a = { ...DEFAULT_FACE, prop: "question", propAmt: 1 };
    const b = { ...DEFAULT_FACE, prop: "none", propAmt: 0 };
    const m = lerpFace(a, b, 0.25);
    expect(m.prop).toBe("question");
    expect(m.propAmt).toBeCloseTo(0.75);
  });
  it("leaves faces without props untouched", () => {
    expect(lerpFace(DEFAULT_FACE, DEFAULT_FACE, 0.5).prop).toBeUndefined();
  });
});

describe("parseFraming", () => {
  it("reads body / face / bust", () => {
    expect(parseFraming(new URLSearchParams("framing=bust"))).toBe("bust");
    expect(parseFraming(new URLSearchParams("framing=face"))).toBe("face");
    expect(parseFraming(new URLSearchParams("framing=x"))).toBe("body");
  });
});
