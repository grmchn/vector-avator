"""Explainer data in three layers (docs/explainer-format.md): content / script / acting.

  python tools/explainer/explainer_format.py check <dir> [<dir> ...]
      JSON Schema (tools/explainer/schema/) + the checks a schema cannot express (§7)
  python tools/explainer/explainer_format.py legacy <dir> <char> [-o OUT]
      content.json + script.<char>.json -> the script form the current tools read
      (the build form: id, scene, icon, gesture, expr, point_at, emphasize, ja, ja_tts, ja_kana, en...)

<dir> holds content.json and script.<char>.json files (data/explainer/<content id>/).
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
LAYOUT = Path(__file__).resolve().parent / "layout.json"
CHAR_DIR = ROOT / "data" / "characters"

# default conversion (§5): the first line tag decides the gesture; emotion decides the expression
TAG_GESTURE = {"greet": "spread", "introduce": "explain", "enumerate": "explain", "emphasize": "spread",
               "point_at": "point", "question": "nod", "think": "think", "surprise": "surprise",
               "agree": "nod", "contrast": "explain", "conclude": "nod"}
NO_TAG_GESTURE = "explain"
EMOTION_EXPR = {"calm": "neutral", "joy": "smile", "surprise": "surprised", "trouble": "troubled"}
KANA_OK = re.compile(r"^[ぁ-ゟー\s、。，．,.！？!?・「」]+$")


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def load_dir(d):
    """(content, {char: script}) of a content folder."""
    d = Path(d)
    content = read_json(d / "content.json")
    scripts = {}
    for p in sorted(d.glob("script.*.json")):
        s = read_json(p)
        scripts[p.name[len("script."):-len(".json")]] = s
    return content, scripts


def schema_errors(doc, name):
    import jsonschema
    schema = read_json(SCHEMA_DIR / name)
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(str(x) for x in e.absolute_path) or '(root)'}: {e.message}" for e in v.iter_errors(doc)]


def line_tags(line):
    return [t for t in line.get("tags", []) if "term" not in t]


def term_tags(line):
    return [t for t in line.get("tags", []) if "term" in t]


def check_content(content, regions=None):
    errs = [f"content: {e}" for e in schema_errors(content, "content.schema.json")]
    if errs:
        return errs
    if regions is None:
        regions = set(read_json(LAYOUT).get("regions", {}))
    seen = set()
    for ln in content["lines"]:
        lid = ln["id"]
        if lid in seen:
            errs.append(f"content {lid}: duplicate line id")
        seen.add(lid)
        terms = set(ln.get("terms", []))
        for t in ln.get("tags", []):
            if "term" in t and t["term"] not in terms:
                errs.append(f"content {lid}: tag {t['tag']} term '{t['term']}' is not in terms")
            if t["tag"] == "point_at" and "region" in t and t["region"] not in regions:
                errs.append(f"content {lid}: point_at region '{t['region']}' is not in layout.json ({', '.join(sorted(regions))})")
    return errs


def check_script(script, content, char_ids=None):
    errs = [f"script.{script.get('char', '?')}: {e}" for e in schema_errors(script, "script.schema.json")]
    if errs:
        return errs
    who = f"script.{script['char']}"
    if script["content"] != content["id"]:
        errs.append(f"{who}: content is '{script['content']}', expected '{content['id']}'")
    if char_ids is None:
        char_ids = {p.stem for p in CHAR_DIR.glob("*.json")}
    if script["char"] not in char_ids:
        errs.append(f"{who}: character '{script['char']}' is not in data/characters/")
    cids = [ln["id"] for ln in content["lines"]]
    sids = [ln["id"] for ln in script["lines"]]
    if cids != sids:
        missing, extra = [i for i in cids if i not in sids], [i for i in sids if i not in cids]
        errs.append(f"{who}: lines differ from the content (missing {missing}, extra {extra}"
                    f"{', order differs' if not missing and not extra else ''})")
    by_id = {ln["id"]: ln for ln in content["lines"]}
    for sl in script["lines"]:
        cl = by_id.get(sl["id"])
        if cl is None:
            continue
        lid = sl["id"]
        if not KANA_OK.match(sl["ja_kana"]):
            bad = sorted({c for c in sl["ja_kana"] if not KANA_OK.match(c)})
            errs.append(f"{who} {lid}: ja_kana has characters other than hiragana: {''.join(bad)}")
        anchors = sl.get("anchors", {})
        need = {t["term"] for t in term_tags(cl)}
        for term in sorted(need - set(anchors)):
            errs.append(f"{who} {lid}: no anchor for the tagged term '{term}'")
        for term, a in anchors.items():
            if term not in set(cl.get("terms", [])):
                errs.append(f"{who} {lid}: anchor '{term}' is not a term of the content line")
            if a["ja"] not in sl["ja"]:
                errs.append(f"{who} {lid}: anchor '{term}' ja '{a['ja']}' is not in the subtitle")
            if a["kana"] not in sl["ja_kana"]:
                errs.append(f"{who} {lid}: anchor '{term}' kana '{a['kana']}' is not in ja_kana")
    return errs


def check_dir(d):
    content, scripts = load_dir(d)
    errs = check_content(content)
    if any(e.startswith("content: ") for e in errs):
        return errs, content, scripts
    for s in scripts.values():
        errs += check_script(s, content)
    return errs, content, scripts


def default_acting(cline):
    """The character-independent default gesture and expression of a content line (§5)."""
    tags = line_tags(cline)
    if not tags:
        g = NO_TAG_GESTURE
    elif tags[0]["tag"] == "demo":
        g = tags[0]["motion"]
    else:
        g = TAG_GESTURE[tags[0]["tag"]]
    return g, EMOTION_EXPR[cline.get("emotion", "calm")]


def to_legacy(content, script):
    """content + script -> the build form of the script (what build_timeline.py reads)."""
    by_id = {ln["id"]: ln for ln in script["lines"]}
    lines = []
    for cl in content["lines"]:
        sl = by_id[cl["id"]]
        g, e = default_acting(cl)
        ov = sl.get("override", {})
        out = {"id": cl["id"], "scene": cl["scene"], "icon": (cl.get("visual") or {}).get("image", ""),
               "gesture": ov.get("gesture", g), "expr": ov.get("expr", e)}
        pt = next((t for t in cl.get("tags", []) if t["tag"] == "point_at" and "region" in t), None)
        if pt:
            out["point_at"] = pt["region"]
        emph = [sl["anchors"][t["term"]]["kana"] for t in term_tags(cl) if t["tag"] == "emphasize"]
        if emph:
            out["emphasize"] = emph
        for k in ("ja", "ja_tts", "ja_kana", "en", "en_tts"):
            if k in sl:
                out[k] = sl[k]
        lines.append(out)
    title = content["title"]
    return {"title": title.get("ja") if len(title) == 1 else title, "content": content["id"], "char": script["char"],
            "lines": lines}


def main(argv=None):
    ap = argparse.ArgumentParser(description="explainer data in three layers (docs/explainer-format.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("dirs", nargs="+")
    lg = sub.add_parser("legacy")
    lg.add_argument("dir")
    lg.add_argument("char")
    lg.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        bad = 0
        for d in a.dirs:
            errs, content, scripts = check_dir(d)
            print(f"{d}: {content['id']} ({len(content['lines'])} lines, scripts: {', '.join(scripts) or 'none'}) "
                  f"{'OK' if not errs else f'{len(errs)} errors'}")
            for e in errs:
                print("  ERROR", e)
            bad += bool(errs)
        return 1 if bad else 0
    errs, content, scripts = check_dir(a.dir)
    if errs:
        print("\n".join("ERROR " + e for e in errs))
        return 1
    if a.char not in scripts:
        print(f"no script.{a.char}.json in {a.dir}")
        return 1
    out = json.dumps(to_legacy(content, scripts[a.char]), ensure_ascii=False, indent=1) + "\n"
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print("wrote", a.out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
