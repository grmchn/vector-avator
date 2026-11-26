import { describe, expect, it } from "vitest";
import { mirrorView, shapeMirrorMap, type BodyViewDoc } from "../src/renderers/vector/bodyView";
import type { VPart } from "../src/renderers/vector/vdata";

const part = (id: string, shapes: [string, string][]): VPart =>
  ({ id, label: id, parent: null, pivot: [500, 500], visible: true, coverage: "", bone: "chest", layer: "body",
     shapes: shapes.map(([name, d]) => ({ name, d, fill: "#000" })) }) as VPart;

describe("shapeMirrorMap (id083 follow-up)", () => {
  // a collar with a flap on each side and a vest with hem lines a..d from screen left to right
  const collar = part("collar", [["flap_R", "M 450 100 L 490 100 L 490 140 Z"], ["flap_L", "M 510 100 L 550 100 L 510 140 Z"]]);
  const torso = part("torso", [
    ["vest", "M 400 100 L 600 100 L 600 300 L 400 300 Z"],
    ["hem_a", "M 410 290 L 440 290 L 440 296 Z"], ["hem_b", "M 460 290 L 490 290 L 490 296 Z"],
    ["hem_c", "M 510 290 L 540 290 L 510 296 Z"], ["hem_d", "M 560 290 L 590 290 L 560 296 Z"],
  ]);
  it("pairs each shape with its mirror counterpart", () => {
    const m = shapeMirrorMap([collar, torso], 500);
    expect(m.get("collar")?.get("flap_R")).toBe("flap_L");
    expect(m.get("collar")?.get("flap_L")).toBe("flap_R");
    expect(m.get("torso")?.get("vest")).toBe("vest");
    expect(m.get("torso")?.get("hem_a")).toBe("hem_d");
    expect(m.get("torso")?.get("hem_b")).toBe("hem_c");
  });
  it("renames the shapes of a mirrored view", () => {
    const m = shapeMirrorMap([collar, torso], 500);
    const v = { yaw: -30, skeleton: { hips: [500, 400], head: [500, 90] }, parts: [collar, torso] } as unknown as BodyViewDoc;
    const r = mirrorView(v, m);
    expect(r.yaw).toBe(30);
    expect(r.parts[1].shapes.map((s) => s.name)).toEqual(["vest", "hem_d", "hem_c", "hem_b", "hem_a"]);
    // without a map, side suffixes are still swapped
    expect(mirrorView(v).parts[0].shapes.map((s) => s.name)).toEqual(["flap_L", "flap_R"]);
  });
});
