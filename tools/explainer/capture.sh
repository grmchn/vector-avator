#!/usr/bin/env bash
# Capture the presenter of an explainer video (the general form of var/explainer/capture_presenters.sh).
#   bash tools/explainer/capture.sh <char> <motion> <seconds> <out.mp4> [lipsync]
#     motion  : a motion name (data/motions/explainer/<motion>.json, e.g. agi_singularity_usagi_ja)
#     lipsync : lip-sync keys under public/ (default audio/<motion>.json)
# The background colour comes from the avatar package (capture.bg). Uses the capture server
# (tools/explainer/capserver.sh, restarted here so a new motion is loaded) unless VIEWER_URL is set.
# Env: DSF (default 2), OUT_FPS (24), FPS (24), CAPTURE_PORT (5285), NO_RESTART=1 (keep the server),
#      BG (override the package's capture.bg), EXTRA (more query), FRAMING=bust (head-and-chest window
#      with the package's capture.bust), TURN (1 = load the turned body / head drawings,
#      body30/60/90.json and head30/60/90.json, so the body turns past 15 deg; 0 = front views only).
set -euo pipefail
cd "$(dirname "$0")/../.."
C=${1:?usage: capture.sh <char> <motion> <seconds> <out.mp4> [lipsync]}
M=${2:?motion}; SECS=${3:?seconds}; OUT=${4:?out.mp4}; LIPS=${5:-audio/$M.json}
if [ -z "${VIEWER_URL:-}" ]; then
  [ -n "${NO_RESTART:-}" ] || bash tools/explainer/capserver.sh
  export VIEWER_URL=http://127.0.0.1:${CAPTURE_PORT:-5285}/
fi
BG=${BG:-}
[ -n "$BG" ] || BG=$(.venv/bin/python -c "import sys; sys.path.insert(0,'tools/avatar'); import package as P; print(P.load('$C')['capture']['bg'])")
# FRAMING=bust: the head-and-chest window, with the package's capture.bust tuning
if [ "${FRAMING:-}" = "bust" ]; then
  EXTRA="${EXTRA:-}$(.venv/bin/python -c "import sys; sys.path.insert(0,'tools/avatar'); import package as P; print(P.bust_query(P.load('$C')))")"
fi
PREFIX=${OUT%.mp4}
start=$(date +%s)
DSF=${DSF:-2} OUT_FPS=${OUT_FPS:-24} node tools/capture/sequence.mjs "$PREFIX" \
  "char=$C&renderer=V&motion=$M&lipsync=$LIPS&blink=1&vPlant=2&vBody=${TURN:-0}&bg=$BG${EXTRA:-}" "${FPS:-24}" "$SECS" > /dev/null
rm -rf "${PREFIX}_frames"
echo "captured $OUT ($SECS s of video in $(( $(date +%s) - start )) s)"
