// Unit tests for turned body views of method V (src/renderers/vector/bodyView.ts):
// side swapping, mirroring, composition of the view with the front head, and the arm turn.
import { describe, expect, it } from "vitest";
import { composeView, frontBodyView, mirrorView, swapSide, mapPathD, withBodyOrder, type BodyViewDoc } from "../src/renderers/vector/bodyView";
import { VRig, len3 } from "../src/renderers/vector/vrig";
import { type VectorDoc, type VPart } from "../src/renderers/vector/vdata";
import { quatFromEulerDeg } from "../src/core/math";

const part = (id: string, bone: string, layer: string, d: string, extra: Partial<VPart> = {}): VPart => ({
  id, label: id, parent: null, pivot: [0, 0], visible: true, coverage: "", bone, layer,
  shapes: [{ name: id, d, fill: "#ffffff" }], ...extra,
});

const front = {
  format: "so-chara-vector/1", character: "t", width: 1024, height: 1536, expressions: {},
  parts: [
    part("tail", "tail", "body", "M600 1200 L640 1200 L640 1240 Z"),
    part("ear_L", "head", "ear", "M560 400 L600 400 L600 500 Z"),
    part("leg_R", "rightUpperLeg", "body", "M470 1150 L500 1150 L500 1350 Z"),
    part("leg_L", "leftUpperLeg", "body", "M530 1150 L560 1150 L560 1350 Z"),
    part("torso", "chest", "body", "M440 900 L590 900 L590 1160 Z"),
    part("head", "head", "head", "M300 450 L720 450 L720 860 Z"),
    part("hand_L_open", "leftHand", "body", "M700 1100 L720 1100 L720 1140 Z", { group: "hand_L", variants: ["open"] }),
  ],
  skeleton: {
    hips: [512, 1150], chest: [512, 1000], neck: [512, 900], head: [512, 870], head_center: [512, 650], head_radius: [260, 230],
    shoulder_L: [610, 930], elbow_L: [670, 1030], wrist_L: [720, 1130],
    shoulder_R: [414, 930], elbow_R: [354, 1030], wrist_R: [304, 1130],
    hip_L: [560, 1150], hip_R: [464, 1150], ankle_L: [560, 1360], ankle_R: [464, 1360],
  },
  chains: [
    { id: "tail", bone: "hips", parts: ["tail"], root: [600, 1220], tip: [640, 1220], segments: 2, stiffness: 0.5, damping: 0.3, gravity: 0.1 },
  ],
  arms: {
    L: { width: { shoulder: 50, elbow: 40, wrist: 32 }, bands: [{ from: 0, to: 1, color: "#ffffff" }], shade: { color: "#eeeeee", side: "under" }, attach: "torso" },
    R: { width: { shoulder: 50, elbow: 40, wrist: 32 }, bands: [{ from: 0, to: 1, color: "#ffffff" }], shade: { color: "#eeeeee", side: "under" }, attach: "torso" },
  },
} as unknown as VectorDoc;

const view: BodyViewDoc = {
  format: "so-chara-vector-view/1", yaw: -30,
  skeleton: {
    hips: [490, 1150], chest: [490, 1000], neck: [485, 900], head: [480, 872],
    shoulder_L: [560, 930], shoulder_R: [420, 930], hip_L: [520, 1150], hip_R: [460, 1150], ankle_L: [520, 1360], ankle_R: [460, 1360],
  },
  parts: [
    part("tail", "tail", "body", "M560 1200 L600 1200 L600 1240 Z"),
    part("leg_R", "rightUpperLeg", "body", "M450 1150 L480 1150 L480 1350 Z"),
    part("torso", "chest", "body", "M430 900 L560 900 L560 1160 Z"),
    part("leg_L", "leftUpperLeg", "body", "M505 1150 L535 1150 L535 1350 Z", { seamlessWith: ["leg_R"] }),
  ],
  chains: [{ id: "tail", bone: "hips", parts: ["tail"], root: [570, 1220], tip: [600, 1220], segments: 2, stiffness: 0.5, damping: 0.3, gravity: 0.1 }],
  arms: { L: { attach: "head" } },
};

describe("swapSide", () => {
  it("swaps _L/_R and left/right prefixes", () => {
    expect(swapSide("leg_L")).toBe("leg_R");
    expect(swapSide("eye_R_white")).toBe("eye_L_white");
    expect(swapSide("leftUpperLeg")).toBe("rightUpperLeg");
    expect(swapSide("rightHand")).toBe("leftHand");
    expect(swapSide("torso")).toBe("torso");
    expect(swapSide("hair_Large")).toBe("hair_Large");
  });
});

describe("mapPathD", () => {
  it("maps every point of an absolute path", () => {
    expect(mapPathD("M1 2 L3 4 C5 6 7 8 9 10 Z", ([x, y]) => [x + 1, y * 2])).toBe("M2 4 L4 8 C6 12 8 16 10 20 Z");
  });
});

describe("mirrorView", () => {
  const m = mirrorView(view);
  it("flips the angle and mirrors about the hips", () => {
    expect(m.yaw).toBe(30);
    expect(m.skeleton.hips).toEqual([490, 1150]);
    // the near shoulder (_L at x 560) becomes the character's right on the other side
    expect(m.skeleton.shoulder_R).toEqual([420, 930]);
    expect(m.skeleton.shoulder_L).toEqual([560, 930]);
  });
  it("swaps the sides of parts, bones, links, chains and arm overrides", () => {
    const ids = m.parts.map((p) => p.id);
    expect(ids).toEqual(["tail", "leg_L", "torso", "leg_R"]);
    const legR = m.parts.find((p) => p.id === "leg_R")!;
    expect(legR.bone).toBe("rightUpperLeg");
    expect(legR.seamlessWith).toEqual(["leg_L"]);
    expect(m.chains![0].root).toEqual([410, 1220]);
    expect(m.arms?.R?.attach).toBe("head");
    expect(m.arms?.L).toBeUndefined();
  });
});

describe("composeView", () => {
  const c = composeView(front, view);
  it("keeps head parts and hands from the front, moved onto the view's neck", () => {
    const head = c.parts.find((p) => p.id === "head")!;
    // the view is first moved onto the front's hips axis (+22: hips 490 -> 512), so its head
    // [502, 872] - front head [512, 870] = (-10, +2)
    expect(head.shapes[0].d.startsWith("M290 452")).toBe(true);
    expect(c.skeleton.head_center).toEqual([502, 652]);
    expect(c.skeleton.hips).toEqual([512, 1150]);
    expect(c.parts.find((p) => p.id === "hand_L_open")!.shapes[0].d).toBe(front.parts[6].shapes[0].d);
  });
  it("puts the view's body parts into the front body slots in the view's order", () => {
    expect(c.parts.map((p) => p.id)).toEqual(["tail", "ear_L", "leg_R", "torso", "leg_L", "head", "hand_L_open"]);
  });
  it("keeps the arm lengths of the front and merges arm overrides", () => {
    const len = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1]);
    for (const s of ["L", "R"]) {
      expect(len(c.skeleton[`shoulder_${s}`], c.skeleton[`elbow_${s}`])).toBeCloseTo(len(front.skeleton[`shoulder_${s}`], front.skeleton[`elbow_${s}`]), 6);
      expect(len(c.skeleton[`elbow_${s}`], c.skeleton[`wrist_${s}`])).toBeCloseTo(len(front.skeleton[`elbow_${s}`], front.skeleton[`wrist_${s}`]), 6);
    }
    expect(c.skeleton.shoulder_L).toEqual([582, 930]);
    expect(c.arms.L.attach).toBe("head");
    expect(c.arms.R.attach).toBe("torso");
    expect(c.arms.L.width.shoulder).toBe(50);
  });
  it("uses the view's body chains", () => {
    expect(c.chains!.find((x) => x.id === "tail")!.root).toEqual([592, 1220]);
  });
});

// a side head (head90.json) carried by any body drawing
const head90: BodyViewDoc = {
  format: "so-chara-vector-view/1", kind: "head", yaw: -90,
  skeleton: { head: [500, 860], head_center: [480, 640], head_radius: [200, 220] },
  parts: [
    part("ear_L", "head", "ear", "M520 400 L560 400 L560 500 Z"),
    part("head", "head", "head", "M300 450 L640 450 L640 860 Z"),
    part("eye_L_white", "head", "feature", "M330 600 L360 600 L360 640 Z", { group: "eye_L", variants: ["open"] }),
  ],
  order: ["tail", "leg_R", "torso", "leg_L", "head", "eye_L_white", "ear_L"],
  parallax: { head: 0.2 },
};

describe("composeView with a side head", () => {
  const c = composeView(front, view, head90);
  it("replaces the front head by the side head, moved onto the body's neck", () => {
    // body head [502, 872] (after the hips alignment) - side head [500, 860] = (+2, +12)
    expect(c.parts.find((p) => p.id === "head")!.shapes[0].d.startsWith("M302 462")).toBe(true);
    expect(c.skeleton.head_center).toEqual([482, 652]);
    expect(c.skeleton.head_radius).toEqual([200, 220]);
  });
  it("draws in the head view's order (hands and sleeves stay)", () => {
    expect(c.parts.map((p) => p.id)).toEqual(["tail", "leg_R", "torso", "leg_L", "head", "eye_L_white", "ear_L", "hand_L_open"]);
  });
  it("merges the head view's parallax over the front one", () => {
    expect(c.parallax?.head).toBe(0.2);
  });
  it("drops front head chains the side head does not have", () => {
    expect(c.chains!.map((x) => x.id)).toEqual(["tail"]);
  });
  it("works on the front body too", () => {
    const f = composeView(front, frontBodyView(front), head90);
    expect(f.skeleton.hips).toEqual(front.skeleton.hips);
    expect(f.parts.find((p) => p.id === "torso")!.shapes[0].d).toBe(front.parts[4].shapes[0].d);
  });
  it("mirrors a head view about its head joint and keeps the radius", () => {
    const m = mirrorView(head90);
    expect(m.yaw).toBe(90);
    expect(m.skeleton.head).toEqual([500, 860]);
    expect(m.skeleton.head_center).toEqual([520, 640]);
    expect(m.skeleton.head_radius).toEqual([200, 220]);
    expect(m.parts.map((p) => p.id)).toEqual(["ear_R", "head", "eye_R_white"]);
    expect(m.order).toContain("eye_R_white");
  });
});

describe("VRig.rotateArms", () => {
  it("turns the arms about the shoulders without changing their lengths", () => {
    const rig = new VRig(front);
    rig.solve({ bones: { leftUpperArm: quatFromEulerDeg(0, 0, -70) }, hips: [0, 0, 0] });
    const S = [...rig.world.leftUpperArm.pos], E = [...rig.world.leftLowerArm.pos], W = [...rig.world.leftHand.pos];
    rig.rotateArms(Math.PI / 6);
    expect(rig.world.leftUpperArm.pos).toEqual(S);
    const d = (a: number[], b: number[]) => len3([a[0] - b[0], a[1] - b[1], a[2] - b[2]]);
    expect(d(rig.world.leftLowerArm.pos, S)).toBeCloseTo(d(E, S), 6);
    expect(d(rig.world.leftHand.pos, rig.world.leftLowerArm.pos)).toBeCloseTo(d(W, E), 6);
    // turning the character to its left (+yaw) brings its left arm's elbow away from the viewer
    expect(rig.world.leftLowerArm.pos[2]).toBeLessThan(E[2]);
  });
});

describe("pickSlot (body drawing switch with hysteresis)", () => {
  // lazy import: vectorRenderer pulls in DOM-free modules only at module level
  const angles = [-90, -60, -30, 0, 30, 60, 90];
  const B = (a: number, b: number) => (a + b) / 2;
  it("switches 3 deg past the midpoints going out and 3 deg before them coming back", async () => {
    const { pickSlot } = await import("../src/renderers/vector/vectorRenderer");
    let s = 0;
    const walk = (xs: number[]) => xs.map((x) => (s = pickSlot(s, x, angles, 3, B)));
    expect(walk([10, 17, 18.5, 30, 46, 48.5, 77, 78.5, 90])).toEqual([0, 0, 30, 30, 30, 60, 60, 90, 90]);
    expect(walk([74, 71.5, 44, 41.5, 13, 11.5, 0])).toEqual([90, 60, 60, 30, 30, 0, 0]);
    expect(walk([-18.5, -48.5, -78.5])).toEqual([-30, -60, -90]);
  });
  it("jumps over several drawings at once after a seek", async () => {
    const { pickSlot } = await import("../src/renderers/vector/vectorRenderer");
    expect(pickSlot(0, 88, angles, 3, B)).toBe(90);
    expect(pickSlot(90, -88, angles, 3, B)).toBe(-90);
  });
});

describe("headOffset and the body order under a head order", () => {
  it("shifts the front head by the body drawing's headOffset (not a head drawing)", () => {
    const plain = composeView(front, view);
    const off = composeView(front, { ...view, headOffset: [-18, 4] });
    expect(off.skeleton.head_center).toEqual([plain.skeleton.head_center[0] - 18, plain.skeleton.head_center[1] + 4]);
    expect(off.skeleton.head).toEqual(plain.skeleton.head); // the pivot stays on the neck
    const side = composeView(front, { ...view, headOffset: [-18, 4] }, head90);
    expect(side.skeleton.head_center).toEqual(composeView(front, view, head90).skeleton.head_center);
  });
  it("mirrors headOffset with the view", () => {
    expect(mirrorView({ ...view, headOffset: [-18, 4] }).headOffset).toEqual([18, 4]);
  });
  it("keeps the slots of the head order but the body drawing's own body order", () => {
    const order = ["ear_R", "leg_R", "leg_L", "torso", "tail", "head", "eye"];
    // the body drawing has the tail behind (its parts order)
    expect(withBodyOrder(order, view)).toEqual(["ear_R", "tail", "leg_R", "torso", "leg_L", "head", "eye"]);
    // a body drawing with its own order
    expect(withBodyOrder(order, { ...view, order: ["leg_R", "leg_L", "torso", "tail", "hand"] })).toEqual(order);
  });
});

describe("headSwitchAt (head drawing switch angles)", () => {
  it("switches front -> 60 at 30, 60 -> 90 at 75, front -> 90 at 60 deg", async () => {
    const { headSwitchAt } = await import("../src/renderers/vector/vectorRenderer");
    expect(headSwitchAt(0, 60)).toBe(30);
    expect(headSwitchAt(60, 90)).toBe(75);
    expect(headSwitchAt(0, 90)).toBe(60);
    expect(headSwitchAt(-60, 0)).toBe(-30);
    expect(headSwitchAt(-90, -60)).toBe(-75);
  });
});
