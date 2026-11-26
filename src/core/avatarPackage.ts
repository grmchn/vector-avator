// Avatar package (docs/avatar-package.md): the per-character settings that live in
// data/characters/<id>.json next to the drawing assets. Every field is optional; resolvePackage()
// fills the defaults, which reproduce the tools' behaviour before the package existed.
// The Python side mirrors this file in tools/avatar/package.py (keep the defaults in sync).

export const AVATAR_SCHEMA_VERSION = 1;

export type HandType = "mitten" | "beast" | "human" | "stick";
/** How far the character can turn (the acting layer never asks for more). */
export type TurnRange = "front" | "parallax30" | "turn90" | "turn90_opp";
export type ReviewStatus = "draft" | "approved";

export interface RigSettings {
  hands?: {
    type?: HandType;
    scale?: number;
    shapeScale?: Record<string, number>;
    dropLines?: string[];
    unavailable?: string[];
    colors?: { base?: string; line?: string; pad?: string };
  };
  /** Rest pose: upper-arm angle in degrees down from horizontal. */
  rest?: { upperArm?: number };
  turn?: TurnRange;
}

export interface VoiceLang {
  /** "files" (WAV files put by hand), "command" (any TTS, voice.<lang>.command) or "irodori" (Irodori-TTS-Custom, IRODORI_HOME). */
  engine?: string;
  /** Voice id in the engine (Irodori-TTS-Custom voices/<id>). */
  voice?: string;
  /** Copy of the voice in the package (tools/avatar/import_voice.py), relative to public/. */
  dir?: string;
}

export interface VoiceSettings {
  ja?: VoiceLang;
  en?: VoiceLang;
  /** Expression -> voice id (e.g. smile -> a brighter voice). */
  byExpression?: Record<string, string>;
  /** Expression -> emotion name of Irodori-TTS-Custom (--emotion). */
  emotion?: Record<string, string>;
  speed?: number;
  timing?: { lineGap?: number; sceneGap?: number; maxPause?: number };
}

export interface PersonaSettings {
  status?: ReviewStatus;
  firstPerson?: string;
  /** How the character's name is read (katakana), when the label is not read as written (毛の多いキャラ -> 毛の多いキャラ). */
  nameReading?: string;
  callsViewer?: string;
  endings?: string[];
  tone?: string;
  avoid?: string[];
  examples?: string[];
}

export interface ActingSettings {
  status?: ReviewStatus;
  /** The owner's words for the acting direction (read by the acting layer). */
  style?: string;
  gestureScale?: number;
  tempo?: number;
  beat?: { amp?: number; rate?: number };
  gestureWeights?: Record<string, number>;
  tiltRate?: number;
  blinkRate?: number;
}

export interface CaptureSettings {
  /** Background colour, hex without '#'. */
  bg?: string;
  /** Centre crop of the presenter video (fraction of its width). */
  crop?: number | null;
  /** Presenter height / top in the frame (fractions); null = layout.json. */
  ph?: number | null;
  py?: number | null;
  /** Bust framing of the small presenter window: vBustTop / Bot / W / X / Follow / Lag. */
  bust?: { top?: number; bot?: number; w?: number; x?: number; follow?: number; lag?: number };
  /** Light outline on the pale areas: colour (hex without '#'), the CIE L* from which a
   *  fill counts as pale, width in drawing px. Viewer URL vRim / vRimL / vRimW; null = off. */
  rim?: { color: string; minL?: number; width?: number } | null;
}

export interface AvatarPackage {
  schemaVersion?: number;
  rig?: RigSettings;
  voice?: VoiceSettings;
  persona?: PersonaSettings;
  acting?: ActingSettings;
  capture?: CaptureSettings;
}

type DeepRequired<T> = { [K in keyof T]-?: T[K] extends object | undefined ? (T[K] extends unknown[] | undefined ? NonNullable<T[K]> : DeepRequired<NonNullable<T[K]>>) : T[K] };

/** Defaults = the tools' behaviour before the package (tts.py, build_timeline.py, perform.py, simple_compose.py). */
export const PACKAGE_DEFAULTS = {
  rig: { hands: { type: "mitten" as HandType, scale: 1.0, shapeScale: {}, dropLines: [], unavailable: [], colors: {} }, rest: { upperArm: 70 }, turn: "parallax30" as TurnRange },
  voice: {
    ja: { engine: "files", voice: "" },
    en: { engine: "files", voice: "" },
    byExpression: {},
    emotion: {},
    speed: 1.0,
    timing: { lineGap: 0.28, sceneGap: 0.8, maxPause: 0 },
  },
  persona: { status: "draft" as ReviewStatus, firstPerson: "", nameReading: "", callsViewer: "", endings: [], tone: "", avoid: [], examples: [] },
  acting: { status: "draft" as ReviewStatus, style: "", gestureScale: 1.0, tempo: 1.0, beat: { amp: 1.0, rate: 1.0 }, gestureWeights: {}, tiltRate: 0.3, blinkRate: 1.0 },
  capture: { bg: "dde6f2", crop: null, ph: null, py: null, rim: null },
};

export type ResolvedPackage = DeepRequired<Omit<AvatarPackage, "schemaVersion">> & { schemaVersion: number };

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Fill missing fields from `base` (objects merge recursively; arrays and scalars replace). */
export function mergeDefaults<T>(base: T, over: unknown): T {
  if (!isPlainObject(base) || !isPlainObject(over)) return (over === undefined ? base : (over as T));
  const out: Record<string, unknown> = { ...base };
  for (const [k, v] of Object.entries(over)) {
    const b = (base as Record<string, unknown>)[k];
    // dictionaries keyed by free names (shapeScale, byExpression, ...) have an empty default: take them as they are
    out[k] = isPlainObject(b) && Object.keys(b).length > 0 ? mergeDefaults(b, v) : v;
  }
  return out as T;
}

/** The package with every default filled in. */
export function resolvePackage(cfg: AvatarPackage): ResolvedPackage {
  const r = mergeDefaults(PACKAGE_DEFAULTS, {
    rig: cfg.rig, voice: cfg.voice, persona: cfg.persona, acting: cfg.acting, capture: cfg.capture,
  }) as unknown as ResolvedPackage;
  r.schemaVersion = cfg.schemaVersion ?? 0;
  return r;
}

const HAND_TYPES: HandType[] = ["mitten", "beast", "human", "stick"];
const TURNS: TurnRange[] = ["front", "parallax30", "turn90", "turn90_opp"];

/** Light structural check (the full checker is id091). Returns problems as messages. */
export function validatePackage(cfg: AvatarPackage & { id?: string }): string[] {
  const errs: string[] = [];
  const v = cfg.schemaVersion;
  if (v !== undefined && (!Number.isInteger(v) || v < 0 || v > AVATAR_SCHEMA_VERSION)) errs.push(`schemaVersion ${v} is not supported`);
  const h = cfg.rig?.hands;
  if (h?.type !== undefined && !HAND_TYPES.includes(h.type)) errs.push(`rig.hands.type ${h.type}`);
  if (h?.scale !== undefined && !(h.scale > 0)) errs.push("rig.hands.scale must be > 0");
  if (cfg.rig?.turn !== undefined && !TURNS.includes(cfg.rig.turn)) errs.push(`rig.turn ${cfg.rig.turn}`);
  const ua = cfg.rig?.rest?.upperArm;
  if (ua !== undefined && !(ua >= 0 && ua <= 90)) errs.push("rig.rest.upperArm must be 0..90");
  for (const st of [cfg.persona?.status, cfg.acting?.status]) {
    if (st !== undefined && st !== "draft" && st !== "approved") errs.push(`status ${st}`);
  }
  const bg = cfg.capture?.bg;
  if (bg !== undefined && !/^[0-9a-fA-F]{6}$/.test(bg)) errs.push(`capture.bg ${bg}`);
  for (const k of ["crop", "ph", "py"] as const) {
    const x = cfg.capture?.[k];
    if (x !== undefined && x !== null && !(x > 0 && x <= 1)) errs.push(`capture.${k} must be in (0, 1]`);
  }
  return errs;
}
