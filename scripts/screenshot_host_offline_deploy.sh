#!/usr/bin/env bash
# Conditional offline copy. Does not bootout or bootstrap.
# Requires a pre-stop identity file and SCREENSHOT_OFFLINE_AUTHORIZATION.
# That variable is the operator's assertion. It is not approval by itself.
# `launchctl print` must fail. Discovery already happened before the stop.

set -u
set -o pipefail

deny() {
  printf '%s\n' "RESTART=not-allowed"
  printf '%s\n' "BOOTSTRAP=not-run"
  exit "${1:-1}"
}

trace() {
  if [ -n "${HOME:-}" ] && [ -d "$HOME" ]; then
    printf '%s\n' "$1" >> "$HOME/screenshot-offline-trace"
  fi
}

source_is_baseline() {
  "$PY" "$checks" source-baseline --root "$1" --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" >&2
}

recover_failed_apply() {
  # This run's intent, written before the first replacement. Never a home-directory
  # receipt and never another run's valid c943 backup.
  RECOVERY_RESULT=failed
  intent="$RUN_DIR/intent.json"
  receipt="$RUN_DIR/apply.json"
  if [ ! -s "$intent" ] && [ ! -s "$receipt" ]; then
    RECOVERY_RESULT=not-needed
    printf '%s\n' "RECOVERY=not-needed"
    return 0
  fi
  if [ ! -s "$intent" ]; then
    RECOVERY_RESULT=failed
    printf '%s\n' "RECOVERY=failed"
    return 1
  fi
  backup=$("$PY" "$checks" recovery-backup --intent "$intent" --run-dir "$RUN_DIR" --root "$ROOT" --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" --receipt "$receipt") || {
    RECOVERY_RESULT=failed
    printf '%s\n' "RECOVERY=failed"
    return 1
  }
  if ! source_is_baseline "$ROOT"; then
    if ! BACKUP="$backup" DEST="$DEST" ROOT="$ROOT" PY="$PY" ARTIFACT="$ARTIFACT" "$ARTIFACT/scripts/screenshot_host_rollback.sh" >&2; then
      RECOVERY_RESULT=failed
      printf '%s\n' "RECOVERY=failed"
      return 1
    fi
  fi
  if source_is_baseline "$ROOT"; then
    RECOVERY_RESULT=source-restored
    printf '%s\n' "RECOVERY=source-restored"
    return 0
  fi
  RECOVERY_RESULT=failed
  printf '%s\n' "RECOVERY=failed"
  return 1
}

emit_restart() {
  # RESTART is permission for a later manual bootstrap. BOOTSTRAP=not-run means
  # this process did not execute launchctl. RESTART=not-run is not a receipt.
  case "$1" in
    verified-new|verified-c943)
      printf '%s\n' "INSTALL=$1"
      printf '%s\n' "RESTART=allowed"
      ;;
    *)
      printf '%s\n' "INSTALL=$1"
      printf '%s\n' "RESTART=not-allowed"
      ;;
  esac
  if [ -n "${PLIST:-}" ]; then
    printf '%s\n' "BOOTSTRAP=not-run ${PLIST}"
    printf '%s\n' "PLIST=${PLIST}"
  else
    printf '%s\n' "BOOTSTRAP=not-run"
  fi
  printf '%s\n' "AUTHORIZATION=original-window"
}

if [ "${SCREENSHOT_OFFLINE_AUTHORIZATION:-}" != "interruptible-offline-window-approved" ]; then
  deny 1
fi
if [ -n "${SCREENSHOT_APPLY_CRASH_AT:-}" ] || [ -n "${SCREENSHOT_APPLY_COPY_PAUSE_SECONDS:-}" ] || [ -n "${SCREENSHOT_APPLY_TEST_HARNESS:-}" ]; then
  printf '%s\n' "HOOKS=rejected"
  printf '%s\n' "RECOVERY=not-needed"
  deny 1
fi
unset SCREENSHOT_APPLY_CRASH_AT SCREENSHOT_APPLY_COPY_PAUSE_SECONDS SCREENSHOT_APPLY_TEST_HARNESS
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

RUN_DIR=$("$PY" "$checks" create-run --home "$HOME") || deny 1
RUN_ID=$(basename -- "$RUN_DIR")
home_real=$("$PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$HOME") || deny 1
case "$RUN_DIR" in
  "$home_real"/screenshot-run-*) ;;
  *) deny 1 ;;
esac
if [ ! -d "$RUN_DIR" ] || [ -n "$(ls -A "$RUN_DIR")" ]; then
  deny 1
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

export ROOT ARTIFACT DEST HOME PY PLIST PORT LABEL RUN_DIR RUN_ID
body="$HOME/screenshot-critical-body.sh"
cat > "$body" <<'BODY'
#!/usr/bin/env bash
set -u
set -o pipefail
unset SCREENSHOT_APPLY_CRASH_AT SCREENSHOT_APPLY_COPY_PAUSE_SECONDS SCREENSHOT_APPLY_TEST_HARNESS
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
  --out "$RUN_DIR/preflight.json" || preflight_exit=$?
trace "preflight-exit=$preflight_exit"
if [ "$preflight_exit" -ne 0 ]; then exit "$preflight_exit"; fi
dry_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --out "$RUN_DIR/dry-run.json" || dry_exit=$?
trace "dry-run-exit=$dry_exit"
if [ "$dry_exit" -ne 0 ]; then exit "$dry_exit"; fi
trace "apply"
apply_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --apply \
  --intent "$RUN_DIR/intent.json" \
  --run-id "$RUN_ID" \
  --out "$RUN_DIR/apply.json" || apply_exit=$?
trace "apply-exit=$apply_exit"
ok=no
wrote=no
if [ -s "$RUN_DIR/apply.json" ]; then
  parsed=$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("yes" if d.get("ok") is True else "no", "yes" if d.get("wrote") is True else "no")' "$RUN_DIR/apply.json") || parsed="no no"
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
  recover_failed_apply || true
  case "$RECOVERY_RESULT" in
    source-restored) emit_restart verified-c943 ;;
    not-needed) emit_restart unchanged ;;
    *) emit_restart incomplete ;;
  esac
  if [ -s "$RUN_DIR/apply.json" ]; then
    printf '%s\n' "APPLY_RECEIPT=$RUN_DIR/apply.json"
  fi
  exit "$section_exit"
fi
if "$PY" "$checks" install-verified --root "$ROOT" --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" --artifact "$ARTIFACT" >&2; then
  printf '%s\n' "APPLY=ok"
  emit_restart verified-new
  printf '%s\n' "APPLY_RECEIPT=$RUN_DIR/apply.json"
  exit 0
fi
printf '%s\n' "APPLY=ok"
emit_restart incomplete
printf '%s\n' "APPLY_RECEIPT=$RUN_DIR/apply.json"
exit 1
