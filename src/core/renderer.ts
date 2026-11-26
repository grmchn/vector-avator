// Contract between the motion side (src/core) and the drawing methods A-D.
import type { Pose } from "./pose";
import type { FaceState } from "./face";
import type { AvatarPackage } from "./avatarPackage";

export type RendererId = "A" | "B" | "C" | "D" | "E" | "V" | "raw";

/** Character definition (data/characters/<id>.json) = drawing assets + avatar package (docs/avatar-package.md). */
export interface CharacterConfig extends AvatarPackage {
  id: string;
  label: string;
  /** 3D model (VRM or GLB) under public/. */
  model3d?: { url: string; format: "vrm" | "glb"; boneMap?: Record<string, string> };
  /** 2D part set produced by tools (paper doll / warp / 2D face). */
  parts2d?: { url: string };
  faces2d?: { url: string };
  /** Vector character for method V (docs/vector-parts.md). */
  vector?: { url: string };
  /** Defaults for viewer URL parameters (e.g. vOuter, vHand), applied when the URL does not set them. */
  urlDefaults?: Record<string, string>;
}

/** Rendering style (Phase 3). Independent from the drawing method. */
export interface StyleSettings {
  name: string;
  lineWidth?: number;
  lineWobble?: number;
  shadeSteps?: number;
}

/** Camera framing (id112 adds "bust": head and chest, for a small presenter window). */
export type Framing = "body" | "face" | "bust";

/** The framing asked for in the URL (?framing=face|bust; anything else is the whole body). */
export function parseFraming(q: URLSearchParams): Framing {
  const f = q.get("framing");
  return f === "face" || f === "bust" ? f : "body";
}

export interface RendererContext {
  container: HTMLElement;
  character: CharacterConfig;
  width: number;
  height: number;
  /** Camera framing: whole body (default), a close-up of the face, or head-and-chest. */
  framing?: Framing;
  /** Draw debug overlays (bone positions). */
  debug?: boolean;
}

export interface Renderer {
  readonly id: RendererId;
  readonly label: string;
  init(ctx: RendererContext): Promise<void>;
  setPose(pose: Pose): void;
  setFace(face: FaceState): void;
  setStyle?(style: StyleSettings): void;
  /** Draw one frame. `time` is the motion time in seconds (for line wobble etc.). */
  render(time: number): void;
  resize(width: number, height: number): void;
  readonly canvas: HTMLCanvasElement;
  dispose(): void;
}
