# PROJECT_STATE.md

Updated: 2026-08-31 04:06 EDT

## Current phase
Phase 1: Bulletproof YouTube Transcripts. Active gate is production release verification and backend hardening.

## Version / phase status

### Version 1 / Phase 1: Bulletproof YouTube transcripts
Status: Near release-clear. Non-English, genuine Shorts, and two-hour/long-video evidence are now passing publicly; browser copy/touch-flow evidence remains open.
- Public no-login app: https://epic-transcript.robyncrane.com/
- Core regression remains passing publicly with 1,460 segments and 15,744 words for `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`.
- Manual-caption control now has fresh public evidence: `dQw4w9WgXcQ`, 61 segments, 366 words, method `native-caption-subtitles`, cache hit.
- Public Phase 1 scripted matrix is now passing against the durable no-login URL for the bounded fixture set: regression, manual-caption control, automatic captions, short French non-English fixture, genuine Shorts, moderate long cached transcript, private/unavailable helpful failure, invalid URL helpful failure, privacy/history, service health, and public upload smoke.
- Backend hardening advanced: the FastAPI API and Cloudflare named tunnel are loaded under launchd KeepAlive agents.
- New non-English production evidence: `https://youtu.be/kv92eqcZVxs`, title `✅ 10 phrases simples en français à apprendre en 1 minute !`, HTTP 200, method `local-whisper`, language `fr`, 2 segments, 37 words, credible French text. First uncached run passed at 2026-08-31 01:34 EDT and repeated matrix run confirmed cache hit.
- New two-hour public long-video proof: `https://www.youtube.com/watch?v=rwfk91ya81s`, job `115c983594bd`, record `5919d7b3c99a`, title `2 Hours of the Craziest Philosophical Theories to Fall Asleep to`, duration 7,244 seconds, HTTP 202 async start then job `done`, method `queued-chunked-local-whisper`, cache miss, 13 audio chunks, 1,446 segments, 19,298 words, language `en`. Native captions, YouTube Transcript API, and yt-dlp subtitles failed/skipped, then chunked local Whisper produced a credible beginning and ending. Public TXT, Markdown, and SRT signed downloads verified HTTP 200.

### Version 2 / Phase 2: Any video or audio
Status: Advanced, not release-complete.
- Local Whisper upload path exists and previous local evidence covered MP3, M4A, MP4, and direct public-media-style URL.
- Full upload/media release matrix still needs completion, but the public API now has production upload proof for generated WAV, MP3, M4A, MP4, MOV, and WebM fixtures.
- Advanced public verification: expanded `scripts/phase2_upload_smoke.py`, which generates a spoken fixture with macOS `say`, converts it with `ffmpeg`, uploads WAV/MP3/M4A/MP4/MOV/WebM to the public no-login API, verifies credible nonempty local-Whisper transcripts, confirms repeat-upload cache reuse, and verifies signed TXT/Markdown/SRT downloads for an upload record.
- Added reusable `scripts/phase2_non_english_upload_smoke.py` for public non-English upload proof without paid providers. It generates French speech with macOS `say -v Thomas`, converts to WAV with `ffmpeg`, uploads to the public no-login API, verifies `local-whisper`, language `fr`, credible French text, and a signed TXT download.
- Fresh public upload proof from 2026-08-31 03:30 EDT: WAV returned HTTP 200 through `local-whisper`, 2 segments, 18 words, cache hit; MP3 returned HTTP 200 through `local-whisper`, 2 segments, 18 words, cache hit; M4A returned HTTP 200 through `local-whisper`, 2 segments, 18 words, cache hit; MP4 returned HTTP 200 through `local-whisper`, 1 segment, 12 words, cache hit; MOV returned HTTP 200 through `local-whisper`, 1 segment, 12 words, cache hit; WebM returned HTTP 200 through `local-whisper`, 1 segment, 12 words, cache miss. Repeat WAV upload returned HTTP 200, `cache_hit=true`, same 18-word transcript. Signed upload downloads passed: TXT HTTP 200, 136 bytes; Markdown HTTP 200, 239 bytes; SRT HTTP 200, 186 bytes.
- Fresh non-English public upload proof from 2026-08-31 04:06 EDT: generated French WAV returned HTTP 200 in 7.78s through `local-whisper`, language `fr`, cache miss, 2 segments, 22 words. Credible text: `Bonjour, ceci est un test français... reconnaître des mots simples en français sans fournisseur payant.` Signed TXT download returned HTTP 200, 174 bytes.

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
- Cleared stale orphan Whisper workers from an old duplicate API process, restoring public Phase 2 upload smoke from Cloudflare 524s to HTTP 200 passes.
- Cleared a duplicate foreground API process that was holding port 8090 outside launchd, then kickstarted `com.epic.transcript-api`. Public `/health` recovered from Cloudflare 502 to HTTP 200 and launchd now owns the running API process.
- Expanded Phase 2 generated-media release smoke coverage from WAV/MP3/MP4 to WAV/MP3/M4A/MP4/MOV/WebM and verified all six against the public no-login API.
- Expanded `scripts/phase2_upload_smoke.py` again to include an owner token, repeat-upload cache proof, and signed TXT/Markdown/SRT download verification for uploaded media.
- Added and publicly verified `scripts/phase2_non_english_upload_smoke.py` for non-English uploaded recording release evidence.

## Latest production regression evidence
URL tested: `https://epic-transcript.robyncrane.com/api/transcribe-url`
Regression video: `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`

Fresh health run from 2026-08-31 02:53 EDT:
- Public root: HTTP 200.
- Public health: HTTP 200, `ready: true`, `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Regression video: HTTP 200, method `native-caption-automatic_captions`, cache hit, 1,460 segments, 15,744 words, language `en`, title `Sell AI Systems, Not AI Agents (how I made $5,407,902 last year)`.
- Manual-caption control `dQw4w9WgXcQ`: HTTP 200, method `native-caption-subtitles`, cache hit, 61 segments, 366 words, language `en`, title `Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)`.
- Two-hour fixture `rwfk91ya81s`: public async job `115c983594bd` completed with record `5919d7b3c99a`, method `queued-chunked-local-whisper`, duration 7,244 seconds, 13 chunks, 1,446 segments, 19,298 words, cache hit `false`. Download verification for the new long record: TXT HTTP 200, 121,979 bytes; Markdown HTTP 200, 127,963 bytes; SRT HTTP 200, 158,972 bytes.

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
- `./.venv/bin/python -m pytest -q`: passed, 32 tests on 2026-08-31 04:06 EDT.
- Public root: HTTP 200, expected app markers present.
- Public health: HTTP 200, `ready: true`, `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public Phase 1 health script now correctly accepts a CLI base URL and passed against `https://epic-transcript.robyncrane.com` for regression and manual-caption control.
- Public Phase 1 matrix from 2026-08-31 02:16 EDT: all 9 bounded scripted cases passed against `https://epic-transcript.robyncrane.com`, including the new French non-English fixture, genuine Shorts URL, moderate long-video cached transcript, and helpful 422 failures for private/unavailable plus invalid URL.
- Public two-hour/long-video async proof from 2026-08-31 02:52 EDT: job `115c983594bd` returned record `5919d7b3c99a` with HTTP 200 job readback, method `queued-chunked-local-whisper`, 13 chunks, 1,446 segments, 19,298 words, and credible start/end transcript text. Signed TXT, Markdown, and SRT downloads for that long record returned HTTP 200.
- Public Phase 2 upload smoke from 2026-08-31 03:30 EDT: generated WAV, MP3, M4A, MP4, MOV, and WebM fixtures all returned HTTP 200 through `local-whisper` with credible nonempty transcript text. Repeat WAV upload returned `cache_hit=true` with the same 18-word transcript. Signed TXT, Markdown, and SRT downloads for the upload record returned HTTP 200.
- Public Phase 2 non-English upload smoke from 2026-08-31 04:06 EDT: generated French WAV returned HTTP 200 in 7.78s via `local-whisper`, language `fr`, cache miss, 2 segments, 22 words, and signed TXT download HTTP 200.
- Long-video async proof completed at 2026-08-31 02:52 EDT using `scripts/public_long_video_proof.py` against two-hour fixture `https://www.youtube.com/watch?v=rwfk91ya81s`. Public API returned HTTP 202, job `115c983594bd` completed `done`, and record `5919d7b3c99a` returned 1,446 segments and 19,298 words through 13 chunked local-Whisper audio chunks.
- Backend restore verification from 2026-08-31 01:34 EDT: local `/health` HTTP 200, public `/health` HTTP 200, `com.epic.transcript-api` state `running`, PID 99082.
- Reusable public Phase 2 upload smoke script expanded at `scripts/phase2_upload_smoke.py`.
- New targeted regression tests for launchd/minimal-PATH binary resolution passed.
- Local generated MP3 upload through FastAPI TestClient passed via `local-whisper` after absolute Whisper binary resolution.
- Design regression tests: passed for Call IQ tokens, hero control placement, dark presentation surface, and light results workspace.
- Public TXT/Markdown/SRT downloads for regression record: passed in prior release-gate evidence.

## Known problems
- The public hostname now has launchd KeepAlive hardening, but it still depends on this iMac and Cloudflare Tunnel. A hosted durable backend remains the cleaner whole-project final release path.
- SMTP config is missing, so Email to Me is not ready.
- Gemini YouTube hook is intentionally present but not enabled because no key is configured and the free caption/local path is primary.
- Browser WebGPU Whisper is not implemented yet. Local server Whisper fallback exists.
- Phase 1 bounded scripted public matrix and two-hour/long-video transcription are passing, but copy-flow browser interaction and fuller mobile touch-flow evidence are still needed before calling Version 1 fully release-clear.
- Public API has reloaded the helpful invalid-link behavior. Invalid non-YouTube URL now returns HTTP 422 instead of HTTP 500.

## Blockers
- Browser copy/touch-flow evidence is blocked by macOS Chrome's `Allow remote debugging?` permission prompt for the browser harness. API and scripted public checks are not blocked; a retry at 2026-08-31 03:30 EDT reproduced the same permission blocker.

## Exact next action
Run browser copy-flow and mobile touch-flow verification once Chrome remote-debug permission is available. In parallel, add Phase 2 proof for a longer uploaded recording and a supported public non-YouTube media URL.

### 2026-08-31 non-English YouTube gate update
- PASS: Fresh uncached exact fixture `https://www.youtube.com/watch?v=vgIle-XrvQI` completed through the new bounded async public route. Start request returned HTTP 202 in 0.08s, polling stayed under 0.1s per request, and final record returned French metadata `language=fr`, `method=local-whisper`, `cache_hit=false`, 31 segments, 228 words, duration 95s.
- Provider evidence for the exact fixture: metadata passed; native caption extractor skipped after timedtext 429s to protect the proxy; YouTube Transcript API skipped for original-language non-English route; yt-dlp subtitle-only failed with no captions; Gemini unavailable; local Whisper passed.
- Genuine Shorts fixture `1WW76Rz4nqM` now returns a transcript from cache via local Whisper: HTTP 200, 13 segments, 151 words, language `en`.
- Long-video transcription remains open. Current CS50 source has YouTube caption access blocked from this origin and audio fallback is too long for the public synchronous path. Do not mark long-video support passed until a long source returns a transcript, not only a bounded helpful 422.


### 2026-08-31 true long-video gate update
- PASS: Fresh public async long-video job completed for `https://www.youtube.com/watch?v=rwfk91ya81s`, title `2 Hours of the Craziest Philosophical Theories to Fall Asleep to`.
- Public async start returned HTTP 202 in 0.08s. Job `4985137fae62` completed with status `done` after 2,049.43s elapsed.
- Duration: 7,244s. Saved record `002b65bba5bb` with method `queued-chunked-local-whisper`, language `en`, 13 audio chunks, 1,446 timestamped segments, 19,298 words, `cache_hit=false`, processing time 2,039.96s.
- Failure-recovery evidence: native caption extractor failed with no usable caption track; YouTube Transcript API was blocked by YouTube/IP; yt-dlp subtitles found no captions; queued chunked local Whisper recovered and passed.
- Progress evidence: public job reported download stage, then chunk progress from 1 of 13 through 12 of 13, then saving with chunks_done 13 / chunks_total 13.
- Transcript proof includes credible beginning at `[00:00] Imagine you're sitting on your couch...` and credible ending through `[02:00:42] together.`
