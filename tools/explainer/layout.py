"""Screen layout of the explainer video: one file (layout.json) read by the compositor
(simple_compose.py) and by the acting layer (perform.py), so the presenter points at the place
where the image is actually drawn.

Coordinates:
  screen  : pixels of the final video (layout["size"]), origin top-left.
  view    : the presenter's viewer canvas, u/v = 0..1 of its width/height (Pose.reach in
            src/core/pose.ts). The compositor crops the centre `crop` of the presenter video's
            width, scales it to `ph` of the frame height, centres it at x = `cx` and puts its top
            at y = `py` (all fractions of the frame).
"""
import json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "layout.json"


def load(path=None):
    return json.load(open(path or DEFAULT))


def region_point(lay, name, anchor=(0.5, 0.5)):
    """A point of a named region in screen pixels (anchor: fractions of the region box)."""
    W, H = lay["size"]
    r = lay["regions"][name]
    return ((r["x"] + r["w"] * anchor[0]) * W, (r["y"] + r["h"] * anchor[1]) * H)


def screen_to_view(lay, X, Y):
    """Screen pixels -> presenter canvas (u, v)."""
    W, H = lay["size"]
    p = lay["presenter"]
    hh = p["ph"] * H                      # presenter height on screen
    ww = p["crop"] * p["aspect"] * hh     # width of the cropped strip on screen
    x0 = p["cx"] * W - ww / 2
    y0 = p["py"] * H
    u = (1 - p["crop"]) / 2 + (X - x0) / (p["aspect"] * hh)
    v = (Y - y0) / hh
    return (u, v)


def view_to_screen(lay, u, v):
    W, H = lay["size"]
    p = lay["presenter"]
    hh = p["ph"] * H
    ww = p["crop"] * p["aspect"] * hh
    x0 = p["cx"] * W - ww / 2
    return (x0 + (u - (1 - p["crop"]) / 2) * p["aspect"] * hh, p["py"] * H + v * hh)


def head_screen(lay):
    """Approximate head centre of the presenter on screen (presenter.head is in view u/v)."""
    return view_to_screen(lay, *lay["presenter"]["head"])


def look_angles(lay, X, Y):
    """Face yaw/pitch and gaze (deg) to look at a screen point; + yaw = the character's left
    = the viewer's right. Kept small (motion-rules M3): the eyes do more than the head."""
    W, H = lay["size"]
    hx, hy = head_screen(lay)
    dx, dy = (X - hx) / W, (Y - hy) / H
    clamp = lambda x, a: max(-a, min(a, x))
    yaw = clamp(math.degrees(math.atan2(dx, 0.55)), 22)
    pitch = clamp(math.degrees(math.atan2(-dy, 0.8)), 10)
    return {"yaw": round(yaw, 1), "pitch": round(pitch, 1),
            "gazeX": round(clamp(yaw * 1.2, 26), 1), "gazeY": round(clamp(pitch * 1.6, 16), 1)}
