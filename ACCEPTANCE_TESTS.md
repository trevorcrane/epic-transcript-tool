# ACCEPTANCE_TESTS.md

## Release standard
A phase is done only when the public, no-login production product passes the full release gate with credible outputs. Building, compiling, localhost success, or a progress report does not count.

## Current production URL
- App: https://epic-transcript.robyncrane.com/
- API: https://epic-transcript.robyncrane.com/api/transcribe-url

## Phase 1 release gate: Bulletproof YouTube transcripts

Production system must remain publicly accessible with no visitor login or signup.

### Regression video, must pass twice in production
URL: https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD

Pass criteria:
- More than 700 transcript segments.
- More than 5,000 words.
- Correct title.
- Nonempty beginning and ending.
- Increasing timestamps.
- Credible, nonempty transcript.
- Second repeated request confirms cache hit.

Current evidence from 2026-08-30 18:18 EDT:

Run 1: PASS
- Public endpoint: `https://epic-transcript.robyncrane.com/api/transcribe-url`
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

Run 2: PASS
- Public endpoint: `https://epic-transcript.robyncrane.com/api/transcribe-url`
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

### Fresh production health evidence
Run time: 2026-08-31 08:53 EDT.

- Public app root: PASS, HTTP 200, 41,404 bytes, no visitor login.
- Netlify review root: PASS, HTTP 200, 41,404 bytes at `https://epic-transcript-machine-review.netlify.app` and immutable deploy `https://6a9579a7b662aa6824e325ab--epic-transcript-machine-review.netlify.app`.
- ChatGPT-reference UX alignment markers: PASS. Root HTML contains `Free Video Transcript`, `Generator`, `FAST · FREE · V3`, `Get Video Transcript`, `Quick and simple. No catch.`, `How it works`, `Frequently Asked Questions (FAQ)`, `faq-stage`, and `step-grid`.
- Review build API base marker: PASS. Netlify HTML contains `https://epic-transcript.robyncrane.com` so review-page actions target the production no-login API.
- Layout ordering: PASS. The primary `hero-control` appears before `How it works`, and `How it works` appears before `Frequently Asked Questions`.
- Public `/health`: PASS, HTTP 200, `ready: true`, required `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public Phase 1 health script: PASS. Regression video returned HTTP 200, cache hit, 1,460 segments, 15,744 words, language `en`; manual-caption control returned HTTP 200, cache hit, 61 segments, 366 words, language `en`.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 44 passed. Static inline script syntax check also passed with `node --check` for the single inline script block.

Run time: 2026-08-31 01:34 EDT.

- Public app root: PASS, HTTP 200.
- Public setup endpoint: PASS, HTTP 200, `ready: true`, required `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public release checker scripts now send a normal browser-style user agent so Cloudflare does not reject Python urllib checks with 1010.
- Backend durability step: `com.epic.transcript-api` and `com.epic.transcript-tunnel` are loaded under launchd with KeepAlive.
- Public Phase 1 health script now accepts a CLI base URL, and the public run passed regression plus manual-caption control.
- Public Phase 1 bounded scripted matrix now passes all 9 cases. Regression, manual-caption control, automatic captions, short French non-English fixture, genuine Shorts, moderate long cached transcript, private/unavailable helpful failure, invalid URL helpful failure, privacy/history, service health, and public upload smoke pass.
- The stricter two-hour/long-video release gate now has public pass evidence from 2026-08-31 02:52 EDT: `https://www.youtube.com/watch?v=rwfk91ya81s` started asynchronously with HTTP 202, job `115c983594bd` completed `done`, and record `5919d7b3c99a` returned title `2 Hours of the Craziest Philosophical Theories to Fall Asleep to`, method `queued-chunked-local-whisper`, language `en`, duration 7,244 seconds, 13 chunks, 1,446 segments, 19,298 words, cache hit `false`, and credible beginning/ending transcript text. Signed public downloads for that record passed: TXT HTTP 200, 121,979 bytes; Markdown HTTP 200, 127,963 bytes; SRT HTTP 200, 158,972 bytes.

### Additional Phase 1 cases
Status: bounded scripted matrix and two-hour/long-video transcription passing in production. Full release gate still open for browser copy/touch-flow evidence.

| Case | URL | Result | Evidence |
| --- | --- | --- | --- |
| Control video | `https://youtu.be/dQw4w9WgXcQ` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 61 segments, 366 words, language `en`. |
| Manual-caption video | `https://youtu.be/dQw4w9WgXcQ` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 61 segments, 366 words. |
| Automatic-caption video | `https://youtu.be/v34Eg12mhDM` | PASS | HTTP 200, `native-caption-automatic_captions`, cache hit, 1,460 segments, 15,744 words. |
| Non-English video | `https://youtu.be/kv92eqcZVxs` plus async fixture `https://www.youtube.com/watch?v=vgIle-XrvQI` | PASS | Short French fixture returned HTTP 200, `local-whisper`, cache hit on repeated matrix run, 2 segments, 37 words, language `fr`, credible French text. Separate fresh uncached async French fixture returned 31 segments, 228 words, language `fr`. |
| Genuine Shorts URL | `https://www.youtube.com/shorts/SXHMnicI6Pg` plus `https://www.youtube.com/shorts/1WW76Rz4nqM` | PASS | Scripted Shorts fixture returned HTTP 200, `native-caption-automatic_captions`, cache hit, 2 segments, 3 words. Stronger exact Shorts fixture `1WW76Rz4nqM` returns HTTP 200 from cache via `local-whisper`, 13 segments, 151 words. Needs periodic fresh-cache-miss recheck. |
| Private/unavailable video | `https://www.youtube.com/watch?v=aaaaaaaaaaa` | PASS helpful failure | HTTP 422 with upload guidance. |
| Invalid URL | `https://not-a-real.example/video` | PASS helpful failure | Public matrix returned HTTP 422 with upload guidance after API reload. |
| Moderate long video | `https://youtu.be/aircAruvnKk` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 286 segments, 3,360 words. |
| Two-hour / long video | `https://www.youtube.com/watch?v=rwfk91ya81s` | PASS | Public async job `115c983594bd` completed `done`, record `5919d7b3c99a`, `queued-chunked-local-whisper`, cache miss, 13 chunks, 1,446 segments, 19,298 words, 7,244 seconds, credible start/end transcript. TXT/Markdown/SRT signed downloads returned HTTP 200. |
| Repeated request confirms a cache hit | Regression and control videos | PASS | Public health script returned cache hit for both. |
| Copy transcript | UI marker present | Pending browser interaction evidence | Needs direct browser copy-flow verification. |
| TXT download | Regression record | PASS | HTTP 200, 94,784 bytes. |
| Markdown download | Regression record | PASS | HTTP 200, 100,829 bytes. |
| SRT download | Regression record | PASS | HTTP 200, 134,557 bytes. |
| Mobile layout | Redesign evidence | PASS visual smoke | Mobile screenshot evidence exists in `evidence/`; full touch-flow still pending. |
| Button contrast and accessibility | Automated design tests | PASS smoke | Design tests passed for dark presentation surface, light results workspace, and functional IDs. Full accessibility audit still pending. |

## Phase 2 release gate: Any video or audio

Current implementation evidence:
- 2026-08-31 08:53 EDT: public UX copy now explicitly names public media URL and upload format support in the how-it-works and FAQ sections. Root HTML verification passed for no-login public access and expected markers.
- 2026-08-31 08:18 EDT: added cleanup/retention hardening and regression evidence.
- Upload temporary media cleanup: PASS automated. `test_upload_temp_directory_is_removed_after_processing` proves the server removes the per-upload temp directory after processing.
- Transcript and analysis retention cleanup: PASS automated and public. `test_delete_transcript_removes_saved_analysis_for_retention` proves an owner-authorized transcript delete removes the transcript and its saved analysis rows; SQLite connections now enable foreign-key enforcement. Public API verification after restart: record `c40edf087acd` and analysis `c3e5e11163a0` both returned HTTP 404 after delete.
- 2026-08-31 05:17 EDT: added `test_non_youtube_media_url_falls_back_to_local_whisper` plus `scripts/phase2_public_url_smoke.py`, then ran it against the public no-login API.
- Public supported non-YouTube media URL: PASS. Fixture `https://epic-transcript.robyncrane.com/static/phase2-public-url.mp3` returned HTTP 206 byte-range, `audio/mpeg`; `/api/transcribe-url` returned HTTP 200 in 8.93s, method `local-whisper`, source_kind `url`, language `en`, cache miss, 2 segments, 18 words. Credible transcript begins `Epic transcript machine phase 2 public URL test...`. Provider trail shows native captions failed cleanly, then free local Whisper succeeded.
- 2026-08-31 04:42 EDT: added upload duration detection and ran `scripts/phase2_long_upload_smoke.py` against the public no-login API.
- Public generated 31-minute MP3 upload: PASS, HTTP 200 in 54.50s, method `local-whisper`, duration `1862.0` seconds, language `en`, cache miss, 3 segments, 34 words, credible transcript begins `Epic transcript machine long upload proof...` and includes `[31:00]` continuation text.
- 2026-08-31 04:06 EDT: added and ran `scripts/phase2_non_english_upload_smoke.py` against the public no-login API.
- Public generated French WAV upload: PASS, HTTP 200 in 7.78s, method `local-whisper`, language `fr`, cache miss, 2 segments, 22 words, credible French text begins `Bonjour, ceci est un test français...`.
- French upload TXT download: PASS, signed TXT link for upload record `17acab42e88f` returned HTTP 200, 174 bytes, with French transcript marker.
- 2026-08-31 03:30 EDT: reran expanded `scripts/phase2_upload_smoke.py` against the public no-login API with owner-scoped upload, cache, and download checks.
- Public generated WAV upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`, cache hit on this run because the fixture had already been processed.
- Public generated MP3 upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`, cache hit.
- Public generated M4A upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`, cache hit.
- Public generated MP4 upload: PASS, HTTP 200, method `local-whisper`, 1 segment, 12 words, credible text begins `Epic transcript machine phase 2 public upload test...`, cache hit.
- Public generated MOV upload: PASS, HTTP 200, method `local-whisper`, 1 segment, 12 words, credible text begins `Epic transcript machine phase 2 public upload test...`, cache hit.
- Public generated WebM upload: PASS, HTTP 200, method `local-whisper`, 1 segment, 12 words, credible text begins `Epic transcript machine phase two public upload test...`, cache miss.
- Repeat generated WAV upload: PASS, HTTP 200, `cache_hit=true`, same 18-word transcript evidence.
- Upload downloads: PASS. Signed TXT, Markdown, and SRT links for upload record `6a047551b093` returned HTTP 200 with expected markers. Sizes: TXT 136 bytes, Markdown 239 bytes, SRT 186 bytes.
- 2026-08-31 02:16 EDT: reran expanded `scripts/phase2_upload_smoke.py` against the public no-login API.
- Public generated WAV upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
- Public generated MP3 upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
- Public generated M4A upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
- Public generated MP4 upload: PASS, HTTP 200, method `local-whisper`, 1 segment, 12 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
- Public generated MOV upload: PASS, HTTP 200, method `local-whisper`, 1 segment, 12 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
- Public generated WebM upload: PASS, HTTP 200, method `local-whisper`, 1 segment, 12 words, credible text begins `Epic transcript machine phase two public upload test...`.
- 2026-08-30 23:24 EDT: local code now resolves `yt-dlp`, `ffmpeg`, and Whisper through configured or absolute binary paths when launchd has a minimal PATH.
- `com.epic.transcript-api.plist` includes `YT_DLP_BIN=/usr/local/bin/yt-dlp`, `FFMPEG_BIN=/usr/local/bin/ffmpeg`, `WHISPER_BIN=/usr/local/bin/whisper`, plus a known PATH.
- Generated MP3 upload passed locally through FastAPI TestClient with HTTP 200, method `local-whisper`, 2 segments, 18 words, and first text `Epic transcript machine phase 2 audio upload test.`

Successfully process:
- Uploaded MP4.
- Uploaded MOV.
- Uploaded WebM.
- Uploaded MP3.
- Uploaded M4A.
- Uploaded WAV.
- Non-English recording. Public French WAV upload passed via local Whisper on 2026-08-31 04:06 EDT.
- 30+ minute recording. Public generated 31-minute MP3 upload passed via local Whisper on 2026-08-31 04:42 EDT with duration metadata `1862.0` seconds.
- Supported non-YouTube URL. Public hosted MP3 URL passed on 2026-08-31 05:17 EDT via `/api/transcribe-url`, `local-whisper`, 2 segments, 18 words, no paid provider.
- Unsupported URL with helpful upload guidance.
- Desktop Chrome.
- Mobile experience.
- Browser without WebGPU using planned fallback.

Verify:
- Timestamps.
- Word count.
- Copy.
- TXT download.
- Markdown download.
- SRT download.
- No required paid provider or surprise usage bills.
- Automatic deletion of temporary server media. PASS automated on 2026-08-31 08:18 EDT for upload work directories; public API uses per-request temp dirs and `finally` cleanup.

## Phase 3 release gate: Video intelligence

After transcript completion, optional one-click outputs must include:
- Executive summary.
- Main ideas.
- Action items.
- Chapters with timestamps.
- Best quotes with timestamps.
- Stories and examples.
- Content framework.
- Blog post.
- Newsletter.
- Social posts.
- Short-form video hooks.
- FAQ.
- Sales insights.
- Objections and answers.
- “How can Trevor use this?”
- “Create 100 content assets”.
- Ask questions about the video.

Pass criteria:
- All AI buttons produce useful outputs.
- Outputs cite transcript timestamps where relevant.
- Long transcripts are handled without truncating critical sections.
- Results can be copied and downloaded.
- Failures do not destroy or hide the original transcript.
- Repeated analysis can reuse cached transcript/context.
- Mobile interface remains usable.
- Generative summaries are clearly distinguished from transcript text.
- Verbatim quotes are not fabricated.

Current evidence:
- 2026-08-31 08:53 EDT: public root still contains Phase 3 analysis markers after the UX alignment pass, including `/api/analyze-all/`, `analysisMenu`, `analysisCopyBtn`, and the ask-a-question controls.
- 2026-08-31 06:32 EDT: Phase 3 starter backend and expanded full-menu UI are live on `https://epic-transcript.robyncrane.com/`.
- 2026-08-31 07:43 EDT: long-transcript Phase 3 public proof passed on the two-hour cached fixture. The backend now samples beginning, middle, and ending timestamp evidence for long records instead of only the opening segments.
- 2026-08-31 07:07 EDT: combined-output copy/download path is live on `https://epic-transcript.robyncrane.com/`.
- Public UI markers: PASS. Root HTML returned HTTP 200 and contains `AI Summary`, `Action Items`, `All Outputs`, `Copy Analysis`, the full output menu container `analysisMenu`, copy control `analysisCopyBtn`, ask-a-question input, `Download Analysis`, `/api/analyze/`, and `/api/analyze-all/` markers.
- Backend starter outputs: PASS. `tests/test_phase3.py` covers owner-protected `/api/analyze/{id}`, `/api/analyze-all/{id}`, every declared `ANALYSIS_OUTPUTS` type, beginning/middle/end evidence sampling for long records, original transcript preservation, Markdown analysis download, combined-output Markdown download, and migration of an older partial `analyses` table.
- Public API proof: PASS starter. Cached control transcript `dQw4w9WgXcQ` returned HTTP 200 with record `2f2b61d2ccf6`, method `native-caption-subtitles`, 366 words, cache hit. `/api/analysis-outputs` returned 17 definitions. All 17 `/api/analyze/{record_id}` calls returned HTTP 200 with useful nonempty text, `AI-generated` disclaimer, and transcript evidence, including `ask_question` with `What should Trevor do with this video?`.
- Public combined-output proof: PASS starter. `scripts/phase3_combined_analysis_smoke.py https://epic-transcript.robyncrane.com` passed at 2026-08-31 07:07 EDT. Cached control transcript returned record `1f5a2b16abd8`, 366 words, method `native-caption-subtitles`, cache hit. `/api/analyze-all/{id}` returned 16 combined starter outputs, 10,036 copy-ready characters, and analysis ID `bfb7ef1f1bab`. `/api/analysis/bfb7ef1f1bab/download` returned HTTP 200, `text/markdown`, 10,600 bytes.
- Public long-transcript combined-output proof: PASS starter. `scripts/phase3_long_analysis_smoke.py https://epic-transcript.robyncrane.com` passed at 2026-08-31 07:43 EDT. Async job `c345b34bc0ba` returned record `837a9891f74d` for the two-hour cached fixture with 19,298 words, 1,446 segments, duration 7,244s, method `queued-chunked-local-whisper`, cache hit. `/api/analyze-all/{id}` returned 16 outputs, 19,106 copy-ready characters, latest cited analysis timestamp 7,242s, and analysis ID `8215f62db5fa`. `/api/analysis/8215f62db5fa/download` returned HTTP 200, `text/markdown`, 19,106 bytes.
- Limit: this is deterministic provider-safe starter intelligence, not the full AI release gate. Fuller AI/provider-backed intelligence quality, mobile interaction proof, and browser click/touch verification remain open. Browser proof is currently blocked by macOS Chrome's `Allow remote debugging?` permission prompt.

## Automated quality loop

Tests run:
- Before deployment.
- After production deployment.
- Daily schedule.

Daily health videos:
- Manual captions.
- Automatic captions.
- Original regression case.

Record for each run:
- HTTP status.
- Provider attempted.
- Provider that succeeded.
- Segment count.
- Word count.
- Language.
- Processing duration.
- Cache status.
- Error category.

Failure behavior:
- If a provider fails, continue to the next provider.
- If the complete pipeline fails, produce a clear alert and retain enough diagnostic information to reproduce it without exposing secrets.

| Two-hour / long video | Fresh 2-hour fixture `https://www.youtube.com/watch?v=rwfk91ya81s` | PASS | Public async job `115c983594bd` returned HTTP 202, then completed `done` after 2,050.73s using `queued-chunked-local-whisper`; duration 7,244s, 13 chunks, 1,446 timestamped segments, 19,298 words, language `en`, cache miss. |

| Exact French YouTube async fallback | `https://www.youtube.com/watch?v=vgIle-XrvQI` | PASS | Fresh uncached public async job. HTTP 202 start in 0.08s, final done after polling, `language=fr`, `local-whisper`, `cache_hit=false`, 31 segments, 228 words. Provider attempts recorded through metadata, subtitle failures/skips, Gemini unavailable, and local Whisper success. |
| Genuine Shorts URL | `https://www.youtube.com/shorts/1WW76Rz4nqM` | PASS, cached evidence | HTTP 200 in 3.57s, `local-whisper`, `language=en`, `cache_hit=true`, 13 segments, 151 words. Needs periodic fresh-cache-miss recheck, but the exact genuine Shorts fixture now returns a transcript. |
| Long-video transcription | Fresh 2-hour fixture `rwfk91ya81s` | PASS | Caption providers failed/blocked, but queued chunked Whisper recovered and saved record `5919d7b3c99a`; transcript has credible start and ending around `[02:00:42]`. |


### True two-hour public proof
Run time: 2026-08-31 02:52 EDT.

- URL: `https://www.youtube.com/watch?v=rwfk91ya81s`.
- Title: `2 Hours of the Craziest Philosophical Theories to Fall Asleep to`.
- Public async start: HTTP 202.
- Job ID: `115c983594bd`.
- Final job status: `done` after 2,050.73s.
- Record ID: `5919d7b3c99a`.
- Duration: 7,244s.
- Method: `queued-chunked-local-whisper`.
- Language: `en`.
- Chunks: 13.
- Segments: 1,446.
- Words: 19,298.
- Cache: fresh miss, `cache_hit=false`.
- Failure recovery: native captions failed, YouTube Transcript API was blocked, yt-dlp subtitles found no captions, then chunked local Whisper succeeded.
- Progress proof: polling showed download stage, chunked transcription progress from chunk 1 through chunk 12, then saving with 13 / 13 chunks.
- Credible transcript start: `[00:00] Imagine you're sitting on your couch, munching on popcorn...`.
- Credible transcript end: `[02:00:42] together.`
- Download proof: TXT HTTP 200, 121,979 bytes; Markdown HTTP 200, 127,963 bytes; SRT HTTP 200, 158,972 bytes.
