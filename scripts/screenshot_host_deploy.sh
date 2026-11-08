#!/usr/bin/env bash
# Deploy entry point. Run this file. Do not paste it into an interactive shell.
#
# Hermes runs it only while the service is not inside a transcript write.
# This script does not inspect or stop the live process, so it does not prove
# that the service is idle. A stand-in for launchctl does not prove the Mac's
# print format. Hermes confirms the printed program and path on the machine.
#
# Required bindings: ROOT ARTIFACT DEST HOME
# Optional: LAUNCHD_LABEL (default gui/501/com.epic.transcript-api)
# The service interpreter and plist are read from `launchctl print`.
# RESTART=allowed only after a verified backup, preflight, dry run, and an
# apply receipt with exit 0, ok true, and wrote true.

set -u
set -o pipefail

deny() {
  printf '%s\n' "RESTART=no"
  exit "${1:-1}"
}

trace() {
  if [ -n "${HOME:-}" ] && [ -d "$HOME" ]; then
    printf '%s\n' "$1" >> "$HOME/screenshot-deploy-trace"
  fi
}

if [ -z "${ROOT:-}" ] || [ -z "${ARTIFACT:-}" ] || [ -z "${DEST:-}" ] || [ -z "${HOME:-}" ]; then
  deny 1
fi
if [ ! -d "$ROOT" ] || [ ! -d "$ARTIFACT" ] || [ ! -d "$HOME" ]; then
  deny 1
fi
case "$DEST" in
  "$ROOT"|"$ROOT"/*) deny 1 ;;
esac
dest_parent=$(dirname -- "$DEST")
if ! mkdir -p -- "$dest_parent"; then
  deny 1
fi
if [ ! -w "$dest_parent" ]; then
  deny 1
fi

LABEL="${LAUNCHD_LABEL:-gui/501/com.epic.transcript-api}"
discovered=$(launchctl print "$LABEL") || deny $?
PLIST=$(printf '%s\n' "$discovered" | sed -n 's/^[[:space:]]*path = //p' | head -n 1)
PY=$(printf '%s\n' "$discovered" | sed -n 's/^[[:space:]]*program = //p' | head -n 1)
if [ -z "$PLIST" ] || [ ! -f "$PLIST" ]; then
  deny 1
fi
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  deny 1
fi
# The printed program must be the interpreter named in that plist.
# This does not prove the Mac print format. Hermes still checks that print.
configured=$("$PY" -c 'import plistlib, sys
with open(sys.argv[1], "rb") as handle:
    data = plistlib.load(handle)
program = data.get("Program") or ""
arguments = data.get("ProgramArguments") or []
if not program and arguments:
    program = arguments[0]
if not isinstance(program, str):
    program = ""
print(program)' "$PLIST") || deny $?
if [ -z "$configured" ] || [ "$configured" != "$PY" ]; then
  trace "interpreter-mismatch"
  deny 1
fi
trace "interpreter=$PY"

backup_tool="$ARTIFACT/scripts/screenshot_outside_backup.py"
preflight_tool="$ARTIFACT/scripts/screenshot_host_preflight.py"
apply_tool="$ARTIFACT/scripts/screenshot_host_apply.py"
if [ ! -f "$backup_tool" ] || [ ! -f "$preflight_tool" ] || [ ! -f "$apply_tool" ]; then
  deny 1
fi

trace "backup"
backup_exit=0
"$PY" "$backup_tool" --root "$ROOT" --dest "$DEST" --plist "$PLIST" || backup_exit=$?
trace "backup-exit=$backup_exit"
if [ "$backup_exit" -ne 0 ]; then
  deny "$backup_exit"
fi
if [ ! -s "$DEST/SHA256SUMS" ]; then
  trace "sums-missing"
  deny 1
fi
trace "sums-ok"

verify_exit=0
"$PY" "$backup_tool" --verify "$DEST" || verify_exit=$?
trace "verify-exit=$verify_exit"
if [ "$verify_exit" -ne 0 ]; then
  deny "$verify_exit"
fi

preflight_exit=0
"$PY" "$preflight_tool" \
  --root "$ROOT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --port 8090 \
  --out "$HOME/screenshot-preflight.json" || preflight_exit=$?
trace "preflight-exit=$preflight_exit"
if [ "$preflight_exit" -ne 0 ]; then
  deny "$preflight_exit"
fi

dry_exit=0
"$PY" "$apply_tool" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --out "$HOME/screenshot-apply-dry-run.json" || dry_exit=$?
trace "dry-run-exit=$dry_exit"
if [ "$dry_exit" -ne 0 ]; then
  deny "$dry_exit"
fi

trace "apply"
apply_exit=0
"$PY" "$apply_tool" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --apply \
  --out "$HOME/screenshot-apply.json" || apply_exit=$?
trace "apply-exit=$apply_exit"
ok=no
wrote=no
if [ -s "$HOME/screenshot-apply.json" ]; then
  parsed=$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("yes" if d.get("ok") is True else "no", "yes" if d.get("wrote") is True else "no")' "$HOME/screenshot-apply.json") || parsed="no no"
  ok=${parsed%% *}
  wrote=${parsed##* }
fi
if [ "$apply_exit" -eq 0 ] && [ "$ok" = "yes" ] && [ "$wrote" = "yes" ]; then
  printf '%s\n' "RESTART=allowed"
else
  printf '%s\n' "RESTART=no"
fi
exit "$apply_exit"
