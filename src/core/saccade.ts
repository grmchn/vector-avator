// Micro saccades: the iris + pupil hold still, then jump a little to a new spot in one
// or two frames, as a sign of life (like breathing). Deterministic for a given seed, so
// captures are reproducible. Offsets are in [-1, 1] (unit = the full amplitude); the renderer
// scales them.
import { mulberry32 } from "./blink";

export interface SaccadeOptions {
  seed?: number;
  /** Fixation length range (s). */
  minHold?: number;
  maxHold?: number;
  /** Duration of a jump (s): a few tens of ms = within one or two frames. */
  jump?: number;
}

interface Fix { t: number; x: number; y: number }

export class Saccader {
  private fix: Fix[] = [];
  private rnd: () => number;
  constructor(private opt: SaccadeOptions = {}) {
    this.rnd = mulberry32(opt.seed ?? 11);
  }

  private target(prev: Fix | undefined): [number, number] {
    // a new spot near the centre (so the gaze does not drift), mostly sideways, and never
    // almost the same spot as before (a jump must be seen)
    for (let k = 0; ; k++) {
      const a = 2 * Math.PI * this.rnd(), r = Math.sqrt(this.rnd());
      const x = r * Math.cos(a), y = 0.6 * r * Math.sin(a);
      if (!prev || k > 8 || Math.hypot(x - prev.x, y - prev.y) > 0.45) return [x, y];
    }
  }

  private ensure(t: number) {
    const min = this.opt.minHold ?? 0.5, max = this.opt.maxHold ?? 2.6;
    if (!this.fix.length) this.fix.push({ t: -1e9, x: 0, y: 0 });
    while (this.fix.length < 2 || this.fix[this.fix.length - 1].t < t + 10) {
      const last = this.fix[this.fix.length - 1];
      const start = this.fix.length === 1 ? 0.4 : last.t;
      const [x, y] = this.target(last);
      this.fix.push({ t: start + min + (max - min) * this.rnd(), x, y });
    }
  }

  /** Offset at time t (seconds). */
  at(t: number): [number, number] {
    this.ensure(t);
    const jump = this.opt.jump ?? 0.03;
    let i = 0;
    while (i + 1 < this.fix.length && this.fix[i + 1].t <= t) i++;
    const a = this.fix[i];
    const prev = this.fix[i - 1];
    if (prev && t - a.t < jump) {
      // ease-out: fast start, settles on the target
      const u = (t - a.t) / jump, e = 1 - (1 - u) * (1 - u) * (1 - u);
      return [prev.x + (a.x - prev.x) * e, prev.y + (a.y - prev.y) * e];
    }
    return [a.x, a.y];
  }
}
