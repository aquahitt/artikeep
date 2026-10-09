#!/bin/bash
# Live check of the Codex adapter: one real Codex turn writes a report outside git,
# then the Stop hook must have archived it. Uses one short Codex request.
#   scripts/e2e-codex.sh [model]      (default: gpt-5.5)
set -u
MODEL="${1:-gpt-5.5}"
WORK="$(mktemp -d /tmp/artikeep-e2e-XXXX)"
STAMP="e2e-$(date +%s)"
ARCHIVE="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from artikeep import config; print(config.home())' "$(cd "$(dirname "$0")/.." && pwd)")"
cd "$WORK" || exit 1
echo "work: $WORK   archive: $ARCHIVE   marker: $STAMP"
codex exec -m "$MODEL" -c service_tier=default --skip-git-repo-check -s workspace-write \
  "Create the file report.md in the current folder with exactly two lines: '# artikeep $STAMP' and 'Codex wrote this.'. Then reply with the absolute path of the file." \
  < /dev/null 2>&1 | grep -v '^warning' | tail -4
[ -f report.md ] || { echo "FAIL: Codex did not write report.md (limit, model, sandbox?)"; exit 1; }
for _ in 1 2 3 4 5 6 7 8 9 10; do
  grep -q "$STAMP" "$ARCHIVE/manifest.json" 2>/dev/null && break
  grep -rqs "$STAMP" "$ARCHIVE/items" && break
  sleep 1
done
if grep -rqs "artikeep $STAMP" "$ARCHIVE/items"; then
  echo "ok: report archived -> $(grep -rls "artikeep $STAMP" "$ARCHIVE/items" | head -1)"
else
  echo "FAIL: report not in the archive"
fi
echo "last codex-stop hook calls:"
grep '"codex-stop"' "$ARCHIVE/.hooklog/payloads.jsonl" 2>/dev/null | tail -2 | cut -c1-300
tail -3 "$ARCHIVE/.hooklog/errors.log" 2>/dev/null
