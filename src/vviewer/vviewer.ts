// Minimal viewer for method V: one character, motions, face controls, lip-sync and PNG export.
// Depends only on src/core and src/renderers/vector (no Three.js), so it can be published alone.
import { parsePose, emptyPose, type Pose, type PoseJson } from "../core/pose";
import { composePose } from "../core/compose";
import {
  DEFAULT_FACE, EYE_STATES, MOUTH_SHAPES, EXPRESSIONS, EYE_LABEL, MOUTH_LABEL, EXPRESSION_LABEL,
  type FaceState,
} from "../core/face";
import type { CharacterConfig } from "../core/renderer";
import { Blinker } from "../core/blink";
import { parseMotion, samplePose, sampleFace, motionTime, type Motion, type MotionJson } from "../core/motion";
import { textToVisemes, mouthAt, type VisemeKey } from "../core/lipsync";
import { VectorRenderer } from "../renderers/vector/vectorRenderer";
import { HAND_PRESETS, DEFAULT_HAND, type HandPreset } from "../renderers/vector/outline";

/** Motions that need parts which are not published (turned body views). */
const HIDDEN_MOTION = /^turn_/;

const poseFiles = import.meta.glob("../../data/poses/*.json", { eager: true, import: "default" }) as Record<string, PoseJson>;
const charFiles = import.meta.glob("../../data/characters/*.json", { eager: true, import: "default" }) as Record<string, CharacterConfig>;
const motionFiles = import.meta.glob("../../data/motions/**/*.json", { eager: true, import: "default" }) as Record<string, MotionJson>;

export const MOTIONS: Record<string, Motion> = {};
for (const json of Object.values(motionFiles)) if (!HIDDEN_MOTION.test(json.name)) MOTIONS[json.name] = parseMotion(json);
export const POSES: Record<string, { label: string; pose: Pose }> = {};
for (const json of Object.values(poseFiles)) POSES[json.name!] = { label: json.description ?? json.name!, pose: parsePose(json) };
export const CHARACTERS: Record<string, CharacterConfig> = {};
for (const c of Object.values(charFiles)) if (c.vector) CHARACTERS[c.id] = c;

const SAY_PRESETS: Record<string, string> = {
  "": "なし",
  "あいうえお": "あいうえお",
  "こんにちは、きょうはよろしくおねがいします。": "こんにちは（あいさつ）",
  "このグラフを見てください。ここがポイントです。": "このグラフを見てください（解説）",
};

interface State {
  character: string;
  pose: string;
  motion: string;
  face: FaceState;
  autoBlink: boolean;
  say: string;
}

function stateFromUrl(): State {
  const q = new URLSearchParams(location.search);
  const num = (k: string, d: number) => (q.has(k) ? Number(q.get(k)) : d);
  return {
    character: q.get("char") ?? (CHARACTERS.usagi ? "usagi" : Object.keys(CHARACTERS)[0] ?? ""),
    pose: q.get("pose") ?? "attention",
    motion: q.get("motion") ?? "",
    face: {
      ...DEFAULT_FACE,
      yaw: num("yaw", 0), pitch: num("pitch", 0), roll: num("roll", 0),
      eye: (q.get("eye") as FaceState["eye"]) ?? "open",
      mouth: (q.get("mouth") as FaceState["mouth"]) ?? "sil",
      expression: (q.get("expr") as FaceState["expression"]) ?? "neutral",
    },
    autoBlink: q.get("blink") !== "0",
    say: q.get("say") ?? "",
  };
}

interface Els { controls: HTMLElement; preview: HTMLElement; status: HTMLElement; statusText: HTMLElement; caption: HTMLElement }

export class VViewer {
  state = stateFromUrl();
  ready = false;
  private renderer: VectorRenderer | null = null;
  private loadToken = 0;
  private blinker = new Blinker({ seed: 7 });
  /** mouth track: from text (looped) or from a lip-sync JSON (with optional audio) */
  private visemes: VisemeKey[] = [];
  private sayLoop = 0;
  private audio: HTMLAudioElement | null = null;
  /** Fixed time for capture (seconds); null = real time. */
  private timeOverride: number | null = null;
  private playing = true;
  private playStart = 0;
  private seek = 0;
  private lastTime = 0;
  private seekEl: HTMLInputElement | null = null;

  constructor(private els: Els) {
    this.buildControls();
    this.setSay(this.state.say);
    const q = new URLSearchParams(location.search);
    const ls = q.get("lipsync");
    if (ls) void fetch(ls).then((r) => r.json()).then((j) => this.setLipsync(j));
    if (q.has("t")) this.timeOverride = Number(q.get("t"));
    void this.load();
    const loop = (t: number) => {
      this.frame(this.timeOverride ?? t / 1000);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  /** Freeze the animation clock (frame capture) and draw immediately. */
  setTime(t: number | null) {
    this.timeOverride = t;
    if (t !== null) this.frame(t);
  }

  renderNow(time = 0) { this.frame(time); }

  /** Length of the selected motion in seconds (0 = static pose). Used by tools/vector/record.mjs. */
  motionDuration(): number { return MOTIONS[this.state.motion]?.duration ?? 0; }

  setSay(text: string) {
    this.state.say = text;
    this.visemes = text ? textToVisemes(text) : [];
    this.sayLoop = this.visemes.length ? this.visemes[this.visemes.length - 1].t + 0.6 : 0;
  }

  /** Lip-sync JSON written by tools/lipsync/align.py: {"keys": [{"t", "mouth"}], "duration"} */
  setLipsync(j: { keys: VisemeKey[]; duration: number }) {
    this.visemes = j.keys;
    this.sayLoop = j.duration + 0.5;
  }

  private setStatus(kind: "ok" | "warn" | "error", text: string) {
    this.els.status.dataset.state = kind === "ok" ? "" : "warn";
    this.els.statusText.textContent = text;
  }

  async load(): Promise<void> {
    const token = ++this.loadToken;
    this.ready = false;
    this.renderer?.dispose();
    this.renderer = null;
    this.els.preview.innerHTML = "";
    const character = CHARACTERS[this.state.character];
    if (!character) {
      this.setStatus("error", "! キャラが見つかりません");
      this.els.preview.innerHTML = `<div class="empty">data/characters/ に "vector" を持つキャラがありません。</div>`;
      return;
    }
    this.setStatus("warn", "◷ 読み込み中");
    const r = new VectorRenderer();
    const rect = this.els.preview.getBoundingClientRect();
    const q = new URLSearchParams(location.search);
    try {
      await r.init({
        container: this.els.preview, character,
        width: Math.round(rect.width) || 960, height: Math.round(rect.height) || 540,
        framing: q.get("framing") === "face" ? "face" : "body", debug: q.has("debug"),
      });
    } catch (e) {
      console.error(e);
      this.setStatus("error", "! 読み込みに失敗しました");
      return;
    }
    if (token !== this.loadToken) { r.dispose(); return; }
    this.renderer = r;
    this.ready = true;
    this.setStatus("ok", character.label);
    this.els.caption.textContent = `${character.label}／${MOTIONS[this.state.motion]?.label ?? POSES[this.state.pose]?.label ?? ""}`;
  }

  private motionClock(time: number): number {
    if (this.timeOverride !== null) return time;
    return this.playing ? time - this.playStart : this.seek;
  }

  private faceAt(t: number, clock: number): FaceState {
    const m = MOTIONS[this.state.motion];
    const f = m ? sampleFace(m, t, {}, { ...this.state.face }) : { ...this.state.face };
    if (this.state.autoBlink && f.eye === "open") f.eye = this.blinker.eyeAt(clock);
    if (this.visemes.length) {
      // with audio playing, follow the audio clock; otherwise loop the track
      const a = this.audio;
      f.mouth = a && !a.paused ? mouthAt(this.visemes, a.currentTime) : mouthAt(this.visemes, clock, this.sayLoop);
    }
    return f;
  }

  private frame(time: number) {
    const r = this.renderer;
    if (!r) return;
    this.lastTime = time;
    const m = MOTIONS[this.state.motion];
    const mt = this.motionClock(time);
    const body = m ? samplePose(m, mt) : POSES[this.state.pose]?.pose ?? emptyPose();
    const face = this.faceAt(mt, m ? mt : time);
    if (m && this.seekEl && this.playing && this.timeOverride === null) this.seekEl.value = String(motionTime(m, mt));
    r.setPose(composePose(body, face));
    r.setFace(face);
    r.render(time);
  }

  savePng(): void {
    if (!this.renderer) return;
    const f = this.state.face;
    const a = document.createElement("a");
    a.href = this.renderer.canvas.toDataURL("image/png");
    a.download = `${this.state.character}_${this.state.motion || this.state.pose}_yaw${f.yaw}_${f.expression}.png`;
    a.click();
  }

  private buildControls() {
    const c = this.els.controls;
    c.innerHTML = "";
    const group = (label: string, el: HTMLElement, parent: HTMLElement = c) => {
      const g = document.createElement("div");
      g.className = "control-group";
      const l = document.createElement("div");
      l.className = "label";
      l.textContent = label;
      g.append(l, el);
      parent.appendChild(g);
    };
    const seg = <T extends string>(items: [T, string][], get: () => T, set: (v: T) => void) => {
      const box = document.createElement("div");
      box.className = "seg";
      box.setAttribute("role", "group");
      const refresh = () => box.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === get())));
      for (const [v, label] of items) {
        const b = document.createElement("button");
        b.type = "button"; b.dataset.v = v; b.textContent = label;
        b.onclick = () => { set(v); refresh(); };
        box.appendChild(b);
      }
      refresh();
      return box;
    };
    const select = (items: [string, string][], get: () => string, set: (v: string) => void) => {
      const s = document.createElement("select");
      for (const [v, label] of items) s.add(new Option(label, v));
      s.value = get();
      s.onchange = () => set(s.value);
      return s;
    };
    const slider = (min: number, max: number, get: () => number, set: (v: number) => void, unit = "°") => {
      const wrap = document.createElement("div");
      const r = document.createElement("input");
      r.type = "range"; r.min = String(min); r.max = String(max); r.step = "1"; r.value = String(get());
      const out = document.createElement("span");
      out.className = "caption";
      const upd = () => { out.textContent = `${r.value}${unit}`; };
      r.oninput = () => { set(Number(r.value)); upd(); };
      upd();
      wrap.append(r, out);
      return wrap;
    };
    const s = this.state;
    const restart = () => { this.playStart = this.lastTime; this.seek = 0; this.playing = true; };

    if (Object.keys(CHARACTERS).length > 1) {
      group("キャラ", select(Object.values(CHARACTERS).map((x) => [x.id, x.label]), () => s.character, (v) => { s.character = v; void this.load(); }));
    }
    // motion + play / seek
    const motionBox = document.createElement("div");
    const msel = select([["", "なし（静止ポーズ）"], ...Object.values(MOTIONS).map((m) => [m.name, m.label] as [string, string])], () => s.motion, (v) => {
      s.motion = v; restart(); updSeek(); updPlay();
    });
    const row = document.createElement("div");
    row.className = "seg";
    row.style.marginTop = "8px";
    const play = document.createElement("button");
    play.type = "button";
    const updPlay = () => { play.textContent = this.playing ? "一時停止" : "再生"; play.setAttribute("aria-pressed", String(this.playing)); };
    play.onclick = () => {
      if (this.playing) { this.seek = this.lastTime - this.playStart; this.playing = false; }
      else { this.playStart = this.lastTime - this.seek; this.playing = true; }
      updPlay();
    };
    const seekEl = document.createElement("input");
    seekEl.type = "range"; seekEl.min = "0"; seekEl.step = "0.01"; seekEl.style.flex = "1";
    seekEl.setAttribute("aria-label", "再生位置");
    seekEl.oninput = () => { this.playing = false; this.seek = Number(seekEl.value); updPlay(); };
    const updSeek = () => { const m = MOTIONS[s.motion]; seekEl.max = String(m?.duration ?? 1); seekEl.disabled = !m; };
    this.seekEl = seekEl;
    row.append(play, seekEl);
    motionBox.append(msel, row);
    updPlay(); updSeek();
    group("モーション", motionBox);
    group("ポーズ（モーションなしのとき）", select(Object.entries(POSES).map(([k, p]) => [k, p.label]), () => s.pose, (v) => { s.pose = v; }));

    group("顔の左右", slider(-30, 30, () => s.face.yaw, (v) => { s.face.yaw = v; }));
    group("顔の上下", slider(-20, 20, () => s.face.pitch, (v) => { s.face.pitch = v; }));
    group("首の傾き", slider(-20, 20, () => s.face.roll, (v) => { s.face.roll = v; }));
    group("目", seg(EYE_STATES.map((e) => [e, EYE_LABEL[e]]), () => s.face.eye, (v) => { s.face.eye = v; }));
    group("口", seg(MOUTH_SHAPES.map((m) => [m, MOUTH_LABEL[m]]), () => s.face.mouth, (v) => { s.face.mouth = v; }));
    group("表情", seg(EXPRESSIONS.map((x) => [x, EXPRESSION_LABEL[x]]), () => s.face.expression, (v) => { s.face.expression = v; }));
    group("自動まばたき", seg([["off", "しない"], ["on", "する"]] as ["off" | "on", string][], () => (s.autoBlink ? "on" : "off"), (v) => { s.autoBlink = v === "on"; }));

    // lip-sync: text preset, or a JSON track (+ optional audio) from tools/lipsync/align.py
    group("口パク（テキスト）", select(Object.entries(SAY_PRESETS), () => s.say, (v) => this.setSay(v)));
    const files = document.createElement("div");
    files.className = "file-row";
    const lsIn = document.createElement("input");
    lsIn.type = "file"; lsIn.accept = ".json,application/json";
    lsIn.setAttribute("aria-label", "口パクの JSON");
    const auIn = document.createElement("input");
    auIn.type = "file"; auIn.accept = "audio/*";
    auIn.setAttribute("aria-label", "音声ファイル");
    const note = document.createElement("p");
    note.className = "caption";
    note.textContent = "上：口パクの JSON、下：音声（任意）。音声を選ぶと最初から再生します。";
    lsIn.onchange = async () => {
      const f = lsIn.files?.[0];
      if (f) this.setLipsync(JSON.parse(await f.text()));
    };
    auIn.onchange = () => {
      const f = auIn.files?.[0];
      this.audio?.pause();
      if (!f) { this.audio = null; return; }
      this.audio = new Audio(URL.createObjectURL(f));
      restart(); updPlay();
      void this.audio.play();
    };
    files.append(lsIn, auIn, note);
    group("口パク（ファイル）", files);

    // outline options of method V (applied live)
    const more = document.createElement("details");
    more.className = "more";
    const sum = document.createElement("summary");
    sum.textContent = "線と動きの設定";
    more.appendChild(sum);
    const opt = () => this.renderer?.opt;
    const toggles: [string, () => boolean, (v: boolean) => void][] = [
      ["自動輪郭線", () => opt()?.outline.enabled ?? true, (v) => { const o = opt(); if (o) o.outline.enabled = v; }],
      ["外側の輪郭線", () => opt()?.outline.outer ?? false, (v) => { const o = opt(); if (o) o.outline.outer = v; }],
      ["揺れ物", () => opt()?.physics ?? true, (v) => { const o = opt(); if (o) o.physics = v; }],
      ["手の遅れ", () => opt()?.handLag ?? true, (v) => { const o = opt(); if (o) o.handLag = v; }],
    ];
    const tbox = document.createElement("div");
    tbox.className = "seg";
    for (const [label, get, set] of toggles) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label;
      const upd = () => b.setAttribute("aria-pressed", String(get()));
      b.onclick = () => { set(!get()); upd(); };
      upd();
      tbox.appendChild(b);
    }
    group("オン・オフ", tbox, more);
    group("線の太さ", slider(0, 8, () => opt()?.outline.width ?? 3, (v) => { const o = opt(); if (o) o.outline.width = v; }, "px"), more);
    type HandSel = "off" | HandPreset;
    // same reading of ?vHand= as outline.ts handFromQuery (index or name)
    const hv = new URLSearchParams(location.search).get("vHand");
    const handNames: HandSel[] = ["off", "weak", "mid", "strong", "sketch"];
    let hand: HandSel = hv == null ? DEFAULT_HAND : (handNames[Number(hv)] ?? (hv in HAND_PRESETS ? (hv as HandSel) : "off"));
    group("手描き風の線", seg<HandSel>([["off", "なし"], ["weak", "弱"], ["mid", "中"], ["strong", "強"], ["sketch", "手描き＋"]],
      () => hand, (v) => { hand = v; const o = opt(); if (o) o.outline.hand = v === "off" ? null : { ...HAND_PRESETS[v] }; }), more);
    c.appendChild(more);

    const save = document.createElement("button");
    save.type = "button";
    save.className = "btn-primary";
    save.textContent = "PNG で保存";
    save.onclick = () => this.savePng();
    c.appendChild(save);
  }
}
