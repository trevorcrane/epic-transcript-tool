#!/usr/bin/env bash
# Record the loaded service identity before any offline stop.
# Does not bootout, bootstrap, back up, or copy source.
# A failing `launchctl print` is a failure. Do not use this after bootout.

set -u
set -o pipefail

deny() {
  printf '%s\n' "RESTART=no"
  exit "${1:-1}"
}

if [ -z "${ROOT:-}" ] || [ ! -d "$ROOT" ] || [ -z "${ARTIFACT:-}" ] || [ ! -d "$ARTIFACT" ] || [ -z "${HOME:-}" ] || [ ! -d "$HOME" ]; then
  deny 1
fi
checks="$ARTIFACT/scripts/screenshot_host_offline_checks.py"
if [ ! -f "$checks" ]; then
  deny 1
fi

LABEL="${LAUNCHD_LABEL:-gui/501/com.epic.transcript-api}"
IDENTITY="${IDENTITY:-$HOME/screenshot-prestop-identity.json}"
discovered=$(launchctl print "$LABEL") || deny $?
PLIST=$(printf '%s\n' "$discovered" | sed -n 's/^[[:space:]]*path = //p' | head -n 1)
PY=$(printf '%s\n' "$discovered" | sed -n 's/^[[:space:]]*program = //p' | head -n 1)
PID=$(printf '%s\n' "$discovered" | sed -n 's/^[[:space:]]*pid = //p' | head -n 1)
if [ -z "$PLIST" ] || [ ! -f "$PLIST" ] || [ -z "$PY" ] || [ ! -x "$PY" ] || [ -z "$PID" ]; then
  deny 1
fi
PGID=$(ps -o pgid= -p "$PID" | tr -d '[:space:]') || deny $?
if [ -z "$PGID" ]; then
  deny 1
fi
"$PY" "$checks" write-identity \
  --root "$ROOT" \
  --plist "$PLIST" \
  --program "$PY" \
  --pid "$PID" \
  --pgid "$PGID" \
  --label "$LABEL" \
  --out "$IDENTITY" || deny $?
if [ ! -s "$IDENTITY" ]; then
  deny 1
fi
printf '%s\n' "CAPTURE=ok"
printf '%s\n' "RESTART=no"
exit 0
