#!/bin/sh
# Rebuild the README screenshots, demo GIF and social preview from a synthetic archive.
# Needs Playwright with Chromium and Pillow in python3. Writes into docs/media/.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
PORT=8790
DEMO=$(mktemp -d)
export ARTIKEEP_HOME="$DEMO"
git -C "$DEMO" init -q -b main
echo '{"git_push": false, "issue_links": false, "notify": false, "lang": "en"}' > "$DEMO/artikeep.json"
python3 "$HERE/seed.py" "$REPO"
python3 "$REPO/bin/artikeep" rebuild --no-push
python3 "$REPO/bin/artikeep" serve --port $PORT > "$DEMO/serve.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; rm -rf "$DEMO"' EXIT
sleep 2
python3 "$HERE/capture.py" "$REPO/docs/media"
python3 "$HERE/render.py"
