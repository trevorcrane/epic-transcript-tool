#!/usr/bin/env bash
# Smoke test for Epic Transcript Tool.
# Exits 0 if the FastAPI app is healthy and the basic endpoints work.
set -u

API="${API:-http://localhost:8090}"
SUITE="${SUITE:-http://localhost:8080}"
FAIL=0

note() { printf "\033[36m›\033[0m %s\n" "$*"; }
ok()   { printf "\033[32m✓\033[0m %s\n" "$*"; }
bad()  { printf "\033[31m✗\033[0m %s\n" "$*"; FAIL=1; }

check_status() {
  local label="$1" url="$2" want="${3:-200}"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" || echo "000")
  if [ "$code" = "$want" ]; then ok "$label ($code)"
  else bad "$label expected $want got $code  [$url]"; fi
}

note "Direct FastAPI checks"
check_status "GET /health"      "$API/health"
check_status "GET /api/setup"   "$API/api/setup"
check_status "GET /api/recent"  "$API/api/recent"
check_status "GET /  (SPA)"     "$API/"

note "Text upload roundtrip"
TMP=$(mktemp -t epic-transcript-smoke).txt
echo "Hello from Epic Transcript Tool smoke test." > "$TMP"
RESP=$(curl -s --max-time 15 -F "file=@${TMP};type=text/plain" "$API/api/transcribe-upload")
rm -f "$TMP"
if echo "$RESP" | grep -qE '"ok"[[:space:]]*:[[:space:]]*true' && echo "$RESP" | grep -q "Hello from Epic Transcript Tool"; then
  ok "txt upload returned transcript"
  ID=$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["record"]["id"])' 2>/dev/null)
  if [ -n "${ID:-}" ]; then
    check_status "GET /api/transcripts/$ID"           "$API/api/transcripts/$ID"
    check_status "GET /api/transcripts/$ID/download"  "$API/api/transcripts/$ID/download"
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X DELETE "$API/api/transcripts/$ID")
    [ "$code" = "200" ] && ok "DELETE /api/transcripts/$ID (200)" || bad "DELETE expected 200 got $code"
  fi
else
  bad "txt upload failed: $RESP"
fi

note "Suite-server proxy checks ($SUITE)"
check_status "GET /epic-transcript/"            "$SUITE/epic-transcript/"
check_status "GET /epic-transcript/health"      "$SUITE/epic-transcript/health"
check_status "GET /epic-transcript/api/recent"  "$SUITE/epic-transcript/api/recent"

if [ "$FAIL" -eq 0 ]; then
  printf "\n\033[32mAll smoke checks passed.\033[0m\n"
  exit 0
else
  printf "\n\033[31mSome checks failed.\033[0m\n"
  exit 1
fi
