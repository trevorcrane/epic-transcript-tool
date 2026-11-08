#!/usr/bin/env bash
# Conditional offline copy. Does not bootout or bootstrap.
# Requires a pre-stop identity file and SCREENSHOT_OFFLINE_AUTHORIZATION.
# That variable is the operator's assertion. It is not approval by itself.
# `launchctl print` must fail. Discovery already happened before the stop.

set -u
set -o pipefail

deny() {
  printf '%s\n' "RESTART=no"
  exit "${1:-1}"
}

trace() {
  if [ -n "${HOME:-}" ] && [ -d "$HOME" ]; then
    printf '%s\n' "$1" >> "$HOME/screenshot-offline-trace"
  fi
}

sha256_file() {
  "$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"
}

recover_failed_apply() {
  receipt="$HOME/screenshot-apply.json"
  if [ ! -s "$receipt" ]; then
    if [ ! -e "$ROOT/screenshots.py" ]; then
      printf '%s\n' "RECOVERY=source-unchanged"
      return 0
    fi
    printf '%s\n' "RECOVERY=failed"
    return 1
  fi
  backup=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("backup") or "")' "$receipt") || backup=""
  if [ -z "$backup" ] || [ ! -f "$backup/app.py" ]; then
    printf '%s\n' "RECOVERY=failed"
    return 1
  fi
  if [ "$(sha256_file "$ROOT/app.py")" != "$(sha256_file "$backup/app.py")" ] || { [ -e "$ROOT/screenshots.py" ] && [ ! -f "$backup/screenshots.py" ]; }; then
    if ! BACKUP="$backup" DEST="$DEST" ROOT="$ROOT" "$ARTIFACT/scripts/screenshot_host_rollback.sh"; then
      printf '%s\n' "RECOVERY=failed"
      return 1
    fi
  fi
  if [ "$(sha256_file "$ROOT/app.py")" != "$(sha256_file "$backup/app.py")" ]; then
    printf '%s\n' "RECOVERY=failed"
    return 1
  fi
  if [ -e "$ROOT/screenshots.py" ] && [ ! -f "$backup/screenshots.py" ]; then
    printf '%s\n' "RECOVERY=failed"
    return 1
  fi
  printf '%s\n' "RECOVERY=source-restored"
  return 0
}

if [ "${SCREENSHOT_OFFLINE_AUTHORIZATION:-}" != "interruptible-offline-window-approved" ]; then
  deny 1
fi
if [ -z "${ROOT:-}" ] || [ ! -d "$ROOT" ] || [ -z "${ARTIFACT:-}" ] || [ ! -d "$ARTIFACT" ] || [ -z "${DEST:-}" ] || [ -z "${HOME:-}" ] || [ ! -d "$HOME" ]; then
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
PORT="${SCREENSHOT_PORT:-8090}"
IDENTITY="${IDENTITY:-$HOME/screenshot-prestop-identity.json}"
checks="$ARTIFACT/scripts/screenshot_host_offline_checks.py"
backup_tool="$ARTIFACT/scripts/screenshot_outside_backup.py"
preflight_tool="$ARTIFACT/scripts/screenshot_host_preflight.py"
apply_tool="$ARTIFACT/scripts/screenshot_host_apply.py"
if [ ! -f "$checks" ] || [ ! -f "$backup_tool" ] || [ ! -f "$preflight_tool" ] || [ ! -f "$apply_tool" ] || [ ! -s "$IDENTITY" ]; then
  deny 1
fi

PY=$(awk -F '\t' '$1=="program" { print $2; exit }' "$IDENTITY")
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  deny 1
fi
identity_exit=0
identity=$("$PY" "$checks" check-identity --root "$ROOT" --identity "$IDENTITY" --label "$LABEL") || identity_exit=$?
trace "identity-exit=$identity_exit"
if [ "$identity_exit" -ne 0 ]; then
  deny "$identity_exit"
fi
PLIST=$(printf '%s\n' "$identity" | sed -n '2p')
PID=$(printf '%s\n' "$identity" | sed -n '3p')
PGID=$(printf '%s\n' "$identity" | sed -n '4p')
if [ -z "$PLIST" ] || [ ! -f "$PLIST" ] || [ -z "$PID" ] || [ -z "$PGID" ]; then
  deny 1
fi
if [ "$(printf '%s\n' "$identity" | sed -n '1p')" != "$PY" ]; then
  deny 11
fi

if launchctl print "$LABEL" >/dev/null 2>&1; then
  trace "service-still-loaded"
  deny 30
fi
trace "service-absent"

port_exit=0
"$PY" "$checks" port --port "$PORT" || port_exit=$?
trace "port-exit=$port_exit"
if [ "$port_exit" -ne 0 ]; then
  deny "$port_exit"
fi

proc_exit=0
"$PY" "$checks" processes --pid "$PID" --pgid "$PGID" || proc_exit=$?
trace "process-exit=$proc_exit"
if [ "$proc_exit" -ne 0 ]; then
  deny "$proc_exit"
fi

jobs_before=""
if [ -f "$ROOT/data/url_jobs.json" ]; then
  jobs_before=$("$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$ROOT/data/url_jobs.json") || deny $?
fi
"$PY" "$checks" interrupted --root "$ROOT" --jobs "$ROOT/data/url_jobs.json" --out "$HOME/screenshot-interrupted-jobs.json" || deny $?
if [ -n "$jobs_before" ]; then
  jobs_after=$("$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$ROOT/data/url_jobs.json") || deny $?
  if [ "$jobs_before" != "$jobs_after" ]; then
    deny 24
  fi
fi

export ROOT ARTIFACT DEST HOME PY PLIST PORT LABEL
body="$HOME/screenshot-critical-body.sh"
cat > "$body" <<'BODY'
#!/usr/bin/env bash
set -u
set -o pipefail
trace() { printf '%s\n' "$1" >> "$HOME/screenshot-offline-trace"; }
trace "backup"
backup_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_outside_backup.py" --root "$ROOT" --dest "$DEST" --plist "$PLIST" || backup_exit=$?
trace "backup-exit=$backup_exit"
if [ "$backup_exit" -ne 0 ]; then exit "$backup_exit"; fi
if [ ! -s "$DEST/SHA256SUMS" ]; then trace "sums-missing"; exit 1; fi
verify_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_outside_backup.py" --verify "$DEST" || verify_exit=$?
trace "verify-exit=$verify_exit"
if [ "$verify_exit" -ne 0 ]; then exit "$verify_exit"; fi
preflight_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_preflight.py" \
  --root "$ROOT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --port "$PORT" \
  --out "$HOME/screenshot-preflight.json" || preflight_exit=$?
trace "preflight-exit=$preflight_exit"
if [ "$preflight_exit" -ne 0 ]; then exit "$preflight_exit"; fi
dry_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --out "$HOME/screenshot-apply-dry-run.json" || dry_exit=$?
trace "dry-run-exit=$dry_exit"
if [ "$dry_exit" -ne 0 ]; then exit "$dry_exit"; fi
trace "apply"
apply_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
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
if [ "$apply_exit" -ne 0 ] || [ "$ok" != "yes" ] || [ "$wrote" != "yes" ]; then
  exit "${apply_exit:-1}"
fi
exit 0
BODY
chmod 700 "$body"
section_exit=0
"$PY" "$checks" guard --db "$ROOT/data/transcripts.db" --ready "$HOME/screenshot-critical-open" -- bash "$body" || section_exit=$?
if [ "$section_exit" -eq 23 ]; then
  trace "exclusive-exit=23"
  deny 23
fi
if [ "$section_exit" -ne 0 ]; then
  recover_failed_apply
  printf '%s\n' "RESTART=no"
  printf '%s\n' "BOOTSTRAP=not-run ${PLIST}"
  exit "$section_exit"
fi
printf '%s\n' "APPLY=ok"
printf '%s\n' "RESTART=not-run"
printf '%s\n' "BOOTSTRAP=not-run ${PLIST}"
exit 0
