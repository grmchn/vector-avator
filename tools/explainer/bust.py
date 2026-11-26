"""Acting for the bust framing: the presenter shown from the chest up in a small window.

- prop_kind / prop_keys: a prop over the head for the line's meaning tag (the character's parts of
  group "prop", drawn by the vector renderer from FaceState.prop / propAmt): a question mark for
  questions and thinking, a light bulb for introducing or stressing an answer. It pops in at the
  start of the first line of a run of lines with the same prop, stays at most 3 s and shrinks.
- GESTURE: the gesture variation used for those lines in the bust framing (hand at the chin to
  think, an arm raised beside the face for an idea).
- lift_arms: the other gestures move the arms further from the rest pose, so the hands come up
  into the window instead of staying below its lower edge.

Used by build_timeline.py with --acting ...,bust (or ...,props for the props alone).
"""
import json

QUESTION_TAGS = ("question", "think")
IDEA_TAGS = ("introduce", "emphasize", "conclude")
GESTURE = {"question": ("think", "think_r"), "idea": ("idea", "idea_r")}

GROW, SHRINK, HOLD = 0.35, 0.3, 3.0   # seconds


def prop_kind(tags):
    """The prop of a line from its first content tag (the line's main meaning), or None: a line
    that contrasts or points first and stresses a word later gets no prop."""
    if not tags:
        return None
    if tags[0] in QUESTION_TAGS:
        return "question"
    if tags[0] in IDEA_TAGS:
        return "idea"
    return None


def pose_runs(ids, props, max_run=2):
    """The lines that take the bust pose of their prop: a pose is not repeated more than `max_run`
    lines in a row (motion-rules M19: no stiff repeats); the prop itself stays on."""
    out, last, run = set(), None, 0
    for i in ids:
        k = props.get(i)
        run = run + 1 if k and k == last else (1 if k else 0)
        last = k
        if k and run <= max_run and not (k == "idea" and run > 1):
            out.add(i)
    return out


def prop_keys(tl, props, hold=HOLD):
    """Face keys (prop, propAmt) for the lines that have a prop. tl: timeline lines (start/end).
    A prop is a short cue, not a state: it
    pops in at the start of the FIRST line of a run of lines with the same prop, stays at most
    `hold` seconds (never past that line's end), and shrinks. The other lines of the run get none."""
    keys = []
    prev = None
    for i, l in enumerate(tl):
        kind = props.get(l["id"])
        first = kind is not None and kind != prev
        prev = kind
        if not first:
            continue
        t0 = max(0.0, l["start"] - 0.15)
        t1 = min(l["end"], l["start"] + hold)
        if i + 1 < len(tl):
            t1 = min(t1, tl[i + 1]["start"] - 0.2 - SHRINK)
        t1 = max(t1, t0 + GROW + 0.4)
        keys += [{"t": round(t0, 3), "face": {"prop": kind, "propAmt": 0}},
                 {"t": round(t0 + GROW, 3), "face": {"prop": kind, "propAmt": 1}},
                 {"t": round(t1, 3), "face": {"prop": kind, "propAmt": 1}},
                 {"t": round(t1 + SHRINK, 3), "face": {"prop": "none", "propAmt": 0}}]
    return keys


def lift_arms(keys, rest_upper=70.0, k_upper=1.45, k_lower=1.15):
    """Move the arms further from the rest pose (upper arms: angle below the horizontal; lower
    arms: elbow bend), so gesture hands rise into the bust window. Rest keys stay as they are."""
    out = []
    for key in keys:
        key = json.loads(json.dumps(key))
        b = key.get("bones")
        if b:
            for name, sgn in (("rightUpperArm", 1), ("leftUpperArm", -1)):
                v = b.get(name)
                if isinstance(v, list):
                    rest = sgn * rest_upper
                    z = rest + (v[2] - rest) * k_upper
                    v[2] = round(max(-80.0, min(80.0, z)) if sgn > 0 else max(-80.0, min(80.0, z)), 2)
            for name in ("rightLowerArm", "leftLowerArm"):
                v = b.get(name)
                if isinstance(v, list) and abs(v[2]) > 10:
                    v[2] = round(max(-150.0, min(150.0, v[2] * k_lower)), 2)
        out.append(key)
    return out


def merge_face_keys(keys, extra):
    """Add face-only keys to a key list (the motion's face track takes keys in time order)."""
    return sorted(keys + extra, key=lambda k: k["t"])
