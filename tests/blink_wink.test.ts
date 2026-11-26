// A wink must not break the blinking: an eye reopened on its own still blinks.
import { describe, expect, it } from "vitest";
import { DEFAULT_FACE, eyeFor, withBlink } from "../src/core/face";

describe("withBlink", () => {
  it("closes both eyes after a wink was reopened with eyeL: open", () => {
    const f = withBlink({ ...DEFAULT_FACE, eyeL: "open" }, "closed");
    expect(eyeFor(f, "L")).toBe("closed");
    expect(eyeFor(f, "R")).toBe("closed");
  });
  it("keeps a wink in progress", () => {
    const f = withBlink({ ...DEFAULT_FACE, eyeL: "closed" }, "half");
    expect(eyeFor(f, "L")).toBe("closed");
    expect(eyeFor(f, "R")).toBe("half");
  });
  it("does nothing while the blink is open", () => {
    const f = withBlink({ ...DEFAULT_FACE, eyeR: "open" }, "open");
    expect(eyeFor(f, "L")).toBe("open");
    expect(eyeFor(f, "R")).toBe("open");
  });
});
