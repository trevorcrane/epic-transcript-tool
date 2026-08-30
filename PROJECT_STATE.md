# PROJECT_STATE.md

Updated: 2026-08-30 18:18 EDT

## Current phase
Phase 1: Bulletproof YouTube Transcripts. Active gate is production release verification.

## Completed work
- Located active local project at `/Users/tc-imac/.openclaw/workspace/epic-transcript-tool`.
- Created source repository: https://github.com/trevorcrane/epic-transcript-tool
- Current branch: `main`.
- Current committed SHA: `27d8805666073d592ae849ade0d060cb9a509df2`.
- Verified GitHub remote with `git ls-remote origin refs/heads/main` and `gh api repos/trevorcrane/epic-transcript-tool/contents/app.py?ref=main`.
- Identified current architecture: FastAPI app, SQLite cache, YouTube normalized media IDs, native caption extraction, youtube-transcript-api fallback, yt-dlp subtitle fallback, optional Gemini hook, local Whisper fallback, and static single-page UI.
- Verified local prerequisites: `yt-dlp`, `ffmpeg`, and local `whisper` are installed. SMTP is not configured and only affects Email to Me.
- Verified local smoke tests: `/health`, `/api/setup`, `/api/recent`, `/`, TXT upload roundtrip, transcript fetch/download/delete, and suite proxy all passed.
- Created named Cloudflare tunnel `epic-transcript-tool` and routed public hostname `https://epic-transcript.robyncrane.com/` to the local FastAPI app on port 8090.
- Verified public no-login URL loads anonymously:
  - `/` returned HTTP 200 with Epic Transcript Tool HTML.
  - `/health` returned HTTP 200 with setup JSON.
  - `/api/setup` returned HTTP 200 with readiness JSON.
- Ran automated unit tests before production check: `pytest -q` returned `6 passed in 0.41s`.
- Ran regression video twice through the public URL and both requests returned HTTP 200.

## Latest production regression evidence
URL tested: `https://epic-transcript.robyncrane.com/api/transcribe-url`
Regression video: `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`

Run 1:
- HTTP status: 200
- Title: `Sell AI Systems, Not AI Agents (how I made $5,407,902 last year)`
- Media ID: `v34Eg12mhDM`
- Method: `native-caption-automatic_captions`
- Segment count: 1460
- Word count: 15744
- Language: `en`
- Cache hit: true
- Timestamps increasing: true
- TXT download: HTTP 200, 94784 bytes
- Markdown download: HTTP 200, 100829 bytes
- SRT download: HTTP 200, 134557 bytes

Run 2:
- HTTP status: 200
- Title: `Sell AI Systems, Not AI Agents (how I made $5,407,902 last year)`
- Media ID: `v34Eg12mhDM`
- Method: `native-caption-automatic_captions`
- Segment count: 1460
- Word count: 15744
- Language: `en`
- Cache hit: true
- Timestamps increasing: true
- TXT download: HTTP 200, 94784 bytes
- Markdown download: HTTP 200, 100829 bytes
- SRT download: HTTP 200, 134557 bytes

Credible beginning:
`[00:01] I wanted to make this video to show you how to actually make money with AI. Last...`

Credible ending:
`...hope you enjoyed this and I hope you got value from it. Look forward to seeing you soon.`

## Test results
- `pytest -q`: passed, 6 tests.
- Local smoke script: passed.
- Public root/health/setup anonymous fetch: passed.
- Public regression video twice: passed.
- Public TXT/Markdown/SRT downloads for regression record: passed.

## Known problems
- The public hostname currently depends on this iMac process and Cloudflare Tunnel staying up. It is public/no-login, but should be hardened with launchd or moved to a hosted container before whole-project final release.
- SMTP config is missing, so Email to Me is not ready.
- Gemini YouTube hook is intentionally present but not enabled because no key is configured and the free caption/local path is primary.
- Browser WebGPU Whisper is not implemented yet. Local server Whisper fallback exists.
- Full Phase 1 matrix is not fully complete yet. Regression case passes, but manual-caption, auto-caption, non-English, Shorts, no-caption, invalid, private, long-video, cache-hit, mobile, contrast, and accessibility still need production evidence.

## Blockers
None requiring Trevor right now.

## Exact next action
Run the remaining Phase 1 production matrix against `https://epic-transcript.robyncrane.com/`, record PASS/FAIL evidence in `ACCEPTANCE_TESTS.md`, fix any failing cases using tests-first, then re-run the full gate.
