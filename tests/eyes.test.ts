import { describe, expect, it } from "vitest";
import { blinkMode, eyeVariant } from "../src/renderers/vector/eyes";

const all = (v: string) => ["open", "half", "closed", "smile", "trouble"].includes(v);

describe("eye variant under blinks", () => {
  it("open eyes take every blink state", () => {
    const ex = { eye: "open" };
    expect(eyeVariant(ex, "open", all)).toBe("open");
    expect(eyeVariant(ex, "half", all)).toBe("half");
    expect(eyeVariant(ex, "closed", all)).toBe("closed");
  });

  it("smile eyes never flash the plain half / closed eye", () => {
    const ex = { eye: "smile" };
    expect(blinkMode(ex)).toBe("none");
    for (const st of ["open", "half", "closed"] as const) expect(eyeVariant(ex, st, all)).toBe("smile");
  });

  it("other expression eyes close but skip the plain half eye", () => {
    const ex = { eye: "trouble" };
    expect(eyeVariant(ex, "half", all)).toBe("trouble");
    expect(eyeVariant(ex, "closed", all)).toBe("closed");
  });

  it("vector.json can override the mode", () => {
    expect(eyeVariant({ eye: "smile", blink: "full" }, "half", all)).toBe("half");
    expect(eyeVariant({ eye: "open", blink: "none" }, "closed", all)).toBe("open");
  });

  it("falls back to open when the character lacks the drawing", () => {
    const some = (v: string) => v === "open" || v === "closed";
    expect(eyeVariant({ eye: "smile", blink: "full" }, "half", some)).toBe("open");
    expect(eyeVariant({}, "half", some)).toBe("open");
  });
});
