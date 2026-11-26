import { describe, expect, it } from "vitest";
import { inwardNormals } from "../src/renderers/vector/outline";
import type { Pt } from "../src/renderers/vector/vdata";

describe("inwardNormals", () => {
  const sq: Pt[] = [[0, 0], [10, 0], [10, 10], [0, 10]];
  const inside = (ring: Pt[]) => {
    const n = inwardNormals(ring);
    return ring.map((p, i) => [p[0] + n[i][0], p[1] + n[i][1]]).every(([x, y]) => x > 0 && x < 10 && y > 0 && y < 10);
  };
  it("points into the ring for both orientations", () => {
    expect(inside(sq)).toBe(true);
    expect(inside([...sq].reverse())).toBe(true);
  });
  it("returns unit vectors", () => {
    for (const [x, y] of inwardNormals(sq)) expect(Math.hypot(x, y)).toBeCloseTo(1, 6);
  });
});
