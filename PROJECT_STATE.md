# PROJECT_STATE.md

Updated: 2026-08-31 00:02 EDT

## Current phase
Phase 1: Bulletproof YouTube Transcripts. Active gate is production release verification and backend hardening.

## Version / phase status

### Version 1 / Phase 1: Bulletproof YouTube transcripts
Status: In release verification.
- Public no-login app: https://epic-transcript.robyncrane.com/
- Core regression remains passing publicly with 1,460 segments and 15,744 words for `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`.
- Manual-caption control now has fresh public evidence: `dQw4w9WgXcQ`, 61 segments, 366 words, method `native-caption-subtitles`, cache hit.
- Release matrix is 8 of 9 passing publicly after the API reload: invalid URL now returns the intended helpful HTTP 422 upload guidance instead of HTTP 500.
- Backend hardening advanced: the FastAPI API and Cloudflare named tunnel are loaded under launchd KeepAlive agents.
- Remaining Phase 1 release-gap is non-English YouTube evidence. The current Despacito candidate is not release-valid because public YouTube access is blocked/helpful-failure, and earlier cache evidence could return English subtitles.

### Version 2 / Phase 2: Any video or audio
Status: Started, not release-complete.
- Local Whisper upload path exists and previous local evidence covered MP3, M4A, MP4, and direct public-media-style URL.
- Full upload/media release matrix still needs completion, but the public API now has first production upload proof for generated WAV, MP3, and MP4 fixtures.
- Advanced public verification: added `scripts/phase2_upload_smoke.py`, which generates a spoken fixture with macOS `say`, converts it with `ffmpeg`, uploads WAV/MP3/MP4 to the public no-login API, and verifies credible nonempty local-Whisper transcripts.
- Fresh public upload proof from 2026-08-31 00:02 EDT: WAV returned HTTP 200 through `local-whisper`, 2 segments, 18 words; MP3 returned HTTP 200 through `local-whisper`, 2 segments, 18 words; MP4 returned HTTP 200 through `local-whisper`, 1 segment, 12 words.

### Version 3 / Phase 3: Video intelligence
Status: Started in queued backend tests, not public-release complete.
- Queued tests define expectations for `/api/analyze/{id}` outputs that preserve original transcripts, return timestamp-cited useful text, and support download.
- UI buttons and provider-safe implementation are not complete yet.

## Completed work
- Located active local project at `/Users/tc-imac/.openclaw/workspace/epic-transcript-tool`.
- Created source repository: https://github.com/trevorcrane/epic-transcript-tool
- Current branch: `main`.
- Verified GitHub remote previously with `git ls-remote origin refs/heads/main` and `gh api repos/trevorcrane/epic-transcript-tool/contents/app.py?ref=main`.
- Identified current architecture: FastAPI app, SQLite cache, YouTube normalized media IDs, native caption extraction, youtube-transcript-api fallback, yt-dlp subtitle fallback, optional Gemini hook, local Whisper fallback, and static single-page UI.
- Verified local prerequisites: `yt-dlp`, `ffmpeg`, and local `whisper` are installed. SMTP is not configured and only affects Email to Me.
- Created named Cloudflare tunnel `epic-transcript-tool` and routed public hostname `https://epic-transcript.robyncrane.com/` to the local FastAPI app on port 8090.
- Pulled the Drive design folder `2026 - Epic Design Images`, including `DESIGN.md` and Epic Call IQ screenshots.
- Rebuilt the public UI into an Epic Call IQ-inspired version: near-black hero, purple/pink neon action gradient, glass transcript control, and warm off-white results workspace.
- Verified the durable public URL serves the redesigned UI anonymously with HTTP 200 and expected design markers.
- Captured visual QC evidence in `evidence/` for desktop and mobile redesign checks.
- Hardened public production process by loading launchd KeepAlive jobs:
  - `com.epic.transcript-api` runs `.venv/bin/python app.py` from the repo on port 8090.
  - `com.epic.transcript-tunnel` runs `cloudflared tunnel --config cloudflared.yml --no-autoupdate run`.
- Updated Phase 1 public test scripts so Cloudflare does not reject Python's default urllib user agent with 1010 during release checks.

## Latest production regression evidence
URL tested: `https://epic-transcript.robyncrane.com/api/transcribe-url`
Regression video: `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`

Fresh health run from 2026-08-30 23:24 EDT:
- Public root: HTTP 200.
- Public setup: HTTP 200, `ready: true`, `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Regression video: HTTP 200, method `native-caption-automatic_captions`, cache hit, 1,460 segments, 15,744 words, language `en`, title `Sell AI Systems, Not AI Agents (how I made $5,407,902 last year)`.
- Manual-caption control `dQw4w9WgXcQ`: HTTP 200, method `native-caption-subtitles`, cache hit, 61 segments, 366 words, language `en`, title `Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)`.

Prior full regression evidence:
- Run 1 and Run 2 both returned HTTP 200.
- Media ID: `v34Eg12mhDM`.
- Method: `native-caption-automatic_captions`.
- Segment count: 1460.
- Word count: 15744.
- TXT download: HTTP 200, 94784 bytes.
- Markdown download: HTTP 200, 100829 bytes.
- SRT download: HTTP 200, 134557 bytes.
- Credible beginning: `[00:01] I wanted to make this video to show you how to actually make money with AI. Last...`
- Credible ending: `...hope you enjoyed this and I hope you got value from it. Look forward to seeing you soon.`

## Test results
- `./.venv/bin/python -m pytest -q`: passed, 19 tests on 2026-08-31 00:02 EDT.
- Public root: HTTP 200, expected app markers present.
- Public setup: HTTP 200, `ready: true`, `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public Phase 1 health script now correctly accepts a CLI base URL and passed against `https://epic-transcript.robyncrane.com` for regression and manual-caption control.
- Public Phase 1 matrix run: 8 of 9 cases are release-valid. Regression, control, manual_caption, automatic_caption, shorts, long_video, private_unavailable, and invalid_url passed. Non-English returned helpful HTTP 422 upload guidance and remains the only release-gap.
- Public Phase 2 upload smoke: generated WAV, MP3, and MP4 fixtures all returned HTTP 200 through `local-whisper` with credible nonempty transcript text.
- New reusable public Phase 2 upload smoke script added at `scripts/phase2_upload_smoke.py`.
- New targeted regression tests for launchd/minimal-PATH binary resolution passed.
- Local generated MP3 upload through FastAPI TestClient passed via `local-whisper` after absolute Whisper binary resolution.
- Design regression tests: passed for Call IQ tokens, hero control placement, dark presentation surface, and light results workspace.
- Public TXT/Markdown/SRT downloads for regression record: passed in prior release-gate evidence.

## Known problems
- The public hostname now has launchd KeepAlive hardening, but it still depends on this iMac and Cloudflare Tunnel. A hosted durable backend remains the cleaner whole-project final release path.
- SMTP config is missing, so Email to Me is not ready.
- Gemini YouTube hook is intentionally present but not enabled because no key is configured and the free caption/local path is primary.
- Browser WebGPU Whisper is not implemented yet. Local server Whisper fallback exists.
- Full Phase 1 matrix is not complete because current non-English YouTube candidates are returning upload-guidance failures under YouTube blocking/rate limiting, and previously cached Despacito evidence could return English subtitles.
- Public API has reloaded the helpful invalid-link behavior. Invalid non-YouTube URL now returns HTTP 422 instead of HTTP 500.

## Blockers
None requiring Trevor right now.

## Exact next action
Commit and push the public Phase 2 upload smoke script and updated release evidence, then continue closing the final Phase 1 non-English YouTube evidence gap. If YouTube continues blocking non-English public candidates, switch to documenting that case as a helpful-failure gate and move Phase 2 toward the full upload/media matrix.
