#!/usr/bin/env bash
# One-shot: put the free Gemini + Groq keys where the Epic Transcript Machine reads them on the iMac,
# then restart the launchd agent so /health shows ai_configured=true.
# Usage:  GEMINI_API_KEY=... GROQ_API_KEY=... bash scripts/set_phase3_ai_keys.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
touch "$ENV_FILE"
put() { # put KEY VALUE  -> upsert into .env
  local k="$1" v="$2"
  [ -z "$v" ] && return 0
  grep -v "^${k}=" "$ENV_FILE" > "$ENV_FILE.tmp" || true
  echo "${k}=${v}" >> "$ENV_FILE.tmp"; mv "$ENV_FILE.tmp" "$ENV_FILE"
  launchctl setenv "$k" "$v" 2>/dev/null || true
}
put GEMINI_API_KEY "${GEMINI_API_KEY:-}"
put GROQ_API_KEY   "${GROQ_API_KEY:-}"
# Models are auto-discovered from Google and Groq. Set PHASE3_GEMINI_MODEL / PHASE3_GROQ_MODEL only to force one.
# Opt-in only: set PHASE3_AI_ALL_SOURCES=1 to let non-YouTube URLs use AI. Uploads never leave the server.
put PHASE3_AI_ALL_SOURCES "${PHASE3_AI_ALL_SOURCES:-}"
chmod 600 "$ENV_FILE"
# restart whichever launchd agent runs the API (label contains 'transcript')
for L in $(launchctl list 2>/dev/null | awk '{print $3}' | grep -i transcript || true); do
  launchctl kickstart -k "gui/$(id -u)/$L" 2>/dev/null || true
done
sleep 3
curl -s http://127.0.0.1:8090/health || curl -s http://127.0.0.1:8080/health || true
echo
echo "Done. Look for ai_configured: true above. Free keys: https://aistudio.google.com/apikey  and  https://console.groq.com/keys"
