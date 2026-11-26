"""Avatar package loader (docs/avatar-package.md).

A character is described by data/characters/<id>.json: the drawing assets (vector, urlDefaults, ...)
plus the package fields rig / voice / persona / acting / capture. Every package field is optional;
load() fills the defaults, which reproduce the tools' behaviour before the package existed.
Mirrors src/core/avatarPackage.ts (keep the defaults in sync).

  import sys; sys.path.insert(0, "tools/avatar"); import package as PKG
  p = PKG.load("usagi")
  p["voice"]["ja"]["engine"]       # -> "files" (or "irodori", "command")
  PKG.voice_for(p, "ja", "smile")  # voice id for a line with that expression
  PKG.tts_args(p, "ja", "smile")   # bin/irodori-voice arguments (uses the voice copied into the package)

CLI: python tools/avatar/package.py <id> [--check]   (prints the resolved package as JSON)
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAR_DIR = ROOT / "data" / "characters"
SCHEMA_VERSION = 1

HAND_TYPES = ("mitten", "beast", "human", "stick")
# TTS engines of voice.<lang>.engine: "irodori" (Irodori-TTS-Custom, IRODORI_HOME), "drama3"
# (speech.cpp, English), "command" (any TTS: voice.<lang>.command is the argument list with
# {text} {out} {expr} {seed} {speed}), "files" (no synthesis: put <line id>_t<take>.wav yourself)
ENGINES = ("irodori", "drama3", "command", "files")
TURNS = ("front", "parallax30", "turn90", "turn90_opp")

DEFAULTS = {
    "rig": {
        "hands": {"type": "mitten", "scale": 1.0, "shapeScale": {}, "dropLines": [], "unavailable": [], "colors": {}},
        "rest": {"upperArm": 70.0},
        "turn": "parallax30",
    },
    "voice": {
        "ja": {"engine": "files", "voice": ""},
        "en": {"engine": "files", "voice": ""},
        "byExpression": {},
        "emotion": {},
        "speed": 1.0,
        "timing": {"lineGap": 0.28, "sceneGap": 0.8, "maxPause": 0.0},
    },
    "persona": {"status": "draft", "firstPerson": "", "nameReading": "", "callsViewer": "", "endings": [], "tone": "", "avoid": [], "examples": []},
    "acting": {"status": "draft", "style": "", "gestureScale": 1.0, "tempo": 1.0, "beat": {"amp": 1.0, "rate": 1.0},
               "gestureWeights": {}, "tiltRate": 0.3, "blinkRate": 1.0},
    "capture": {"bg": "dde6f2", "crop": None, "ph": None, "py": None, "rim": None},
}
PACKAGE_KEYS = tuple(DEFAULTS)


def merge_defaults(base, over):
    """Fill missing fields of `over` from `base` (dicts merge recursively; lists and scalars replace).
    A dict whose default is empty (free-named keys such as shapeScale) is taken as it is."""
    if over is None:
        return copy.deepcopy(base)
    if not isinstance(base, dict) or not isinstance(over, dict):
        return copy.deepcopy(over)
    out = copy.deepcopy(base)
    for k, v in over.items():
        b = base.get(k)
        out[k] = merge_defaults(b, v) if isinstance(b, dict) and b else copy.deepcopy(v)
    return out


def resolve(cfg):
    """The character definition with every package default filled in."""
    out = copy.deepcopy(cfg)
    for k in PACKAGE_KEYS:
        out[k] = merge_defaults(DEFAULTS[k], cfg.get(k))
    out["schemaVersion"] = cfg.get("schemaVersion", 0)
    return out


def path_of(char_id):
    return CHAR_DIR / f"{char_id}.json"


def ids():
    return sorted(p.stem for p in CHAR_DIR.glob("*.json"))


def load(char_id, resolve_defaults=True):
    cfg = json.loads(path_of(char_id).read_text(encoding="utf-8"))
    if cfg.get("id") != char_id:
        raise ValueError(f"{path_of(char_id)}: id is {cfg.get('id')!r}, expected {char_id!r}")
    return resolve(cfg) if resolve_defaults else cfg


def validate(cfg):
    """Light structural check (the full checker is id091). Returns a list of messages."""
    errs = []
    v = cfg.get("schemaVersion")
    if v is not None and (not isinstance(v, int) or not 0 <= v <= SCHEMA_VERSION):
        errs.append(f"schemaVersion {v!r} is not supported")
    rig = cfg.get("rig") or {}
    h = rig.get("hands") or {}
    if "type" in h and h["type"] not in HAND_TYPES:
        errs.append(f"rig.hands.type {h['type']!r}")
    if "scale" in h and not (isinstance(h["scale"], (int, float)) and h["scale"] > 0):
        errs.append("rig.hands.scale must be > 0")
    if "turn" in rig and rig["turn"] not in TURNS:
        errs.append(f"rig.turn {rig['turn']!r}")
    ua = (rig.get("rest") or {}).get("upperArm")
    if ua is not None and not 0 <= ua <= 90:
        errs.append("rig.rest.upperArm must be 0..90")
    for lang, spec in (cfg.get("voice") or {}).items():
        if lang in ("ja", "en") and isinstance(spec, dict):
            eng = spec.get("engine")
            if eng is not None and eng not in ENGINES:
                errs.append(f"voice.{lang}.engine {eng!r}")
            if eng == "command" and not (isinstance(spec.get("command"), list) and spec["command"]):
                errs.append(f"voice.{lang}.command must be a non-empty list")
    for sec in ("persona", "acting"):
        st = (cfg.get(sec) or {}).get("status")
        if st is not None and st not in ("draft", "approved"):
            errs.append(f"{sec}.status {st!r}")
    cap = cfg.get("capture") or {}
    bg = cap.get("bg")
    if bg is not None and not (isinstance(bg, str) and len(bg) == 6 and all(c in "0123456789abcdefABCDEF" for c in bg)):
        errs.append(f"capture.bg {bg!r}")
    for k in ("crop", "ph", "py"):
        x = cap.get(k)
        if x is not None and not 0 < x <= 1:
            errs.append(f"capture.{k} must be in (0, 1]")
    rim = cap.get("rim")
    if rim is not None:   # light outline on the pale areas (vRim)
        c = rim.get("color") if isinstance(rim, dict) else None
        if not (isinstance(c, str) and len(c) == 6 and all(x in "0123456789abcdefABCDEF" for x in c)):
            errs.append(f"capture.rim.color {c!r}")
        if isinstance(rim, dict) and not 0 <= rim.get("minL", 88) <= 100:
            errs.append("capture.rim.minL must be 0..100")
        if isinstance(rim, dict) and not rim.get("width", 4.5) > 0:
            errs.append("capture.rim.width must be > 0")
    bust = cap.get("bust") or {}
    for k, v in bust.items():   # bust framing of the presenter window (vBust* URL params)
        if k not in BUST_KEYS or not isinstance(v, (int, float)):
            errs.append(f"capture.bust.{k} {v!r}")
    return errs


# capture.bust -> the viewer's URL params of the bust framing
BUST_KEYS = {"top": "vBustTop", "bot": "vBustBot", "w": "vBustW", "x": "vBustX", "follow": "vBustFollow", "lag": "vBustLag"}


def bust_query(pkg):
    """URL query of the package's bust framing (capture.bust), e.g. '&framing=bust&vBustTop=0.35'."""
    bust = (pkg.get("capture") or {}).get("bust") or {}
    return "&framing=bust" + "".join(f"&{BUST_KEYS[k]}={v}" for k, v in bust.items() if k in BUST_KEYS)


def rim_query(pkg):
    """URL query of the package's rim on pale areas (capture.rim), e.g. '&vRim=c8cbd3&vRimL=88'; '' when unset."""
    rim = (pkg.get("capture") or {}).get("rim")
    if not rim:
        return ""
    return f"&vRim={rim['color']}" + "".join(f"&{q}={rim[k]}" for k, q in (("minL", "vRimL"), ("width", "vRimW")) if k in rim)


def voice_for(pkg, lang="ja", expression=None):
    """Voice id for a line: the expression's voice if the package names one, else the language's voice."""
    by = pkg["voice"].get("byExpression") or {}
    if expression and expression in by:
        return by[expression]
    return pkg["voice"][lang]["voice"]


def voice_dir(pkg, lang="ja"):
    """Absolute folder of the language's voice copied into the package (import_voice.py), or None."""
    d = pkg["voice"][lang].get("dir")
    return ROOT / "public" / d if d else None


def tts_args(pkg, lang="ja", expression=None):
    """Arguments for Irodori-TTS-Custom bin/irodori-voice (without --text / -o) for a line.

    A voice copied into the package is synthesised from the copy: a reference voice only from the
    copied reference audio (--ref-wavs, no lookup in the library), a LoRA voice with the library's
    adapter and the copied reference audio. Other voices (by-expression voices, voices not copied)
    are named by id."""
    vid = voice_for(pkg, lang, expression)
    d = voice_dir(pkg, lang)
    args = []
    if d and vid == pkg["voice"][lang]["voice"]:
        m = json.loads((d / "voice.json").read_text(encoding="utf-8"))
        refs = [str(d / r["path"]) for r in m["refs"]]
        if m["method"] == "lora":
            args += ["--voice", vid]
            if m["lora"].get("reference", True):
                args += ["--ref-wavs", *refs]
        else:
            args += ["--ref-wavs", *refs]
        if m.get("caption"):
            args += ["--caption", m["caption"]]
    else:
        args += ["--voice", vid]
    emo = emotion_for(pkg, expression)
    if emo:
        args += ["--emotion", emo]
    return args


def emotion_for(pkg, expression=None):
    """Irodori-TTS-Custom --emotion name for a line with that expression, or None."""
    return (pkg["voice"].get("emotion") or {}).get(expression) if expression else None


def irodori_home():
    """Irodori-TTS-Custom install folder: $IRODORI_HOME, else the default place."""
    import os
    h = os.environ.get("IRODORI_HOME")
    if h:
        return Path(h).expanduser()
    return Path("IRODORI_HOME-is-not-set")


def command_args(pkg, lang, text, out, expression=None, seed=0, speed=1.0):
    """The voice.<lang>.command argument list of a "command" engine, filled in for one line."""
    tpl = pkg["voice"][lang].get("command") or []
    if not tpl:
        raise SystemExit(f"voice.{lang}.engine is 'command' but voice.{lang}.command is empty")
    vals = {"text": text, "out": str(Path(out).resolve()), "expr": expression or "neutral", "seed": seed, "speed": speed}
    return [str(s).format(**vals) for s in tpl]


def say(pkg, text, out, lang="ja", expression=None, extra=()):
    """Synthesise one line in the character's voice (Japanese, Irodori-TTS-Custom)."""
    import subprocess
    eng = pkg["voice"][lang]["engine"]
    if eng == "command":
        subprocess.run(command_args(pkg, lang, text, out, expression), check=True)
        return
    if eng != "irodori":
        raise SystemExit(f"say(): engine {eng} cannot synthesise here (use 'irodori' or 'command')")
    cmd = [str(irodori_home() / "bin/irodori-voice"), *tts_args(pkg, lang, expression), "--text", text, "-o", str(Path(out).resolve())]
    if extra:
        cmd += ["--", *extra]
    subprocess.run(cmd, check=True)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="print a character's resolved avatar package")
    ap.add_argument("char", nargs="?", help="character id (default: all, with --check)")
    ap.add_argument("--check", action="store_true", help="validate instead of printing")
    ap.add_argument("--say", help="synthesise this text in the character's voice (needs --out)")
    ap.add_argument("--out", help="output wav for --say")
    ap.add_argument("--expression", help="expression of the line (voice.byExpression / voice.emotion)")
    a = ap.parse_args(argv)
    if a.say:
        if not (a.char and a.out):
            ap.error("--say needs a character id and --out")
        say(load(a.char), a.say, a.out, expression=a.expression)
        return 0
    targets = [a.char] if a.char else ids()
    if not a.check:
        for c in targets:
            print(json.dumps(load(c), ensure_ascii=False, indent=2))
        return 0
    bad = 0
    for c in targets:
        errs = validate(load(c, resolve_defaults=False))
        print(f"{c}: {'ok' if not errs else '; '.join(errs)}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
