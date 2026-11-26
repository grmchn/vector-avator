"""Check an avatar package against docs/avatar-package.md.

  python tools/avatar/check.py <char> [<char> ...] [--all] [--json OUT] [--quick]

Errors make the package fail (exit 1); warnings are listed for review. Checks:
  definition  the fields' types and values (package.validate), id / label / vector.url
  vector      vector.json exists; tools/vector/check_parts.py on it and on every turned view the
              declared turn range uses (--quick skips check_parts)
  turn        rig.turn matches the drawings: turn90 needs body30/60/90 and head30/60/90,
              turn90_opp also head30/60/90_opp; drawings beyond the declared range are a warning
  hands       the eight hand shapes (docs/vector-parts.md 4.3) on both sides; the legacy four are
              errors, the newer four warnings unless rig.hands.unavailable lists them
  voice       a voice copied into the package (voice.<lang>.dir): voice.json, reference files and
              their sha256; a LoRA voice's adapter in the library and its sha256. A voice named by
              id only must exist in Irodori-TTS-Custom (warning: not copied). drama3 voice files.
  persona / acting  filled in and approved (warnings)
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import package as PKG  # noqa: E402

PUBLIC = ROOT / "public"
VOICE_HOME = PKG.irodori_home()
DRAMA3_DIR = ROOT / "var/explainer/audio"
HANDS_LEGACY = ("open", "point", "fist", "palm")
HANDS_NEW = ("palm_up", "point_front", "peace", "thumbs_up")
VIEW_NAME = re.compile(r"^(body|head)\d+(_opp)?$")
TURN_VIEWS = {
    "front": [],
    "parallax30": [],
    "turn90": ["body30", "body60", "body90", "head30", "head60", "head90"],
    "turn90_opp": ["body30", "body60", "body90", "head30", "head60", "head90", "head30_opp", "head60_opp", "head90_opp"],
}


class Report:
    def __init__(self, char):
        self.char, self.errors, self.warnings = char, [], []

    def err(self, area, msg):
        self.errors.append(f"[{area}] {msg}")

    def warn(self, area, msg):
        self.warnings.append(f"[{area}] {msg}")

    def as_dict(self):
        return {"char": self.char, "ok": not self.errors, "errors": self.errors, "warnings": self.warnings}


def rel(p):
    """A path for messages: relative to the project when it is inside it."""
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_check_parts(rep, char, view=None):
    cmd = [sys.executable, str(ROOT / "tools/vector/check_parts.py"), char, "--no-render"]
    if view:
        cmd += ["--view", view]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    area = f"parts{':' + view if view else ''}"
    for line in (out.stdout + out.stderr).splitlines():
        if line.startswith("ERROR"):
            rep.err(area, line[5:].strip())
        elif line.startswith("WARN"):
            rep.warn(area, line[5:].strip())
    if out.returncode not in (0, 1):
        rep.err(area, f"check_parts.py failed (exit {out.returncode}): {(out.stderr or out.stdout).strip()[-300:]}")


def check_definition(rep, raw):
    for e in PKG.validate(raw):
        rep.err("definition", e)
    for k in ("id", "label"):
        if not isinstance(raw.get(k), str) or not raw.get(k):
            rep.err("definition", f"{k} is missing")
    if raw.get("schemaVersion") is None:
        rep.warn("definition", "schemaVersion is missing (read as the old form 0)")
    if not (raw.get("vector") or {}).get("url"):
        rep.err("definition", "vector.url is missing (method V)")


def vector_files(pkg):
    vjson = PUBLIC / pkg["vector"]["url"]
    return vjson, vjson.parent


def check_vector(rep, pkg, quick):
    vjson, vdir = vector_files(pkg)
    if not vjson.is_file():
        rep.err("vector", f"{rel(vjson)} not found")
        return None
    art = json.loads(vjson.read_text(encoding="utf-8"))
    if not quick:
        run_check_parts(rep, pkg["id"])
    return art


def check_turn(rep, pkg, vdir, quick):
    turn = pkg["rig"]["turn"]
    if "turn" not in (PKG.load(pkg["id"], resolve_defaults=False).get("rig") or {}):
        rep.warn("turn", f"rig.turn is not declared (default {turn})")
    if turn not in TURN_VIEWS:
        return   # reported by check_definition
    need = TURN_VIEWS[turn]
    for v in need:
        if not (vdir / f"{v}.json").is_file():
            rep.err("turn", f"rig.turn {turn} needs {v}.json")
        elif not quick:
            run_check_parts(rep, pkg["id"], v)
    extra = sorted(p.stem for p in vdir.glob("*.json") if VIEW_NAME.match(p.stem) and p.stem not in need)
    if extra and turn in ("front", "parallax30"):
        rep.warn("turn", f"turned drawings exist ({', '.join(extra)}) but rig.turn is {turn}")
    elif not quick:
        # optional drawings used when present (body<deg>_opp.json for asymmetric bodies)
        for v in extra:
            run_check_parts(rep, pkg["id"], v)


def hand_variants(art):
    got = {"L": set(), "R": set()}
    for p in art.get("parts", []):
        g = p.get("group", "")
        if g in ("hand_L", "hand_R"):
            got[g[-1]].update(p.get("variants") or [])
    return got


def check_hands(rep, pkg, art):
    if art is None:
        return
    raw_rig = PKG.load(pkg["id"], resolve_defaults=False).get("rig") or {}
    if "type" not in (raw_rig.get("hands") or {}):
        rep.warn("hands", "rig.hands.type is not declared (hand template unknown)")
    got = hand_variants(art)
    unavailable = set(pkg["rig"]["hands"]["unavailable"])
    for s in ("L", "R"):
        for h in HANDS_LEGACY:
            if h not in got[s]:
                rep.err("hands", f"hand_{s} has no '{h}'")
        for h in HANDS_NEW:
            if h not in got[s] and h not in unavailable:
                rep.warn("hands", f"hand_{s} has no '{h}' (draws a fallback; list it in rig.hands.unavailable if intended)")
    for h in sorted(unavailable):
        if all(h in got[s] for s in ("L", "R")):
            rep.warn("hands", f"'{h}' is listed as unavailable but both hands have it")


def check_voice(rep, pkg, raw):
    v = pkg["voice"]
    for lang in ("ja", "en"):
        spec = v[lang]
        declared = lang in (raw.get("voice") or {})
        if spec["engine"] == "irodori":
            d = PKG.voice_dir(pkg, lang)
            if d:
                check_voice_copy(rep, lang, spec["voice"], d)
            else:
                if not (VOICE_HOME / "voices" / spec["voice"] / "voice.yaml").is_file():
                    rep.err("voice", f"{lang}: voice '{spec['voice']}' is not in Irodori-TTS-Custom")
                msg = "not copied into the package (tools/avatar/import_voice.py)" if declared else "not declared (default)"
                rep.warn("voice", f"{lang}: voice '{spec['voice']}' {msg}")
        elif spec["engine"] == "drama3":
            f = DRAMA3_DIR / f"{spec['voice']}.drama3.voice.gguf"
            if not f.is_file():
                rep.warn("voice", f"{lang}: drama3 voice file {rel(f)} not found (made in id094)")
        elif spec["engine"] == "command":
            if not spec.get("command"):
                rep.err("voice", f"{lang}: engine 'command' without voice.{lang}.command")
        elif spec["engine"] == "files":
            pass  # the WAV files are put by hand (tools/explainer/tts.py lists the missing ones)
        else:
            rep.err("voice", f"{lang}: unknown engine '{spec['engine']}'")
    for expr, vid in v["byExpression"].items():
        if not (VOICE_HOME / "voices" / vid / "voice.yaml").is_file():
            rep.err("voice", f"byExpression.{expr}: voice '{vid}' is not in Irodori-TTS-Custom")


def check_voice_copy(rep, lang, vid, d):
    vj = d / "voice.json"
    if not vj.is_file():
        rep.err("voice", f"{lang}: {rel(d)}/voice.json not found (run import_voice.py)")
        return
    m = json.loads(vj.read_text(encoding="utf-8"))
    if m.get("voice") != vid:
        rep.err("voice", f"{lang}: the copy is of '{m.get('voice')}', the package names '{vid}'")
    if not m.get("refs"):
        rep.err("voice", f"{lang}: the copy has no reference audio")
    for r in m.get("refs", []):
        f = d / r["path"]
        if not f.is_file():
            rep.err("voice", f"{lang}: {r['path']} is missing in the copy")
        elif r.get("sha256") and sha256(f) != r["sha256"]:
            rep.err("voice", f"{lang}: {r['path']} differs from its record (sha256)")
    if m.get("method") == "lora":
        lo = m.get("lora") or {}
        a = VOICE_HOME / lo.get("adapter", "?") / "adapter_model.safetensors"
        if not a.is_file():
            rep.err("voice", f"{lang}: LoRA adapter {lo.get('adapter')} is not in the library")
        elif lo.get("sha256") and sha256(a) != lo["sha256"]:
            rep.warn("voice", f"{lang}: the library's LoRA adapter changed since the copy (re-import)")


def check_persona_acting(rep, pkg, raw):
    for sec in ("persona", "acting"):
        if sec not in raw:
            rep.warn(sec, "not filled in (needed to perform in the explainer)")
        elif pkg[sec]["status"] != "approved":
            rep.warn(sec, "not approved by the owner yet (status draft)")
    if "persona" in raw and not pkg["persona"]["examples"]:
        rep.warn("persona", "no example lines")


def check_char(char, quick=False):
    rep = Report(char)
    try:
        raw = PKG.load(char, resolve_defaults=False)
    except (OSError, ValueError) as e:
        rep.err("definition", str(e))
        return rep
    check_definition(rep, raw)
    if rep.errors and any("vector.url" in e for e in rep.errors):
        return rep
    pkg = PKG.resolve(raw)
    art = check_vector(rep, pkg, quick)
    if art is not None:
        check_turn(rep, pkg, vector_files(pkg)[1], quick)
        check_hands(rep, pkg, art)
    check_voice(rep, pkg, raw)
    check_persona_acting(rep, pkg, raw)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="check avatar packages (docs/avatar-package.md)")
    ap.add_argument("chars", nargs="*")
    ap.add_argument("--all", action="store_true", help="every character in data/characters/")
    ap.add_argument("--quick", action="store_true", help="skip tools/vector/check_parts.py")
    ap.add_argument("--json", help="write the reports as JSON")
    a = ap.parse_args(argv)
    chars = PKG.ids() if a.all or not a.chars else a.chars
    reports = [check_char(c, a.quick) for c in chars]
    for r in reports:
        print(f"== {r.char}: {'PASS' if not r.errors else 'FAIL'} ({len(r.errors)} errors, {len(r.warnings)} warnings)")
        for e in r.errors:
            print("  ERROR", e)
        for w in r.warnings:
            print("  WARN ", w)
    if a.json:
        Path(a.json).write_text(json.dumps([r.as_dict() for r in reports], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if any(r.errors for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
