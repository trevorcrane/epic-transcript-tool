# PROJECT_STATE.md

Updated: 2026-08-30 18:14 EDT

## Current phase
Phase 1: Bulletproof YouTube Transcripts. Core Phase 1 routing is implemented and passing the primary regression locally and through a public test tunnel. Remaining Phase 1 gate work: complete the full video matrix, mobile/browser visual QC, and durable production deployment.

## Completed work
- Located active project at `/Users/tc-imac/.openclaw/workspace/epic-transcript-tool`.
- Confirmed architecture before changes: FastAPI, SQLite, `yt-dlp`, static single-page UI, suite proxy `/epic-transcript` to port 8090.
- Reproduced current production-like failure: suite server on port 8080 returned HTTP 502 because the FastAPI backend on port 8090 was not running.
- Started the FastAPI backend and restored local suite access.
- Added `PROJECT_STATE.md` and `ACCEPTANCE_TESTS.md`.
- Added automated Phase 1 tests for YouTube ID normalization, invalid URL behavior, VTT timestamp parsing, cache-first routing, and TXT/Markdown/SRT downloads.
- Migrated transcript storage to include media ID, source URL, title, creator, duration, language, timestamped segments, word count, provider attempts, method, created time, and cache-hit status in responses.
- Implemented YouTube URL normalization for `youtube.com/watch`, `youtu.be`, `youtube.com/shorts`, `youtube.com/embed`, `youtube.com/live`, query strings, and raw 11-character video IDs.
- Implemented Phase 1 provider order:
  1. SQLite cache by normalized YouTube video ID.
  2. Native caption extractor via `yt-dlp` metadata caption URLs.
  3. `youtube-transcript-api` fallback.
  4. `yt-dlp` subtitle download fallback.
  5. Optional Gemini hook when `GEMINI_API_KEY` exists. Currently no key is configured.
  6. Free local Whisper fallback when the `whisper` CLI exists. Currently not installed.
- Removed paid OpenAI Whisper as a required fallback path.
- Added TXT, Markdown, and SRT download formats.
- Updated the UI to show TXT, Markdown, and SRT download buttons.
- Created a temporary public test link via localtunnel: https://ten-dryers-own.loca.lt

## Test results
- `pytest tests/test_phase1.py -q`: 6 passed.
- `python -m py_compile app.py`: passed.
- `./smoke.sh`: all checks passed for direct FastAPI and suite proxy.
- Public page check: `https://ten-dryers-own.loca.lt/` returned HTTP 200 and contained the expected EPIC Transcript UI markers plus Markdown and SRT buttons.
- Regression video first run, local API: HTTP 200, title `Sell AI Systems, Not AI Agents (how I made $5,407,902 last year)`, method `native-caption-automatic_captions`, cache hit false, 1,460 segments, 15,744 words, nonempty first and last segments, increasing timestamps.
- Regression video second run, local API: HTTP 200, cache hit true, 1,460 segments, 15,744 words, nonempty first and last segments, increasing timestamps.
- Regression video through public test link: HTTP 200, cache hit true, 1,460 segments, 15,744 words, correct title.
- Control video `dQw4w9WgXcQ`: HTTP 200, title `Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)`, method `native-caption-subtitles`, 61 segments, 366 words.
- Download checks for regression transcript: TXT HTTP 200, Markdown HTTP 200, SRT HTTP 200.
- Invalid URL: HTTP 422 with helpful upload guidance.
- Private/unavailable synthetic YouTube ID: HTTP 422 with required blocked-video upload guidance.

## Known problems
- The public link is a temporary localtunnel URL, not a durable production deployment.
- Cloudflare quick tunnel attempts returned HTTP 404 from the generated trycloudflare URLs, so localtunnel was used as the temporary clickable test link.
- Supabase cache is not connected because `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_ANON_KEY` are not present in this environment. SQLite cache is active and working.
- Gemini fallback is configured as an optional hook, but `GEMINI_API_KEY` is not present and the hook is not enabled.
- Free local Whisper fallback requires the `whisper` CLI. It is not installed in the active environment.
- Browser visual QC is blocked until Chrome remote-debugging permission is approved on the iMac. Terminal HTTP checks were used instead.
- Automatic-caption VTT from YouTube can include overlapping partial caption segments. It passes the release gate counts and timestamp checks, but a future cleanup pass should merge overlapping partials for readability.

## Blockers
No blocker for continued Phase 1 engineering. Blockers for full release gate: durable public deployment target/credential if localtunnel is not acceptable, Chrome remote-debugging permission for browser/mobile visual QC, optional Supabase/Gemini/local Whisper credentials/install if Trevor wants those routes fully active now.

## Exact next action
Finish the full Phase 1 release matrix: manual-caption, automatic-caption, non-English, Shorts, no-caption, invalid, private/unavailable, long video, copy/download/mobile/accessibility. Then either create a durable public deployment or request the exact deployment credential/target if it is not available locally.
