#!/usr/bin/env bash
# Restore one named interrupted run from its durable intent.
# Does not scan $HOME, does not read $HOME/screenshot-apply.json,
# and does not bootout or bootstrap.
# SCREENSHOT_OFFLINE_AUTHORIZATION must be the same original window string.
# That string is not a new approval.
# Required: ROOT ARTIFACT HOME
# Either RUN_DIR names one interrupted run, or SCREENSHOT_RECOVER_UNTOUCHED=1
# with RUN_DIR unset verifies the live tree and does not restore anything.
# Optional: IDENTITY (default $HOME/screenshot-prestop-identity.json)
#           LAUNCHD_LABEL, SCREENSHOT_PORT

set -u
set -o pipefail

finish() {
  if [ -n "${PLIST:-}" ]; then
    printf '%s\n' "BOOTSTRAP=not-run ${PLIST}"
    printf '%s\n' "PLIST=${PLIST}"
  else
    printf '%s\n' "BOOTSTRAP=not-run"
  fi
  exit "${1:-1}"
}

refuse() {
  printf '%s\n' "RECOVERY=failed"
  printf '%s\n' "RESTART=not-allowed"
  finish "${1:-1}"
}

classified() {
  printf '%s\n' "RECOVERY=$1"
  printf '%s\n' "INSTALL=$2"
  if [ "$3" = "allowed" ]; then
    printf '%s\n' "RESTART=allowed"
    printf '%s\n' "AUTHORIZATION=original-window"
    printf '%s\n' "RUNTIME=unchanged .env,data/url_jobs.json,data/transcripts.db"
    finish 0
  fi
  printf '%s\n' "RESTART=not-allowed"
  finish "${4:-1}"
}

if [ "${SCREENSHOT_OFFLINE_AUTHORIZATION:-}" != "interruptible-offline-window-approved" ]; then
  refuse 1
fi
if [ -n "${SCREENSHOT_APPLY_CRASH_AT:-}" ] || [ -n "${SCREENSHOT_APPLY_COPY_PAUSE_SECONDS:-}" ] || [ -n "${SCREENSHOT_APPLY_TEST_HARNESS:-}" ]; then
  printf '%s\n' "HOOKS=rejected"
  refuse 1
fi
unset SCREENSHOT_APPLY_CRASH_AT SCREENSHOT_APPLY_COPY_PAUSE_SECONDS SCREENSHOT_APPLY_TEST_HARNESS
if [ -z "${ROOT:-}" ] || [ ! -d "$ROOT" ] || [ -z "${ARTIFACT:-}" ] || [ ! -d "$ARTIFACT" ] || [ -z "${HOME:-}" ] || [ ! -d "$HOME" ]; then
  refuse 1
fi
untouched=0
if [ "${SCREENSHOT_RECOVER_UNTOUCHED:-}" = "1" ]; then
  untouched=1
  if [ -n "${RUN_DIR:-}" ]; then
    refuse 1
  fi
elif [ -z "${RUN_DIR:-}" ]; then
  refuse 1
fi

LABEL="${LAUNCHD_LABEL:-gui/501/com.epic.transcript-api}"
PORT="${SCREENSHOT_PORT:-8090}"
IDENTITY="${IDENTITY:-$HOME/screenshot-prestop-identity.json}"
checks="$ARTIFACT/scripts/screenshot_host_offline_checks.py"
rollback="$ARTIFACT/scripts/screenshot_host_rollback.sh"
manifest="$ARTIFACT/docs/screenshot-install-manifest.json"
if [ ! -f "$checks" ] || [ ! -f "$rollback" ] || [ ! -f "$manifest" ] || [ ! -s "$IDENTITY" ]; then
  refuse 1
fi

PY=$(awk -F '\t' '$1=="program" { print $2; exit }' "$IDENTITY")
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  refuse 1
fi
identity_exit=0
identity=$("$PY" "$checks" check-identity --root "$ROOT" --identity "$IDENTITY" --label "$LABEL") || identity_exit=$?
if [ "$identity_exit" -ne 0 ]; then
  refuse "$identity_exit"
fi
PLIST=$(printf '%s\n' "$identity" | sed -n '2p')
PID=$(printf '%s\n' "$identity" | sed -n '3p')
PGID=$(printf '%s\n' "$identity" | sed -n '4p')
if [ -z "$PLIST" ] || [ ! -f "$PLIST" ] || [ -z "$PID" ] || [ -z "$PGID" ]; then
  refuse 1
fi
if [ "$(printf '%s\n' "$identity" | sed -n '1p')" != "$PY" ]; then
  refuse 11
fi

if launchctl print "$LABEL" >/dev/null 2>&1; then
  refuse 30
fi
port_exit=0
"$PY" "$checks" port --port "$PORT" || port_exit=$?
if [ "$port_exit" -ne 0 ]; then
  refuse "$port_exit"
fi
proc_exit=0
"$PY" "$checks" processes --pid "$PID" --pgid "$PGID" || proc_exit=$?
if [ "$proc_exit" -ne 0 ]; then
  refuse "$proc_exit"
fi

hash_file() {
  if [ -f "$1" ]; then
    "$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"
  else
    printf '%s\n' "missing"
  fi
}

if [ "$untouched" -eq 1 ]; then
  env_before=$(hash_file "$ROOT/.env") || refuse 1
  jobs_before=$(hash_file "$ROOT/data/url_jobs.json") || refuse 1
  db_before=$(hash_file "$ROOT/data/transcripts.db") || refuse 1
  if "$PY" "$checks" source-baseline --root "$ROOT" --manifest "$manifest" >&2; then
    env_after=$(hash_file "$ROOT/.env") || refuse 1
    jobs_after=$(hash_file "$ROOT/data/url_jobs.json") || refuse 1
    db_after=$(hash_file "$ROOT/data/transcripts.db") || refuse 1
    if [ "$env_before" = "$env_after" ] && [ "$jobs_before" = "$jobs_after" ] && [ "$db_before" = "$db_after" ]; then
      classified not-needed verified-untouched-c943 allowed
    fi
  fi
  classified not-needed unverified not-allowed
fi

home_real=$("$PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$HOME") || refuse 1
run_real=$("$PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$RUN_DIR") || refuse 1
case "$run_real" in
  "$home_real"/screenshot-run-*) ;;
  *) refuse 1 ;;
esac
RUN_ID=$(basename -- "$run_real")
if [ "$run_real" = "$home_real" ] || [ ! -d "$run_real" ] || [ ! -s "$run_real/intent.json" ]; then
  refuse 1
fi
# The operator names this directory. Do not search for another run.
if [ "$(dirname -- "$run_real")" != "$home_real" ]; then
  refuse 1
fi

env_before=$(hash_file "$ROOT/.env") || refuse 1
jobs_before=$(hash_file "$ROOT/data/url_jobs.json") || refuse 1
db_before=$(hash_file "$ROOT/data/transcripts.db") || refuse 1

receipt="$run_real/apply.json"
backup=$("$PY" "$checks" recovery-backup --intent "$run_real/intent.json" --run-dir "$run_real" --root "$ROOT" --manifest "$manifest" --receipt "$receipt") || refuse 42
if ! "$PY" "$checks" source-baseline --root "$ROOT" --manifest "$manifest" >&2; then
  if ! BACKUP="$backup" ROOT="$ROOT" PY="$PY" ARTIFACT="$ARTIFACT" "$rollback" >&2; then
    refuse 1
  fi
fi
if ! "$PY" "$checks" source-baseline --root "$ROOT" --manifest "$manifest" >&2; then
  refuse 40
fi
env_after=$(hash_file "$ROOT/.env") || refuse 1
jobs_after=$(hash_file "$ROOT/data/url_jobs.json") || refuse 1
db_after=$(hash_file "$ROOT/data/transcripts.db") || refuse 1
if [ "$env_before" != "$env_after" ] || [ "$jobs_before" != "$jobs_after" ] || [ "$db_before" != "$db_after" ]; then
  refuse 24
fi

printf '%s\n' "RECOVERY=source-restored"
printf '%s\n' "INSTALL=verified-c943"
printf '%s\n' "RESTART=allowed"
printf '%s\n' "BOOTSTRAP=not-run ${PLIST}"
printf '%s\n' "PLIST=${PLIST}"
printf '%s\n' "RUN_DIR=${run_real}"
printf '%s\n' "AUTHORIZATION=original-window"
printf '%s\n' "RUNTIME=unchanged .env,data/url_jobs.json,data/transcripts.db"
exit 0
