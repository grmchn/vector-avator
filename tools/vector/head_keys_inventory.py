#!/usr/bin/env python3
"""List how the key heads (front / head30 / head60 / head90) line up for the in-betweens (docs/vector-parts.md 8.7).

For every head part (parent == head in vector.json, or any part of a headNN.json) print, per key head:
the shape names, and the number of closed rings per shape. Flags parts / shapes that exist in only some keys
and shapes with more than one ring (the morph expects one closed ring per shape).

usage: python tools/vector/head_keys_inventory.py <char> [--md out.md] [--opp]
  --opp: the keys turned the other way (head<deg>_opp.json) instead
"""
import argparse, json, os, re, sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def rings(d):
    return len(re.findall(r"[Mm]", d or ""))


def head_parts(doc, front):
    out = {}
    for p in doc["parts"]:
        if front and p.get("parent") != "head" and p.get("id") != "head" and p.get("layer") not in ("ear", "hair_back", "hair_side", "hair_front", "feature", "head"):
            continue
        if front and p.get("layer") == "body":
            continue
        out[p["id"]] = [(s.get("name") or f"#{i}", rings(s.get("d"))) for i, s in enumerate(p.get("shapes") or [])]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("char")
    ap.add_argument("--md")
    ap.add_argument("--opp", action="store_true")
    a = ap.parse_args()
    base = os.path.join(ROOT, "public", "characters", a.char, "vector")
    keys = {}
    keys["0"] = head_parts(json.load(open(os.path.join(base, "vector.json"))), True)
    for k in ("30", "60", "90"):
        f = os.path.join(base, f"head{k}{'_opp' if a.opp else ''}.json")
        if os.path.exists(f):
            keys[k + ("o" if a.opp else "")] = head_parts(json.load(open(f)), False)
    names = list(keys)
    ids = []
    for k in names:
        for i in keys[k]:
            if i not in ids:
                ids.append(i)
    lines = [f"# {a.char}: key heads {', '.join(n + '°' for n in names)}", "",
             "| part | " + " | ".join(n + "°" for n in names) + " | note |", "|---|" + "---|" * len(names) + "---|"]
    issues = 0
    for i in ids:
        cells, notes = [], []
        sets = []
        for k in names:
            sh = keys[k].get(i)
            if sh is None:
                cells.append("—")
                continue
            sets.append(tuple(n for n, _ in sh))
            cells.append(", ".join(f"{n}{'×' + str(r) if r != 1 else ''}" for n, r in sh))
            if any(r != 1 for _, r in sh):
                notes.append(f"multi-ring@{k}")
        if "—" in cells:
            notes.append("missing in " + ",".join(n for n, c in zip(names, cells) if c == "—"))
        if len(set(sets)) > 1:
            notes.append("shape names/order differ")
        if notes:
            issues += 1
        lines.append(f"| {i} | " + " | ".join(cells) + " | " + "; ".join(notes) + " |")
    lines += ["", f"parts with notes: {issues} / {len(ids)}"]
    txt = "\n".join(lines)
    if a.md:
        open(a.md, "w").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
