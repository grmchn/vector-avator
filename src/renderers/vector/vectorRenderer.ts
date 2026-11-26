// Method V: vector standing picture (specs/vector_plan.md).
// SVG-path parts from vector.json are drawn with Canvas 2D. The body follows the common
// skeleton through VRig (3D FK with the character's own bone lengths, orthographic
// projection); arms are generated (arm.ts); the head turns by Live2D-style deformation of the
// one front drawing (head.ts);
// swinging parts use spring chains (spring.ts); outlines are generated where a part overlaps
// a part of a similar colour (outline.ts).
import type { CharacterConfig, Framing, Renderer, RendererContext } from "../../core/renderer";
import { resolveHandShape, type Pose, type HandShape } from "../../core/pose";
import { autoHandShape, bodyHandShape, mirrorDot, thumbUpSide } from "./handShape";
import { DEFAULT_FACE, eyeFor, type FaceState } from "../../core/face";
import { loadVector, emitPath, mulAff, apply, type Affine, type LoadedPart, type LoadedVector, type MapFn, type Pt } from "./vdata";
import { VRig } from "./vrig";
import { buildArm, multiPolygonPath, type ArmGeom } from "./arm";
import { DEFAULT_HEAD_TURN, DEFAULT_PARALLAX, attachPlace, faceDisp, featurePlace, headReach, headShift, shellMap, type HeadFrame } from "./head";
import { SpringChain } from "./spring";
import { plantedLegAffine } from "./plant";
import { eyeVariant } from "./eyes";
import { Saccader } from "../../core/saccade";
import { composeView, frontBodyView, headPartIds, loadBodyView, mirrorView, shapeMirrorMap, type BodyViewDoc } from "./bodyView";
import { TurnEngine } from "./turnEngine";
import { prepareVector, translate } from "./vdata";
import { IDENTITY, quatMul, quatSlerp, type Quat } from "../../core/math";
import { getRotation } from "../../core/pose";
import { screenTarget, solveArm } from "../../core/ik";
import { OutlineSettings, drawOutlines, haloOutline, silhouetteRings, type DrawItem, outerOutline, rimOutline, type RimSettings, darken, handFromQuery, faceWobbleMap, featureFill } from "./outline";
import { emitWobbled, frameWobbleMap, shapeFromQuery, shapeWobbleMap, wobbleMulti, wobbleRing } from "./wobble";
import type { MultiPolygon } from "./pc";


const EXPR_KEY: Record<string, string> = { neutral: "normal", smile: "smile", surprised: "surprise", troubled: "trouble" };
// per-character defaults for the URL parameters (data/characters/<id>.json "urlDefaults"),
// used when the URL does not set them (e.g. a character with a thick black outline: thick black outer line, no hand-drawn line)
const charDefaults = Object.fromEntries(
  Object.values(import.meta.glob("../../../data/characters/*.json", { eager: true, import: "default" }) as Record<string, CharacterConfig>)
    .map((c) => [c.id, c.urlDefaults ?? {}]),
) as Record<string, Record<string, string>>;
const q = () => {
  const p = new URLSearchParams(typeof location === "undefined" ? "" : location.search);
  for (const [k, v] of Object.entries(charDefaults[p.get("char") ?? ""] ?? {})) if (!p.has(k)) p.set(k, v);
  return p;
};
const num = (k: string, d: number) => (q().has(k) ? Number(q().get(k)) : d);
const flag = (k: string, d: boolean) => (q().has(k) ? q().get(k) !== "0" : d);

export interface VectorOptions {
  /** background colour; "none" = transparent (alpha capture) */
  bg: string;
  /** light outline on the pale areas only (vRim=<hex>, vRimL, vRimW); null = off */
  rim: RimSettings | null;
  outline: OutlineSettings;
  physics: boolean;
  physGain: number;    // how strongly swinging parts react to motion (1 = as tuned)
  accMax: number;      // cap on the root acceleration a swinging part feels (px/s^2)
  handLag: boolean;
  depthGain: number;   // arm width gain per head-radius of depth
  armCurve: number;
  /** when the forearm is in front of the chest, the upper arm comes to the front with it
   *  (one arm from the shoulder) unless the elbow is further behind the chest than this (head
   *  radii, e.g. -0.3; NaN = off). Split, the forearm's round elbow end floated on the belly and
   *  the torso's edge line was cut short over the upper arm's root. */
  armJoin: number;
  breath: number;      // breathing lift of the chest (drawing px, 0 = off)
  breathPeriod: number;
  wag: number;         // idle tail wag amplitude (radians, 0 = off)
  saccade: number;     // micro saccade amplitude of the iris + pupil (fraction of the eye white, 0 = off)
  plant: boolean;      // planted legs: the soles stay put, the leg shears to the hip (plant.ts)
  plantLift: boolean;  // vPlant=2: planted on the ground, but the feet leave it when the hips rise (jumps)
}

export function optionsFromUrl(): VectorOptions {
  const p = q();
  return {
    bg: p.get("bg") === "none" ? "none" : p.get("bg") ? `#${p.get("bg")!.replace(/^#/, "")}` : "#dde6f2",
    rim: p.get("vRim") && p.get("vRim") !== "0"
      ? { color: `#${p.get("vRim")!.replace(/^#/, "")}`, minL: num("vRimL", 88), width: num("vRimW", 4.5) }
      : null,
    outline: {
      enabled: flag("vOutline", true),
      outer: flag("vOuter", false),
      width: num("vLine", 3.2),
      darken: num("vDark", 0.2),
      threshold: num("vThr", 16),
      outerColor: p.get("vOuterColor") ? `#${p.get("vOuterColor")}` : "",
      hand: handFromQuery(p),
      shape: shapeFromQuery(p),
      inner: p.get("vInner") === "outer" ? "outer" : "inside",
      rootGap: num("vRootGap", 0),
    },
    physics: flag("vPhys", true),
    physGain: num("vPhysGain", 1),
    accMax: num("vAccMax", 60000),
    handLag: flag("vLag", true),
    depthGain: num("vDepth", 0.18),
    armCurve: num("vCurve", 0.035),
    armJoin: num("vArmJoin", NaN),
    breath: num("vBreath", 5),
    breathPeriod: num("vBreathT", 3.6),
    wag: num("vWag", 0.07),
    saccade: num("vSacc", 0.05),
    plant: flag("vPlant", false),
    plantLift: num("vPlant", 0) >= 2,
  };
}

interface HandState { a: number; v: number; init: boolean }

export class VectorRenderer implements Renderer {
  readonly id = "V" as const;
  readonly label = "V：ベクター立ち絵";
  private cv!: HTMLCanvasElement;
  private g!: CanvasRenderingContext2D;
  private lv!: LoadedVector;
  private rig!: VRig;
  private pose: Pose = { bones: {}, hips: [0, 0, 0] };
  private face: FaceState = DEFAULT_FACE;
  private view: Affine = [1, 0, 0, 1, 0, 0];
  private W = 960; private H = 540;
  private framing: Framing = "body";
  /** bust framing: smoothed camera offset that follows the neck, and the last frame time */
  private follow: { off: Pt; t: number | null } = { off: [0, 0], t: null };
  opt: VectorOptions = optionsFromUrl();
  private chains = new Map<string, SpringChain>();
  private partChain = new Map<string, SpringChain>();
  private lastT = -1;
  private saccader = new Saccader({ seed: 11 });
  private sacc: [number, number] = [0, 0];
  private groupCenter = new Map<string, Pt>();
  private groupHalf = new Map<string, number>();
  /** silhouettes of the parts, made when first drawn; per part object, so the drawings the turn
   *  engine keeps in its cache keep theirs */
  private silRest = new WeakMap<LoadedPart, Pt[][]>();
  private reach: [number, number, number] = [1, 1, 1];
  private par: Record<string, number> = { ...DEFAULT_PARALLAX };
  private turn: Record<string, number> = {};
  private armLayer = { L: { upper: false, fore: false, raised: false, crossing: false, joined: false }, R: { upper: false, fore: false, raised: false, crossing: false, joined: false } };
  private sleeveState = { L: "straight", R: "straight" };
  /** local x side of the index finger in the pointing-hand drawings, and the current mirroring */
  private thumbSide: Record<"L" | "R", number> = { L: 0, R: 0 };
  /** local x side of the raised thumb in the thumbs-up drawings */
  private thumbUpSide: Record<"L" | "R", number> = { L: 0, R: 0 };
  private handMirror: Record<"L" | "R", boolean> = { L: false, R: false };
  /** hand drawings each side has (variant names), and the last automatic choice (hysteresis) */
  private handVariants: Record<"L" | "R", Set<string>> = { L: new Set(), R: new Set() };
  private autoHand: Record<"L" | "R", HandShape> = { L: "open", R: "open" };
  /** last drawing chosen for a flat hand named in the motion, read against the body turn */
  private bodyHand: Record<"L" | "R", HandShape> = { L: "open", R: "open" };
  /** screen x of the palm normal of that hand while it is drawn edge-on (palm_up), 0 otherwise */
  private edgeNx: Record<"L" | "R", number> = { L: 0, R: 0 };
  private hand: Record<"L" | "R", HandState> = { L: { a: 0, v: 0, init: false }, R: { a: 0, v: 0, init: false } };
  private debug = false;
  private dt = 0;
  /** last frame's draw list (for tests / debugging) */
  lastItems: DrawItem[] = [];
  /** turned body views (bodyView.ts): angle of this view's body drawing (radians) */
  private viewYaw = 0;
  /** angle of this view's head drawing (radians): 0 = the front head, +-90 deg = the side head */
  private headYaw = 0;
  /** body / head drawings by angle (deg; mirrored ones included). When present, this renderer
   *  only composites child renderers, one per (body drawing, head drawing) pair, made on demand */
  private viewSet: { bodies: Map<number, BodyViewDoc>; heads: Map<number, BodyViewDoc>; w: number; h: number; framing: Framing; debug: boolean } | null = null;
  private kids = new Map<string, VectorRenderer>();
  private activeViews = new Set<VectorRenderer>();
  /** hysteresis state of the switches: the angle (deg) of the body / head drawing in use */
  private bodySlot = 0;
  private headSlot = 0;
  /** timed crossfade (vSwitch=fadeT): drawings bottom to top; the bottom one is opaque, the
   *  others have progress p (opacity p^n) going in (dir +1) or out (dir -1) */
  private fadeStack: { v: VectorRenderer; p: number; dir: number }[] = [];
  private fadeLastT = -1;
  private maxYawDeg = 30;
  private cssSize: [number, number] = [960, 540];
  /** body chains (tail) moved behind the body toward where the turned view has them */
  private slide = new Map<string, Pt>();
  private slideAff(id: string, aff: Affine): Affine {
    const d = this.slide.get(id);
    return d ? mulAff(translate(d[0], d[1]), aff) : aff;
  }
  /** body yaw (deg) and the views drawn in the last frame (for tests / captures) */
  lastBody: { yaw: number; headYaw?: number; views: { yaw: number; head?: number; alpha: number }[] } = { yaw: 0, views: [] };

  get canvas(): HTMLCanvasElement { return this.cv; }

  async init(ctx: RendererContext): Promise<void> {
    const c: CharacterConfig = ctx.character;
    if (!c.vector) throw new Error(`${c.label} has no vector data (method V)`);
    this.lv = await loadVector(c.vector.url);
    this.setup(ctx.width, ctx.height, ctx.framing ?? "body", !!ctx.debug);
    // turned body drawings (body<deg>.json next to vector.json at 15 deg steps, whichever exist:
    // body30/60/90 for every character, body15/45/75 where drawn), the
    // side head (head90.json) and the 60 deg head (head60.json). vBody=0 turns them all
    // off, vViews=30,60,90 keeps only the listed body angles, vHeads=90 only the listed head
    // angles, vSideHead=0 keeps the front head
    if (flag("vBody", true)) {
      const dir = c.vector.url.replace(/[^/]*$/, "");
      // the turn engine (vMorph=1) uses the 30 deg keys
      const want = (q().get("vViews") ?? (flag("vMorph", true) ? "30,60,90" : "15,30,45,60,75,90")).split(",").map(Number);
      const bodies = new Map<number, BodyViewDoc>(), heads = new Map<number, BodyViewDoc>();
      // shapes inside a part are paired with their mirror counterparts of the front drawing
      // (collar flaps, hem lines; id083 follow-up): vMirrorShapes=0 keeps the names
      const fd = this.lv.doc, hp = headPartIds(fd);
      const smap = flag("vMirrorShapes", true)
        ? new Map([...shapeMirrorMap(fd.parts.filter((p) => !hp.has(p.id)), fd.skeleton.hips[0]), ...shapeMirrorMap(fd.parts.filter((p) => hp.has(p.id)), fd.skeleton.head[0])])
        : undefined;
      const both = (m: Map<number, BodyViewDoc>, v: BodyViewDoc | null) => { if (v) { m.set(v.yaw, v); const r = mirrorView(v, smap); m.set(r.yaw, r); } };
      // asymmetric bodies (a character with a cross-body strap's cross-body strap) may have the bodies turned the
      // other way drawn too (body<deg>_opp.json): mirroring would move the strap to the other
      // shoulder and the in-betweens would cross it; vOppBodies=0 mirrors as before
      const oppBodies = flag("vOppBodies", true);
      for (const a of [15, 30, 45, 60, 75, 90]) if (want.includes(a)) {
        const v = await loadBodyView(dir + (a === 30 ? q().get("vBodyFile") ?? "body30.json" : `body${a}.json`));
        const o = v && oppBodies ? await loadBodyView(dir + `body${a}_opp.json`) : null;
        if (v && o) { bodies.set(v.yaw, v); bodies.set(o.yaw, o); } else both(bodies, v);
      }
      // the 30 deg head is a key of the turn engine only (the switch has no slot for it)
      const wantHeads = (q().get("vHeads") ?? (flag("vMorph", true) ? "30,60,90" : "60,90")).split(",").map(Number);
      // characters with asymmetric hair have the heads turned the other way drawn too
      // (head<deg>_opp.json): mirroring the keys would swap the hair's sides, and the
      // in-betweens from the front head to a mirrored key cross the hair over; vOppHeads=0
      // mirrors the keys as before
      const opp = flag("vOppHeads", true);
      if (flag("vSideHead", true)) for (const a of [30, 60, 90]) if (wantHeads.includes(a)) {
        const v = await loadBodyView(dir + `head${a}.json`);
        const o = v && opp ? await loadBodyView(dir + `head${a}_opp.json`) : null;
        if (v && o) { heads.set(v.yaw, v); heads.set(o.yaw, o); } else both(heads, v);
      }
      if (bodies.size || heads.size) {
        this.viewSet = { bodies, heads, w: ctx.width, h: ctx.height, framing: ctx.framing ?? "body", debug: !!ctx.debug };
        this.resize(ctx.width, ctx.height);
      }
    }
    ctx.container.appendChild(this.cv);
  }

  /** The child renderer for a body drawing (deg) carrying a head drawing (deg), made on demand. */
  private kid(body: number, head: number): VectorRenderer {
    const key = `${body}|${head}`;
    const have = this.kids.get(key);
    if (have) return have;
    const vs = this.viewSet!;
    const front = this.lv.doc;
    const lv = !body && !head ? this.lv
      : prepareVector(composeView(front, body ? vs.bodies.get(body)! : frontBodyView(front), head ? vs.heads.get(head) : undefined));
    return this.spawn(key, lv, body, head);
  }

  /** Turn engine (vMorph=1): body and head drawings at any angle from the key drawings
   *  and in-betweens (turnEngine.ts, morph.ts). vMorphEngine = swap (default: one child renderer
   *  whose shapes are swapped, swapVector) | spawn (a child renderer per drawing angle pair, as
   *  the first prototype) | proto (spawn, and the in-betweens go through path strings).
   *  vMorphStep (deg, default 3), vMorphDead (body, deg, default 7.5) / vMorphHeadDead (head,
   *  default 20: the front head's parallax, liked up to 30 deg, keeps gestures as before):
   *  see turnEngine.ts. vMorphHead=0 keeps the head switch (hysteresis) with the body in-betweens. */
  private engine: TurnEngine | null = null;
  private morphR: VectorRenderer | null = null;
  private morphKeys: string[] = [];
  private turnEngine(): TurnEngine {
    if (!this.engine) {
      const vs = this.viewSet!;
      const dead = num("vMorphDead", 7.5);
      this.engine = new TurnEngine(this.lv.doc, vs.bodies, vs.heads, {
        step: Math.max(0.1, num("vMorphStep", 3)), bodyDead: dead, headDead: num("vMorphHeadDead", 20),
        strings: q().get("vMorphEngine") === "proto",
      });
    }
    return this.engine;
  }
  private morphTarget(body: number, head: number): VectorRenderer {
    const e = this.turnEngine();
    const mode = q().get("vMorphEngine") ?? "swap";
    const maxYaw = num("vSideMaxYaw", 30) + num("vHyst", 3);
    if (mode === "swap") {
      if (!this.morphR) {
        this.morphR = this.spawn("morph", e.build(body, head), body, head);
        this.morphR.maxYawDeg = maxYaw;
      } else if (this.morphR.viewYaw !== (body * Math.PI) / 180 || this.morphR.headYaw !== (head * Math.PI) / 180) {
        this.morphR.swapVector(e.build(body, head), body, head);
      }
      return this.morphR;
    }
    const key = `m${body}|${head}`;
    const have = this.kids.get(key);
    if (have) return have;
    const r = this.spawn(key, e.build(body, head), body, head);
    r.maxYawDeg = maxYaw;
    this.morphKeys.push(key);
    while (this.morphKeys.length > 16) {
      const k = this.morphKeys.find((x) => !this.activeViews.has(this.kids.get(x)!));
      if (!k) break;
      this.kids.get(k)!.dispose();
      this.kids.delete(k);
      this.morphKeys.splice(this.morphKeys.indexOf(k), 1);
    }
    return r;
  }

  /** Take another composed character (the turn engine's drawing at body / head angles, deg)
   *  keeping the canvas, the swing of the chains, the hand lag and the face state. */
  swapVector(lv: LoadedVector, body: number, head: number): void {
    this.lv = lv;
    this.viewYaw = (body * Math.PI) / 180;
    this.headYaw = (head * Math.PI) / 180;
    this.rig = new VRig(lv.doc);
    this.index(true);
  }

  private spawn(key: string, lv: LoadedVector, body: number, head: number): VectorRenderer {
    const vs = this.viewSet!;
    const r = new VectorRenderer();
    r.viewYaw = (body * Math.PI) / 180;
    r.headYaw = (head * Math.PI) / 180;
    // the front head turns by parallax up to its head switch (or 45 deg with the 30 deg body
    // only); a turned head (60 / 90 deg) by up to vSideMaxYaw around its own angle,
    // plus the hysteresis band of the switches
    const far = Math.max(0, ...[...vs.bodies.keys()].map(Math.abs));
    const hy = num("vHyst", 3);
    r.maxYawDeg = head ? num("vSideMaxYaw", 30) + hy
      : vs.heads.size ? Math.abs(headSwitchAt(0, vs.heads.has(60) ? 60 : 90)) + hy
      : far > 30 ? 90 : 45;
    r.setup(vs.w, vs.h, vs.framing, vs.debug, lv);
    r.resize(this.cssSize[0], this.cssSize[1]);
    r.view = [...this.view] as Affine;
    this.kids.set(key, r);
    return r;
  }

  /** Separate from init for tests (no fetch, no DOM container). */
  setup(width: number, height: number, framing: Framing = "body", debug = false, lv?: LoadedVector) {
    if (lv) this.lv = lv;
    this.rig = new VRig(this.lv.doc);
    this.framing = framing;
    this.debug = debug;
    this.cv = document.createElement("canvas");
    // software canvas: Canvas 2D clipping on an emulated GPU (headless SwiftShader) is very slow
    this.g = this.cv.getContext("2d", { willReadFrequently: flag("vSoft", true) })!;
    this.index(false);
    this.resize(width, height);
  }

  /** Everything derived from the composed character: chains, feature groups, hand drawings,
   *  head-turn tunables and the rim of the head. `rebase`: keep the swing of the chains that
   *  stay (swapVector). */
  private index(rebase: boolean) {
    // vStiff / vDamp / vGrav (0..1) override every chain (for comparisons)
    const ov = (k: string, v: number) => (q().has(k) ? Number(q().get(k)) : v);
    const old = this.chains;
    this.chains = new Map();
    this.partChain = new Map();
    for (const ch0 of this.lv.doc.chains ?? []) {
      const ch = { ...ch0, stiffness: ov("vStiff", ch0.stiffness), damping: ov("vDamp", ch0.damping), gravity: ov("vGrav", ch0.gravity) };
      const have = rebase ? old.get(ch.id) : undefined;
      const sc = have ?? new SpringChain(ch);
      if (have) have.rebase(ch);
      sc.accMax = this.opt.accMax;
      this.chains.set(ch.id, sc);
      for (const pid of ch.parts) this.partChain.set(pid, sc);
    }
    this.groupCenter.clear();
    this.groupHalf.clear();
    this.pairMidX = undefined;
    // group centres (default variant) for rigid feature placement
    const groups = new Map<string, LoadedPart[]>();
    for (const p of this.lv.parts) if (p.group) { if (!groups.has(p.group)) groups.set(p.group, []); groups.get(p.group)!.push(p); }
    for (const [gname, ps] of groups) {
      const vis = ps.filter((p) => p.visible);
      const use = vis.length ? vis : ps;
      const x0 = Math.min(...use.map((p) => p.box[0])), y0 = Math.min(...use.map((p) => p.box[1]));
      const x1 = Math.max(...use.map((p) => p.box[2])), y1 = Math.max(...use.map((p) => p.box[3]));
      this.groupCenter.set(gname, [(x0 + x1) / 2, (y0 + y1) / 2]);
      this.groupHalf.set(gname, (x1 - x0) / 2);
    }
    // which local side (+x / -x) the index finger of the pointing hand is drawn on
    for (const sd of ["L", "R"] as const) {
      this.handVariants[sd] = new Set(this.lv.parts.filter((x) => x.group === `hand_${sd}`).flatMap((x) => x.variants ?? []));
      // the turn engine swaps the drawing every few degrees (rebase): keep the hysteresis state
      if (!rebase) { this.autoHand[sd] = "open"; this.bodyHand[sd] = "open"; }
      const tu = this.lv.parts.find((x) => x.group === `hand_${sd}` && x.variants?.includes("thumbs_up"));
      this.thumbUpSide[sd] = tu ? thumbUpSide(tu.rings, tu.pivot[0]) : 0;
      const hp = this.lv.parts.find((x) => x.group === `hand_${sd}` && x.variants?.includes("point"));
      if (!hp) continue;
      let tip: Pt = hp.pivot, best = -Infinity;
      for (const r of hp.rings) for (const q of r) { const d = q[1] - hp.pivot[1]; if (d > best) { best = d; tip = q; } }
      const w = hp.box[2] - hp.box[0];
      const dx = tip[0] - hp.pivot[0];
      this.thumbSide[sd] = Math.abs(dx) > 0.06 * w ? Math.sign(dx) : 0;
    }
    // head turn: layer amounts and tunables (vector.json, then URL: vPar=feature:0.6,head:0.3
    // and vTurn=shift:0.1,irisRoll:0.2), and the rim of the whole head (fixed head parts)
    const kv = (k: string) => Object.fromEntries((q().get(k) ?? "").split(",").filter((x) => x.includes(":")).map((x) => { const [a, b] = x.split(":"); return [a, Number(b)]; }));
    const ht = this.lv.doc.headTurn ?? {};
    this.par = { ...DEFAULT_PARALLAX, ...(this.lv.doc.parallax ?? {}), ...kv("vPar") };
    const { reach: reachIn, ...turnIn } = ht;
    this.turn = { ...(turnIn as Record<string, number>), ...kv("vTurn") };
    const sk0 = this.lv.doc.skeleton;
    const fixed = this.lv.parts.filter((p) => p.bone === "head" && p.layer !== "feature" && p.layer !== "ear" && p.layer !== "body" && !this.partChain.has(p.id) && p.visible);
    this.reach = reachIn ?? headReach(sk0.head_center, sk0.head_radius, fixed.map((p) => p.box));
  }

  resize(cw: number, ch: number): void {
    this.cssSize = [cw, ch];
    // draw at the device pixel ratio (sharper shots with a deviceScaleFactor; vdpr overrides)
    const dpr = num("vdpr", typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1);
    const w = Math.round(cw * dpr), h = Math.round(ch * dpr);
    this.W = w; this.H = h;
    this.cv.width = w; this.cv.height = h;
    const sk = this.lv.doc.skeleton;
    let box: [number, number, number, number];
    if (this.framing === "face") {
      const [cx, cy] = sk.head_center, [rx, ry] = sk.head_radius;
      box = [cx - rx * 1.9, cy - ry * 2.2, cx + rx * 1.9, cy + ry * 1.6];
    } else if (this.framing === "bust") {
      // head and chest, for a small presenter window: from above the head (room for the
      // props over it: vBustTop x the head height) down to part of the torso (vBustBot: 0 = neck,
      // 1 = hips); width vBustW x the height (1 = square, for a round mask)
      const [cx, cy] = sk.head_center, [, ry] = sk.head_radius;
      // the head's own top or anything drawn on the head above it (ears, hair, hats)
      const onHead = this.lv.parts.filter((p) => p.visible && p.bone === "head").map((p) => p.box[1]);
      const top = Math.min(cy - ry, ...onHead) - num("vBustTop", 0.22) * 2 * ry;
      const bot = sk.neck[1] + num("vBustBot", 0.55) * (sk.hips[1] - sk.neck[1]);
      const half = ((bot - top) / 2) * num("vBustW", 1);
      const cxs = cx + num("vBustX", 0) * 2 * half;
      box = [cxs - half, top, cxs + half, bot];
    } else {
      const xs = this.lv.parts.filter((p) => p.visible).map((p) => p.box);
      const x0 = Math.min(...xs.map((b) => b[0])), y0 = Math.min(...xs.map((b) => b[1]));
      const x1 = Math.max(...xs.map((b) => b[2])), y1 = Math.max(...xs.map((b) => b[3]));
      const span = Math.max(sk.wrist_L[0] - sk.wrist_R[0], 0) + 2 * (this.rig.upperLen.L + this.rig.foreLen.L);
      const cx = (x0 + x1) / 2;
      const half = Math.max((x1 - x0) / 2, span / 2) * 1.05;
      box = [cx - half, y0 - (y1 - y0) * 0.06, cx + half, y1 + (y1 - y0) * 0.04];
      // vPad: extra margin (x the body height) on every side, e.g. for hops and swinging ears
      const pad = num("vPad", 0) * (y1 - y0);
      box = [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad];
    }
    const s = Math.min(w / (box[2] - box[0]), h / (box[3] - box[1]));
    const ox = (w - s * (box[2] - box[0])) / 2 - s * box[0];
    const oy = (h - s * (box[3] - box[1])) / 2 - s * box[1];
    this.view = [s, 0, 0, s, ox, oy];
    // body views share the framing of the front view (the character stays put on screen)
    for (const v of this.kids.values()) { v.resize(cw, ch); v.view = [...this.view] as Affine; }
  }

  setPose(pose: Pose): void { this.pose = pose; }
  setFace(face: FaceState): void { this.face = face; }

  // ------------------------------------------------------------------ state helpers
  private exprKey(): string { return EXPR_KEY[this.face.expression] ?? "normal"; }
  private variantFor(group: string): string | undefined {
    const ex = this.lv.doc.expressions[this.exprKey()] ?? this.lv.doc.expressions.normal ?? {};
    const has = (v: string) => this.lv.parts.some((p) => p.group === group && p.variants?.includes(v));
    if (group.startsWith("eye_")) {
      const side = group.endsWith("_L") ? "L" : "R";
      return eyeVariant(ex, eyeFor(this.face, side), has);
    }
    if (group.startsWith("brow_")) { const v = ex.brow ?? "normal"; return has(v) ? v : undefined; }
    if (group === "mouth") {
      const m = this.face.mouth;
      if (m !== "sil" && has(m)) return m;
      const v = ex.mouth ?? "closed";
      return has(v) ? v : "closed";
    }
    if (group.startsWith("hand_")) return this.handShape(group.endsWith("_L") ? "L" : "R");
    if (group.startsWith("sleeve_")) return this.sleeveState[group.endsWith("_L") ? "L" : "R"];
    // props over the head: the face state's prop while it is shown at all; otherwise none
    if (group === "prop") return (this.face.propAmt ?? 1) > 0.01 && this.face.prop ? this.face.prop : "none";
    return undefined;
  }

  /** The shape asked for: the pose's, or an automatic one from the palm direction. */
  private handWant(side: "L" | "R"): HandShape {
    const want = this.pose.hands?.[side];
    if (want) {
      // palm named in motions is seen from the front of the body: turn it with the chest
      // (yaw only, so a bow does not change it). A turned body view solved the body without its
      // drawing's angle, so that angle is added back. open keeps its back drawing.
      // vHandTurn=0: as drawn (before)
      this.edgeNx[side] = 0;
      if (want !== "palm" || !flag("vHandTurn", true) || !this.rig.world.chest) return want;
      const f = this.rig.axis("chest", [0, 0, 1]);
      const yaw = Math.atan2(f[0], f[2]) + this.viewYaw;
      const got = (this.bodyHand[side] = bodyHandShape(want, yaw, this.bodyHand[side], this.handVariants[side].has("palm_up")));
      if (got === "palm_up") this.edgeNx[side] = Math.sin(yaw);
      return got;
    }
    // automatic: palm toward the viewer -> palm, palm up -> palm_up (hysteresis)
    const bone = side === "L" ? "leftHand" : "rightHand";
    if (!this.rig.world[bone]) return "open";
    const n = this.rig.axis(bone, [0, -1, 0]); // palm normal in the T-pose points down
    return (this.autoHand[side] = autoHandShape(n, this.autoHand[side], this.handVariants[side].has("palm_up")));
  }

  /** The shape to draw: the one asked for, or the first of its fallbacks the character has. */
  private handShape(side: "L" | "R"): HandShape {
    const vs = this.handVariants[side];
    return resolveHandShape(this.handWant(side), (s) => vs.has(s));
  }

  private isVisible(p: LoadedPart): boolean {
    if (!p.group) return p.visible;
    const v = this.variantFor(p.group);
    if (v === undefined) return p.visible;
    return !!p.variants?.includes(v);
  }

  // ------------------------------------------------------------------ head
  private headFrame(): HeadFrame {
    const sk = this.lv.doc.skeleton;
    const f0 = this.rig.axis("head", [0, 0, 1]);
    // a turned body view solved the body without the drawing's angle: add it back, then take
    // the head drawing's own angle out (the front head turns by the full world yaw, the side
    // head by what is left of it around 90 deg)
    const va = this.viewYaw - this.headYaw;
    const cv = Math.cos(va), sv = Math.sin(va);
    const f = [f0[0] * cv + f0[2] * sv, f0[1], -f0[0] * sv + f0[2] * cv];
    // rule G (docs/character-pipeline.md): 2D head turns are limited to +-30 deg (pitch +-20);
    // with a turned body drawing head and body together reach 45 deg
    const lim = (num("vMaxYaw", this.maxYawDeg) * Math.PI) / 180, plim = (20 * Math.PI) / 180;
    const yaw = Math.max(-lim, Math.min(lim, Math.atan2(f[0], f[2])));
    const pitch = Math.max(-plim, Math.min(plim, Math.asin(Math.max(-1, Math.min(1, f[1])))));
    return { c: sk.head_center, r: sk.head_radius, yaw, pitch, reach: this.reach, turn: this.turn, base: this.headYaw, pairMid: this.headYaw ? this.pairMid() : undefined };
  }

  /** Midpoint of the rest anchors of the paired head attachments (ear_L / ear_R, twintail_L /
   *  twintail_R): the axis their gap scales about on a turned head drawing. */
  private pairMidX?: number | null;
  private pairMid(): number | undefined {
    if (this.pairMidX === undefined) {
      const xs: number[] = [];
      for (const p of this.lv.parts) {
        if (!/_(L|R)$/.test(p.id) || p.bone === undefined) continue;
        const chain = this.partChain.get(p.id);
        if (!chain && p.layer !== "ear") continue;
        if (chain && chain.def.bone !== "head") continue;
        xs.push((chain ? chain.def.root : p.pivot)[0]);
      }
      this.pairMidX = xs.length >= 2 ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
    }
    return this.pairMidX ?? undefined;
  }

  /** The neck leans with the chin (id056 follow-up): the face outline slides toward the turn
   *  (parallax), so the top of the neck, drawn up behind the chin, would stick out beside the
   *  jaw on the trailing side. Points of the neck part move by the chin's displacement, fully
   *  from the head joint up and fading to nothing at the neck joint (under the collar).
   *  k = fraction of the chin's displacement (1 = the neck top rides with the chin, which
   *  uncovers the collar on the leading side; 0 = off). */
  private neckMap(hf: HeadFrame, k: number): MapFn | null {
    if (!k || (!hf.yaw && !hf.pitch)) return null;
    const sk = this.lv.doc.skeleton;
    const y1 = sk.head[1], y0 = sk.neck[1];
    if (!(y0 > y1)) return null;
    const pv = this.par.head ?? DEFAULT_PARALLAX.head;
    const fd = faceDisp(hf, pv, [hf.c[0], hf.c[1] + hf.r[1]]), hs = headShift(hf);
    const dx = k * (fd[0] + hs[0]), dy = k * (fd[1] + hs[1]);
    return (q: Pt) => {
      const w = Math.max(0, Math.min(1, (y0 - q[1]) / (y0 - y1)));
      return [q[0] + dx * w, q[1] + dy * w];
    };
  }

  /** IK reach: the wrist goes toward a point of the view (Pose.reach, u/v of the canvas),
   *  blended over the keyed arm by w; the rig is solved again with the blended arms. */
  private applyReach(): void {
    const rc = this.pose.reach;
    if (!rc || (!rc.L && !rc.R)) return;
    const [a, b, c, d, e, f] = this.view;
    const det = a * d - b * c;
    if (!det) return;
    const bones = { ...this.pose.bones };
    let changed = false;
    for (const s of ["L", "R"] as const) {
      const r = rc[s];
      if (!r || r.w <= 0) continue;
      const side = s === "L" ? "left" : "right";
      const sh = this.rig.world[`${side}UpperArm`], par = this.rig.world[`${side}Shoulder`];
      if (!sh || !par) continue;
      // canvas (device px) -> drawing px -> rig space (x right, y up, relative to the rest hips)
      const X = r.u * this.W - e, Y = r.v * this.H - f;
      const px = (d * X - c * Y) / det, py = (-b * X + a * Y) / det;
      const target = screenTarget(sh.pos, px - this.rig.hips[0], this.rig.hips[1] - py, num("vReachFwd", 8));
      const sol = solveArm({ side: s, shoulder: sh.pos, parentRot: par.rot, upperLen: this.rig.upperLen[s], foreLen: this.rig.foreLen[s], target, limits: { maxUp: num("vReachUp", 40) } });
      const w = Math.min(1, r.w);
      bones[`${side}UpperArm`] = quatSlerp(getRotation(this.pose, `${side}UpperArm`), sol.upper, w);
      bones[`${side}LowerArm`] = quatSlerp(getRotation(this.pose, `${side}LowerArm`), sol.lower, w);
      bones[`${side}Hand`] = quatSlerp(getRotation(this.pose, `${side}Hand`), IDENTITY, w);
      changed = true;
    }
    if (!changed) return;
    this.pose = { ...this.pose, bones };
    this.rig.solve(this.pose);
  }

  private headAffine(): Affine {
    // translation of the head joint + in-plane roll; yaw/pitch are handled by parallax
    const rest = this.rig.restScreen("head");
    const cur = this.rig.screen("head").p;
    const up = this.rig.axis("head", [0, 1, 0]);
    const roll = Math.atan2(up[0], up[1]); // screen clockwise
    const co = Math.cos(roll), si = Math.sin(roll);
    return [co, si, -si, co, cur[0] - co * rest[0] + si * rest[1], cur[1] - si * rest[0] - co * rest[1]];
  }

  // ------------------------------------------------------------------ frame
  render(time: number): void {
    if (this.viewSet) { this.renderViews(time); return; }
    this.rig.solve(this.pose);
    this.applyReach();
    this.rig.rotateArms(this.viewYaw);
    // micro saccades: the iris + pupil jump a little now and then
    this.sacc = this.opt.saccade ? this.saccader.at(time) : [0, 0];
    // breathing (a sign of life): the chest rises and falls; the torso stretches from the hips
    const breath = this.opt.breath * 0.5 * (1 - Math.cos((2 * Math.PI * time) / this.opt.breathPeriod));
    const torsoAff = this.rig.boneAffine("chest"), spineAff = this.rig.boneAffine("spine");
    const hipsS = this.rig.screen("hips").p, chestS = this.rig.screen("chest").p;
    const span = Math.max(1, hipsS[1] - chestS[1]);
    const sy = (span + breath) / span;
    const stretch: Affine = [1, 0, 0, sy, 0, hipsS[1] - sy * hipsS[1]];
    this.rig.breathe(breath);
    const hf = this.headFrame();
    const headAff = this.headAffine();
    const par = this.par;
    // dt = 0 when the same time is drawn again (frozen clock during capture): no step.
    // A jump backwards or a long gap (seek, tab switch) restarts the simulation.
    const jump = this.lastT < 0 || time < this.lastT - 1e-9 || time - this.lastT > 0.5;
    if (jump) { for (const c of this.chains.values()) c.reset(); this.hand.L.init = false; this.hand.R.init = false; }
    const dt = jump ? 0 : time - this.lastT;
    this.lastT = time;
    this.dt = dt;
    this.opt.outline.clock = time;

    // spring chains: root follows its parent bone
    for (const ch of this.chains.values()) {
      ch.gain = this.opt.physics ? this.opt.physGain * (ch.def.gain ?? 1) : 0;
      const isHead = ch.def.bone === "head";
      const aff = isHead ? headAff : this.slideAff(ch.def.id, this.rig.boneAffine(ch.def.bone));
      const root = apply(aff, ch.def.root);
      const ang = Math.atan2(aff[1], aff[0]);
      // tails wag a little on their own (two mixed slow waves, so it does not look mechanical)
      const wag = isHead ? 0 : this.opt.wag * (Math.sin(2 * Math.PI * 0.85 * time) * 0.7 + Math.sin(2 * Math.PI * 0.37 * time + 1.3) * 0.3);
      if (this.opt.physics) ch.step(dt, root, ang, isHead ? hf.yaw : 0, isHead ? hf.pitch : 0, wag);
      else ch.reset();
    }

    const items: DrawItem[] = [];
    const headParts = (p: LoadedPart) => p.bone === "head" || (this.chains.get(p.bone)?.def.bone === "head");

    // arms first (geometry), inserted into the list below
    const arms = (["L", "R"] as const).map((s) => this.armItems(s));

    // each arm goes behind its own attach part (a turned body has the near arm in front);
    // an attach part that does not exist puts the arm behind everything else
    const attachOf = (s: "L" | "R") => this.lv.doc.arms[s].attach ?? this.lv.doc.arms.L.attach ?? "torso";
    const att = (["L", "R"] as const).map((s) => (this.lv.byId[attachOf(s)] ? attachOf(s) : this.lv.parts[0]?.id));
    for (const p of this.lv.parts) {
      arms.forEach((a, i) => { if (p.id === att[i]) items.push(...a.back); });
      if (!this.isVisible(p)) continue;
      if (p.group?.startsWith("hand_") || p.group?.startsWith("sleeve_")) continue; // drawn with the arm
      const chain = this.partChain.get(p.id);
      let map: MapFn | null = null;
      let aff: Affine = [1, 0, 0, 1, 0, 0];
      if (headParts(p)) {
        const layer = p.layer;
        const pv = par[layer] ?? 0;
        aff = headAff;
        if (layer === "feature") {
          aff = mulAff(headAff, this.featureLocal(p, hf));
        } else if (chain || layer === "ear") {
          // attached at its root: rigid, narrower on the turning side; inner shapes slide a little
          const a = chain ? chain.def.root : p.pivot;
          const pl = attachPlace(hf, pv, a, /_(L|R)$/.test(p.id));
          const place = (dx: number): MapFn => (pt: Pt) => {
            const d = chain ? chain.deform(pt) : pt;
            return [a[0] + (d[0] - a[0]) * pl.sx + pl.d[0] + dx, d[1] + pl.d[1]];
          };
          map = place(0);
          const inner = (this.turn.earInner ?? DEFAULT_HEAD_TURN.earInner) * (p.box[2] - p.box[0]) * Math.sin(hf.yaw);
          if (p.cmds.length > 1 && Math.abs(inner) > 0.01) {
            const mi = place(inner);
            const it = this.partItem(p, aff, map, (i) => (i > 0 ? mi : map!));
            it.clipSelf = true;
            items.push(it);
            continue;
          }
        } else {
          map = shellMap(hf, pv, layer === "head");
        }
      } else {
        const b = chain ? chain.def.bone : p.bone;
        aff = b === "chest" ? mulAff(stretch, torsoAff) : b === "spine" ? mulAff(stretch, spineAff) : this.rig.boneAffine(b);
        if (this.opt.plant && (b === "leftUpperLeg" || b === "rightUpperLeg")) {
          const sk = this.lv.doc.skeleton;
          const hip = b === "leftUpperLeg" ? sk.hip_L : sk.hip_R;
          const ankle = b === "leftUpperLeg" ? sk.ankle_L : sk.ankle_R;
          aff = plantedLegAffine(hip, apply(aff, hip), ankle[0], p.box[3], this.floorPoint(), this.pose.squash ?? 1, this.opt.plantLift);
        }
        if (chain) { map = (pt: Pt) => chain.deform(pt); aff = this.slideAff(chain.def.id, aff); }
        else if (b === "neck") map = this.neckMap(hf, num("vNeckFollow", 0.5));
      }
      if (p.group === "prop") aff = mulAff(aff, popScale(p.pivot, this.face.propAmt ?? 1));
      items.push(this.partItem(p, aff, map));
    }
    // an arm in front of the body goes behind the head unless its hand reaches over the head:
    // a chibi head lies over the shoulders, and the root of an arm crossing the chest would
    // otherwise cover the head's lower edge
    // the head in front of the body: the run of head parts at the end of the list (back hair,
    // drawn behind the body, is not in it)
    const isHead = (it: DrawItem) => !!this.lv.byId[it.id] && headParts(this.lv.byId[it.id]);
    let headAt = items.length;
    while (headAt > 0 && isHead(items[headAt - 1])) headAt--;
    const headBox = headAt === items.length ? null : items.slice(headAt)
      .reduce<DrawItem["box"] | null>((b, it) => (b ? [Math.min(b[0], it.box[0]), Math.min(b[1], it.box[1]), Math.max(b[2], it.box[2]), Math.max(b[3], it.box[3])] : [...it.box]), null);
    const late: DrawItem[] = [], early: DrawItem[] = [];
    arms.forEach((a, i) => {
      const s = i === 0 ? "L" : "R";
      const hand = a.front.find((it) => it.id.startsWith(`hand_${s}`)) ?? a.front.find((it) => it.id.endsWith("_fore"));
      let over = this.armLayer[s].raised;
      if (!over && hand && headBox) {
        const b = hand.box;
        const ix = Math.max(0, Math.min(b[2], headBox[2]) - Math.max(b[0], headBox[0]));
        const iy = Math.max(0, Math.min(b[3], headBox[3]) - Math.max(b[1], headBox[1]));
        over = ix * iy > 0.2 * Math.max(1, (b[2] - b[0]) * (b[3] - b[1]));
      }
      (over || !headBox ? late : early).push(...a.front);
    });
    if (early.length) items.splice(headAt, 0, ...early);
    items.push(...late);

    // ---- draw
    // whole-body squash & stretch (Pose.squash): vertical scale about the feet, widened by
    // 1/sqrt(squash) so the volume reads as kept (squashed = wider, stretched = narrower)
    const baseView = this.view;
    this.view = this.followView(time);
    const sq = this.pose.squash ?? 1;
    if (Math.abs(sq - 1) > 1e-6) {
      const F = this.floorPoint();
      const sx = 1 / Math.sqrt(sq);
      this.view = mulAff(this.view, [sx, 0, 0, sq, F[0] - sx * F[0], F[1] - sq * F[1]]);
    }
    try { this.drawAll(items); } finally { this.view = baseView; }
  }

  /** Bust framing: the camera follows the neck a little (vBustFollow, 0..1, default 0.6),
   *  smoothed (vBustLag seconds), so a sway or a nod does not push the head out of the small
   *  window while the window still shows the body moving. Other framings: the view as it is. */
  private followView(time: number): Affine {
    const f = this.framing === "bust" ? num("vBustFollow", 0.6) : 0;
    if (f <= 0) return this.view;
    const n = this.rig.screen("neck").p, rest = this.lv.doc.skeleton.neck;
    const target: Pt = [(n[0] - rest[0]) * f, (n[1] - rest[1]) * f];
    const st = this.follow;
    const dt = st.t === null ? Infinity : Math.max(0, time - st.t);
    const k = dt === Infinity || dt > 1 ? 1 : 1 - Math.exp(-dt / Math.max(1e-3, num("vBustLag", 0.3)));
    st.off = [st.off[0] + (target[0] - st.off[0]) * k, st.off[1] + (target[1] - st.off[1]) * k];
    st.t = time;
    return mulAff(this.view, [1, 0, 0, 1, -st.off[0], -st.off[1]]);
  }

  // ------------------------------------------------------------------ body views
  /** Pick the body and head drawings from the body / head yaw and composite the views.
   *  Body: the drawing (0, +-15 ... +-90 deg; whichever exist) nearest to the body yaw, the
   *  rest (at most half a step) rotated as flat parts; switches at the midpoints between the
   *  drawings (15 / 45 / 75 deg with 30 deg steps, 7.5 / 22.5 / ... with 15 deg steps).
   *  Head: the front head up to 30 deg (vHead60At), the 60 deg head up to 75 deg (vHead90At),
   *  then the side head; without a 60 deg head, the side head from 60 deg (vHeadSwitch).
   *  vSwitch = cut | hyst (default) | fade | fadeT compares ways to hide the change: hyst and
   *  fadeT switch with a hysteresis of +-vHyst deg; fade blends the body over an angle range;
   *  fadeT crossfades over a time after the switch. */
  private renderViews(time: number): void {
    const vs = this.viewSet!;
    this.rig.solve(this.pose);
    const deg = (v: number[]) => (Math.atan2(v[0], v[2]) * 180) / Math.PI;
    const yaw = deg(this.rig.axis("chest", [0, 0, 1]));
    const hyaw = deg(this.rig.axis("head", [0, 0, 1]));
    // default: the hysteresis switch alone; the timed crossfade
    // (fadeT, the provisional default of 2026-11-19) read worse once the drawings came at
    // many angles
    const mode = q().get("vSwitch") ?? "hyst";
    const at = num("vSwitchAt", 15), hw = num("vFade", 4), hy = mode === "cut" ? 0 : num("vHyst", 3);
    const bodyAngles = [0, ...vs.bodies.keys()].sort((a, b) => a - b);
    const bodyB = (a: number, b: number) => (a === 0 || b === 0 ? Math.sign(a + b) * Math.min(at, Math.abs(a + b) / 2) : (a + b) / 2);
    const headAngles = [0, ...vs.heads.keys()].sort((a, b) => a - b);
    const headB = headSwitchAt;
    this.bodySlot = pickSlot(this.bodySlot, yaw, bodyAngles, hy, bodyB);
    this.headSlot = pickSlot(this.headSlot, hyaw, headAngles, hy, headB);
    // vBodyPin / vHeadPin hold one drawing whatever the yaw (seam measurements)
    if (q().has("vBodyPin") && bodyAngles.includes(num("vBodyPin", 0))) this.bodySlot = num("vBodyPin", 0);
    if (q().has("vHeadPin") && headAngles.includes(num("vHeadPin", 0))) this.headSlot = num("vHeadPin", 0);
    let layers: { v: VectorRenderer; alpha: number }[];
    // vMorph=1: the turn engine (key drawings 30 deg apart + in-betweens)
    const morph = flag("vMorph", true) && !q().has("vBodyPin");
    let target: VectorRenderer;
    if (morph) {
      const e = this.turnEngine();
      const hd = flag("vMorphHead", true) && !q().has("vHeadPin") ? e.headAngle(hyaw) : this.headSlot;
      target = this.morphTarget(e.bodyAngle(yaw), hd);
    } else target = this.kid(this.bodySlot, this.headSlot);
    if (mode === "fadeT") {
      layers = this.timedFade(time, target);
    } else if (mode === "fade") {
      // the body blends across +-hw of each switch angle (the head switches with hysteresis)
      layers = [{ v: target, alpha: 1 }];
      for (let i = 0; i + 1 < bodyAngles.length; i++) {
        const a = bodyAngles[i], b = bodyAngles[i + 1], B = bodyB(a, b);
        if (Math.abs(yaw - B) >= hw) continue;
        const t = (yaw - (B - hw)) / (2 * hw), sm = t * t * (3 - 2 * t);
        layers = [{ v: this.kid(a, this.headSlot), alpha: 1 }, { v: this.kid(b, this.headSlot), alpha: sm }];
      }
    } else {
      layers = [{ v: target, alpha: 1 }];
    }
    // hand the swing of ears/tails and the hand lag over to a view that comes in
    const prev = [...this.activeViews];
    const now = new Set(layers.map((l) => l.v));
    for (const l of layers) if (!this.activeViews.has(l.v) && prev.length) l.v.adoptDynamics(prev[prev.length - 1]);
    this.activeViews = now;
    if (!morph) for (const l of layers) this.slideTails(l.v, yaw, bodyAngles, bodyB);
    for (const l of layers) {
      const turned = withHipsYaw(this.pose, -l.v.viewYaw);
      l.v.setPose(flag("vLegTurn", true) ? withLegsTurned(turned, l.v.viewYaw) : turned);
      l.v.setFace(this.face);
      l.v.render(time);
    }
    const g = this.g;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalAlpha = 1;
    if (this.opt.bg === "none") g.clearRect(0, 0, this.W, this.H);   // the views are transparent too
    for (const l of layers) {
      g.globalAlpha = l.alpha;
      g.drawImage(l.v.canvas, 0, 0);
    }
    g.globalAlpha = 1;
    const top = layers[layers.length - 1];
    this.lastItems = top.v.lastItems;
    const d = (r: number) => Math.round((r * 180) / Math.PI);
    this.lastBody = { yaw, headYaw: hyaw, views: layers.map((l) => ({ yaw: d(l.v.viewYaw), head: d(l.v.headYaw), alpha: l.alpha })) };
  }

  /** Timed crossfade: the switch is decided with hysteresis, then the
   *  incoming drawing is laid over the outgoing one during vFadeT seconds with an ease-in
   *  opacity p^vFadePow: it starts faint and slowly, and comes in fast at the end.
   *  - Turning back during a fade fades the incoming drawing out again from the same opacity.
   *  - A further switch during a fade (a fast turn passing two switch angles, or the head
   *    switching while the body fades) stacks a third drawing over the two; once a
   *    drawing is fully in, everything under it is dropped. At most 3 drawings.
   *  A seek or a long gap finishes the fade at once. */
  private timedFade(time: number, target: VectorRenderer): { v: VectorRenderer; alpha: number }[] {
    const T = Math.max(1e-3, num("vFadeT", 1)), n = Math.max(1, num("vFadePow", 2));
    const jump = this.fadeLastT < 0 || time < this.fadeLastT - 1e-9 || time - this.fadeLastT > 0.5;
    const dt = jump ? 0 : time - this.fadeLastT;
    this.fadeLastT = time;
    let st = this.fadeStack;
    if (!st.length || jump) st = [{ v: target, p: 1, dir: 1 }];
    // progress
    for (let i = 1; i < st.length; i++) st[i].p = Math.max(0, Math.min(1, st[i].p + (st[i].dir * dt) / T));
    st = st.filter((l, i) => i === 0 || l.p > 0 || l.dir > 0);
    // the wanted drawing
    const top = st[st.length - 1];
    if (top.v !== target) {
      const below = st.length >= 2 ? st[st.length - 2] : null;
      if (below && below.v === target) top.dir = -1;                         // turned back: fade the top out
      else if (st[0].v === target) for (const l of st.slice(1)) l.dir = -1;  // back to the bottom drawing
      else { st = st.filter((l, i) => i === 0 || l.v !== target); st.push({ v: target, p: 0, dir: 1 }); }
    } else if (top.dir < 0) top.dir = 1;                                     // turned forward again
    // a drawing fully in hides everything under it
    for (let i = st.length - 1; i > 0; i--) if (st[i].p >= 1 && st[i].dir > 0) { st = st.slice(i); st[0].p = 1; break; }
    while (st.length > 3) st.shift();
    this.fadeStack = st;
    return st.map((l, i) => ({ v: l.v, alpha: i === 0 ? 1 : Math.pow(l.p, n) }));
  }

  /** A tail drawn to one side of the body would jump to the other side when the next drawing
   *  comes in. While the body turns from a drawing's angle toward the next drawing outward,
   *  the tail slides behind the body, reaching the next drawing's place exactly at the switch
   *  angle (vTailSlide=0 turns it off). */
  private slideTails(v: VectorRenderer, yaw: number, angles: number[], B: (a: number, b: number) => number): void {
    v.slide.clear();
    const V = Math.round((v.viewYaw * 180) / Math.PI);
    if (!flag("vTailSlide", true) || yaw === V) return;
    const dir = Math.sign(yaw - V);
    if (V !== 0 && dir !== Math.sign(V)) return; // only toward the outer drawing
    const i = angles.indexOf(V), N = angles[i + dir];
    if (N === undefined) return;
    const b = B(V, N);
    const k = Math.max(0, Math.min(1, (yaw - V) / (b - V)));
    const r = Math.PI / 180;
    const h = this.lv.doc.skeleton.hips[0];
    const vs = this.viewSet!;
    const nb = N ? vs.bodies.get(N)! : frontBodyView(this.lv.doc);
    const ax = h - nb.skeleton.hips[0]; // drawings are put on the front's hips axis (composeView)
    for (const c of v.lv.doc.chains ?? []) {
      if (c.bone === "head") continue;
      const s = nb.chains?.find((x) => x.id === c.id) ?? (N ? null : this.lv.doc.chains?.find((x) => x.id === c.id));
      if (!s) continue;
      // both drawings turn about the hips axis: this one by b - V, the next one by b - N
      const xf = h + (c.root[0] - h) * Math.cos((b - V) * r), xs = h + (s.root[0] + ax - h) * Math.cos((b - N) * r);
      v.slide.set(c.id, [(xs - xf) * k, (s.root[1] - c.root[1]) * k]);
    }
  }

  /** Continue the physics and hysteresis state of another view (see SpringChain.adopt). */
  private adoptDynamics(o: VectorRenderer): void {
    for (const [id, ch] of this.chains) { const oc = o.chains.get(id); if (oc) ch.adopt(oc); else ch.reset(); }
    this.hand = { L: { ...o.hand.L }, R: { ...o.hand.R } };
    this.handMirror = { ...o.handMirror };
    this.autoHand = { ...o.autoHand };
    this.bodyHand = { ...o.bodyHand };
    this.armLayer = { L: { ...o.armLayer.L }, R: { ...o.armLayer.R } };
    this.sleeveState = { ...o.sleeveState };
    this.lastT = o.lastT;
  }

  /** Centre of the feet on the floor (drawing px): the fixed point of squash & stretch. */
  private floorPoint(): Pt {
    const sk = this.lv.doc.skeleton;
    const legs = this.lv.parts.filter((p) => p.visible && /Leg|Foot/.test(p.bone));
    const y = legs.length ? Math.max(...legs.map((p) => p.box[3])) : Math.max(sk.ankle_L[1], sk.ankle_R[1]);
    return [(sk.ankle_L[0] + sk.ankle_R[0]) / 2, y];
  }

  private drawAll(items: DrawItem[]): void {
    const g = this.g;
    g.setTransform(1, 0, 0, 1, 0, 0);
    if (this.opt.bg === "none") g.clearRect(0, 0, this.W, this.H);
    else { g.fillStyle = this.opt.bg; g.fillRect(0, 0, this.W, this.H); }
    if (this.opt.rim) rimOutline(g, this.W, this.H, this.view, items, this.opt.rim);
    if (this.opt.outline.outer) {
      outerOutline(g, this.W, this.H, this.view, items, this.opt.outline);
    }
    const drawn: DrawItem[] = [];
    for (const it of items) {
      const halo = !!it.halo && this.opt.outline.outer;
      if (halo) haloOutline(g, this.view, it, this.opt.outline);
      this.drawItem(it, items);
      if (this.opt.outline.enabled && !it.noOutline && !halo) drawOutlines(g, this.view, it, drawn, this.opt.outline);
      drawn.push(it);
    }
    this.lastItems = items;
    if (this.debug) this.drawDebug();
  }

  private partItem(p: LoadedPart, aff: Affine, map: MapFn | null, shapeMap?: (i: number) => MapFn): DrawItem {
    // hand-drawn lines: a tiny wobble of the face features (eye white + its clip copy)
    const fw = p.layer === "feature" ? faceWobbleMap(this.opt.outline.hand, this.opt.outline.clock) : null;
    if (fw && !map && !shapeMap && !p.clipTo) map = fw;
    // wobble of the flat shapes: rest points are displaced first, then the part's own
    // map (spring chain, head shell) is applied; face features are left to the wobble above
    const shp = this.opt.outline.shape;
    const sw = p.layer !== "feature" && !p.clipTo ? shapeWobbleMap(shp, this.opt.outline.clock) : null;
    const withSw = (m: MapFn | null | undefined): MapFn | null => (sw ? (m ? (pt: Pt) => m(sw(pt)) : sw) : m ?? null);
    const paths = p.cmds.map((c, i) => (sw ? emitWobbled(c, withSw(shapeMap ? shapeMap(i) : map)!, shp!.step) : emitPath(c, shapeMap ? shapeMap(i) : map ?? undefined)));
    let silR = this.silRest.get(p);
    if (!silR) { silR = silhouetteRings(p); this.silRest.set(p, silR); }
    const swMap = withSw(map);
    const sil = sw ? silR.map((r) => wobbleRing(r, swMap!, shp!.step)) : silR.map((r) => (map ? r.map(map) : r));
    const silPath = new Path2D();
    for (const r of sil) { r.forEach(([x, y], i) => (i ? silPath.lineTo(x, y) : silPath.moveTo(x, y))); silPath.closePath(); }
    let box = bboxOf(sil.map((r) => r.map((pt) => apply(aff, pt))));
    let clip: DrawItem["clip"];
    if (p.clipTo && this.lv.byId[p.clipTo]) {
      const cp = this.lv.byId[p.clipTo];
      // the clip part uses the same placement as its group (eye white)
      const cAff = this.featureAffineOf(cp) ?? aff;
      clip = { aff: cAff, path: cp.cmds.reduce((acc, c) => emitPath(c, fw ?? undefined, acc), new Path2D()) };
    }
    if (!isFinite(box[0])) box = [0, 0, 0, 0];
    return { id: p.id, aff, paths, fills: p.fills, sil: silPath, color: p.baseColor, box, clip,
      noOutline: !!p.clipTo || p.layer === "feature", outline: p.outline, halo: p.halo, outer: p.outer, seamless: p.seamlessWith, rings: sil,
      ...(p.shapes.some((x) => x.alpha !== undefined) ? { alphas: p.shapes.map((x) => x.alpha ?? 1) } : {}) };
  }

  /** Rigid placement of a feature part in head coordinates (rules C, E, F of method D). */
  private featureLocal(p: LoadedPart, hf: HeadFrame): Affine {
    const pv = this.par.feature ?? 0;
    const centre = (x: LoadedPart): Pt => (x.group ? this.groupCenter.get(x.group)! : [(x.box[0] + x.box[2]) / 2, (x.box[1] + x.box[3]) / 2]);
    const c0 = centre(p);
    const half = (x: LoadedPart) => (x.group ? this.groupHalf.get(x.group)! : (x.box[2] - x.box[0]) / 2);
    const nose = this.lv.byId.nose;
    let pl = featurePlace(hf, pv, c0, half(p), p.id === "nose" ? this.turn.noseDepth ?? DEFAULT_HEAD_TURN.noseDepth : 1);
    if (p.group === "mouth" && nose) {
      // the mouth stays under the nose: it turns with the nose's column and keeps its offset
      const nc = centre(nose);
      const n = featurePlace(hf, pv, [nc[0], c0[1]], half(p));
      pl = { c: [n.c[0] + (c0[0] - nc[0]) * n.sx, n.c[1]], sx: n.sx, sy: n.sy };
    }
    let gx = 0, gy = 0, qx = 1, qy = 1;
    let ci: Pt = c0;
    if (p.clipTo && /_(iris|pupil)$/.test(p.id)) {
      // eyeball model: the iris is a disc on a small sphere (radius = half the eye white).
      // Rolling toward the turn / gaze moves it by sin(a) and foreshortens it by cos(a); the
      // pupil sits in front of the iris (cornea bulge) and moves further (pupilDepth).
      const T = this.turn;
      const r = this.irisRoll(p.clipTo, hf);
      const depth = p.id.endsWith("_pupil") ? T.pupilDepth ?? DEFAULT_HEAD_TURN.pupilDepth : 1;
      gx = r.gx * depth;
      gy = r.gy * depth;
      const k = T.irisSqueeze ?? DEFAULT_HEAD_TURN.irisSqueeze;
      qx = 1 - k * (1 - Math.cos(r.ax));
      qy = 1 - k * (1 - Math.cos(r.ay));
      // foreshorten about the part's own centre (the iris/pupil centre)
      const iris = p.id.endsWith("_pupil") ? this.lv.byId[p.id.replace(/_pupil$/, "_iris")] ?? p : p;
      ci = [(iris.box[0] + iris.box[2]) / 2, (iris.box[1] + iris.box[3]) / 2];
    } else if (p.group?.startsWith("eye_") && /_(lash|half|lid_half)$/.test(p.id)) {
      // the upper lid follows the iris down, so the lash keeps covering the iris top
      const f = this.turn.lidFollow ?? DEFAULT_HEAD_TURN.lidFollow;
      const w = `${p.group}_white`;
      if (f && this.lv.byId[w]) gy = f * Math.max(0, this.irisRoll(w, hf).gy);
    }
    // x -> pl.sx * (ci + q (x - ci) - c0) + pl.c + g
    const ax2 = pl.sx * qx, ay2 = pl.sy * qy;
    return [ax2, 0, 0, ay2, pl.sx * (ci[0] - qx * ci[0] - c0[0]) + pl.c[0] + gx, pl.sy * (ci[1] - qy * ci[1] - c0[1]) + pl.c[1] + gy];
  }

  /** Roll of the iris inside an eye white (head turn, gaze, micro saccade): angles and the
   *  offset of the iris centre in drawing px (gy + = down). */
  private irisRoll(white: string, hf: HeadFrame): { ax: number; ay: number; gx: number; gy: number } {
    const w = this.lv.byId[white];
    const ew = w.box[2] - w.box[0], eh = w.box[3] - w.box[1];
    const T = this.turn;
    const sa = this.opt.saccade;
    const rx = (T.irisRoll ?? DEFAULT_HEAD_TURN.irisRoll) * Math.sin(hf.yaw) + 0.25 * (this.face.gazeX / 30) + sa * this.sacc[0];
    const ry = 0.12 * Math.sin(hf.pitch) + 0.2 * (this.face.gazeY / 20) + sa * this.sacc[1];
    const ax = Math.asin(Math.max(-0.95, Math.min(0.95, 2 * rx))), ay = Math.asin(Math.max(-0.95, Math.min(0.95, 2 * ry)));
    return { ax, ay, gx: (ew / 2) * Math.sin(ax), gy: -(eh / 2) * Math.sin(ay) };
  }

  /** placement of a feature part without the iris roll (used for clip shapes) */
  private featureAffineOf(p: LoadedPart): Affine | null {
    if (p.layer !== "feature") return null;
    return mulAff(this.headAffine(), this.featureLocal(p, this.headFrame()));
  }

  private drawItem(it: DrawItem, _all: DrawItem[]) {
    const g = this.g;
    g.save();
    if (it.clip) {
      const m = mulAff(this.view, it.clip.aff);
      g.setTransform(m[0], m[1], m[2], m[3], m[4], m[5]);
      g.clip(it.clip.path);
    }
    const m = mulAff(this.view, it.aff);
    g.setTransform(m[0], m[1], m[2], m[3], m[4], m[5]);
    if (it.regions) {
      // generated arm: base, then each colour band (with its own shade), clipped to the silhouette
      if (it.fills[0]) { g.fillStyle = it.fills[0]; g.fill(it.sil); }
      g.clip(it.sil);
      for (const r of it.regions) {
        g.save();
        g.clip(r.path);
        g.fillStyle = r.color;
        g.fill(r.path);
        if (it.shadePath && r.shade) { g.fillStyle = r.shade; g.fill(it.shadePath); }
        g.restore();
      }
      g.restore();
      return;
    }
    it.paths.forEach((p, i) => {
      const f = it.fills[i];
      if (!f) return;
      // face features (noOutline): dark lines get the hand-drawn line texture; not the
      // iris / pupil (clipped to the eye white): they are fills, not lines
      g.fillStyle = it.noOutline && !it.clip ? featureFill(g, f, this.opt.outline, m, this.view) : f;
      if (it.clipSelf && i === 1) g.clip(it.paths[0], "nonzero");
      g.globalAlpha = it.alphas?.[i] ?? 1;
      g.fill(p, it.clipSelf && i > 0 ? "nonzero" : it.evenodd ? "evenodd" : "nonzero");
    });
    g.globalAlpha = 1;
    g.restore();
  }

  // ------------------------------------------------------------------ arms
  private armItems(s: "L" | "R"): { back: DrawItem[]; front: DrawItem[] } {
    const side = s === "L" ? "left" : "right";
    const def = this.lv.doc.arms[s];
    const S = this.rig.screen(`${side}UpperArm`), E = this.rig.screen(`${side}LowerArm`), Wr = this.rig.screen(`${side}Hand`);
    const chestZ = this.rig.screen("chest").z;
    const R = this.lv.doc.skeleton.head_radius[0];
    const hipsX = this.lv.doc.skeleton.hips[0];
    const geom = buildArm({
      S: S.p, E: E.p, W: Wr.p, zS: S.z, zE: E.z, zW: Wr.z,
      upperLen: this.rig.upperLen[s], foreLen: this.rig.foreLen[s], def,
      towardBody: S.p[0] < hipsX ? 1 : -1, depthGain: this.opt.depthGain / R, curve: this.opt.armCurve,
    });
    // front/back with hysteresis (in head radii)
    const st = this.armLayer[s];
    const zf = ((E.z + Wr.z) / 2 - chestZ) / R, zu = (E.z - chestZ) / R;
    // chibi bodies are shallow: a forearm 0.1 head radii in front of the chest is already in front
    st.fore = st.fore ? zf > 0.04 : zf > 0.1;
    st.upper = st.upper ? zu > 0.2 : zu > 0.35;
    // a chibi head is wider than the shoulders: an arm raised above the neck would vanish
    // behind it, so it goes in front (with a little hysteresis)
    // Only a forearm within the head's width can vanish behind it; an arm raised out to the side
    // (pointing up and away) stays behind the shoulder like any other arm.
    const neckY = this.rig.screen("neck").p[1];
    const foreY = (E.p[1] + Wr.p[1]) / 2;
    const foreX = (E.p[0] + Wr.p[0]) / 2, headX = this.rig.screen("head").p[0];
    const overHead = Math.abs(foreX - headX) < (st.raised ? 1.1 : 1.0) * R;
    const above = overHead && (st.raised ? foreY < neckY + 0.15 * R : foreY < neckY);
    st.raised = above;
    if (above) { st.fore = true; if (E.p[1] < neckY) st.upper = true; }
    // an arm that crosses toward the body centre (elbow inside the shoulder line) must pass in
    // front of the chest; behind the torso it would vanish (pointing between the legs)
    const cx = this.lv.doc.skeleton.hips[0];
    const inward = Math.abs(S.p[0] - cx) - Math.abs(E.p[0] - cx);
    const crossing = st.crossing ? inward > 0.06 * R : inward > 0.12 * R;
    st.crossing = crossing;
    if (crossing && zu > -0.15) { st.upper = true; st.fore = true; }
    // a forearm in front pulls the upper arm to the front (hysteresis 0.1 head radii)
    const jz = this.opt.armJoin;
    st.joined = isFinite(jz) && st.fore && (st.joined ? zu > jz - 0.1 : zu > jz);
    if (st.joined) st.upper = true;
    // sleeve variant by elbow bend (3D)
    const u = norm3(sub3(this.rig.world[`${side}LowerArm`].pos, this.rig.world[`${side}UpperArm`].pos));
    const f = norm3(sub3(this.rig.world[`${side}Hand`].pos, this.rig.world[`${side}LowerArm`].pos));
    const bend = Math.acos(Math.max(-1, Math.min(1, u[0] * f[0] + u[1] * f[1] + u[2] * f[2]))) * 180 / Math.PI;
    const cur = this.sleeveState[s];
    const lv = cur === "straight" ? (bend > 40 ? "bent" : "straight") : cur === "bent" ? (bend < 30 ? "straight" : bend > 95 ? "folded" : "bent") : (bend < 85 ? "bent" : "folded");
    this.sleeveState[s] = lv;

    const ratio = def.shade.ratio ?? 0.3;
    const shadeOf = (band: string) => (def.bands.length === 1 && def.shade.color ? def.shade.color : darken(band, 0.07));
    // wobble of the flat shapes: one frame for the whole arm (shoulder -> wrist), so the
    // upper arm, the forearm and the whole-arm drawing share the same field and follow the arm
    const shp = this.opt.outline.shape;
    const field = shapeWobbleMap(shp, this.opt.outline.clock);
    const wobFrame = field ? frameWobbleMap(field, S.p, Math.atan2(Wr.p[1] - S.p[1], Wr.p[0] - S.p[0])) : null;
    const wob = (mp: MultiPolygon): MultiPolygon => (wobFrame ? wobbleMulti(mp, wobFrame, shp!.step) : mp);
    const armItem = (id: string, gsil0: ArmGeom["silhouette"], bands0: ArmGeom["bands"], shade0: ArmGeom["shade"]): DrawItem => {
      const gsil = wob(gsil0), shade = wob(shade0);
      const bands = bands0.map((b) => ({ ...b, poly: wob(b.poly) }));
      const sil = multiPolygonPath(gsil);
      const regions = bands.map((b) => ({ path: multiPolygonPath(b.poly), color: b.color, shade: shadeOf(b.color) }));
      const box = bboxOf(gsil.flatMap((poly) => poly.map((r) => r as Pt[])));
      const base = def.bands[0]?.color ?? "#ffffff";
      // several bands covering the whole arm: no base fill under them. Its anti-aliased edge
      // showed as a light rim where a navy forearm's round end lies over the navy upper arm.
      const covered = def.bands.length > 1 && def.bands[0].from <= 1e-6 && def.bands[def.bands.length - 1].to >= 1 - 1e-6
        && def.bands.every((b, i) => i === 0 || Math.abs(b.from - def.bands[i - 1].to) < 1e-6);
      // no line round the arm's root: the lines of a piece starting at the
      // shoulder stop at the shoulder point, so an arm in front of the body joins it without a seam
      const root = !id.endsWith("_fore");
      const ul = Math.hypot(E.p[0] - S.p[0], E.p[1] - S.p[1]) || 1;
      const lineFrom = root ? { p: S.p, n: [(E.p[0] - S.p[0]) / ul, (E.p[1] - S.p[1]) / ul] as Pt, r: def.width.shoulder } : undefined;
      // no line round the whole root (vRootGap x the shoulder width), neither the arm's own
      // (it starts below the armpit) nor the torso's over an arm behind it (no stray tick there)
      const rg = this.opt.outline.rootGap ?? 0;
      const gapR = root && rg > 0 ? rg * def.width.shoulder : 0;
      const lineGap = gapR > 0 ? { c: S.p, r: gapR } : undefined;
      const noLineZone = root && (def.rootGap || gapR) ? { c: S.p, r: Math.max(def.rootGap ?? 0, gapR) } : undefined;
      return { id, aff: [1, 0, 0, 1, 0, 0], paths: [sil], fills: [covered ? null : base], sil, color: base, box, group: `arm_${s}`, lineFrom, noLineZone, lineGap,
        clipSelf: true, regions, shadePath: ratio > 0 && shade.length ? multiPolygonPath(shade) : undefined,
        rings: gsil.flatMap((poly) => poly.map((r) => r as Pt[])) };
    };
    const handItem = this.handItem(s, geom, Wr.z, R);
    const sleeveItem = this.sleeveItem(s, S.p, E.p, Wr.p);
    const back: DrawItem[] = [], front: DrawItem[] = [];
    // seamless hands go under the forearm: the forearm's round end covers the wrist, so neither
    // a wrist line nor the hand's wrist edge shows over whatever is behind (e.g. the head)
    // ... except a hand pointing at the viewer, which sticks out in front of the forearm
    const handUnder = !!def.seamlessHand && !(handItem && handItem.id.endsWith("_point_front"));
    if (st.upper === st.fore) {
      const it = armItem(`arm_${s}`, geom.silhouette, geom.bands, geom.shade);
      const list = st.fore ? front : back;
      if (handItem && handUnder) list.push(handItem);
      list.push(it);
      if (sleeveItem) list.push(sleeveItem);
      if (handItem && !handUnder) list.push(handItem);
    } else {
      const up = geom.parts.upper, fo = geom.parts.fore;
      (st.upper ? front : back).push(armItem(`arm_${s}_upper`, up.silhouette, up.bands, up.shade));
      const lst = st.fore ? front : back;
      if (handItem && handUnder) lst.push(handItem);
      lst.push(armItem(`arm_${s}_fore`, fo.silhouette, fo.bands, fo.shade));
      if (sleeveItem) lst.push(sleeveItem);
      if (handItem && !handUnder) lst.push(handItem);
    }
    return { back, front };
  }

  private handItem(s: "L" | "R", geom: ArmGeom, z: number, R: number): DrawItem | null {
    const shape = this.handShape(s);
    const side = s === "L" ? "left" : "right";
    const hx0 = this.rig.axis(`${side}Hand`, [s === "L" ? 1 : -1, 0, 0]);
    const toViewer = Math.hypot(hx0[0], hx0[1]) < 0.55 * (Math.hypot(hx0[0], hx0[1], hx0[2]) || 1);
    // optional "pointing at the viewer" drawing (finger foreshortened, fingertip toward us)
    const front = shape === "point" && this.handWant(s) === "point" && toViewer
      ? this.lv.parts.find((x) => x.group === `hand_${s}` && x.variants?.includes("point_front")) : undefined;
    const p = front ?? this.lv.parts.find((x) => x.group === `hand_${s}` && x.variants?.includes(shape))
      ?? this.lv.parts.find((x) => x.group === `hand_${s}` && x.visible);
    if (!p) return null;
    // direction: forearm direction, bent by the wrist rotation (projected hand axis)
    const hx = this.rig.axis(`${side}Hand`, [s === "L" ? 1 : -1, 0, 0]);
    const hd: Pt = [hx[0], -hx[1]];
    const hl = Math.hypot(hd[0], hd[1]);
    const fd = geom.foreDir;
    const dir = hl > 0.35 ? [hd[0] / hl, hd[1] / hl] : fd;
    let target = Math.atan2(dir[1], dir[0]) - Math.PI / 2; // drawn pointing down (+Y)
    // secondary motion: the hand follows with a slight lag and overshoot (vector_plan §9)
    const hs = this.hand[s];
    if (!hs.init || !this.opt.handLag) { hs.a = target; hs.v = 0; hs.init = true; }
    else {
      while (target - hs.a > Math.PI) target -= 2 * Math.PI;
      while (target - hs.a < -Math.PI) target += 2 * Math.PI;
      const k = 260, c = 18; // underdamped: small overshoot
      const n = Math.max(0, Math.min(120, Math.round(this.dt * 240)));
      const h = n ? this.dt / n : 0;
      for (let i = 0; i < n; i++) { hs.v += (k * (target - hs.a) - c * hs.v) * h; hs.a += hs.v * h; }
    }
    const sc = Math.max(0.6, 1 + this.opt.depthGain * z / R);
    const a = hs.a;
    // foreshortening: a hand pointing toward (or away from) the viewer gets shorter along its
    // own length (the drawing's +Y), so a finger aimed at the camera reads as coming forward
    const hl3 = Math.hypot(hx[0], hx[1], hx[2]) || 1;
    const fy = front ? 1 : Math.max(0.6, Math.min(1, Math.hypot(hx[0], hx[1]) / hl3 + 0.15));
    const co = Math.cos(a) * sc, si = Math.sin(a) * sc;
    const w = geom.wrist;
    const pv = p.pivot;
    // rotation R(a)*sc after a local squash S(1, fy) about the wrist pivot
    let A = co, B = si;
    const C = -si * fy, D = co * fy;
    // pointing hands: the index finger goes to the body side when pointing down, at the
    // viewer or up, and to the top when pointing sideways. The drawing is
    // mirrored about its own axis when its index finger would end up on the other side.
    // thumbs-up hands: the thumb goes to the top
    const sig = shape === "thumbs_up" ? this.thumbUpSide[s] : this.thumbSide[s];
    if ((shape === "point" || shape === "thumbs_up") && sig) {
      // the body side is judged from the shoulder (the hand may cross the centre line)
      const hipsX = this.lv.doc.skeleton.hips[0];
      const sh = this.rig.screen(`${side}UpperArm`).p;
      const tb = Math.sign(hipsX - sh[0]) || 1;
      const dot = mirrorDot(shape, sig, a, tb);
      this.handMirror[s] = this.handMirror[s] ? dot < 0.15 : dot < -0.15;
      if (this.handMirror[s]) { A = -A; B = -B; }
    } else if (shape === "palm_up" && this.edgeNx[s]) {
      // a flat hand named in the motion, seen edge-on: the palm of the edge drawing
      // (+x of the _L drawing, -x of the mirrored _R one) goes to the screen side the palm faces
      const dot = (s === "L" ? 1 : -1) * Math.cos(a) * this.edgeNx[s];
      this.handMirror[s] = this.handMirror[s] ? dot < 0.15 : dot < -0.15;
      if (this.handMirror[s]) { A = -A; B = -B; }
    } else this.handMirror[s] = false;
    const aff: Affine = [A, B, C, D, w[0] - A * pv[0] - C * pv[1], w[1] - B * pv[0] - D * pv[1]];
    const it = this.partItem(p, aff, null);
    if (this.lv.doc.arms[s].seamlessHand) it.group = `arm_${s}`;
    return it;
  }

  private sleeveItem(s: "L" | "R", S: Pt, E: Pt, W: Pt): DrawItem | null {
    const v = this.sleeveState[s];
    const p = this.lv.parts.find((x) => x.group === `sleeve_${s}` && x.variants?.includes(v));
    if (!p) return null;
    // drawn with the upper arm pointing up (-Y) from the elbow pivot
    const up: Pt = [S[0] - E[0], S[1] - E[1]];
    const a = Math.atan2(up[1], up[0]) + Math.PI / 2;
    // mirror when the forearm bends to the other side than drawn (drawn: toward the body)
    const fo: Pt = [W[0] - E[0], W[1] - E[1]];
    const cross = up[0] * fo[1] - up[1] * fo[0];
    const towardBodyDrawn = s === "L" ? -1 : 1;
    const flip = Math.sign(cross || 1) !== towardBodyDrawn && v !== "straight" ? -1 : 1;
    const co = Math.cos(a), si = Math.sin(a);
    const pv = p.pivot;
    const base: Affine = [flip, 0, 0, 1, pv[0] - flip * pv[0], 0];
    const rot: Affine = [co, si, -si, co, E[0] - co * pv[0] + si * pv[1], E[1] - si * pv[0] - co * pv[1]];
    return this.partItem(p, mulAff(rot, base), null);
  }

  private drawDebug() {
    const g = this.g;
    g.save();
    const m = this.view;
    g.setTransform(m[0], m[1], m[2], m[3], m[4], m[5]);
    g.strokeStyle = "#e8305a"; g.lineWidth = 3 / m[0];
    for (const j of this.rig.joints) {
      if (!j.parent) continue;
      const a = this.rig.screen(j.name).p, b = this.rig.screen(j.parent).p;
      g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
    }
    g.restore();
  }

  dispose(): void { this.cv?.remove(); for (const v of this.kids.values()) v.dispose(); }
  /** turn engine statistics (measurements) */
  get turnStats(): { builds: number } | null { return this.engine ? { builds: this.engine.builds } : null; }
}

function bboxOf(rings: Pt[][]): [number, number, number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const r of rings) for (const [x, y] of r) { if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y; }
  return [x0, y0, x1, y1];
}
/** The pose with the hips turned by `yaw` (radians) about the vertical axis (body views). */
function withHipsYaw(pose: Pose, yaw: number): Pose {
  if (!yaw) return pose;
  const r: Quat = [0, Math.sin(yaw / 2), 0, Math.cos(yaw / 2)];
  return { ...pose, bones: { ...pose.bones, hips: quatMul(r, pose.bones.hips ?? IDENTITY) } };
}
/** The legs of a turned body drawing (walking): the body is solved facing the viewer
 *  with the drawing's angle taken out of the hips, but the drawn legs are seen from that angle.
 *  Each leg rotation is turned by the drawing's angle about the vertical axis (conjugated), so
 *  a forward swing (about the body's sideways axis) becomes a swing in the picture plane on the
 *  side view, and part of it on the oblique views. The front drawing (yaw 0) is unchanged. */
const LEG_BONES = ["leftUpperLeg", "rightUpperLeg", "leftLowerLeg", "rightLowerLeg", "leftFoot", "rightFoot"];
export function withLegsTurned(pose: Pose, yaw: number): Pose {
  if (!yaw || !LEG_BONES.some((b) => pose.bones[b])) return pose;
  const r: Quat = [0, Math.sin(yaw / 2), 0, Math.cos(yaw / 2)], ri: Quat = [0, -Math.sin(yaw / 2), 0, Math.cos(yaw / 2)];
  const bones = { ...pose.bones };
  for (const b of LEG_BONES) if (bones[b]) bones[b] = quatMul(quatMul(r, bones[b]), ri);
  return { ...pose, bones };
}
/** Head yaw (deg) at which the head drawing at angle a switches to the neighbouring one at b
 *  (0 / +-60 / +-90 deg). */
export function headSwitchAt(a: number, b: number): number {
  const s = Math.sign(a + b) || 1;
  const lo = Math.min(Math.abs(a), Math.abs(b)), hi = Math.max(Math.abs(a), Math.abs(b));
  if (lo === 0 && hi === 90) return s * num("vHeadSwitch", 60);
  if (lo === 0) return s * num("vHead60At", 30);
  return s * num("vHead90At", 75);
}
/** Hysteresis switch between drawings at sorted angles (deg): stay on `cur` until x passes the
 *  switch angle B(a, b) between neighbours by more than hy. */
export function pickSlot(cur: number, x: number, angles: number[], hy: number, B: (a: number, b: number) => number): number {
  let i = angles.indexOf(cur);
  if (i < 0) i = angles.indexOf(0);
  while (i + 1 < angles.length && x > B(angles[i], angles[i + 1]) + hy) i++;
  while (i > 0 && x < B(angles[i - 1], angles[i]) - hy) i--;
  return angles[i];
}
const sub3 = (a: number[], b: number[]) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const norm3 = (a: number[]) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

/** Pop-in scale of a prop about its pivot: 0 -> 1 with a small overshoot (ease-out back). */
function popScale(c: Pt, amt: number): Affine {
  const u = Math.min(1, Math.max(0, amt)) - 1;
  const s = 1 + 2.70158 * u * u * u + 1.70158 * u * u;
  return [s, 0, 0, s, c[0] - s * c[0], c[1] - s * c[1]];
}
