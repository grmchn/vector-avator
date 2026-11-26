// Turned body views for method V (docs/vector-parts.md §7).
// A body turned more than 15 deg is not drawn by rotating the flat front parts any further;
// the renderer switches to a drawing of the body seen from about 30 deg (body30.json) and
// rotates that by the remaining -15..+15 deg. The head, hands and sleeves stay the front
// parts: the head parts are translated so that the head joint sits on the turned body's neck.
// The opposite direction uses the same drawing mirrored (with _L/_R swapped).
// bodies drawn at 60 and 90 deg (body60.json, body90.json) and a side head
// (head90.json, kind "head") extend this to a full side view; any body drawing can carry
// either the front head or the side head (docs/vector-parts.md §8).
import type { ArmDef, ChainDef, Pt, VectorDoc, VPart, VShape } from "./vdata";
import { flatten, mapCmds, parsePath } from "./vdata";

export interface BodyViewDoc {
  format: string;
  character?: string;
  view?: string;
  /** "head" for a head drawing (head90.json); body drawings omit it */
  kind?: "body" | "head";
  /** angle of the drawing in degrees; + = the character turned to its left (screen right) */
  yaw: number;
  skeleton: Record<string, Pt>;
  parts: VPart[];
  chains?: ChainDef[];
  arms?: { L?: Partial<ArmDef>; R?: Partial<ArmDef> };
  /** optional full draw order (part ids of the composed character); required for a head view */
  order?: string[];
  /** body views: shift [dx, dy] of the front head on this body so that it matches the
   *  reference's head (skeleton.head is the pivot, the centre of the neck top; docs §8.2) */
  headOffset?: Pt;
  /** head views: overrides of the front parallax / head-turn tunables */
  parallax?: Record<string, number>;
  headTurn?: VectorDoc["headTurn"];
  /** in-between head drawings: how much of the front head it is (1 = the front head
   *  as a view, frontHeadView). Such a head takes the body drawing's headOffset by this weight
   *  and, while it is nearer to the front head (>= 0.5), the body drawing's draw order */
  frontWeight?: number;
}

export async function loadBodyView(url: string): Promise<BodyViewDoc | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") ?? "";
    // the dev server answers unknown paths with index.html
    if (ct.includes("html")) return null;
    return (await res.json()) as BodyViewDoc;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- path / name helpers

const fmt = (v: number) => (Math.round(v * 100) / 100).toString();

/** Re-emit a path with every point mapped (absolute M/L/C/Z). */
export function mapPathD(d: string, f: (p: Pt) => Pt): string {
  const out: string[] = [];
  for (const c of parsePath(d)) {
    if (c.k === "M" || c.k === "L") { const p = f(c.p); out.push(`${c.k}${fmt(p[0])} ${fmt(p[1])}`); }
    else if (c.k === "C") { const [a, b, e] = c.p.map(f); out.push(`C${fmt(a[0])} ${fmt(a[1])} ${fmt(b[0])} ${fmt(b[1])} ${fmt(e[0])} ${fmt(e[1])}`); }
    else out.push("Z");
  }
  return out.join(" ");
}

/** Swap the character's own sides in an id / bone / skeleton key (_L <-> _R, left <-> right). */
export function swapSide(s: string): string {
  return s
    .replace(/_L(?=$|_)/g, "\u0001").replace(/_R(?=$|_)/g, "_L").replace(/\u0001/g, "_R")
    .replace(/^left/, "\u0002").replace(/^right/, "left").replace(/^\u0002/, "right");
}

function mapPart(p: VPart, f: (q: Pt) => Pt, rename: (s: string) => string = (s) => s): VPart {
  return {
    ...p,
    id: rename(p.id),
    bone: rename(p.bone),
    group: p.group ? rename(p.group) : p.group,
    clipTo: p.clipTo ? rename(p.clipTo) : p.clipTo,
    parent: p.parent ? rename(p.parent) : p.parent,
    seamlessWith: p.seamlessWith?.map(rename),
    pivot: f(p.pivot),
    // parsed shapes (in-betweens) are mapped point by point, without a path string
    shapes: p.shapes.map((s) => (s.cmds ? { ...s, cmds: mapCmds(s.cmds, f), flat: s.flat?.map((r) => r.map(f)) } : { ...s, d: mapPathD(s.d, f) })),
  };
}

function mapChain(c: ChainDef, f: (q: Pt) => Pt, rename: (s: string) => string = (s) => s): ChainDef {
  return { ...c, id: rename(c.id), bone: rename(c.bone), parts: c.parts.map(rename), root: f(c.root), tip: f(c.tip) };
}

/** Mirror pairing of the shapes inside each part, read from the (nearly symmetric) front
 *  drawing: part id -> shape name -> the name of the shape
 *  that the mirrored shape becomes. A mirrored key drawing swaps the part ids (_L <-> _R) but a
 *  part's own shapes carry sides too (the collar's flap_R / flap_L, the vest's hem lines a..d
 *  from one side to the other): without renaming them, the in-between from the front drawing
 *  to the mirrored key paired the right flap with the left one and the hem lines crossed.
 *  Each shape is paired with the shape of the counterpart part (the part itself, or its _L/_R
 *  twin) whose outline, mirrored about x = cx, lies nearest; only one-to-one pairings of
 *  close outlines are kept. */
export function shapeMirrorMap(parts: VPart[], cx: number): Map<string, Map<string, string>> {
  const pts = (sh: VShape): Pt[] => (sh.cmds ? flatten(sh.cmds, 2).flat() : flatten(parsePath(sh.d), 2).flat());
  const byId = new Map(parts.map((p) => [p.id, p]));
  const out = new Map<string, Map<string, string>>();
  for (const p of parts) {
    const q = byId.get(swapSide(p.id));
    if (!q || p.shapes.length < 2 || p.shapes.length !== q.shapes.length) continue;
    const mq = q.shapes.map((sh) => pts(sh).map(([x, y]): Pt => [2 * cx - x, y]));
    const cost = (a: Pt[], b: Pt[]) => {
      if (!a.length || !b.length) return Infinity;
      let sum = 0;
      for (const u of a) { let m = Infinity; for (const w of b) m = Math.min(m, (u[0] - w[0]) ** 2 + (u[1] - w[1]) ** 2); sum += Math.sqrt(m); }
      return sum / a.length;
    };
    const m = new Map<string, string>();
    const used = new Set<number>();
    p.shapes.forEach((sh) => {
      const a = pts(sh);
      let best = -1, bc = Infinity;
      mq.forEach((b, j) => { const c = cost(a, b); if (c < bc) { bc = c; best = j; } });
      const size = Math.max(...a.map((u) => u[0])) - Math.min(...a.map((u) => u[0])) + Math.max(...a.map((u) => u[1])) - Math.min(...a.map((u) => u[1]));
      if (best >= 0 && !used.has(best) && bc < Math.max(8, 0.25 * size)) { used.add(best); m.set(sh.name, q.shapes[best].name); }
    });
    if (m.size === p.shapes.length && [...m].some(([a, b]) => a !== b)) out.set(p.id, m);
  }
  return out;
}

/** The view drawn the other way round: mirrored about the hips and with the sides swapped.
 *  `shapes` (shapeMirrorMap of the front drawing) renames the shapes inside a part to their
 *  mirror counterparts; without it, shape names with _L/_R are swapped. */
export function mirrorView(v: BodyViewDoc, shapes?: Map<string, Map<string, string>>): BodyViewDoc {
  // a head view has no hips: it is mirrored about its head joint
  const cx = (v.skeleton.hips ?? v.skeleton.head)[0];
  const f = (p: Pt): Pt => [2 * cx - p[0], p[1]];
  const skeleton: Record<string, Pt> = {};
  for (const [k, p] of Object.entries(v.skeleton)) skeleton[swapSide(k)] = k === "head_radius" ? p : f(p);
  const arms = v.arms ? { L: v.arms.R, R: v.arms.L } : undefined;
  const sw = (a?: Partial<ArmDef>) => (a?.attach ? { ...a, attach: swapSide(a.attach) } : a);
  return {
    ...v,
    ...(v.headOffset ? { headOffset: [-v.headOffset[0], v.headOffset[1]] as Pt } : {}),
    yaw: -v.yaw,
    skeleton,
    parts: v.parts.map((p) => {
      const q = mapPart(p, f, swapSide);
      const m = shapes?.get(p.id);
      return { ...q, shapes: q.shapes.map((sh) => ({ ...sh, name: m?.get(sh.name) ?? swapSide(sh.name) })) };
    }),
    chains: v.chains?.map((c) => mapChain(c, f, swapSide)),
    arms: arms ? { L: sw(arms.L), R: sw(arms.R) } : undefined,
    order: v.order?.map(swapSide),
  };
}

/** The view moved sideways by dx (drawing px). */
export function alignView(v: BodyViewDoc, dx: number): BodyViewDoc {
  const f = (p: Pt): Pt => [p[0] + dx, p[1]];
  const skeleton: Record<string, Pt> = {};
  for (const [k, p] of Object.entries(v.skeleton)) skeleton[k] = k === "head_radius" ? p : f(p);
  return { ...v, skeleton, parts: v.parts.map((p) => mapPart(p, f)), chains: v.chains?.map((c) => mapChain(c, f)) };
}

// ---------------------------------------------------------------- composition

const isHandOrSleeve = (p: VPart) => !!p.group && /^(hand|sleeve)_/.test(p.group);

/** Parts that turn with the head (bone head, or a spring chain hanging from the head). */
export function headPartIds(doc: VectorDoc): Set<string> {
  const headChains = new Set((doc.chains ?? []).filter((c) => c.bone === "head").map((c) => c.id));
  return new Set(doc.parts.filter((p) => p.bone === "head" || headChains.has(p.bone)).map((p) => p.id));
}

/** The front body as a view (to put the side head on the front body). */
export function frontBodyView(front: VectorDoc): BodyViewDoc {
  const heads = headPartIds(front);
  return {
    format: "so-chara-vector-view/1", view: "body0", yaw: 0, skeleton: { ...front.skeleton },
    parts: front.parts.filter((p) => !heads.has(p.id) && !isHandOrSleeve(p)),
    chains: (front.chains ?? []).filter((c) => c.bone !== "head"),
  };
}

/** The front head as a head view (the 0 deg key of the head in-betweens). Parallax and
 *  head-turn tunables are complete (defaults filled in by the caller when needed). */
export function frontHeadView(front: VectorDoc): BodyViewDoc {
  const heads = headPartIds(front);
  const sk = front.skeleton;
  const { reach: _reach, ...turn } = front.headTurn ?? {};
  return {
    format: "so-chara-vector-view/1", view: "head0", kind: "head", yaw: 0,
    skeleton: { head: sk.head, head_center: sk.head_center, head_radius: sk.head_radius },
    parts: front.parts.filter((p) => heads.has(p.id)),
    chains: (front.chains ?? []).filter((c) => c.bone === "head"),
    parallax: { ...(front.parallax ?? {}) },
    headTurn: turn,
    frontWeight: 1,
  };
}

/** A complete character doc for a turned body view: the view's body parts, the head (the
 *  front head, or the side head view `head` when given) translated onto the view's neck,
 *  hands and sleeves, and a merged skeleton whose arm bones keep the front lengths. */
export function composeView(front: VectorDoc, view0: BodyViewDoc, head?: BodyViewDoc): VectorDoc {
  // The body turns about the vertical axis through the hips: the view is placed so that its
  // hips are on the front's axis (the references were aligned by the feet, which are off the
  // axis in a turned view, so the head would jump sideways at the switch).
  const ax = front.skeleton.hips[0] - view0.skeleton.hips[0];
  const view = ax ? alignView(view0, ax) : view0;
  const fs = front.skeleton, vs = view.skeleton;
  const hs = head?.skeleton ?? fs;
  // the front head is put off the pivot by the body drawing's headOffset (a head drawing has
  // that shift in it already)
  const fw = head ? head.frontWeight ?? 0 : 1;
  const frontish = !head || fw >= 0.5;
  const off = view.headOffset ? [view.headOffset[0] * fw, view.headOffset[1] * fw] : [0, 0];
  const d: Pt = [vs.head[0] - hs.head[0] + off[0], vs.head[1] - hs.head[1] + off[1]];
  const shift = (p: Pt): Pt => [p[0] + d[0], p[1] + d[1]];
  const heads = headPartIds(front);

  // skeleton: the view's body landmarks; arms keep the front lengths; the head moves by d
  const skeleton: Record<string, Pt> = { ...fs };
  for (const [k, p] of Object.entries(vs)) skeleton[k] = p;
  for (const s of ["L", "R"]) {
    const sh = vs[`shoulder_${s}`] ?? fs[`shoulder_${s}`];
    for (const j of ["elbow", "wrist"]) {
      const off: Pt = [fs[`${j}_${s}`][0] - fs[`shoulder_${s}`][0], fs[`${j}_${s}`][1] - fs[`shoulder_${s}`][1]];
      skeleton[`${j}_${s}`] = [sh[0] + off[0], sh[1] + off[1]];
    }
  }
  skeleton.head_center = shift(hs.head_center);
  if (head) skeleton.head_radius = [...hs.head_radius] as Pt;

  // parts
  const kept = new Map<string, VPart>();
  for (const p of front.parts) {
    if (heads.has(p.id)) { if (!head) kept.set(p.id, mapPart(p, shift)); }
    else if (isHandOrSleeve(p)) kept.set(p.id, p);
  }
  for (const p of head?.parts ?? []) kept.set(p.id, mapPart(p, shift));
  const viewParts = new Map(view.parts.map((p) => [p.id, p]));
  let parts: VPart[];
  // a side head brings its own full order (head and body change places, docs §8.3)
  let order = head && !frontish ? head.order ?? [...view.parts.map((p) => p.id), ...(head.parts.map((p) => p.id))] : view.order;
  // ...but the body parts among themselves keep the body drawing's order: a head drawn at one
  // angle can sit on a body drawn at another (e.g. the side head on the 60 deg body)
  if (head && !frontish && order) order = withBodyOrder(order, view);
  if (order?.length) {
    parts = order.map((id) => kept.get(id) ?? viewParts.get(id)).filter((p): p is VPart => !!p);
    // anything not listed keeps a sensible place: hands/sleeves are drawn with the arms anyway
    for (const p of front.parts) if (isHandOrSleeve(p) && !order.includes(p.id)) parts.push(p);
    // body parts missing from a head order go behind everything rather than vanish
    for (const p of view.parts) if (!order.includes(p.id)) parts.unshift(p);
  } else {
    // the view's body parts fill the slots of the front body parts, in the view's order
    parts = [];
    let k = 0;
    for (const p of front.parts) {
      const keep = kept.get(p.id);
      if (keep) { parts.push(keep); continue; }
      if (k < view.parts.length) parts.push(view.parts[k++]);
    }
    while (k < view.parts.length) parts.push(view.parts[k++]);
  }
  // head parts the order does not list (an in-between head carrying a part the front head
  // lacks, e.g. the eye-white ring) go right after the part before them in the head
  if (head) {
    const placed = new Set(parts.map((p) => p.id));
    const hp = head.parts;
    hp.forEach((p, i) => {
      if (placed.has(p.id)) return;
      let j = -1;
      for (let k = i - 1; k >= 0 && j < 0; k--) j = parts.findIndex((x) => x.id === hp[k].id);
      parts.splice(j + 1, 0, kept.get(p.id)!);
      placed.add(p.id);
    });
  }

  // chains: head chains move with the head; body chains come from the view
  const vChains = new Map((view.chains ?? []).map((c) => [c.id, c]));
  const hChains = new Map((head?.chains ?? []).map((c) => [c.id, c]));
  const hipShift: Pt = [vs.hips[0] - fs.hips[0], vs.hips[1] - fs.hips[1]];
  const chains: ChainDef[] = [];
  for (const c of front.chains ?? []) {
    if (c.bone === "head") {
      if (!head) chains.push(mapChain(c, shift));
      else if (hChains.has(c.id)) chains.push(mapChain(hChains.get(c.id)!, shift));
      continue;
    }
    chains.push(vChains.get(c.id) ?? mapChain(c, (p) => [p[0] + hipShift[0], p[1] + hipShift[1]]));
  }
  for (const c of view.chains ?? []) if (!chains.some((x) => x.id === c.id)) chains.push(c);
  for (const c of head?.chains ?? []) if (!chains.some((x) => x.id === c.id)) chains.push(mapChain(c, shift));

  const arms = {
    L: { ...front.arms.L, ...(view.arms?.L ?? {}) } as ArmDef,
    R: { ...front.arms.R, ...(view.arms?.R ?? {}) } as ArmDef,
  };
  const out: VectorDoc = { ...front, parts, skeleton, chains, arms };
  if (head?.parallax) out.parallax = { ...(front.parallax ?? {}), ...head.parallax };
  if (head) {
    // the rim of the whole head (reach) belongs to the front drawing
    const { reach, ...rest } = front.headTurn ?? {};
    out.headTurn = { ...rest, ...(head.headTurn ?? {}) } as VectorDoc["headTurn"];
    if (fw >= 1 && reach) out.headTurn!.reach = reach;
  }
  return out;
}

/** `order` with its body part ids re-sequenced in the body view's own order (view.order, or
 *  the order of its parts), keeping the slots where the head order put body parts. */
export function withBodyOrder(order: string[], view: BodyViewDoc): string[] {
  const body = new Set(view.parts.map((p) => p.id));
  const own = view.order?.filter((id) => body.has(id)) ?? view.parts.map((p) => p.id);
  const listed = new Set(order.filter((id) => body.has(id)));
  const seq = own.filter((id) => listed.has(id));
  let k = 0;
  return order.map((id) => (body.has(id) ? seq[k++] ?? id : id));
}
