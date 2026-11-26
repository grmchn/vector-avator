"""Acting layer of the explainer presenter (G12: id096-id099, G11: id094).

  act()       : content + script layer + avatar package -> performed lines (
                docs/explainer-format.md): the semantic tags become a gesture chosen with the
                character's gesture weights, a size and tempo, an expression and a voice.
  point_keys / beat_keys / pause_keys / GestureChooser : motion keys for build_timeline.py (G12).
The character habits come from the avatar package (data/characters/<id>.json `acting`,
tools/avatar/package.py); a name that is not a character gets the defaults.

  point_keys  : point at a region of the screen (layout.json) with an IK arm, eyes and face
                lead toward it and come back to the viewer at the end of the line.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "avatar"))
import layout as LAYOUT  # noqa: E402
import package as PKG  # noqa: E402


def r3(x):
    return round(float(x), 3)


def point_keys(region, t0, speech_end, t_next, lay, hand="point", reach_time=0.5, return_time=0.45):
    """Keys that point at `region` of the layout.

    t0         : start of the move (a little before the line starts: gestures lead the voice)
    speech_end : end of the line's voice; the face comes back to the viewer around it
    t_next     : the next line's move starts here; everything is back by then
    The arm is solved by the renderer (Pose.reach, core/ik.ts); the keys carry only the target
    (u, v of the presenter's canvas) and its weight.
    """
    X, Y = LAYOUT.region_point(lay, region)
    u, v = LAYOUT.screen_to_view(lay, X, Y)
    px = lay["presenter"]["cx"] * lay["size"][0]
    S = "L" if X >= px else "R"          # screen right = the character's left arm
    s = 1 if S == "L" else -1
    look = LAYOUT.look_angles(lay, X, Y)
    zero = {"yaw": 0, "pitch": 0, "gazeX": 0, "gazeY": 0}
    # timing: reach, hold through the line, return; squeezed when the window is short
    t_end = min(t_next - 0.05, max(speech_end + 0.35, t0 + reach_time + 0.6))
    t_hold = max(t0 + reach_time, t_end - return_time)
    face_back = max(t0 + reach_time + 0.3, min(speech_end - 0.1, t_hold))
    tgt = lambda w: {S: [r3(u), r3(v), w]}
    keys = [
        {"t": r3(t0), "reach": tgt(0), "face": dict(zero), "bones": {"chest": [0, 0, 0]}, "hips": [0, 0, 0]},
        # the eyes go first, the head follows (motion-rules M3)
        {"t": r3(t0 + 0.1), "face": {"gazeX": look["gazeX"], "gazeY": look["gazeY"]}},
        {"t": r3(t0 + 0.15), "hands": {S: hand}},
        {"t": r3(t0 + reach_time), "reach": tgt(1), "bones": {"chest": [0, s * 6, 0]}, "hips": [s * 0.012, 0, 0],
         "face": {"yaw": look["yaw"], "pitch": r3(look["pitch"] * 0.6)}},
        # back to the viewer at the end of the line, while the arm still points
        {"t": r3(face_back), "face": {"yaw": look["yaw"], "pitch": r3(look["pitch"] * 0.6), "gazeX": look["gazeX"], "gazeY": look["gazeY"]}},
        {"t": r3(face_back + 0.3), "face": dict(zero)},
        {"t": r3(t_hold), "reach": tgt(1), "bones": {"chest": [0, s * 6, 0]}, "hips": [s * 0.012, 0, 0]},
        {"t": r3(t_end - 0.15), "hands": {S: "open"}},
        {"t": r3(t_end), "reach": tgt(0), "bones": {"chest": [0, 0, 0]}, "hips": [0, 0, 0]},
    ]
    return sorted(keys, key=lambda k: k["t"])


def point_brief_keys(region, t0, t_next, lay, hold=0.8, hand="point", reach_time=0.45, return_time=0.4,
                     glance=0.5, look_amount=0.5):
    """A short point at `region`: reach, hold `hold` seconds, return; the eyes and the head
    only glance at the region (`glance` seconds, `look_amount` of the full look angle) and come back
    to the viewer while the arm still points. Returns (keys, t_end, quiet) where t_end is when the
    arm is back at rest (the line's own gesture can start after it) and quiet = (start, end) of the
    glance (no head sway there).

    Owner 2026-11-22: the presenter looks at the camera most of the time; looking at the
    figure is only a lead for the viewer's eyes, and a turned face shows the drawing's limits."""
    X, Y = LAYOUT.region_point(lay, region)
    u, v = LAYOUT.screen_to_view(lay, X, Y)
    px = lay["presenter"]["cx"] * lay["size"][0]
    S = "L" if X >= px else "R"
    s = 1 if S == "L" else -1
    look = LAYOUT.look_angles(lay, X, Y)
    zero = {"yaw": 0, "pitch": 0, "gazeX": 0, "gazeY": 0}
    t_end = min(t_next - 0.05, t0 + reach_time + hold + return_time)
    t_hold = max(t0 + reach_time, t_end - return_time)
    g_end = min(t_hold, t0 + reach_time + glance)
    see = {"yaw": r3(look["yaw"] * look_amount), "pitch": r3(look["pitch"] * look_amount * 0.6),
           "gazeX": look["gazeX"], "gazeY": r3(look["gazeY"] * 0.8)}
    tgt = lambda w: {S: [r3(u), r3(v), w]}
    keys = [
        {"t": r3(t0), "reach": tgt(0), "face": dict(zero), "bones": {"chest": [0, 0, 0]}, "hips": [0, 0, 0]},
        {"t": r3(t0 + 0.08), "face": {"gazeX": look["gazeX"], "gazeY": r3(look["gazeY"] * 0.8)}},
        {"t": r3(t0 + 0.12), "hands": {S: hand}},
        {"t": r3(t0 + reach_time), "reach": tgt(1), "bones": {"chest": [0, s * 6, 0]}, "hips": [s * 0.012, 0, 0], "face": dict(see)},
        {"t": r3(g_end), "face": dict(see)},
        {"t": r3(g_end + 0.28), "face": dict(zero)},
        {"t": r3(t_hold), "reach": tgt(1), "bones": {"chest": [0, s * 6, 0]}, "hips": [s * 0.012, 0, 0]},
        {"t": r3(t_end - 0.12), "hands": {S: "open"}},
        {"t": r3(t_end), "reach": tgt(0), "bones": {"chest": [0, 0, 0]}, "hips": [0, 0, 0]},
    ]
    return sorted(keys, key=lambda k: k["t"]), t_end, (t0, g_end + 0.3)


# ------------------------------------------------------------------ head sway
def sway_keys(lines, total, rng, yaw=7.0, roll=4.0, quiet=()):
    """Additive face keys: the head turns a little from side to side and tilts now and then while
    the presenter talks, so the face is never fixed square to the camera.

    A new head target every 1.3-2.4 s during each line: yaw up to `yaw` deg (the side mostly
    alternates), roll mostly small with an occasional clear tilt up to `roll` deg. Inside the `quiet`
    windows (glances at the figure, the pause acts) the sway goes back to 0, so the layers do not
    add up to a large head turn."""
    def in_quiet(t, pad=0.25):
        return any(a - pad <= t <= b + pad for a, b in quiet)

    keys = [{"t": 0.0, "face": {"yaw": 0, "roll": 0}}]
    for a, b in quiet:
        keys += [{"t": r3(max(0.0, a - 0.2)), "face": {"yaw": 0, "roll": 0}}, {"t": r3(b + 0.2), "face": {"yaw": 0, "roll": 0}}]
    sign = rng.choice((-1, 1))
    for l in lines:
        t = l["start"] + rng.uniform(0.2, 0.6)
        while t < l["end"] - 0.5:
            if not in_quiet(t):
                sign = -sign if rng.random() < 0.75 else sign
                y = sign * yaw * rng.uniform(0.35, 1.0)
                r = (rng.choice((-1, 1)) * roll * rng.uniform(0.7, 1.0)) if rng.random() < 0.3 else rng.uniform(-0.35, 0.35) * roll
                keys.append({"t": r3(t), "face": {"yaw": r3(y), "roll": r3(r)}})
            t += rng.uniform(1.3, 2.4)
        if not in_quiet(l["end"] + 0.4):
            keys.append({"t": r3(l["end"] + 0.4), "face": {"yaw": 0, "roll": 0}})
    keys.append({"t": r3(total), "face": {"yaw": 0, "roll": 0}})
    return sorted(keys, key=lambda k: k["t"])


# ------------------------------------------------------------------ beats
# Character habits: from the avatar package (acting.beat), see habits_for()
DEFAULT_HABITS = {"beat_amp": 1.0, "beat_rate": 1.0}


def habits_for(char):
    """Beat habits of a character from its avatar package; defaults for a name that is not one."""
    if not char or not PKG.path_of(char).is_file():
        return dict(DEFAULT_HABITS)
    b = PKG.load(char)["acting"]["beat"]
    return {"beat_amp": float(b["amp"]), "beat_rate": float(b["rate"])}

# which body parts give the beat while a gesture is on (the gesture's own arm(s) only;
# a pointing or thinking arm stays still, a nodding head is left alone)
BEAT_PARTS = {
    "explain": {"head", "chest", "R"},
    "spread": {"head", "chest", "L", "R"},
    "point": {"head", "chest"},
    "think": {"chest"},
    "idea": {"head", "chest"},
    "nod": set(), "surprise": set(),
    "idle": {"head", "chest"}, "turn": {"chest"},
}
# peak of one beat at amplitude 1 (local rotations added on top of the gesture, deg)
BEAT_POSE = {
    "head": {"head": [4.0, 0, 0]},
    "chest": {"chest": [1.5, 0, 0]},
    "R": {"rightLowerArm": [0, 0, 9.0], "rightHand": [0, 0, 12.0]},
    "L": {"leftLowerArm": [0, 0, -9.0], "leftHand": [0, 0, -12.0]},
}


def beat_keys(beats, parts, amp, lead=0.12, rise=0.1, fall=0.26, emph_gain=1.35):
    """Additive keys (MotionJson.additive) for the chosen beats: a quick down-stroke that peaks
    `lead` seconds before the stressed syllable (gestures lead the voice) and a slower return."""
    if amp <= 0 or not parts:
        return []
    bones = {}
    for p in parts:
        bones.update(BEAT_POSE[p])
    zero = {b: [0, 0, 0] for b in bones}
    keys = []
    for c in beats:
        k = amp * (emph_gain if "emphasis" in c["kind"] else 1.0)
        tp = c["t"] - lead
        keys += [{"t": r3(tp - rise), "bones": dict(zero)},
                 {"t": r3(tp), "bones": {b: [round(v * k, 2) for v in e] for b, e in bones.items()}},
                 {"t": r3(tp + fall), "bones": dict(zero)}]
    return keys


# ------------------------------------------------------------------ variety
# variations per gesture tag (data/motions/explainer_vocab/, tools/explainer/make_vocab.py)
# and the arm(s) they use: R / L / B (both) / "" (none)
VOCAB = {
    "explain": [("explain_r", "R"), ("explain_l", "L"), ("explain_both", "B"), ("explain_mb", "B")],
    "spread": [("spread_big", "B"), ("spread_small", "B"), ("spread_one_l", "L"), ("spread_mb", "B")],
    "point": [("point_l", "L"), ("point_l_small", "L"), ("point_r", "R")],
    "nod": [("nod_double", ""), ("nod_once", ""), ("nod_tilt", "")],
    "think": [("think_r", "R"), ("think_l", "L")],
    "idea": [("idea_r", "R"), ("idea_l", "L")],   # bust framing: the arm up beside the face, a light bulb over the head
    "surprise": [("surprise_big", "B"), ("surprise_small", "B"), ("surprise_mb", "B")],   # *_mb: MotionBricks
}


class GestureChooser:
    """Picks a variation for each gesture tag: never the same variation twice in a row,
    one-handed gestures alternate sides, otherwise random (seeded, so a build is reproducible)."""

    def __init__(self, rng, prefer=None):
        self.rng = rng
        self.prev = None
        self.last_side = None
        self.last_of = {}
        # tag -> side the gesture must use (pointing goes toward the image: the screen right
        # is the character's left)
        self.prefer = prefer or {}

    def choose(self, tag):
        opts = VOCAB.get(tag)
        if not opts:
            return None, None
        if tag in self.prefer:
            opts = [o for o in opts if o[1] == self.prefer[tag]] or opts
        # not the variation used last (overall, or the last time this tag came)
        c = [o for o in opts if o[0] != self.prev and o[0] != self.last_of.get(tag)] or \
            [o for o in opts if o[0] != self.prev] or opts
        if self.last_side in ("L", "R") and tag not in self.prefer:
            other = [o for o in c if o[1] != self.last_side]
            c = other or c
        name, side = c[self.rng.randrange(len(c))]
        self.prev = name
        self.last_of[tag] = name
        if side in ("L", "R"):
            self.last_side = side
        return name, side


def jitter(keys, rng, dt=0.04, deg=2.5):
    """Small random changes of the inner keys' times and angles, so a gesture is never
    repeated exactly. The first and last keys (the rest pose at both ends) stay."""
    if len(keys) < 3 or len(keys) > 16:   # dense keys (MotionBricks, 30 fps) would only get noise
        return keys
    out = [dict(k) for k in keys]
    for i in range(1, len(out) - 1):
        k = out[i]
        lo, hi = out[i - 1]["t"] + 0.02, keys[i + 1]["t"] - 0.02
        if hi > lo:
            k["t"] = r3(min(hi, max(lo, k["t"] + rng.uniform(-dt, dt))))
        if "bones" in k:
            k["bones"] = {b: [round(v + (rng.uniform(-deg, deg) if abs(v) > 1e-6 else 0.0), 2) for v in e]
                          for b, e in k["bones"].items()}
    return out


def beat_parts(tag, side):
    """Parts that beat for a gesture variation (BEAT_PARTS, with the variation's own arm)."""
    parts = set(BEAT_PARTS.get(tag, {"head", "chest"}))
    if side and parts & {"L", "R"}:
        parts -= {"L", "R"}
        parts |= {"L", "R"} if side == "B" else {side}
    return parts


# ------------------------------------------------------------------ pauses
PAUSE_ACTS = ("nod", "tilt", "none")


def pause_keys(lines, total, lay, rng, card_region="card", pointing=False, brief_points=False):
    """Additive keys for the silences between lines.

    - same scene (short gap): at the end of a line, a small closing nod or a head tilt, chosen
      at random but not twice in a row; skipped after nodding or pointing lines.
    - scene change to a line that brings a new image: the eyes and the head glance at the image
      during the gap and come back to the viewer as the next line starts.
    """
    keys, prev = [], None
    look = LAYOUT.look_angles(lay, *LAYOUT.region_point(lay, card_region))
    for i, l in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        gap_end = nxt["start"] if nxt else total
        e = l["end"]
        new_image = nxt and nxt.get("icon") and nxt.get("icon") != l.get("icon")
        # a pointing line looks at the image by itself: no glance before it (the two
        # would add up to a head turn past the +-30 deg of the front head)
        next_points = pointing and nxt and nxt.get("point_at")
        if nxt and nxt["scene"] != l["scene"] and new_image and gap_end - e >= 0.4 and not next_points:
            a, b = e + 0.02, gap_end + 0.05
            m = (a + b) / 2
            keys += [{"t": r3(a), "face": {"yaw": 0, "gazeX": 0, "gazeY": 0, "pitch": 0}},
                     {"t": r3(a + 0.12), "face": {"gazeX": look["gazeX"], "gazeY": look["gazeY"] * 0.6}},
                     {"t": r3(m), "face": {"yaw": r3(look["yaw"] * 0.6), "pitch": r3(look["pitch"] * 0.4),
                                            "gazeX": look["gazeX"], "gazeY": r3(look["gazeY"] * 0.6)}},
                     {"t": r3(b + 0.25), "face": {"yaw": 0, "gazeX": 0, "gazeY": 0, "pitch": 0}}]
            prev = "glance"
            continue
        if l.get("gesture") in ("nod", "point") or (l.get("point_at") and not brief_points):
            continue
        acts = [a for a in PAUSE_ACTS if a != prev] if prev in PAUSE_ACTS and prev != "none" else list(PAUSE_ACTS)
        act = acts[rng.randrange(len(acts))]
        prev = act
        if act == "nod":
            keys += [{"t": r3(e - 0.12), "bones": {"head": [0, 0, 0]}},
                     {"t": r3(e + 0.08), "bones": {"head": [7, 0, 0]}},
                     {"t": r3(e + 0.4), "bones": {"head": [0, 0, 0]}}]
        elif act == "tilt":
            s = rng.choice((-1, 1))
            keys += [{"t": r3(e - 0.1), "face": {"roll": 0}},
                     {"t": r3(e + 0.15), "face": {"roll": 5 * s}},
                     {"t": r3(min(gap_end + 0.6, e + 0.9)), "face": {"roll": 0}}]
    return keys


# ------------------------------------------------------------------ body angle
def track_at(track, t):
    """Value of a key track [(t, v)] at time t, eased like the motions' "smooth" keys
    (smoothstep between neighbouring keys, held before the first and after the last)."""
    if not track:
        return 0.0
    if t <= track[0][0]:
        return track[0][1]
    for (t0, v0), (t1, v1) in zip(track, track[1:]):
        if t0 <= t <= t1:
            a = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * a * a * (3 - 2 * a)
    return track[-1][1]


def weight_keys(lines, total, rng, amp=0.045, roll_per_m=110.0, spine=1.3, every=(2.5, 4.0), ramp=0.6):
    """Weight shifts (motion rules R2/R3, docs/motion-rules.md M16/M21): a standing speaker moves
    the weight from foot to foot every few seconds, so the hips travel over the supporting foot and
    tilt (the hip over it rises), and the shoulders lean the other way (contrapposto).

    A shift starts `every` seconds after the last one; when a line starts a little later (within
    0.8 s), it waits for the line start (a new sentence is a natural moment). The side alternates.
    Each shift takes `ramp` seconds and is then held. Returns the additive keys for the hips
    position and the spine's counter-tilt, and the track of the hips bone's roll [(t, deg)], which
    body_keys merges with the body turn (both turn the hips bone). The figure stands square at both
    ends. Draw with vPlant=2 (feet planted), as capture.sh does."""
    end = min(total, lines[-1]["end"] + 0.7) if lines else total
    starts = [max(0.0, l["start"] - 0.15) for l in lines]
    shifts = []   # (time the shift starts, side)
    side = rng.choice((-1.0, 1.0))
    t = starts[0] if starts else end
    while t + ramp < end - ramp:
        snap = [s for s in starts if t <= s <= t + 0.8]
        t = snap[0] if snap else t
        shifts.append((t, side))
        side = -side
        t += rng.uniform(*every)
    xs = [(0.0, 0.0)]
    for t, s in shifts:
        if t + ramp >= end:
            break
        x = s * amp * rng.uniform(0.8, 1.15)
        xs += [(r3(t), xs[-1][1]), (r3(t + ramp), round(x, 4))]
    xs += [(r3(max(xs[-1][0], end - ramp)), xs[-1][1]), (r3(end), 0.0)]
    keys = []
    for t, x in xs:
        roll = round(x * roll_per_m, 2)
        keys.append({"t": t, "hips": [x, 0, 0], "bones": {"spine": [0, 0, round(-roll * spine, 2)]}})
    roll_track = [(t, round(x * roll_per_m, 2)) for t, x in xs]
    return keys, roll_track


# how long an expression other than neutral is shown in a line (motion rules R5, M17): the
# smiling eyes close the irises, so they are an accent at the end of a line (its punch), not a state
EXPR_ACCENT = {"smile": ("end", 1.2), "surprised": ("start", 1.0), "troubled": ("start", 1.8)}


def expression_keys(line, g0, nxt, short=2.2):
    """Face keys of a line's expression with neutral eyes most of the time (R5): a smile only for
    the last 1.2 s of the line (held through the pause after it), surprise and trouble for the
    first 1.0 / 1.8 s. A short line (< `short` s) keeps its expression throughout."""
    e = line["expr"]
    if e not in EXPR_ACCENT or line["end"] - line["start"] < short:
        return [{"t": r3(g0), "face": {"expression": e}}]
    where, dur = EXPR_ACCENT[e]
    if where == "end":
        t = max(g0 + 0.3, line["end"] - dur)
        return [{"t": r3(g0), "face": {"expression": "neutral"}}, {"t": r3(t), "face": {"expression": e}}]
    t = min(g0 + dur, nxt - 0.2)
    return [{"t": r3(g0), "face": {"expression": e}}, {"t": r3(t), "face": {"expression": "neutral"}}]


def body_keys(lines, total, lay, rng, max_deg=30.0, card_region="card", small=(7.0, 15.0), big=(20.0, 28.0),
              roll_track=None):
    """Additive keys for a slight turn of the whole body (hips yaw), at most `max_deg` degrees.

    The body sways from side to side across the lines instead of staying square to the camera (the
    difference between a flat 2D puppet and a Live2D-like performer): each line turns the body to
    a small angle (`small`), a surprised line to a bigger one (`big`); the sign alternates, so the
    presenter does not lean one way for long. A line that points at the card turns toward it
    (the same sign as the face's look angle toward the card). The body rests square at both ends.
    The change between two lines happens in the gap before the next line, taking 0.6 s.
    """
    look = LAYOUT.look_angles(lay, *LAYOUT.region_point(lay, card_region))
    toward = 1.0 if look["yaw"] >= 0 else -1.0
    keys = [{"t": 0.0, "bones": {"hips": [0, 0, 0]}}]
    sign, prev = -toward, 0.0
    for i, l in enumerate(lines):
        if l.get("point_at"):
            sign, mag = toward, rng.uniform(*small) * 0.8
        else:
            sign = -sign if rng.random() < 0.8 else sign
            mag = rng.uniform(*(big if l.get("expr") == "surprised" else small))
        yaw = round(max(-max_deg, min(max_deg, sign * mag)), 2)
        t_in = max(0.0, l["start"] - 0.15)
        keys.append({"t": r3(t_in), "bones": {"hips": [0, prev, 0]}})
        keys.append({"t": r3(t_in + 0.6), "bones": {"hips": [0, yaw, 0]}})
        prev = yaw
    keys.append({"t": r3(lines[-1]["end"]), "bones": {"hips": [0, prev, 0]}})
    keys.append({"t": r3(min(total, lines[-1]["end"] + 0.7)), "bones": {"hips": [0, 0, 0]}})
    if roll_track:
        # the weight shifts (weight_keys) tilt the same hips bone: one track with both, keyed at
        # every time either changes (keys of one bone from two layers would undo each other)
        yaw_track = sorted({k["t"]: k["bones"]["hips"][1] for k in keys}.items())
        times = sorted({t for t, _ in yaw_track} | {t for t, _ in roll_track})
        keys = [{"t": t, "bones": {"hips": [0, round(track_at(yaw_track, t), 2), round(track_at(roll_track, t), 2)]}}
                for t in times]
    return keys


# ------------------------------------------------------------------ tags -> acting
# gesture candidates of each semantic tag (docs/explainer-format.md §3): (gesture, base weight).
# "nod:nod_tilt" = the gesture with a fixed variation. The first candidate is the tag's own
# meaning; the others are what a character may prefer instead (acting.gestureWeights).
TAG_CANDIDATES = {
    "greet": [("spread", 1.0), ("explain", 0.3)],
    "introduce": [("explain", 1.0), ("spread", 0.4)],
    "enumerate": [("explain", 1.0), ("point", 0.5)],
    "emphasize": [("spread", 1.0), ("explain", 0.5)],
    "point_at": [("point", 1.0)],
    "question": [("nod:nod_tilt", 1.0), ("think", 0.5)],
    "think": [("think", 1.0)],
    "surprise": [("surprise", 1.0)],
    "agree": [("nod", 1.0)],
    "contrast": [("explain", 1.0), ("spread", 0.3)],
    "conclude": [("nod", 1.0), ("spread", 0.5)],
}
TAG_ORDER_WEIGHT = (1.0, 0.5, 0.3)     # the line's 1st, 2nd, 3rd+ tag
SHARPEN = 2.0                         # weight ** SHARPEN: the tag's own meaning stays the likely pick
STRENGTH_SCALE = {"weak": 0.75, "mid": 1.0, "strong": 1.25}
EMOTION_EXPR = {"calm": "neutral", "joy": "smile", "surprise": "surprised", "trouble": "troubled"}


def gesture_weights(cline, pkg):
    """{(gesture, variant): weight} of a content line for a character."""
    prefs = pkg["acting"].get("gestureWeights") or {}
    out = {}
    tags = [t for t in cline.get("tags", []) if "term" not in t and t["tag"] != "demo"]
    for i, t in enumerate(tags):
        w0 = TAG_ORDER_WEIGHT[min(i, len(TAG_ORDER_WEIGHT) - 1)]
        for cand, base in TAG_CANDIDATES[t["tag"]]:
            g, _, var = cand.partition(":")
            key = (g, var or None)
            out[key] = out.get(key, 0.0) + w0 * base * float(prefs.get(g, 1.0))
    return out


def pick(weights, rng):
    keys = sorted(weights, key=lambda k: (k[0], k[1] or ""))
    w = [weights[k] ** SHARPEN for k in keys]
    x = rng.uniform(0, sum(w))
    for k, wk in zip(keys, w):
        x -= wk
        if x <= 0:
            return k
    return keys[-1]


def act_line(cline, sline, pkg, rng):
    """One performed line: the legacy script fields (build_timeline.py) + size, tempo and voice."""
    tags = [t for t in cline.get("tags", []) if "term" not in t]
    ov = sline.get("override", {})
    variant = None
    if ov.get("gesture"):
        gesture, source = ov["gesture"], "override"
    elif tags and tags[0]["tag"] == "demo":
        gesture, source = tags[0]["motion"], "demo"
    elif not tags:
        gesture, source = "explain", "no tag"
    else:
        gesture, variant = pick(gesture_weights(cline, pkg), rng)
        source = "tags"
    strength = next((t.get("strength") for t in tags if t["tag"] != "demo"), None) or "mid"
    expr = ov.get("expr") or EMOTION_EXPR[cline.get("emotion", "calm")]
    a = pkg["acting"]
    out = {"id": cline["id"], "scene": cline["scene"], "icon": (cline.get("visual") or {}).get("image", ""),
           "card_text": ((cline.get("visual") or {}).get("text") or {}).get("ja", ""),
           "gesture": gesture, "expr": expr, "gesture_source": source,
           "scale": round(STRENGTH_SCALE[strength] * float(a["gestureScale"]), 3), "tempo": float(a["tempo"]),
           "voice": PKG.voice_for(pkg, "ja", expr), "tts_emotion": PKG.emotion_for(pkg, expr)}
    if variant:
        out["variant"] = variant
    pt = next((t for t in cline.get("tags", []) if t["tag"] == "point_at" and "region" in t), None)
    if pt:
        out["point_at"] = pt["region"]
    emph = [sline["anchors"][t["term"]]["kana"] for t in cline.get("tags", [])
            if t["tag"] == "emphasize" and "term" in t]
    if emph:
        out["emphasize"] = emph
    for k in ("ja", "ja_tts", "ja_kana", "en", "en_tts"):
        if k in sline:
            out[k] = sline[k]
    return out


def act(content, script, pkg, seed=94):
    """content + script layer + package -> performed script (the legacy form plus acting fields).
    The same inputs and seed always give the same result."""
    import random
    rng = random.Random(f"{seed}:{content['id']}:{script['char']}")
    by_id = {ln["id"]: ln for ln in script["lines"]}
    lines = [act_line(cl, by_id[cl["id"]], pkg, rng) for cl in content["lines"]]
    return {"title": content["title"].get("ja", content["id"]), "content": content["id"], "char": script["char"],
            "seed": seed, "lines": lines}
