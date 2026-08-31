# PROJECT_STATE.md

Updated: 2026-08-31 11:06 EDT

## Current phase
Phase 1: Bulletproof YouTube Transcripts. Active gate is production release verification and backend hardening.

## Version / phase status

### Version 1 / Phase 1: Bulletproof YouTube transcripts
Status: Release-clear on the public no-login product for the current fixture gate. Non-English, genuine Shorts, two-hour/long-video, desktop copy, mobile touch, downloads, and the bounded public matrix have passed; backend migration hardening has advanced from container packaging to seeded-container release smoke validation.
- Public no-login app: https://epic-transcript.robyncrane.com/
- Core regression remains passing publicly with 1,460 segments and 15,744 words for `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`.
- Manual-caption control now has fresh public evidence: `dQw4w9WgXcQ`, 61 segments, 366 words, method `native-caption-subtitles`, cache hit.
- Public Phase 1 scripted matrix is now passing against the durable no-login URL for the bounded fixture set: regression, manual-caption control, automatic captions, short French non-English fixture, genuine Shorts, moderate long cached transcript, private/unavailable helpful failure, invalid URL helpful failure, privacy/history, service health, and public upload smoke.
- Backend hardening advanced: the FastAPI API and Cloudflare named tunnel are loaded under launchd KeepAlive agents. Hosted-backend migration spike now adds env-configurable runtime paths, Docker container packaging, and a migration checklist in `docs/HOSTED_BACKEND_MIGRATION.md`.
- Hosted backend validation advanced: a Docker container on `127.0.0.1:8091` with a repo-local bind-mounted `/data` volume seeded from `data/transcripts.db` passed the updated async Phase 1 matrix. The same container also passed Phase 2 upload smoke and Phase 3 UI contract smoke. A cold empty `/data` container exposed the expected staging risk: current YouTube/IP conditions can block some uncached YouTube fixtures, so first staging needs the existing transcript cache migrated before DNS cutover.
- UX alignment advanced: the live public root now shows `Free Video Transcript Generator`, `FAST · FREE · V3`, `Get Video Transcript`, `How it works`, and `Frequently Asked Questions (FAQ)` markers in the expected first-control then support-section order.
- Netlify review URL was updated to the same public UX build. Stable review URL `https://epic-transcript-machine-review.netlify.app` and immutable deploy `https://6a9579a7b662aa6824e325ab--epic-transcript-machine-review.netlify.app` both returned HTTP 200 with the new UX markers and the production API base marker.
- New non-English production evidence: `https://youtu.be/kv92eqcZVxs`, title `✅ 10 phrases simples en français à apprendre en 1 minute !`, HTTP 200, method `local-whisper`, language `fr`, 2 segments, 37 words, credible French text. First uncached run passed at 2026-08-31 01:34 EDT and repeated matrix run confirmed cache hit.
- New two-hour public long-video proof: `https://www.youtube.com/watch?v=rwfk91ya81s`, job `115c983594bd`, record `5919d7b3c99a`, title `2 Hours of the Craziest Philosophical Theories to Fall Asleep to`, duration 7,244 seconds, HTTP 202 async start then job `done`, method `queued-chunked-local-whisper`, cache miss, 13 audio chunks, 1,446 segments, 19,298 words, language `en`. Native captions, YouTube Transcript API, and yt-dlp subtitles failed/skipped, then chunked local Whisper produced a credible beginning and ending. Public TXT, Markdown, and SRT signed downloads verified HTTP 200.

### Version 2 / Phase 2: Any video or audio
Status: Advanced, not release-complete. Hosted-container upload path now passes against a seeded persistent `/data` volume.
- Local Whisper upload path exists and previous local evidence covered MP3, M4A, MP4, and direct public-media-style URL.
- Full upload/media release matrix now has public proof for generated WAV, MP3, M4A, MP4, MOV, WebM, non-English French WAV, a 31-minute MP3 recording, and a supported public non-YouTube MP3 URL. Remaining Phase 2 evidence is fuller browser UX proof.
- Cleanup/retention hardening advanced on 2026-08-31 08:18 EDT: upload temp directories are covered by an automated removal regression, transcript deletion now also removes saved analyses, SQLite connections now enable foreign-key enforcement, and the public API verified delete cleanup with record `c40edf087acd` / analysis `c3e5e11163a0` returning HTTP 404 after deletion.
- Advanced public verification: expanded `scripts/phase2_upload_smoke.py`, which generates a spoken fixture with macOS `say`, converts it with `ffmpeg`, uploads WAV/MP3/M4A/MP4/MOV/WebM to the public no-login API, verifies credible nonempty local-Whisper transcripts, confirms repeat-upload cache reuse, and verifies signed TXT/Markdown/SRT downloads for an upload record.
- Public UX copy now makes upload support clearer on the page: the how-it-works and FAQ sections explicitly mention public media URLs and MP4, MOV, WebM, MP3, M4A, WAV, TXT, Markdown, SRT, and VTT support.
- Added reusable `scripts/phase2_non_english_upload_smoke.py` for public non-English upload proof without paid providers. It generates French speech with macOS `say -v Thomas`, converts to WAV with `ffmpeg`, uploads to the public no-login API, verifies `local-whisper`, language `fr`, credible French text, and a signed TXT download.
- Added reusable `scripts/phase2_long_upload_smoke.py` for 30+ minute public upload proof. It generates spoken audio with macOS `say`, pads to a 31-minute MP3 using `ffmpeg`, uploads to the public no-login API, and verifies saved media duration metadata plus credible transcript text.
- Fresh public upload proof from 2026-08-31 03:30 EDT: WAV returned HTTP 200 through `local-whisper`, 2 segments, 18 words, cache hit; MP3 returned HTTP 200 through `local-whisper`, 2 segments, 18 words, cache hit; M4A returned HTTP 200 through `local-whisper`, 2 segments, 18 words, cache hit; MP4 returned HTTP 200 through `local-whisper`, 1 segment, 12 words, cache hit; MOV returned HTTP 200 through `local-whisper`, 1 segment, 12 words, cache hit; WebM returned HTTP 200 through `local-whisper`, 1 segment, 12 words, cache miss. Repeat WAV upload returned HTTP 200, `cache_hit=true`, same 18-word transcript. Signed upload downloads passed: TXT HTTP 200, 136 bytes; Markdown HTTP 200, 239 bytes; SRT HTTP 200, 186 bytes.
- Fresh non-English public upload proof from 2026-08-31 04:06 EDT: generated French WAV returned HTTP 200 in 7.78s through `local-whisper`, language `fr`, cache miss, 2 segments, 22 words. Credible text: `Bonjour, ceci est un test français... reconnaître des mots simples en français sans fournisseur payant.` Signed TXT download returned HTTP 200, 174 bytes.
- Fresh 30+ minute public upload proof from 2026-08-31 04:42 EDT: generated 31-minute MP3, 7,448,625 bytes, returned HTTP 200 in 54.50s through `local-whisper`, language `en`, cache miss, duration `1862.0` seconds, 3 segments, 34 words. Credible transcript begins `Epic transcript machine long upload proof...` and includes text at `[31:00]`.

### Version 3 / Phase 3: Video intelligence
Status: Advanced publicly, not release-complete. Hosted-container UI/API contract now passes against a seeded persistent `/data` volume.
- Added the first provider-safe Phase 3 backend: `/api/analyze/{transcript_id}` now produces timestamp-cited executive summary, action items, chapters, quotes, FAQ, sales insights, Trevor-use, starter content-asset maps, and question-answer outputs without paid providers or hiding the original transcript.
- Added `/api/analysis/{analysis_id}/download` so generated analysis can be downloaded as Markdown.
- Expanded the public UI from two starter buttons to the full starter intelligence menu: `All Outputs`, 16 individual output choices, ask-a-question input, `Ask`, and `Download Analysis` controls in the transcript workspace.
- Fresh public proof from 2026-08-31 06:32 EDT: root HTML served the new Phase 3 UI markers (`All Outputs`, `analysisMenu`, `content_assets_100`, ask-a-question input, `/api/analyze/`); `/api/analysis-outputs` returned 17 output definitions; Rick Astley cached transcript returned HTTP 200 with 366 words; all 17 public analysis calls returned HTTP 200 with `AI-generated` disclaimer and transcript evidence, including `ask_question` with a Trevor-specific question.
- Fresh combined-output copy/download proof from 2026-08-31 07:07 EDT: root HTML served `Copy Analysis`, `analysisCopyBtn`, and `/api/analyze-all/`; public combined analysis returned HTTP 200 with 16 saved starter outputs, 10,036 copy-ready characters, analysis ID `bfb7ef1f1bab`, and Markdown download HTTP 200 with 10,600 bytes.
- Fresh long-transcript intelligence proof from 2026-08-31 07:43 EDT: Phase 3 analysis now samples beginning, middle, and ending timestamp evidence for long records. Public two-hour cached fixture `rwfk91ya81s` returned job `c345b34bc0ba`, record `837a9891f74d`, 19,298 words, 1,446 segments, duration 7,244s, method `queued-chunked-local-whisper`, cache hit. `/api/analyze-all/837a9891f74d` produced 16 outputs, 19,106 copy-ready characters, latest cited analysis timestamp 7,242s, analysis ID `8215f62db5fa`, and Markdown download HTTP 200 with 19,106 bytes.
- Remaining Phase 3 work: turn the deterministic starter into fuller AI/provider-backed long-transcript intelligence once a free/no-surprise provider path is selected. The new no-Chrome public UI contract harness now covers visible controls, async endpoint wiring, all-output analysis, ask-a-question, copy/download wiring, and Markdown download without depending on Chrome remote debugging.

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
- Added upload media-duration detection with `ffprobe`, covered by `test_upload_records_media_duration_for_long_recordings`, then publicly verified `scripts/phase2_long_upload_smoke.py` against a generated 31-minute MP3 recording.
- Added `test_non_youtube_media_url_falls_back_to_local_whisper` and reusable `scripts/phase2_public_url_smoke.py`; public proof now covers a no-login hosted MP3 URL at `/static/phase2-public-url.mp3` through `/api/transcribe-url` with local Whisper and no paid provider.
- Added Phase 3 starter implementation: `ANALYSIS_OUTPUTS`, `/api/analyze/{transcript_id}`, `/api/analyze-all/{transcript_id}`, `/api/analysis/{analysis_id}/download`, active `tests/test_phase3.py`, and public UI buttons for AI Summary, Action Items, All Outputs, Copy Analysis, the full output menu, ask-a-question, and Download Analysis.
- Improved Phase 3 long-transcript evidence selection so analysis outputs cite beginning, middle, and ending timestamps instead of only the opening segments; added regression coverage and `scripts/phase3_long_analysis_smoke.py` public proof.
- Advanced Phase 2 cleanup/retention hardening: SQLite now enables `PRAGMA foreign_keys`, deleting a transcript removes saved analyses, tests cover upload temp directory removal after processing, and public delete cleanup verified record `c40edf087acd` plus analysis `c3e5e11163a0` returned HTTP 404 after deletion.
- Advanced the public UX/design acceptance gate from the ChatGPT-reference prompt: added and satisfied regression coverage for `Free Video Transcript Generator`, `FAST · FREE · V3`, `Get Video Transcript`, `How it works`, `Frequently Asked Questions (FAQ)`, `faq-stage`, and `step-grid` markers.
- Added `scripts/phase3_ui_contract_smoke.py`, a no-Chrome public UI contract harness that verifies visible Phase 3 controls, async job wiring, absence of the old synchronous submit path, all-outputs analysis, ask-question analysis, and Markdown download against the public no-login URL.
- Deployed the synchronized static review build to Netlify site `epic-transcript-machine-review`, deploy `6a9579a7b662aa6824e325ab`, and verified both stable and immutable Netlify URLs anonymously.
- Updated `scripts/phase1_matrix.py` to test YouTube links through the public UI's async job path (`/api/transcribe-url-job` plus `/api/jobs/{id}`) instead of relying on the older synchronous URL endpoint for long YouTube sources.

## Latest production regression evidence
URL tested: `https://epic-transcript.robyncrane.com/api/transcribe-url`
Regression video: `https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD`

Fresh health/design run from 2026-08-31 08:53 EDT:
- Public root: HTTP 200, 41,404 bytes, no login. Markers present: `Free Video Transcript`, `Generator`, `FAST · FREE · V3`, `Get Video Transcript`, `Quick and simple. No catch.`, `Frequently Asked Questions (FAQ)`, `faq-stage`, `step-grid`, and `/api/analyze-all/`. DOM order check passed: `hero-control` appears before `How it works`, which appears before `Frequently Asked Questions`.
- Netlify review root: HTTP 200, 41,404 bytes at `https://epic-transcript-machine-review.netlify.app` and immutable deploy `https://6a9579a7b662aa6824e325ab--epic-transcript-machine-review.netlify.app`, with the same UX markers plus `https://epic-transcript.robyncrane.com` API base marker.
- Public `/health`: HTTP 200, `ready: true`, required `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public Phase 1 health script passed again: regression video returned HTTP 200, cache hit, 1,460 segments, 15,744 words, language `en`; manual-caption control returned HTTP 200, cache hit, 61 segments, 366 words, language `en`.

Prior fresh health run from 2026-08-31 02:53 EDT:
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
- `python3 -m py_compile scripts/phase1_matrix.py`: passed on 2026-08-31 11:06 EDT after switching the matrix to the async public UI path for YouTube links.
- Seeded hosted-container Phase 1 matrix passed on 2026-08-31 11:06 EDT at `http://127.0.0.1:8091`: all 9 cases passed. Regression returned HTTP 200, cache hit, 1,460 segments, 15,744 words; control/manual caption returned HTTP 200, cache hit, 61 segments, 366 words; non-English returned HTTP 200, cache hit, 37 words, `fr`; Shorts returned HTTP 200, cache hit; moderate long returned HTTP 200, cache hit; private/unavailable and invalid URL returned helpful HTTP 422 guidance.
- Seeded hosted-container Phase 2 upload smoke passed on 2026-08-31 11:06 EDT at `http://127.0.0.1:8091`: WAV, MP3, M4A, MP4, MOV, and WebM returned HTTP 200 through `local-whisper`; repeat WAV cache check returned `cache_hit=true`; signed TXT, Markdown, and SRT downloads returned HTTP 200.
- Seeded hosted-container Phase 3 UI contract smoke passed on 2026-08-31 11:06 EDT at `http://127.0.0.1:8091`: root HTTP 200, required UI IDs present, async wiring present, old sync submit absent, Rick Astley transcript job done with cache hit, all-output analysis produced 16 sections and 13,076 chars, Markdown download HTTP 200 with 13,960 bytes, ask-question output 784 chars.
- `./.venv/bin/python -m pytest -q`: passed, 45 tests on 2026-08-31 10:06 EDT.
- `scripts/phase1_health.py https://epic-transcript.robyncrane.com`: passed on 2026-08-31 10:06 EDT. Regression returned HTTP 200, cache hit, 1,460 segments, 15,744 words; manual-caption control returned HTTP 200, cache hit, 61 segments, 366 words.
- Hosted-backend spike verification passed on 2026-08-31 10:06 EDT: `docker build -t epic-transcript-machine:hosted-spike .` succeeded; container run on `127.0.0.1:8091` returned `/health` HTTP 200 with `ready: true`, `missing: []`, `local_whisper: true`; root returned HTTP 200 and 41,404 bytes; mounted `/data` created `transcripts.db`.
- `./.venv/bin/python -m pytest -q`: passed, 44 tests on 2026-08-31 09:32 EDT.
- `python3 -m py_compile scripts/phase3_ui_contract_smoke.py`: passed on 2026-08-31 09:32 EDT.
- `scripts/phase3_ui_contract_smoke.py https://epic-transcript.robyncrane.com`: passed on 2026-08-31 09:32 EDT. Public root HTTP 200, required UI IDs present, async submit/job and analysis endpoints wired, old sync submit absent, transcript job HTTP 202 then done for `dQw4w9WgXcQ`, record `18cc682b7b51`, 366 words, 61 segments, all-output analysis `b8614a2d6247`, 16 sections, 13,076 chars, Markdown download HTTP 200 with 13,960 bytes, ask-question analysis `b72d30a12ad0`, 784 chars.
- Public root marker check passed at 2026-08-31 08:53 EDT with HTTP 200 and 41,404 bytes.
- Netlify stable and immutable review URL marker checks passed at 2026-08-31 08:53 EDT with HTTP 200 and 41,404 bytes.
- Public `/health` returned HTTP 200, `ready: true`, and no required missing dependencies at 2026-08-31 08:53 EDT.
- Public Phase 1 health script passed at 2026-08-31 08:53 EDT for regression and manual-caption control.
- Public root: HTTP 200, expected app markers present, including new Phase 3 `All Outputs`, `Copy Analysis`, `analysisMenu`, `analysisCopyBtn`, `content_assets_100`, ask-a-question, `/api/analyze/`, and `/api/analyze-all/` markers.
- Public health: HTTP 200, `ready: true`, `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public cleanup/delete proof from 2026-08-31 08:18 EDT: after launchd restart, text upload returned HTTP 200, analysis creation returned HTTP 200, owner-authorized delete returned HTTP 200, deleted transcript readback returned HTTP 404, and deleted analysis download returned HTTP 404 for record `c40edf087acd` / analysis `c3e5e11163a0`.
- Public Phase 2 supported URL smoke from 2026-08-31 08:18 EDT: public fixture `https://epic-transcript.robyncrane.com/static/phase2-public-url.mp3` returned HTTP 206 byte-range, `audio/mpeg`; `/api/transcribe-url` returned HTTP 200 in 9.59s, method `local-whisper`, source_kind `url`, cache miss, language `en`, 2 segments, 18 words.
- Public Phase 3 long-transcript proof from 2026-08-31 07:43 EDT: `scripts/phase3_long_analysis_smoke.py https://epic-transcript.robyncrane.com` passed. Public async job `c345b34bc0ba` reused the two-hour cached fixture and returned record `837a9891f74d`, 19,298 words, 1,446 segments, duration 7,244s, method `queued-chunked-local-whisper`, cache hit. Combined analysis returned 16 outputs, 19,106 characters, analysis ID `8215f62db5fa`, latest cited timestamp 7,242s, and Markdown download HTTP 200, `text/markdown`, 19,106 bytes.
- Public Phase 3 full starter menu proof from 2026-08-31 06:32 EDT: cached control transcript `dQw4w9WgXcQ` returned HTTP 200, record `2f2b61d2ccf6`, method `native-caption-subtitles`, 366 words, cache hit. `/api/analysis-outputs` returned 17 outputs. All 17 `/api/analyze/{id}` calls returned HTTP 200 with useful nonempty text, `AI-generated` disclaimer, and transcript evidence; `ask_question` passed with question `What should Trevor do with this video?`.
- Public Phase 3 combined-output proof from 2026-08-31 07:07 EDT: `scripts/phase3_combined_analysis_smoke.py https://epic-transcript.robyncrane.com` passed. Rick Astley cached transcript returned HTTP 200, record `1f5a2b16abd8`, 366 words, method `native-caption-subtitles`, cache hit. `/api/analyze-all/{id}` returned 16 combined starter outputs, 10,036 copy-ready characters, analysis ID `bfb7ef1f1bab`; `/api/analysis/bfb7ef1f1bab/download` returned HTTP 200, `text/markdown`, 10,600 bytes.
- Browser visual/DOM check remains blocked by macOS Chrome's `Allow remote debugging?` permission prompt; browser harness retry at 2026-08-31 06:32 EDT reproduced the same permission blocker.
- Public Phase 2 supported URL smoke from 2026-08-31 05:17 EDT: public fixture `https://epic-transcript.robyncrane.com/static/phase2-public-url.mp3` returned HTTP 206 byte-range, `audio/mpeg`; `/api/transcribe-url` returned HTTP 200 in 8.93s, method `local-whisper`, source_kind `url`, cache miss, language `en`, 2 segments, 18 words, credible transcript beginning `Epic transcript machine phase 2 public URL test...`, and provider trail showed captions failed then local Whisper succeeded.
- Public Phase 1 health script now correctly accepts a CLI base URL and passed against `https://epic-transcript.robyncrane.com` for regression and manual-caption control.
- Public Phase 1 matrix from 2026-08-31 02:16 EDT: all 9 bounded scripted cases passed against `https://epic-transcript.robyncrane.com`, including the new French non-English fixture, genuine Shorts URL, moderate long-video cached transcript, and helpful 422 failures for private/unavailable plus invalid URL.
- Public two-hour/long-video async proof from 2026-08-31 02:52 EDT: job `115c983594bd` returned record `5919d7b3c99a` with HTTP 200 job readback, method `queued-chunked-local-whisper`, 13 chunks, 1,446 segments, 19,298 words, and credible start/end transcript text. Signed TXT, Markdown, and SRT downloads for that long record returned HTTP 200.
- Public Phase 2 upload smoke from 2026-08-31 03:30 EDT: generated WAV, MP3, M4A, MP4, MOV, and WebM fixtures all returned HTTP 200 through `local-whisper` with credible nonempty transcript text. Repeat WAV upload returned `cache_hit=true` with the same 18-word transcript. Signed TXT, Markdown, and SRT downloads for the upload record returned HTTP 200.
- Public Phase 2 non-English upload smoke from 2026-08-31 04:06 EDT: generated French WAV returned HTTP 200 in 7.78s via `local-whisper`, language `fr`, cache miss, 2 segments, 22 words, and signed TXT download HTTP 200.
- Public Phase 2 30+ minute upload smoke from 2026-08-31 04:42 EDT: generated 31-minute MP3 returned HTTP 200 in 54.50s via `local-whisper`, duration `1862.0` seconds, language `en`, cache miss, 3 segments, 34 words, and credible transcript text at the beginning plus `[31:00]`.
- Long-video async proof completed at 2026-08-31 02:52 EDT using `scripts/public_long_video_proof.py` against two-hour fixture `https://www.youtube.com/watch?v=rwfk91ya81s`. Public API returned HTTP 202, job `115c983594bd` completed `done`, and record `5919d7b3c99a` returned 1,446 segments and 19,298 words through 13 chunked local-Whisper audio chunks.
- Backend restore verification from 2026-08-31 01:34 EDT: local `/health` HTTP 200, public `/health` HTTP 200, `com.epic.transcript-api` state `running`, PID 99082.
- Reusable public Phase 2 upload smoke script expanded at `scripts/phase2_upload_smoke.py`.
- New targeted regression tests for launchd/minimal-PATH binary resolution passed.
- Local generated MP3 upload through FastAPI TestClient passed via `local-whisper` after absolute Whisper binary resolution.
- Design regression tests: passed for Call IQ tokens, hero control placement, dark presentation surface, and light results workspace.
- Public TXT/Markdown/SRT downloads for regression record: passed in prior release-gate evidence.

## Known problems
- The public hostname now has launchd KeepAlive hardening, but it still depends on this iMac and Cloudflare Tunnel. A hosted durable backend remains the cleaner whole-project final release path.
- A fresh empty hosted `/data` volume is not enough for release parity under current YouTube/IP conditions. The cold container passed non-English, control via Whisper, upload, and analysis paths, but failed the regression and Shorts fixtures when captions/audio were blocked. Staging cutover must seed the existing SQLite transcript cache into the persistent volume first, then verify the matrix.
- Browser Use automation can still hit a fresh macOS `Allow remote debugging?` prompt in new browser sessions. This no longer blocks Version 1 proof because prior direct Chrome desktop/mobile proof passed and the new no-Chrome public UI contract harness covers the release-critical wiring.
- SMTP config is missing, so Email to Me is not ready.
- Gemini YouTube hook is intentionally present but not enabled because no key is configured and the free caption/local path is primary.
- Browser WebGPU Whisper is not implemented yet. Local server Whisper fallback exists.
- Phase 1 bounded scripted public matrix and two-hour/long-video transcription are passing, but copy-flow browser interaction and fuller mobile touch-flow evidence are still needed before calling Version 1 fully release-clear.
- Public API has reloaded the helpful invalid-link behavior. Invalid non-YouTube URL now returns HTTP 422 instead of HTTP 500.

## Blockers
- Phase 1 public product proof is no longer blocked. New browser sessions may still need the macOS Chrome remote-debug prompt approved, but release-critical proof has a prior direct Chrome pass plus the no-Chrome UI contract harness.

## Exact next action
Prepare the first no-DNS-cutover hosted staging deployment on the lowest-risk persistent Docker host, with Orgo/persistent Linux VM as the preferred path, mount `/data`, seed it from the current `data/transcripts.db`, then run Phase 1, Phase 2, and Phase 3 smoke tests against that public staging URL before any DNS cutover.

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


### 2026-08-31 browser and mobile UX gate update
- PASS: Chrome remote-debugging permission was cleared and direct Chrome CDP browser verification ran against `https://epic-transcript.robyncrane.com/`.
- Desktop copy-flow PASS: public page loaded with async markers present and old sync call absent; submitted French YouTube fixture `vgIle-XrvQI`; result displayed title `Avoir d'la broue dans l'toupèt!`, method `local-whisper`, 1,578 transcript chars; Copy button produced `Copied to clipboard ✓` and clipboard text matched the full transcript.
- Mobile touch-flow PASS: emulated 390x844 mobile viewport; no horizontal overflow; URL field, Transcribe button, upload drop zone, Copy, TXT, Markdown, and SRT controls were visible and usable; submitted genuine Shorts fixture `1WW76Rz4nqM`; result displayed `HOW TO: Edit with AI in YouTube Shorts`, 887 transcript chars, and Copy matched clipboard.
- Public matrix rerun PASS: `scripts/phase1_matrix.py https://epic-transcript.robyncrane.com` returned `all_ok=true` across regression, control/manual captions, automatic captions, non-English, Shorts, moderate long cached video, private/unavailable helpful failure, and invalid URL helpful failure.
- Test suite PASS: `pytest -q` returned 44 passed.
- Evidence saved under `evidence/browser-mobile-qc/` with desktop/mobile initial and result screenshots plus `report.json`.

### 2026-08-31 hosted backend migration spike
- PASS: Added env-configurable runtime paths: `TRANSCRIPT_DATA_DIR` for the SQLite/cache volume and `TRANSCRIPT_STATIC_DIR` for the bundled UI. Defaults preserve the existing iMac behavior.
- PASS: Added `Dockerfile`, `.dockerignore`, and `docs/HOSTED_BACKEND_MIGRATION.md` for a no-surprise hosted backend path that keeps ffmpeg, yt-dlp, and local Whisper instead of adding paid providers.
- PASS: Added regression coverage `test_hosted_backend_can_move_runtime_data_dir_without_code_changes`. Full suite now returns 45 passed.
- PASS: Built `epic-transcript-machine:hosted-spike` locally and ran it with a mounted `/data` volume. Container `/health` returned HTTP 200, `ready=true`, `missing=[]`, `local_whisper=true`; root returned HTTP 200 with the live UI bytes; persistent `transcripts.db` was created in the mounted data directory.

### 2026-08-31 hosted backend seeded-container validation
- PASS: Restarted the hosted Docker container with a repo-local bind-mounted persistent volume seeded from the current `data/transcripts.db`. Docker Desktop did not reliably expose a `/tmp/...` seed path into the container, so staging instructions now prefer a repo or real host volume path.
- PASS: Updated and compiled `scripts/phase1_matrix.py` so YouTube cases use the async UI path. Seeded container Phase 1 matrix passed all 9 cases on `http://127.0.0.1:8091`.
- PASS: Seeded container Phase 2 upload smoke passed for WAV, MP3, M4A, MP4, MOV, WebM, repeat cache, and TXT/Markdown/SRT downloads.
- PASS: Seeded container Phase 3 UI contract smoke passed for async transcript, all-output analysis, ask-question, and Markdown download.
- FINDING: An empty cold hosted container is not release-parity yet because current YouTube/IP behavior can block fresh uncached regression and Shorts pulls. First staging deployment must migrate the existing transcript cache before it can replace the iMac tunnel safely.
