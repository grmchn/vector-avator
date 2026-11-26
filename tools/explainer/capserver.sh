#!/usr/bin/env bash
# (Re)start the explainer capture dev server (no watch, no HMR; tools/explainer/vite.capture.config.ts)
# and wait until it answers. The motions are loaded at start, so restart it after build_timeline.py.
#   bash tools/explainer/capserver.sh          (port: CAPTURE_PORT, default 5285)
#   bash tools/explainer/capserver.sh stop
set -euo pipefail
cd "$(dirname "$0")/../.."
PORT=${CAPTURE_PORT:-5285}
mkdir -p var/explainer
PID=var/explainer/capserver_$PORT.pid
if [ -f "$PID" ]; then kill "$(cat "$PID")" 2>/dev/null || true; rm -f "$PID"; sleep 1; fi
[ "${1:-}" = stop ] && { echo "capture server on :$PORT stopped"; exit 0; }
CAPTURE_PORT=$PORT nohup node node_modules/vite/bin/vite.js --config tools/explainer/vite.capture.config.ts \
  > "var/explainer/capserver_$PORT.log" 2>&1 &
echo $! > "$PID"
for _ in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1; done
curl -s -o /dev/null "http://127.0.0.1:$PORT/" || { echo "capture server did not start (var/explainer/capserver_$PORT.log)" >&2; exit 1; }
echo "capture server on :$PORT"
