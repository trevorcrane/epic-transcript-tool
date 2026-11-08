#!/usr/bin/env bash
# Restore installer source files only. Never prints RESTART=allowed.
# Does not copy DEST, and does not delete or replace live data, .env, or plist.
# Required: ROOT, BACKUP, ARTIFACT.
# ARTIFACT is the unpacked pack. The confinement checker lives there and is not
# copied onto ROOT. PY, when set and executable, is the identity program.
# Otherwise the script uses python3 on PATH. DEST is optional and is refused
# when BACKUP points at it. This command does not grant a manual bootstrap.

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

py="${PY:-}"
if [ -z "$py" ] || [ ! -x "$py" ]; then
  py=$(command -v python3 || true)
fi
checker=""
if [ -n "${ARTIFACT:-}" ]; then
  checker="$ARTIFACT/scripts/screenshot_host_offline_checks.py"
fi
if [ -z "$py" ] || [ -z "$checker" ] || [ ! -f "$checker" ]; then
  deny 1
fi
resolved=$("$py" "$checker" confine-backup --root "$ROOT" --backup "$BACKUP") || deny 1
BACKUP="$resolved"

while IFS= read -r rel; do
  case "$rel" in
    ""|data/*|.env|*.plist) deny 1 ;;
  esac
  if [ -L "$BACKUP/$rel" ] || [ -L "$ROOT/$rel" ]; then
    deny 1
  fi
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
