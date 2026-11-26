import { describe, expect, it } from "vitest";
import { Saccader } from "../src/core/saccade";

describe("micro saccades", () => {
  const frames = (s: Saccader, secs: number, fps = 30) => Array.from({ length: secs * fps }, (_, i) => s.at(i / fps));

  it("is deterministic for a seed and stays within the unit amplitude", () => {
    const a = frames(new Saccader({ seed: 11 }), 30), b = frames(new Saccader({ seed: 11 }), 30);
    expect(a).toEqual(b);
    for (const [x, y] of a) expect(Math.hypot(x, y)).toBeLessThanOrEqual(1 + 1e-9);
  });

  it("holds still most of the time and jumps within two frames", () => {
    const f = frames(new Saccader({ seed: 11 }), 60);
    const moving = f.map((p, i) => (i > 0 && (p[0] !== f[i - 1][0] || p[1] !== f[i - 1][1]) ? 1 : 0));
    const total = moving.reduce((s: number, v) => s + v, 0);
    expect(total / f.length).toBeLessThan(0.1);
    // no run of more than 2 moving frames at 30 fps
    let run = 0;
    for (const m of moving) { run = m ? run + 1 : 0; expect(run).toBeLessThanOrEqual(2); }
    // jumps happen every 0.5..2.6 s: about 40 in a minute (each takes 1-2 frames)
    expect(total).toBeGreaterThan(20);
  });

  it("starts centred", () => {
    expect(new Saccader().at(0)).toEqual([0, 0]);
  });
});
