#!/usr/bin/env bash
# MiniMax H3 360-degree turntable of the adopted front image, used as an angle reference (optional).
# usage: bash tools/vector/sheets/turntable.sh <id> [seed]
# needs: a ComfyUI server with MiniMax H3 (env COMFY_SERVER, default http://127.0.0.1:8188), ffmpeg
# out:   public/characters/<id>/vector/ref/turntable.mp4, angle_000/030/045/090/180/270.png
set -euo pipefail
cd "$(dirname "$0")/../../.."
id=$1; seed=${2:-1}
py=${PYTHON:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)}
ref=public/characters/$id/vector/ref
work=var/vector/$id/h3; mkdir -p "$work"
# pad the portrait front image to a square (H3 renders a square video)
"$py" - "$ref/front.png" "$work/front_sq.png" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB")
s = max(im.size); out = Image.new("RGB", (s, s), im.getpixel((2, 2)))
out.paste(im, ((s - im.width) // 2, (s - im.height) // 2)); out.resize((768, 768), Image.LANCZOS).save(sys.argv[2])
PY
start=$(date +%s)
"$py" tools/h3/turntable.py "$work/front_sq.png" "tools/vector/sheets/h3/$id.txt" "$ref/turntable.mp4" \
  --seconds 8 --size 768 --seed "$seed" --server "${COMFY_SERVER:-http://127.0.0.1:8188}" | tee "$work/run.log"
# angle frames (turning to its right: 1 s = 45 deg, 2 s = 90 deg (left profile), 4 s = back)
for a in 000:0 030:0.667 045:1.0 090:2.0 180:4.0 270:6.0; do
  ffmpeg -loglevel error -y -ss "${a#*:}" -i "$ref/turntable.mp4" -frames:v 1 "$ref/angle_${a%%:*}.png"
done
echo "turntable $id done in $(( $(date +%s) - start ))s"
