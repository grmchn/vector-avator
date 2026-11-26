// Hand shapes: fallbacks for characters without every drawing, automatic palm /
// palm-up choice with hysteresis, and the shapes accepted in motions.
import { describe, expect, it } from "vitest";
import { HAND_FALLBACK, HAND_SHAPES, resolveHandShape, type HandShape } from "../src/core/pose";
import { parseMotion, samplePose } from "../src/core/motion";
import { autoHandShape, bodyHandShape, mirrorDot, thumbUpSide } from "../src/renderers/vector/handShape";
import type { Vec3 } from "../src/core/math";

const has = (...shapes: HandShape[]) => (s: HandShape) => shapes.includes(s);

describe("hand shape fallbacks", () => {
  it("lists every shape and ends every chain at open", () => {
    expect(HAND_SHAPES).toEqual(["open", "point", "fist", "palm", "palm_up", "peace", "thumbs_up"]);
    for (const s of HAND_SHAPES) {
      const chain = [s, ...HAND_FALLBACK[s]];
      expect(chain[chain.length - 1]).toBe("open");
      expect(new Set(chain).size).toBe(chain.length); // no loops
    }
  });
  it("uses the shape itself when the character has it", () => {
    expect(resolveHandShape("peace", has("open", "point", "peace"))).toBe("peace");
  });
  it("falls back along the chain for a legacy four-shape character", () => {
    const legacy = has("open", "point", "fist", "palm");
    expect(resolveHandShape("palm_up", legacy)).toBe("palm");
    expect(resolveHandShape("peace", legacy)).toBe("point");
    expect(resolveHandShape("thumbs_up", legacy)).toBe("fist");
  });
  it("reaches open when the first fallback is also missing", () => {
    expect(resolveHandShape("palm_up", has("open"))).toBe("open");
    expect(resolveHandShape("thumbs_up", has("open", "point"))).toBe("open");
  });
  it("returns the requested shape when nothing matches (the renderer then draws the visible default)", () => {
    expect(resolveHandShape("fist", has())).toBe("fist");
  });
});

describe("automatic hand shape", () => {
  const down: Vec3 = [0, -1, 0], toViewer: Vec3 = [0, 0, 1], up: Vec3 = [0, 1, 0];
  const mid = (a: Vec3, b: Vec3, t: number): Vec3 => {
    const v: Vec3 = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    const l = Math.hypot(...v);
    return [v[0] / l, v[1] / l, v[2] / l];
  };
  it("is open when the palm points down", () => {
    expect(autoHandShape(down, "open", true)).toBe("open");
  });
  it("is palm toward the viewer, palm_up upward", () => {
    expect(autoHandShape(toViewer, "open", true)).toBe("palm");
    expect(autoHandShape(up, "open", true)).toBe("palm_up");
  });
  it("keeps the old behaviour for characters without a palm-up drawing", () => {
    expect(autoHandShape(up, "open", false)).toBe("open");
    expect(autoHandShape(toViewer, "open", false)).toBe("palm");
  });
  it("does not flicker around a boundary (hysteresis)", () => {
    // sweep the palm normal from the viewer to straight up and back: it may switch once each way
    let prev: HandShape = "open";
    const seq: HandShape[] = [];
    const sweep = [...Array.from({ length: 21 }, (_, i) => i / 20), ...Array.from({ length: 21 }, (_, i) => 1 - i / 20)];
    for (const t of sweep) {
      prev = autoHandShape(mid(toViewer, up, t), prev, true);
      seq.push(prev);
    }
    const switches = seq.filter((s, i) => i > 0 && s !== seq[i - 1]).length;
    expect(switches).toBeLessThanOrEqual(2);
    // the same normal gives different answers depending on where it came from
    const n = mid(toViewer, up, 0.5);
    expect(autoHandShape(n, "palm", true)).toBe("palm");
    expect(autoHandShape(n, "palm_up", true)).toBe("palm_up");
  });
  it("leaves palm when the normal moves well away from the viewer", () => {
    expect(autoHandShape(mid(toViewer, down, 0.8), "palm", true)).toBe("open");
  });
});

describe("hand shapes in motion JSON", () => {
  it("accepts the new shapes", () => {
    const m = parseMotion({ name: "n", duration: 3, keys: [
      { t: 0, hands: { L: "palm_up", R: "peace" } }, { t: 1, hands: { R: "thumbs_up" } },
    ] });
    expect(samplePose(m, 0.5).hands).toEqual({ L: "palm_up", R: "peace" });
    expect(samplePose(m, 1.5).hands).toEqual({ L: "palm_up", R: "thumbs_up" });
  });
  it("still rejects an unknown shape", () => {
    expect(() => parseMotion({ name: "bad", duration: 1, keys: [{ t: 0, hands: { R: "wave" as HandShape } }] })).toThrow(/unknown hand shape/);
  });
});

describe("mirroring of thumbs_up and point drawings", () => {
  // the hand's rotation a: 0 = pointing down, -PI/2 = pointing to the screen right, +PI/2 = left
  const right = -Math.PI / 2, left = Math.PI / 2;
  it("puts the thumb on top: a left-hand drawing (thumb at +x) is fine when the forearm goes right", () => {
    expect(mirrorDot("thumbs_up", +1, right, 1)).toBeGreaterThan(0.9);
    expect(mirrorDot("thumbs_up", +1, left, 1)).toBeLessThan(-0.9); // forearm to the left: mirror it
    expect(mirrorDot("thumbs_up", -1, left, -1)).toBeGreaterThan(0.9);
  });
  it("has no preference while the hand points straight down or up (the previous choice stays)", () => {
    expect(Math.abs(mirrorDot("thumbs_up", 1, 0, 1))).toBeLessThan(1e-9);
    expect(Math.abs(mirrorDot("thumbs_up", 1, Math.PI, 1))).toBeLessThan(1e-9);
  });
  it("keeps the old pointing rule: index finger to the body side when pointing down", () => {
    expect(mirrorDot("point", +1, 0, +1)).toBeGreaterThan(0);   // body on the right, finger at +x
    expect(mirrorDot("point", -1, 0, +1)).toBeLessThan(0);
    expect(mirrorDot("point", +1, right, 1)).toBeGreaterThan(0); // pointing sideways: finger on top
  });
  it("finds the side the thumb sticks out to", () => {
    const ring = (x0: number, x1: number): [number, number][] => [[x0, 0], [x1, 0], [x1, 10], [x0, 10]];
    expect(thumbUpSide([ring(-40, 70)], 0)).toBe(1);
    expect(thumbUpSide([ring(-70, 40)], 0)).toBe(-1);
    expect(thumbUpSide([ring(-50, 50)], 0)).toBe(0);
    expect(thumbUpSide([], 0)).toBe(0);
  });
});

describe("flat hands named in motions follow the body turn", () => {
  const deg = (d: number) => (d * Math.PI) / 180;
  const at = (label: HandShape, d: number, prev: HandShape = label, edge = true) => bodyHandShape(label, deg(d), prev, edge);
  it("keeps the front view as it was (body 0 deg)", () => {
    expect(at("palm", 0)).toBe("palm");
    expect(at("open", 0)).toBe("open");
  });
  it("still shows the palm / the back at +-45 deg", () => {
    for (const d of [45, -45]) {
      expect(at("palm", d)).toBe("palm");
      expect(at("open", d)).toBe("open");
    }
  });
  it("shows the edge of a palm at +-80 and +-90 deg", () => {
    for (const d of [80, -80, 90, -90]) expect(at("palm", d)).toBe("palm_up");
  });
  it("keeps the relaxed open hand as drawn at any angle", () => {
    for (const d of [0, 45, 80, -90, 180]) expect(at("open", d, "palm_up")).toBe("open");
  });
  it("shows the back of a palm when the body faces away (180 deg)", () => {
    expect(at("palm", 180, "palm_up")).toBe("open");
  });
  it("leaves the other shapes alone", () => {
    for (const s of ["point", "fist", "peace", "thumbs_up", "palm_up"] as HandShape[]) expect(at(s, 90)).toBe(s);
  });
  it("does not flicker while the body sweeps 0 -> 90 -> 0 deg with small jitter", () => {
    let prev: HandShape = "palm";
    const seq: HandShape[] = [];
    for (let i = 0; i <= 180; i++) {
      const d = (i <= 90 ? i : 180 - i) + (i % 2 ? 1.5 : -1.5); // +-1.5 deg jitter (the in-between step)
      prev = bodyHandShape("palm", deg(d), prev, true);
      seq.push(prev);
    }
    const switches = seq.filter((s, i) => i > 0 && s !== seq[i - 1]).length;
    expect(switches).toBe(2);
    // the band between ~50 and ~60 deg answers by where it came from
    expect(at("palm", 55, "palm")).toBe("palm");
    expect(at("palm", 55, "palm_up")).toBe("palm_up");
  });
  it("falls back to the nearer face without an edge drawing", () => {
    expect(at("palm", 80, "palm", false)).toBe("palm");
    expect(at("palm", 100, "palm", false)).toBe("open");
    expect(at("palm", 90.5, "palm", false)).toBe("palm"); // at the boundary the previous stays
  });
});
