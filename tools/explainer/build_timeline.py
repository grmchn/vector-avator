"""Timeline for the explainer video: narration track, lip-sync keys and the presenter's motion.

Usage: .venv/bin/python tools/explainer/build_timeline.py <ja|en> [--takes L03=2,L07=2]
       .venv/bin/python tools/explainer/build_timeline.py ja --content data/explainer/samples/<id> --avatar <char>
         (the three-layer data; the acting layer (perform.act) turns the tags into gestures with
          the character's habits, and the rest pose, gaps, pauses and beats come from the avatar
          package. Audio: var/explainer/audio/<content>/<char>/ from tts.py --content/--avatar.)

Inputs : --content <folder> --avatar <char> (or --script), var/explainer/audio/<lang>/<id>_t<take>.wav
Outputs: var/explainer/public/<lang>/narration.wav    (48 kHz mono, for Remotion)
         var/explainer/public/<lang>/timeline.json    (line start/end, scenes, total)
         public/audio/explainer_<lang>.json           (lip-sync keys for the viewer, ?lipsync=)
         data/motions/explainer/explainer_<lang>.json (presenter motion: existing gestures spliced in time)
"""
import argparse, json, random, subprocess, sys, wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/lipsync"))
from align import morae  # noqa: E402  (kana -> mouth shapes)
sys.path.insert(0, str(ROOT / "tools/explainer"))
import layout as LAYOUT  # noqa: E402
import perform  # noqa: E402  (acting layer, G12)
import bust as BUST  # noqa: E402  (bust framing acting)
import beats as BEATS  # noqa: E402  (beat gestures)
import beeps as BEEPS  # noqa: E402  (TTS edge-beep cleanup)

SR = 48000
LEAD, GAP, SCENE_GAP, TAIL = 0.7, 0.28, 0.8, 2.2   # scene gap 0.55 -> 0.8
ACTING = "point,beats,vary,pause,body,sway,weight,eyes"   # defaults (owner 2026-11-22; body, sway: id101 / M15;
#   weight, eyes: id121 / M16, M17); "none" = as id057/id089
GESTURE_EXPR = {"surprise"}   # gestures whose own expression keys are kept (none with the feature "eyes")
REST = {"leftUpperArm": [0, 0, -70], "leftLowerArm": [0, 0, -5], "leftHand": [0, 0, 0],
        "rightUpperArm": [0, 0, 70], "rightLowerArm": [0, 0, 5], "rightHand": [0, 0, 0],
        "head": [0, 0, 0], "neck": [0, 0, 0], "chest": [0, 0, 0], "spine": [0, 0, 0]}
GESTURES = {"spread": "spread", "nod": "nod_surprise", "surprise": "nod_surprise", "explain": "explain",
            "point": "point", "think": "think"}


def load_wav(path):
    """Decode any WAV to 48 kHz mono float32 with ffmpeg."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def trim(x, thr_db=-42.0, pad=0.04):
    """Cut leading/trailing silence (20 ms RMS frames below thr_db)."""
    hop = int(SR * 0.02)
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    on = np.where(20 * np.log10(rms) > thr_db)[0]
    if len(on) == 0:
        return x
    a = max(0, on[0] * hop - int(pad * SR)); b = min(len(x), (on[-1] + 1) * hop + int(pad * SR))
    return x[a:b]


def cap_pauses(x, max_pause, thr_db=-40.0, fade=0.01):
    """Shorten silent gaps inside a line to max_pause seconds (cross-faded), keeping the speech untouched."""
    hop = int(SR * 0.01)
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    quiet = 20 * np.log10(rms) < thr_db
    keep, i, out = int(max_pause / 0.01), 0, []
    pos = 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]: j += 1
            if j - i > keep and i > 0 and j < n:
                a, b = i * hop + keep // 2 * hop, j * hop - keep // 2 * hop
                out.append(x[pos:a]); pos = b
            i = j
        else:
            i += 1
    out.append(x[pos:])
    f = int(fade * SR)
    for k in range(1, len(out)):  # short fades at the cuts (they sit in silence anyway)
        if len(out[k - 1]) > f: out[k - 1][-f:] *= np.linspace(1, 0, f)
        if len(out[k]) > f: out[k][:f] *= np.linspace(0, 1, f)
    return np.concatenate(out)


def speedup(x, rate):
    """Time-compress a clip (float32, SR Hz) by `rate` with ffmpeg's atempo (pitch kept)."""
    if abs(rate - 1.0) < 1e-3:
        return x
    raw = np.clip(x, -1, 1).astype("<f4").tobytes()
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-af", f"atempo={rate:.4f}", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-"],
                       input=raw, capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype="<f4").astype(np.float32)


def voiced_spans(x, t0, thr_db=-34.0, min_gap=0.09):
    hop = int(SR * 0.01)
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    peak = 20 * np.log10(np.percentile(rms, 95))
    on = 20 * np.log10(rms) > max(thr_db, peak - 26)
    spans, s = [], None
    for i, v in enumerate(on):
        if v and s is None: s = i
        if not v and s is not None: spans.append([s, i]); s = None
    if s is not None: spans.append([s, n])
    merged = []
    for a, b in spans:
        if merged and (a - merged[-1][1]) * 0.01 < min_gap: merged[-1][1] = b
        else: merged.append([a, b])
    return [(t0 + a * 0.01, t0 + b * 0.01) for a, b in merged if (b - a) * 0.01 > 0.05]


def en_shapes(text):
    """Very rough English mouth shapes: one per vowel group of each word."""
    import re
    out = []
    for w in re.findall(r"[a-zA-Z']+|\d", text.lower()):
        groups = re.findall(r"[aeiouy]+", w) or ["e"]
        for g in groups:
            c = g[0]
            out.append({"a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "y": "i"}[c])
        if re.search(r"[mbp]$", w): out.append("sil")
    return out


def distribute(shapes, spans, min_len=0.06):
    keys = []
    total = sum(b - a for a, b in spans) or 1
    rest = list(shapes)
    for i, (a, b) in enumerate(spans):
        share = len(shapes) * (b - a) / total
        k = max(1, round(share)) if i < len(spans) - 1 else max(1, len(rest))
        part, rest = rest[:k], rest[k:]
        if not part: part = ["a"]
        step = max(min_len, (b - a) / len(part))
        for j, m in enumerate(part):
            t = a + j * step
            if t < b: keys.append({"t": round(t, 3), "mouth": m})
        keys.append({"t": round(b, 3), "mouth": "sil"})
    return keys


def scale_bones(bones, amp):
    """Gesture size: rotations scaled around the rest pose (REST; other bones around 0)."""
    out = {}
    for b, v in bones.items():
        if not isinstance(v, list):   # quaternion keys of the MotionBricks variants ({"q": ...}): kept as they are
            out[b] = v
            continue
        r = REST.get(b, [0, 0, 0])
        out[b] = [round(r[i] + (v[i] - r[i]) * amp, 2) for i in range(3)]
    return out


def gesture_keys(name, t0, window, variant=None, rng=None, amp=1.0, tempo=1.0):
    """Keys of an existing gesture (or a synthetic one), shifted to t0 and squeezed into the window.
    variant: a motion of data/motions/explainer_vocab/ to use instead; rng: jitter its keys.
    amp / tempo (the character's acting habits): size around the rest pose, speed."""
    if name == "idle":
        return []
    if name == "turn":
        d = min(window, 4.0)
        return [{"t": t0, "face": {"yaw": 0}}, {"t": t0 + d * 0.3, "face": {"yaw": -28}},
                {"t": t0 + d * 0.45, "face": {"yaw": -28}}, {"t": t0 + d * 0.75, "face": {"yaw": 28}},
                {"t": t0 + d * 0.88, "face": {"yaw": 28}}, {"t": t0 + d, "face": {"yaw": 0}}]
    m = json.load(open(ROOT / (f"data/motions/explainer_vocab/{variant}.json" if variant else f"data/motions/{GESTURES[name]}.json")))
    if rng is not None:
        m["keys"] = perform.jitter(m["keys"], rng)
    scale = min(1.0, max(0.7, window / m["duration"]))
    if tempo != 1.0:
        scale = max(0.5, scale / tempo)
    keys = []
    for k in m["keys"]:
        k = json.loads(json.dumps(k))
        if "face" in k:
            k["face"].pop("mouth", None)
            if name not in GESTURE_EXPR: k["face"].pop("expression", None)
            if not k["face"]: k.pop("face")
        k["t"] = round(t0 + k["t"] * scale, 3)
        if amp != 1.0 and "bones" in k:
            k["bones"] = scale_bones(k["bones"], amp)
        keys.append(k)
    if BUST_LIFT and name not in ("think", "idea", "nod", "point"):
        keys = BUST.lift_arms(keys, BUST_LIFT)   # gesture hands rise into the bust window
    return keys


BUST_LIFT = 0.0   # rest angle of the upper arms when the bust framing lifts the gestures (set in main)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lang", choices=["ja", "en"])
    ap.add_argument("--takes", default="")
    ap.add_argument("--audio-dir", default="", help="folder under var/explainer/audio (default: the language)")
    ap.add_argument("--max-pause", type=float, default=None, help="cap silent gaps inside a line (s); 0 = keep (default 0 or the package's voice.timing.maxPause)")
    ap.add_argument("--script", default="", help="script JSON in the build form (relative to the project root); normally --content and --avatar")
    ap.add_argument("--name", default="explainer", help="output name: public/audio/<name>_<lang>.json, data/motions/explainer/<name>_<lang>.json")
    ap.add_argument("--audio-root", default="var/explainer/audio", help="folder that holds <audio-dir>/<id>_t<take>.wav")
    ap.add_argument("--pub-dir", default="", help="Remotion public folder (default: var/explainer/public/<lang>)")
    ap.add_argument("--rest-upper", type=float, default=None, help="upper-arm angle of the rest pose (deg down from horizontal; default 70 or the package's rig.rest.upperArm)")
    ap.add_argument("--layout", default="", help="screen layout (default tools/explainer/layout.json)")
    ap.add_argument("--acting", default=ACTING, help="acting features of G12, comma-separated: point, beats, "
                    "vary / pause, body (a slight body turn), sway (small head turns and tilts), "
                    "weight (the weight moves from foot to foot every few seconds, M16), eyes (neutral eyes most of the time, "
                    "a smile only at the end of a line, surprise / trouble only at its start, M17); 'none' = as id057/id089 (then also --scene-gap 0.55)")
    ap.add_argument("--char", default="", help="character id for the acting habits (avatar package acting.beat); default: --avatar, then --name")
    ap.add_argument("--beat-level", default="mid", choices=list(BEATS.LEVELS), help="beats: off / weak / mid / strong")
    ap.add_argument("--beat-lead", type=float, default=0.12, help="beats: how much the beat leads the voice (s)")
    ap.add_argument("--seed", type=int, default=98, help="vary / pause: random seed (the same seed gives the same motion)")
    ap.add_argument("--gap", type=float, default=None, help="silence between lines of the same scene (s; default GAP or the package's)")
    ap.add_argument("--scene-gap", type=float, default=None, help="silence at a scene change (s; default SCENE_GAP or the package's)")
    ap.add_argument("--content", default="", help="a content folder of the three-layer data (content.json + script.<avatar>.json)")
    ap.add_argument("--avatar", default="", help="character id; its avatar package gives the voice timing, rest pose, habits")
    ap.add_argument("--keep-beeps", action="store_true", help="keep the TTS edge beeps (default: mute them, tools/explainer/beeps.py)")
    ap.add_argument("--speedup", type=float, default=1.0, help="time-compress every line by this factor after synthesis (1.0 = off; 1.2 = a fast news read)")
    ap.add_argument("--point-brief", type=float, default=0.8, help="point only briefly (hold this many seconds, a short glance), "
                    "then the line's own gesture to the camera (default, M15); 0 = point through the whole line")
    ap.add_argument("--sway-yaw", type=float, default=7.0, help="sway: largest head turn of the sway (deg)")
    ap.add_argument("--sway-roll", type=float, default=4.0, help="sway: largest head tilt of the sway (deg)")
    ap.add_argument("--body-max", type=float, default=15.0, help="body: largest body turn in degrees (the acting feature 'body')")
    ap.add_argument("--lead", type=float, default=None, help="seconds before the first line (default LEAD), e.g. room for an intro clip")
    ap.add_argument("--extra-gaps", default="", help="extra silence before some lines, e.g. L15=1.5,L23=0.6 (s)")
    ap.add_argument("--act-seed", type=int, default=94, help="seed of the acting layer's gesture choice")
    a = ap.parse_args()
    pkg = None
    if a.avatar:
        sys.path.insert(0, str(ROOT / "tools/avatar"))
        import package as PKG  # noqa: E402
        pkg = PKG.load(a.avatar)
        tm = pkg["voice"]["timing"]
        a.rest_upper = pkg["rig"]["rest"]["upperArm"] if a.rest_upper is None else a.rest_upper
        a.gap = tm["lineGap"] if a.gap is None else a.gap
        a.scene_gap = tm["sceneGap"] if a.scene_gap is None else a.scene_gap
        a.max_pause = tm["maxPause"] if a.max_pause is None else a.max_pause
        a.char = a.char or a.avatar
    a.rest_upper = 70.0 if a.rest_upper is None else a.rest_upper
    a.gap = GAP if a.gap is None else a.gap
    a.scene_gap = SCENE_GAP if a.scene_gap is None else a.scene_gap
    a.max_pause = 0.0 if a.max_pause is None else a.max_pause
    acting = set(x for x in a.acting.split(",") if x and x != "none")
    if "eyes" in acting:
        GESTURE_EXPR.clear()   # the surprise gesture's own surprised face would outlast the accent
    global BUST_LIFT
    BUST_LIFT = a.rest_upper if "bust" in acting else 0.0
    lay = LAYOUT.load(a.layout or None)
    rest = json.loads(json.dumps(REST))
    rest["leftUpperArm"][2], rest["rightUpperArm"][2] = -a.rest_upper, a.rest_upper
    takes = dict(kv.split("=") for kv in a.takes.split(",") if kv)
    if a.content:
        if not pkg:
            raise SystemExit("--content needs --avatar (the script layer is per character)")
        import explainer_format as EF  # noqa: E402
        content, scripts = EF.load_dir(ROOT / a.content)
        if a.avatar not in scripts:
            raise SystemExit(f"no script.{a.avatar}.json in {a.content}")
        script = perform.act(content, scripts[a.avatar], pkg, a.act_seed)
        # the line's own tags (not the ones on a term): the bust prop follows the line's meaning
        line_tags = {cl["id"]: [x["tag"] for x in EF.line_tags(cl)] for cl in content["lines"]}
        tag = f"{content['id']}_{a.avatar}"
        if a.name == "explainer":
            a.name = tag
        a.audio_dir = a.audio_dir or f"{content['id']}/{a.avatar}"
        a.pub_dir = a.pub_dir or f"var/explainer/public/{tag}/{a.lang}"
        perf = ROOT / a.pub_dir / "performed.json"
        perf.parent.mkdir(parents=True, exist_ok=True)
        perf.write_text(json.dumps(script, ensure_ascii=False, indent=1))
    else:
        script = json.load(open(ROOT / a.script))
        line_tags = {}
    lines = script["lines"]
    def clean(x):  # mute the TTS's stray edge beeps before trimming (they read as a sound effect)
        return x if a.keep_beeps else BEEPS.mute(x, BEEPS.find_beeps(x))
    clips = [(lambda x: speedup(cap_pauses(x, a.max_pause) if a.max_pause > 0 else x, a.speedup))(trim(clean(load_wav(ROOT / f"{a.audio_root}/{a.audio_dir or a.lang}/{l['id']}_t{takes.get(l['id'], '1')}.wav")))) for l in lines]
    habits = perform.habits_for(a.char or a.name)
    extra = {k: float(v) for k, v in (kv.split("=") for kv in a.extra_gaps.split(",") if kv)}
    t, out, tl, lips, beat_info = (LEAD if a.lead is None else a.lead), [], [], [], []
    for i, (l, x) in enumerate(zip(lines, clips)):
        if i > 0:
            t += a.scene_gap if l["scene"] != lines[i - 1]["scene"] else a.gap
        t += extra.get(l["id"], 0.0)
        start, end = t, t + len(x) / SR
        tl.append({"id": l["id"], "scene": l["scene"], "start": round(start, 3), "end": round(end, 3),
                   "text": l[a.lang], "gesture": l["gesture"], "expr": l["expr"], "icon": l.get("icon", ""),
                   "point_at": l.get("point_at", "")})
        if a.content:   # the acting fields (size, tempo, fixed variation) and the card text
            tl[-1].update({k: l[k] for k in ("card_text", "scale", "tempo", "voice") if k in l})
            if l.get("variant"):
                tl[-1]["fixed_variant"] = l["variant"]
        shapes = morae(l["ja_kana"]) if a.lang == "ja" else en_shapes(l["en_tts"])
        spans = voiced_spans(x, start)
        lips += distribute(shapes, spans)
        if "beats" in acting:
            emph = BEATS.emphasis_ranges(l, spans) if a.lang == "ja" else []
            beat_info.append(BEATS.candidates(x, start, spans, emph))
        out.append((start, x))
        t = end
    total = round(t + TAIL, 3)
    audio = np.zeros(int(total * SR) + 1, dtype=np.float32)
    for s, x in out:
        i = int(round(s * SR)); audio[i:i + len(x)] += x
    peak = float(np.max(np.abs(audio))) or 1.0
    audio *= min(1.0, 0.89 / peak)
    pub = ROOT / (a.pub_dir or f"var/explainer/public/{a.lang}")
    pub.mkdir(parents=True, exist_ok=True)
    raw = pub / "narration_raw.wav"
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    # same loudness for both languages (SNS players: about -16 LUFS)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", str(SR), "-ac", "1", str(pub / "narration.wav")], check=True)
    raw.unlink()
    (pub / "timeline.json").write_text(json.dumps({"lang": a.lang, "total": total, "lines": tl}, ensure_ascii=False, indent=1))
    lips_path = ROOT / f"public/audio/{a.name}_{a.lang}.json"
    lips_path.parent.mkdir(parents=True, exist_ok=True)
    lips_path.write_text(json.dumps({"keys": [{"t": 0, "mouth": "sil"}] + lips, "duration": total}))
    # presenter motion
    keys = [{"t": 0, "bones": rest, "hips": [0, 0, 0], "face": {"yaw": 0, "pitch": 0, "expression": "smile"},
             "hands": {"L": "open", "R": "open"}}]
    props = {}
    if "bust" in acting or "props" in acting:
        for l in tl:
            kind = BUST.prop_kind(line_tags.get(l["id"], []))
            if kind:
                props[l["id"]] = kind
        posed = BUST.pose_runs([l["id"] for l in tl], props)
        for l in tl:
            if "bust" in acting and l["id"] in posed and not l["point_at"]:
                l["gesture"], l["fixed_variant"] = BUST.GESTURE[props[l["id"]]]
    card_x = lay["card"]["cx"] - lay["presenter"]["cx"]
    quiet = []   # windows where the head must not sway (glances at the figure, pause acts)
    chooser = perform.GestureChooser(random.Random(a.seed), {"point": "L" if card_x > 0 else "R"})
    jrng = random.Random(a.seed + 1)
    for i, l in enumerate(tl):
        nxt = tl[i + 1]["start"] if i + 1 < len(tl) else total
        g0 = max(0.0, l["start"] - 0.15)
        if "eyes" in acting:
            keys += perform.expression_keys(l, g0, nxt)
        else:
            keys.append({"t": round(g0, 3), "face": {"expression": l["expr"]}})
        l["variant"], l["side"] = "", ""
        if "point" in acting and l["point_at"] and a.point_brief > 0:
            # a short point and glance, then the line's own gesture toward the camera
            pk, t_pe, qw = perform.point_brief_keys(l["point_at"], g0, nxt - 0.15, lay, hold=a.point_brief)
            keys += pk
            quiet.append(qw)
            l["point_end"] = round(t_pe, 3)
            g = l["gesture"] if l["gesture"] != "point" else "explain"
            t1, win = t_pe + 0.1, nxt - t_pe - 0.2
            if win >= 1.4 and g in perform.VOCAB:
                if l.get("fixed_variant"):
                    l["variant"] = l["fixed_variant"]
                    l["side"] = dict(perform.VOCAB.get(g, [])).get(l["variant"], "")
                elif "vary" in acting:
                    l["variant"], l["side"] = chooser.choose(g)
                keys += gesture_keys(g, t1, win, l["variant"] or None, jrng, l.get("scale", 1.0), l.get("tempo", 1.0))
        elif "point" in acting and l["point_at"]:
            keys += perform.point_keys(l["point_at"], g0, l["end"], nxt - 0.15, lay)
        elif l.get("fixed_variant"):   # the tag asks for one variation (question -> nod_tilt)
            l["variant"] = l["fixed_variant"]
            l["side"] = dict(perform.VOCAB.get(l["gesture"], [])).get(l["variant"], "")
            keys += gesture_keys(l["gesture"], g0, nxt - g0 - 0.1, l["variant"], jrng, l.get("scale", 1.0), l.get("tempo", 1.0))
        elif "vary" in acting and l["gesture"] in perform.VOCAB:
            l["variant"], l["side"] = chooser.choose(l["gesture"])
            keys += gesture_keys(l["gesture"], g0, nxt - g0 - 0.1, l["variant"], jrng, l.get("scale", 1.0), l.get("tempo", 1.0))
        else:
            keys += gesture_keys(l["gesture"], g0, nxt - g0 - 0.1, amp=l.get("scale", 1.0), tempo=l.get("tempo", 1.0))
    keys.append({"t": total, "bones": rest, "face": {"yaw": 0, "expression": "smile"}})
    if props:
        keys = BUST.merge_face_keys(keys, BUST.prop_keys(tl, props))
    additive, beat_log = [], []
    if "beats" in acting:
        for i, l in enumerate(tl):
            nxt = tl[i + 1]["start"] if i + 1 < len(tl) else total
            g0 = max(0.0, l["start"] - 0.15)
            g = "point" if ("point" in acting and l["point_at"]) else l["gesture"]
            # busy: the big strokes of the gesture (going out and coming back)
            busy = [(g0, g0 + 0.6), (nxt - 0.65, nxt)]
            if l.get("point_end"):   # the short point, then the line's own gesture
                g = l["gesture"] if l["gesture"] != "point" else "explain"
                busy = [(g0, l["point_end"] + 0.6), (nxt - 0.65, nxt)]
            chosen = BEATS.select(beat_info[i], l["start"], l["end"], a.beat_level, busy, habits["beat_rate"])
            amp = BEATS.LEVELS[a.beat_level]["amp"] * habits["beat_amp"]
            additive += perform.beat_keys(chosen, perform.beat_parts(g, l["side"]), amp, lead=a.beat_lead)
            beat_log.append((l["id"], [round(c["t"], 2) for c in chosen]))
    if "pause" in acting:
        pk = perform.pause_keys(tl, total, lay, random.Random(a.seed + 2), pointing="point" in acting,
                                brief_points=a.point_brief > 0)
        additive += pk
        # the face acts of the pauses (glance, tilt) are quiet windows for the head sway
        ft = sorted(k["t"] for k in pk if "face" in k)
        for t in ft:
            if quiet and quiet[-1][1] >= t - 1.0 and quiet[-1][2:] == ("p",):
                quiet[-1] = (quiet[-1][0], t, "p")
            else:
                quiet.append((t, t, "p"))
    if "sway" in acting:
        additive += perform.sway_keys(tl, total, random.Random(a.seed + 4), a.sway_yaw, a.sway_roll,
                                      [(q[0], q[1]) for q in quiet])
    roll_track = None
    if "weight" in acting:   # id121 (M16, M21): weight shifts; the hips bone's tilt goes with the body turn
        wk, roll_track = perform.weight_keys(tl, total, random.Random(a.seed + 5))
        additive += wk
    if "body" in acting:
        additive += perform.body_keys(tl, total, lay, random.Random(a.seed + 3), max_deg=a.body_max, roll_track=roll_track)
    elif roll_track:
        additive += [{"t": t, "bones": {"hips": [0, 0, r]}} for t, r in roll_track]
    motion = {"name": f"{a.name}_{a.lang}", "label": f"{a.name} presenter ({a.lang})", "duration": total,
              "loop": False, "keys": keys, **({"additive": additive} if additive else {})}
    mp = ROOT / f"data/motions/explainer/{a.name}_{a.lang}.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(motion, ensure_ascii=False))
    print(json.dumps({"total": total, "lines": [(l["id"], l["start"], l["end"]) + ((l["variant"],) if l.get("variant") else ()) for l in tl],
                      **({"beats": beat_log} if beat_log else {})}, ensure_ascii=False))


if __name__ == "__main__":
    main()
