// Rim on pale areas: which fills count as pale.
import { describe, expect, it } from "vitest";
import { isPale } from "../src/renderers/vector/outline";
import { resolvePackage } from "../src/core/avatarPackage";

describe("isPale", () => {
  it("takes light fills only", () => {
    expect(isPale("#ffffff", 88)).toBe(true);
    expect(isPale("#fde2db", 88)).toBe(true);     // a character with a cross-body strap's skin
    expect(isPale("#7adcdc", 88)).toBe(false);    // a twin-tail character's hair
    expect(isPale("#2f3d70", 88)).toBe(false);
  });
  it("ignores gradients and missing fills", () => {
    expect(isPale(null, 88)).toBe(false);
    expect(isPale("url(#g)", 88)).toBe(false);
  });
  it("follows the threshold", () => {
    expect(isPale("#d0d4dc", 80)).toBe(true);
    expect(isPale("#d0d4dc", 92)).toBe(false);
  });
});

describe("capture.rim", () => {
  it("is off by default", () => {
    expect(resolvePackage({}).capture.rim).toBeNull();
  });
});
