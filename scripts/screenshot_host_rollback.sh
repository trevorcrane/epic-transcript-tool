#!/usr/bin/env bash
# Restore installer source files only. Never prints RESTART=allowed.
# Does not copy DEST, and does not delete or replace live data, .env, or plist.
# Required bindings: ROOT BACKUP
# Optional: ARTIFACT (unused, accepted so the same environment can call this)
#            DEST (refused if BACKUP points at it)

set -u
set -o pipefail

deny() {
  printf '%s\n' "RESTART=no"
  exit "${1:-1}"
}

if [ -z "${ROOT:-}" ] || [ ! -d "$ROOT" ] || [ -z "${BACKUP:-}" ] || [ ! -d "$BACKUP" ]; then
  deny 1
fi
if [ -n "${DEST:-}" ]; then
  case "$BACKUP" in
    "$DEST"|"$DEST"/*) deny 1 ;;
  esac
fi
case "$BACKUP" in
  "$ROOT/data"|"$ROOT/data"/*) deny 1 ;;
esac
if [ ! -f "$BACKUP/app.py" ]; then
  deny 1
fi

while IFS= read -r rel; do
  case "$rel" in
    ""|data/*|.env|*.plist) deny 1 ;;
  esac
  if [ -f "$BACKUP/$rel" ]; then
    mkdir -p "$ROOT/$(dirname -- "$rel")" || deny $?
    cp "$BACKUP/$rel" "$ROOT/$rel" || deny $?
  elif [ -e "$ROOT/$rel" ] || [ -L "$ROOT/$rel" ]; then
    rm -f "$ROOT/$rel" || deny $?
  fi
done <<'FILES'
app.py
static/index.html
Dockerfile
README.md
screenshots.py
docs/SCREENSHOT_DEPLOY.md
docs/screenshot-install-manifest.json
scripts/screenshot_host_preflight.py
scripts/screenshot_host_apply.py
FILES

printf '%s\n' "ROLLBACK=ok"
printf '%s\n' "RESTART=no"
exit 0
