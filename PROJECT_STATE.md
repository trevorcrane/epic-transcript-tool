# PROJECT_STATE.md

Updated: 2026-08-30 23:24 EDT

## Current phase
Phase 1: Bulletproof YouTube Transcripts. Active gate is production release verification and backend hardening.

## Version / phase status

### Version 1 / Phase 1: Bulletproof YouTube transcripts
Status: In release verification.
- Public no-login app: https://epic-transcript.robyncrane.com/
- Core regression remains passing publicly with 1,460 segments and 15,744 words for `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`.
- Manual-caption control now has fresh public evidence: `dQw4w9WgXcQ`, 61 segments, 366 words, method `native-caption-subtitles`, cache hit.
- Release matrix is partially passing. Non-English test case needs a better known-accessible source video or fallback work because the previous Despacito case is blocked by YouTube.
- Backend hardening advanced: the FastAPI API and Cloudflare named tunnel are loaded under launchd KeepAlive agents.
- Public matrix re-run now exposes two release-gate issues instead of one: the previously cached Despacito record can return an English subtitle track, so it is not valid non-English evidence, and the invalid-URL public case returned HTTP 500 from the currently running API process.

### Version 2 / Phase 2: Any video or audio
Status: Started, not release-complete.
- Local Whisper upload path exists and previous local evidence covered MP3, M4A, MP4, and direct public-media-style URL.
- Full upload/media release matrix still needs production evidence.
- Advanced backend hardening: local code now resolves `yt-dlp`, `ffmpeg`, and Whisper by configured or absolute binary path when launchd starts with a minimal PATH. The launchd API plist now sets `YT_DLP_BIN=/usr/local/bin/yt-dlp`, `FFMPEG_BIN=/usr/local/bin/ffmpeg`, `WHISPER_BIN=/usr/local/bin/whisper`, plus a known PATH for the next API restart.
- Fresh local upload proof after the fix: generated MP3 upload returned HTTP 200 through `local-whisper`, 2 segments, 18 words, first text `Epic transcript machine phase 2 audio upload test.`

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
- `./.venv/bin/python -m pytest -q`: passed, 15 tests on 2026-08-30 22:40 EDT.
- Public root/setup after launchd hardening: HTTP 200 / HTTP 200.
- Public Phase 1 health script after launchd hardening: passed regression and manual-caption control.
- Public Phase 1 health script: passed regression and manual-caption control.
- Public Phase 1 matrix run: 7 of 9 cases are release-valid. Regression, control, manual_caption, automatic_caption, shorts, long_video, and private_unavailable passed. The non_english row returned HTTP 200 from cache but with language `en-US`, so it is not valid non-English evidence. The invalid_url row returned HTTP 500 from the currently running public process and needs the API restart/code reload to pick up the local helpful 422 behavior.
- `./.venv/bin/python -m pytest -q`: passed, 17 tests on 2026-08-30 23:24 EDT.
- New targeted regression tests for launchd/minimal-PATH binary resolution passed.
- Local generated MP3 upload through FastAPI TestClient passed via `local-whisper` after absolute Whisper binary resolution.
- Design regression tests: passed for Call IQ tokens, hero control placement, dark presentation surface, and light results workspace.
- Public TXT/Markdown/SRT downloads for regression record: passed in prior release-gate evidence.

## Known problems
- The public hostname now has launchd KeepAlive hardening, but it still depends on this iMac and Cloudflare Tunnel. A hosted durable backend remains the cleaner whole-project final release path.
- SMTP config is missing, so Email to Me is not ready.
- Gemini YouTube hook is intentionally present but not enabled because no key is configured and the free caption/local path is primary.
- Browser WebGPU Whisper is not implemented yet. Local server Whisper fallback exists.
- Full Phase 1 matrix is not complete because the current non-English evidence is not release-valid and fresh non-English YouTube candidates are currently returning upload-guidance failures under YouTube blocking/rate limiting.
- Public API process has not yet reloaded the local binary-path hardening. Launchd plist is updated for the next restart, but the restart attempt was held by the automation approval guard.

## Blockers
None requiring Trevor right now.

## Exact next action
Commit and push the binary-path hardening and release evidence updates, then reload the public API as soon as the automation guard allows it. After reload, verify public setup, public upload audio, invalid-URL helpful failure, and continue searching for release-valid non-English YouTube evidence.
