"""TTS for the explainer video, one WAV per script line, in the character's package voice.

  python tools/explainer/tts.py ja --content data/explainer/samples/<id> --avatar <char> [--take N] [--only L01,L02] [--force]

The engine is the package's voice.ja.engine (data/characters/<char>.json):
  files    no synthesis: lists the WAV files to put by hand (any TTS or a recording)
  command  any TTS: voice.ja.command is the argument list, with {text} {out} {expr} {seed} {speed}
  irodori  Irodori-TTS-Custom (set IRODORI_HOME), with a voice per expression (voice.byExpression)
           and an emotion (voice.emotion); the speaking speed voice.speed -> --duration-scale
Output: var/explainer/audio/<content>/<char>/<line id>_t<take>.wav (generated audio is never committed).
"""
import argparse, json, subprocess, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "data/explainer/script.json"
OUT = ROOT / "var/explainer/audio"
sys.path.insert(0, str(ROOT / "tools/avatar"))
import package as PKG  # noqa: E402
VOICE_HOME = PKG.irodori_home()
SPEECH = "speech"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lang", choices=["ja", "en"])
    ap.add_argument("--voice", default="")
    ap.add_argument("--take", type=int, default=1)
    ap.add_argument("--only", default="")
    ap.add_argument("--script", default=str(SCRIPT), help="script JSON (default: the id057 script)")
    ap.add_argument("--out-dir", default="", help="output folder (default: var/explainer/audio/<lang>[_<voice>])")
    ap.add_argument("--content", default="", help="content folder (three-layer data); needs --avatar")
    ap.add_argument("--avatar", default="", help="character id (its package voice)")
    ap.add_argument("--force", action="store_true", help="synthesise again even when the file exists")
    ap.add_argument("--speed", type=float, default=0.0, help="--avatar: speaking speed override (1.0 = normal, 1.2 = faster); default: the package's voice.speed")
    a = ap.parse_args()
    if a.avatar:
        return avatar_tts(a)
    raise SystemExit("use --content <content folder> --avatar <character id> (the package's voice)")
    lines = json.load(open(a.script))["lines"]
    if a.only:
        keep = set(a.only.split(","))
        lines = [l for l in lines if l["id"] in keep]
    out = Path(a.out_dir) if a.out_dir else OUT / f"{a.lang}_{a.voice}"
    out.mkdir(parents=True, exist_ok=True)
    if a.lang == "ja":
        for l in lines:
            target = out / f"{l['id']}_t{a.take}.wav"
            seed = 57000 + zlib.crc32(l["id"].encode()) % 1000 + a.take * 7
            # the voice's long source file has moved; pass its 12 cut segments as the reference instead
            refs = sorted(str(p) for p in (VOICE_HOME / "data" / a.voice / "segments").glob("*.wav"))
            extra = ["--ref-wavs", *refs] if refs else []   # voices with a files source use their own references
            subprocess.run([str(VOICE_HOME / "bin/irodori-voice"), "--voice", a.voice, "--text", l["ja_tts"],
                            "-o", str(target), *extra, "--", "--seed", str(seed)], check=True)
            print("wrote", target, flush=True)
        return
    # English: Drama 3 (speech.cpp) with a voice file made from the voice's first Japanese segments
    #   speech voice drama-3 <segments...> --transcript ... var/explainer/audio/<voice>.drama3.voice.gguf
    vf = OUT / f"{a.voice}.drama3.voice.gguf"
    for l in lines:
        target = out / f"{l['id']}_t{a.take}.wav"
        seed = 57000 + zlib.crc32(l["id"].encode()) % 1000 + a.take * 7
        subprocess.run([SPEECH, "tts", "drama-3", "--add-voice", f"p={vf}", "--voice", "p", "--seed", str(seed),
                        "-o", str(target), l["en_tts"]], check=True)
        print("wrote", target, flush=True)


def avatar_tts(a):
    """read the character's script layer in its package voice."""
    sys.path.insert(0, str(ROOT / "tools/explainer"))
    import explainer_format as EF
    import perform
    if a.lang != "ja":
        raise SystemExit("--avatar: only ja for now (the English voices are made per character later)")
    if not a.content:
        raise SystemExit("--avatar needs --content (the script layer is per character)")
    pkg = PKG.load(a.avatar)
    content, scripts = EF.load_dir(ROOT / a.content)
    lines = perform.act(content, scripts[a.avatar], pkg)["lines"]
    if a.only:
        keep = set(a.only.split(","))
        lines = [l for l in lines if l["id"] in keep]
    out = Path(a.out_dir) if a.out_dir else OUT / content["id"] / a.avatar
    out.mkdir(parents=True, exist_ok=True)
    speed = float(a.speed or pkg["voice"].get("speed") or 1.0)
    engine = pkg["voice"]["ja"].get("engine", "irodori")
    if engine == "files":
        # no synthesis: the WAV files are made with any TTS (or recorded) and put here by hand
        missing = [l for l in lines if not (out / f"{l['id']}_t{a.take}.wav").is_file()]
        for l in missing:
            print(f"missing {out / (l['id'] + f'_t{a.take}.wav')}: {l['ja_tts']}", flush=True)
        if missing:
            raise SystemExit(f"voice.ja.engine is 'files': put the {len(missing)} WAV file(s) above in {out} (one per line, read as written after the colon)")
        print(f"all {len(lines)} WAV files found in {out}")
        return 0
    if engine not in ("irodori", "command"):
        raise SystemExit(f"voice.ja.engine {engine!r}: use 'irodori', 'command' or 'files'")
    for l in lines:
        target = out / f"{l['id']}_t{a.take}.wav"
        if target.is_file() and not a.force:
            print("keep", target, flush=True)
            continue
        seed = 57000 + zlib.crc32(l["id"].encode()) % 1000 + a.take * 7
        if engine == "command":
            cmd = PKG.command_args(pkg, "ja", l["ja_tts"], target, l["expr"], seed, speed)
        else:
            extra = ["--seed", str(seed)] + (["--duration-scale", f"{1 / speed:.4f}"] if speed != 1.0 else [])
            cmd = [str(VOICE_HOME / "bin/irodori-voice"), *PKG.tts_args(pkg, "ja", l["expr"]),
                   "--text", l["ja_tts"], "-o", str(target.resolve()), "--", *extra]
        subprocess.run(cmd, check=True)
        print("wrote", target, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
