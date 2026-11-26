"""Script layer in a character's voice (docs/explainer-format.md §6).

  python tools/explainer/make_script.py brief <content dir> <char> [-o OUT]
      the rewrite request for one character: tools/explainer/rewrite_brief.md filled with the
      character's persona (data/characters/<char>.json) and the content lines
  python tools/explainer/make_script.py check <content dir> [<char> ...]
      explainer_format checks (errors) + the rewrite checks (warnings): length against the content's
      `seconds`, first person, the content's terms in the subtitle, letters / digits left in ja_tts,
      subtitle length
  python tools/explainer/make_script.py compare <content dir> <char> [<char> ...] [-o OUT.json]
      the same lines side by side (for the comparison table)
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools/avatar"))
import explainer_format as EF  # noqa: E402
import package as PKG  # noqa: E402

TEMPLATE = HERE / "rewrite_brief.md"
MORA_RATE = 6.0          # kana morae per second with pauses (id057 timeline: median 6.03)
LEN_RANGE = (0.7, 1.3)   # allowed ratio of the estimated length to the content's `seconds`
MAX_SUBTITLE = 70
SMALL = set("ゃゅょぁぃぅぇぉゎ")
FIRST_PERSON = ["わたくし", "わたし", "ワタシ", "私", "あたし", "アタシ", "ぼく", "ボク", "僕", "おれ", "オレ", "俺"]
TAG_LABEL = {"greet": "あいさつ", "introduce": "話題の提示・予告", "enumerate": "列挙", "emphasize": "強調",
             "point_at": "画面のものを指す", "question": "問いかけ", "think": "考える・溜め", "surprise": "驚き",
             "agree": "同意・念押し", "contrast": "対比", "conclude": "まとめ", "demo": "機能を体で見せる"}
EMOTION_LABEL = {"calm": "平静", "joy": "喜び", "surprise": "驚き", "trouble": "困り"}


def mora(kana):
    return sum(1 for ch in kana if ("ぁ" <= ch <= "ゟ" and ch not in SMALL) or ch == "ー")


def speed_of(pkg):
    return float(pkg["voice"].get("speed") or 1.0)


def tag_text(t):
    s = TAG_LABEL[t["tag"]]
    if "n" in t:
        s += f"（{t['n']}）"
    if t.get("motion"):
        s += f"（{t['motion']}）"
    if t.get("term"):
        s += f"「{t['term']}」"
    return s


def lines_md(content, speed):
    out = []
    for ln in content["lines"]:
        rows = [f"### {ln['id']}（場面 `{ln['scene']}`）", "", f"- 要旨：{ln['gist']}"]
        if ln.get("terms"):
            rows.append("- 必ず言う語：" + "、".join(ln["terms"]))
        emph = [t["term"] for t in ln.get("tags", []) if t["tag"] == "emphasize" and "term" in t]
        if emph:
            rows.append("- 強調する語（`anchors` に書く）：" + "、".join(emph))
        if ln.get("tags"):
            rows.append("- 意味（演技のタグ）：" + "、".join(tag_text(t) for t in ln["tags"]))
        rows.append(f"- 感情：{EMOTION_LABEL[ln.get('emotion', 'calm')]}")
        if ln.get("seconds"):
            rows.append(f"- 長さの目安：{ln['seconds']} 秒（かなで約 {round(ln['seconds'] * MORA_RATE * speed)} モーラ）")
        if (ln.get("reference") or {}).get("ja"):
            rows.append(f"- 参考の言い回し（中立。口調はキャラに合わせて変える）：{ln['reference']['ja']}")
        if ln.get("note"):
            rows.append(f"- 備考：{ln['note']}")
        out.append("\n".join(rows))
    return "\n\n".join(out)


def brief(content_dir, char):
    content, _ = EF.load_dir(content_dir)
    pkg = PKG.load(char)
    p, a = pkg["persona"], pkg["acting"]
    speed = speed_of(pkg)
    vals = {
        "content_title": content["title"].get("ja", content["id"]), "content_id": content["id"],
        "content_dir": str(Path(content_dir)), "char": char, "char_label": pkg["label"], "char_name": pkg["label"],
        "name_reading": p.get("nameReading") or pkg["label"],
        "first_person": p["firstPerson"] or "（指定なし）", "calls_viewer": p["callsViewer"] or "（指定なし）",
        "endings": "、".join(p["endings"]) or "（指定なし）", "tone": p["tone"] or "（指定なし）",
        "avoid": "、".join(p["avoid"]) or "（なし）", "acting_style": a.get("style") or "（指定なし）",
        "speed": f"{speed:g}", "mora_rate": f"{MORA_RATE * speed:g}",
        "examples": "\n".join(f"- {e}" for e in p["examples"]) or "（なし）",
        "out_path": str(Path(content_dir) / f"script.{char}.json"),
        "lines": lines_md(content, speed),
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for k, v in vals.items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        raise SystemExit(f"unfilled placeholders: {left}")
    return text


def rewrite_warnings(content, script, pkg):
    """Warnings for a rewritten script (the format errors come from explainer_format)."""
    warns = []
    by_id = {ln["id"]: ln for ln in script["lines"]}
    rate = MORA_RATE * speed_of(pkg)
    fp = pkg["persona"].get("firstPerson") or ""
    for cl in content["lines"]:
        sl = by_id.get(cl["id"])
        if sl is None:
            continue
        lid = cl["id"]
        if cl.get("seconds"):
            est = mora(sl["ja_kana"]) / rate
            r = est / cl["seconds"]
            if not LEN_RANGE[0] <= r <= LEN_RANGE[1]:
                warns.append(f"{lid}: length about {est:.1f} s against {cl['seconds']} s (x{r:.2f})")
        if fp:
            found = [w for w in FIRST_PERSON if w in sl["ja"]]
            found = [w for w in found if not any(w != o and w in o for o in found)]   # わたし inside わたくし
            found = [w for w in found if w != fp]
            if found:
                warns.append(f"{lid}: first person {'・'.join(found)} (persona: {fp})")
        for term in cl.get("terms", []):
            if term not in sl["ja"] and term not in (sl.get("anchors", {}).get(term, {}).get("ja", "")):
                warns.append(f"{lid}: the term '{term}' is not in the subtitle")
        if re.search(r"[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]", sl["ja_tts"]):
            warns.append(f"{lid}: ja_tts still has letters or digits: {sl['ja_tts']}")
        if len(sl["ja"]) > MAX_SUBTITLE:
            warns.append(f"{lid}: subtitle is {len(sl['ja'])} characters (over {MAX_SUBTITLE})")
    return warns


def check(content_dir, chars=None):
    content, scripts = EF.load_dir(content_dir)
    errs = EF.check_content(content)
    results = {}
    for char, s in scripts.items():
        if chars and char not in chars:
            continue
        e = EF.check_script(s, content)
        w = rewrite_warnings(content, s, PKG.load(char)) if not e else []
        results[char] = (e, w)
    for c in chars or []:
        if c not in scripts:
            results[c] = ([f"script.{c}.json not found"], [])
    return errs, results


def compare(content_dir, chars):
    content, scripts = EF.load_dir(content_dir)
    rows = []
    for cl in content["lines"]:
        row = {"id": cl["id"], "gist": cl["gist"]}
        for c in chars:
            sl = next((x for x in scripts[c]["lines"] if x["id"] == cl["id"]), None)
            row[c] = sl["ja"] if sl else ""
        rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="script layer in a character's voice")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("dir")
    b.add_argument("char")
    b.add_argument("-o", "--out")
    c = sub.add_parser("check")
    c.add_argument("dir")
    c.add_argument("chars", nargs="*")
    m = sub.add_parser("compare")
    m.add_argument("dir")
    m.add_argument("chars", nargs="+")
    m.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    if a.cmd == "brief":
        text = brief(a.dir, a.char)
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
            print("wrote", a.out)
        else:
            sys.stdout.write(text)
        return 0
    if a.cmd == "compare":
        rows = compare(a.dir, a.chars)
        out = json.dumps(rows, ensure_ascii=False, indent=1)
        if a.out:
            Path(a.out).write_text(out + "\n", encoding="utf-8")
        else:
            print(out)
        return 0
    errs, results = check(a.dir, a.chars or None)
    for e in errs:
        print("ERROR content:", e)
    bad = bool(errs)
    for char, (e, w) in results.items():
        print(f"== {char}: {'OK' if not e else 'FAIL'} ({len(e)} errors, {len(w)} warnings)")
        for x in e:
            print("  ERROR", x)
        for x in w:
            print("  WARN ", x)
        bad |= bool(e)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
