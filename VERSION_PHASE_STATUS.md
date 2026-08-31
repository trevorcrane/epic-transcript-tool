# EPIC Transcript Machine Version / Phase Status

Updated: 2026-08-31 00:38 EDT

## Version 1 / Phase 1: Bulletproof YouTube Transcripts
Status: In release verification.

Done means the public production URL passes the full YouTube matrix, not just a build or localhost test.

Current evidence:
- Public URL: https://epic-transcript.robyncrane.com/
- Regression video passed publicly with correct title, 1,460 segments, 15,744 words, increasing timestamps, and cache hit.
- Manual-caption control passed publicly with 61 segments and 366 words.
- TXT, Markdown, and SRT downloads passed for the regression record.
- Public no-login access passed after launchd API and tunnel hardening.
- Public Phase 1 matrix is 8 of 9 release-valid. Latest run completed without Cloudflare 524s after stale Whisper workers were cleared; invalid and unavailable URLs return helpful HTTP 422 guidance.
- Epic Call IQ-inspired UI redesign is live.

Remaining:
- Replace or prove a release-valid original-language non-English matrix source. Current Despacito public run returns helpful long-video/upload guidance, and earlier cache evidence could return `en-US`, which is not valid non-English evidence.
- Complete browser copy-flow, mobile touch-flow, and fuller accessibility evidence.
- Move from iMac plus Cloudflare Tunnel to a hosted durable backend when ready for whole-project final release.

## Version 2 / Phase 2: Any Video or Audio
Status: Started.

Done means uploads and technically/legal accessible non-YouTube media work with clear progress, cache, cleanup, copy, TXT, Markdown, and SRT.

Current evidence:
- Uploaded MP3 passed through local Whisper in prior local evidence.
- Uploaded M4A passed through local Whisper in prior local evidence.
- Uploaded MP4 passed through local Whisper in prior local evidence.
- Direct public-media-style URL passed through local Whisper in prior local evidence.
- Public upload smoke passed again for generated WAV, MP3, and MP4 through `local-whisper` with credible nonempty transcripts after clearing stale orphan Whisper workers.
- Added reusable public upload gate script: `scripts/phase2_upload_smoke.py`.
- Hardening added so `yt-dlp`, `ffmpeg`, and local Whisper can be found from launchd's minimal environment using configured env vars or absolute known paths.

Remaining:
- MP4, MOV, WebM, MP3, M4A, WAV full release matrix.
- 30+ minute recording.
- Non-English recording.
- Supported non-YouTube URL.
- Unsupported URL guidance.
- Mobile/WebGPU/fallback evidence.

## Version 3 / Phase 3: Video Intelligence
Status: Started in queued backend tests, not public-release complete.

Done means every post-transcript intelligence button produces useful timestamp-cited outputs without hiding or damaging the original transcript.

Current evidence:
- Backend analysis route tests are queued for `/api/analyze/{id}`.
- Expected safeguards are defined: preserve the original transcript, include timestamp evidence, return useful output for all declared analysis types, and allow downloads.

Remaining:
- Implement the analysis route and make the queued tests active.
- Wire all intelligence buttons into the UI.
- Verify long transcript handling.
- Verify copy/download and repeated analysis cache.
- Add provider hook for Gemini/LLM only when keys are configured. No billing introduced.

## 30-minute loop
A recurring Hermes cron job is installed:
- Job ID: 26ac787743cc
- Name: EPIC Transcript Machine 30-minute progress loop
- Schedule: every 30m
- Delivery: back to origin chat
- Purpose: continue implementation, test, update docs, and post a concise progress report every run.
