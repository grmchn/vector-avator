// Avatar package: the TypeScript defaults match the Python loader and every character validates.
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolvePackage, validatePackage, PACKAGE_DEFAULTS } from "../src/core/avatarPackage";
import type { CharacterConfig } from "../src/core/renderer";

const dir = "data/characters";
const chars: CharacterConfig[] = readdirSync(dir).filter((f) => f.endsWith(".json")).map((f) => JSON.parse(readFileSync(`${dir}/${f}`, "utf8")));

describe("avatar package", () => {
  it("every character definition validates", () => {
    expect(chars.length).toBeGreaterThanOrEqual(1);
    for (const c of chars) expect(validatePackage(c), c.id).toEqual([]);
  });

  it("an empty package resolves to the defaults", () => {
    const r = resolvePackage({});
    expect(r.schemaVersion).toBe(0);
    expect(r.voice.ja.voice).toBe("");
    expect(r.rig.rest.upperArm).toBe(70);
    expect(r.capture.bg).toBe("dde6f2");
  });

  it("partial fields merge and the defaults stay unchanged", () => {
    const r = resolvePackage({ voice: { ja: { voice: "voice_a" } }, rig: { hands: { shapeScale: { open: 0.8 } } } });
    expect(r.voice.ja).toEqual({ engine: "files", voice: "voice_a" });
    expect(r.rig.hands.shapeScale).toEqual({ open: 0.8 });
    expect(r.rig.hands.type).toBe("mitten");
    expect(PACKAGE_DEFAULTS.rig.hands.shapeScale).toEqual({});
  });

  it("resolves the same as tools/avatar/package.py", () => {
    for (const c of chars) {
      const py = JSON.parse(execFileSync(".venv/bin/python", ["tools/avatar/package.py", c.id], { encoding: "utf8" }));
      const ts = resolvePackage(c);
      for (const k of ["rig", "voice", "persona", "acting", "capture", "schemaVersion"] as const) expect(ts[k], `${c.id}.${k}`).toEqual(py[k]);
    }
  });
});
