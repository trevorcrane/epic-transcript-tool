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
Run time: 2026-08-31 14:58 EDT, real browser model follow-up.

- Real browser Whisper fallback execution: PASS. Added `scripts/phase2_browser_real_whisper_smoke.py` after a failing-first test. The script does not use the localhost test stub. It verifies the public root contains `Xenova/whisper-tiny.en`, forced `/api/transcribe-upload` to HTTP 503 in mobile Playwright, uploaded a generated WAV, ran the actual browser model path, rendered `browser-whisper-webgpu · 61 chars`, produced transcript `browser whisper real model proof for epic transcript machine.`, saved local history, and verified VTT download `epic-transcript-browser.vtt` with `WEBVTT` and full timestamp format. Evidence saved at `evidence/phase2-browser-real-whisper-attempt.json`.

Run time: 2026-08-31 14:58 EDT.

- Browser fallback local-download proof: PASS. After a failing-first regression, `scripts/phase2_browser_fallback_ui_smoke.py` now clicks and verifies local browser-only TXT, Markdown, SRT, and VTT downloads from the failed-upload browser fallback path. Public root returned HTTP 200 with fallback wiring and guarded localhost stub markers. Mobile Playwright proof forced `/api/transcribe-upload` to HTTP 503, rendered `browser-whisper-webgpu · 123 chars`, saved one `browser_only` local-history record, then verified download markers: TXT 123 bytes, Markdown 201 bytes, SRT 156 bytes, VTT 162 bytes, suggested VTT filename `epic-transcript-browser.vtt`, and `WEBVTT` with full timestamp format. Evidence saved at `evidence/phase2-browser-fallback-ui-report.json` plus `.png`.
- Browser-only subtitle formatting: PASS. Static browser-only SRT/VTT downloads now use full `HH:MM:SS,mmm` and `HH:MM:SS.mmm` timestamps through `formatSubtitleDuration`.
- Netlify review deploy: PASS. Site `epic-transcript-machine-review`, deploy `6a95ceab31812a30a3191b50`; stable URL and immutable deploy both returned HTTP 200 with `formatSubtitleDuration`, fallback guard markers, `Get Transcript`, and production API base.
- Regression suite and public smokes: PASS. `./.venv/bin/python -m pytest -q` returned 62 passed; inline static JavaScript `node --check` passed; Phase 1 health passed; Phase 2 release gate returned `all_ok=true`; Phase 3 UI contract passed with combined analysis 16 outputs / 40,077 chars and Markdown download HTTP 200 / 41,227 bytes.

Run time: 2026-08-31 14:42 EDT.

- Browser fallback clickable UI proof: PASS for guarded production wiring and mobile fallback flow. Added failing-first regression for `scripts/phase2_browser_fallback_ui_smoke.py`, added a localhost-only `window.__EPIC_BROWSER_WHISPER_TEST_STUB` guard, then ran the smoke script. Public no-login root returned HTTP 200 with guarded fallback markers: `window.__EPIC_BROWSER_WHISPER_TEST_STUB`, `Browser fallback test stub is not active`, `Server upload failed, trying private browser transcription`, `Xenova/whisper-tiny.en`, and `epicTranscriptHistory`. The browser proof drove a 390x844 mobile Playwright page, forced `/api/transcribe-upload` to HTTP 503, uploaded a WAV candidate, rendered a browser-only transcript with method `browser-whisper-webgpu · 123 chars`, saved one `browser_only` local-history item, and captured evidence at `evidence/phase2-browser-fallback-ui-report.json` plus `.png`.
- Netlify review deploy: PASS. Site `epic-transcript-machine-review`, deploy `6a95cae308ff4f121e6d3827`; stable URL and immutable deploy both returned HTTP 200 with fallback guard markers and production API base.
- Regression suite: PASS. `./.venv/bin/python -m pytest -q` returned 62 passed; inline static JavaScript `node --check` passed.
- Public phase smokes: PASS. Phase 1 health returned regression 1,460 segments / 15,744 words and manual-caption control 61 segments / 366 words. Phase 2 release gate returned `all_ok=true`, `/health` ready true with required `missing=[]`, unsupported `.exe` helpful HTTP 400, unsupported URL helpful HTTP 422, and delete cleanup readback HTTP 404 for transcript `5f1fd4068e19` / analysis `b7b5c355fdac`. Phase 3 UI contract returned Rick Astley 366 words / 61 segments, combined analysis 16 outputs / 40,077 chars, Markdown download HTTP 200 / 41,227 bytes, and ask-question 958 chars.

Run time: 2026-08-31 14:25 EDT.

- Browser fallback wiring: PASS shipped code path, OPEN full model execution proof. Added failing-first regression `test_browser_local_whisper_fallback_is_actually_wired_for_failed_uploads`, then implemented the failed-server-upload recovery path in the public static UI. Supported audio/video files now fall back to private browser Whisper through `@xenova/transformers@2.17.2`, label output as `browser-whisper-webgpu` or `browser-whisper-wasm`, render a browser-only transcript record, save it to local browser history, and use local TXT/Markdown/SRT/VTT downloads. Public production root returned HTTP 200 with release `3.2.1` and the fallback wiring markers. Stable Netlify review and immutable deploy `https://6a95c6ef4bcd59c584c116de--epic-transcript-machine-review.netlify.app/` returned HTTP 200 with the same markers plus production API base.
- Regression suite: PASS. `./.venv/bin/python -m pytest -q` returned 61 passed; inline static JavaScript `node --check` passed.
- Public phase smokes: PASS. Phase 1 health returned regression 1,460 segments / 15,744 words and manual-caption control 61 segments / 366 words. Phase 2 release gate returned `all_ok=true`, `/health` ready true with required `missing=[]`, unsupported `.exe` helpful HTTP 400, unsupported URL helpful HTTP 422, and delete cleanup readback HTTP 404 for transcript `0ae20be8f274` / analysis `bcf1d4d6f901`. Phase 3 UI contract returned Rick Astley 366 words / 61 segments, combined analysis 16 outputs / 40,077 chars, Markdown download HTTP 200 / 41,227 bytes, and ask-question 958 chars.

Run time: 2026-08-31 12:51 EDT.

- Owner-facing UI correction: PASS. Public production root, stable Netlify review URL, and immutable Netlify deploy `https://6a95b112692fe0f07390daf5--epic-transcript-machine-review.netlify.app/` returned HTTP 200 with `Your Transcript History`, `Unlock All EPIC Machines`, `placeholder="Enter URL..."`, compact upload control `uploadBtn`, release version footer, `https://epic.media`, production API base marker on Netlify, and no old `drop-zone` marker.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 56 passed. Inline static JavaScript syntax check returned exit 0.
- Phase 1 public health: PASS. Regression returned HTTP 200, cache hit, 1,460 segments / 15,744 words; manual-caption control returned HTTP 200, cache hit, 61 segments / 366 words.
- Phase 3 UI contract: PASS. Public root returned HTTP 200; Rick Astley transcript returned 366 words / 61 segments; combined analysis returned 16 outputs / 40,077 chars; Markdown download returned HTTP 200 / 41,227 bytes; ask-question returned 958 chars.

Run time: 2026-08-31 12:19 EDT.

- VTT download support: PASS. Public Phase 1 DOM/click/mobile/a11y smoke verified `downloadVttBtn`, VTT click wiring, and signed VTT download HTTP 200 / 1,194 bytes for Shorts record `68a1105cf6d5`.
- Phase 2 upload/download smoke: PASS. Public WAV/MP3/M4A/MP4/MOV/WebM uploads returned HTTP 200 through `local-whisper`; repeat WAV returned `cache_hit=true`; TXT/Markdown/SRT/VTT downloads returned HTTP 200, with VTT 190 bytes and `WEBVTT` marker.
- Phase 2 release smoke: PASS. Public root returned HTTP 200 with all supported extensions in the file accept contract and TXT/Markdown/SRT/VTT markers; `/health` returned ready true with required `missing: []`; unsupported `.exe` returned helpful HTTP 400; unsupported URL returned helpful HTTP 422; delete cleanup readback returned transcript/analysis HTTP 404 for record `46a97a716a50` / analysis `b2372631aed6`.
- Phase 3 UI contract: PASS. Public root returned HTTP 200 with `Get Transcript`; Rick Astley cached transcript returned 366 words / 61 segments; combined analysis returned 16 outputs / 31,087 chars; Markdown download returned HTTP 200 / 33,103 bytes; ask-question returned 958 chars.
- Visual correction deploy: PASS. Public production root, stable Netlify review URL, and immutable Netlify deploy `https://6a95aa18ce55f098dbd49568--epic-transcript-machine-review.netlify.app/` returned HTTP 200 with `Free Video Transcript`, `Machine`, `Get Transcript`, `Choose file`, `downloadVttBtn`, `TXT / MD / SRT / VTT`, theme icons, async job wiring, and analysis wiring. Old `Get Video Transcript`, `FAST · FREE · V3`, and hero phase cards are absent.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 53 passed. Inline JavaScript syntax check returned exit 0.

Run time: 2026-08-31 11:58 EDT.

- Phase 2 browser-only fallback: PASS deployed and disclosed. Public production root, stable Netlify review, and immutable Netlify deploy `6a95a49d4bcd595e06c116e6` returned HTTP 200 / 51,917 bytes with `browserLocal`, `Browser-only fallback`, `File stays on this device`, `WebGPU when available`, `WASM when WebGPU is not available`, `browser-whisper-webgpu`, `browser-whisper-wasm`, and `Xenova/whisper-tiny.en` markers.
- Phase 2 direct/social URL matrix: PASS. Added and ran `scripts/phase2_url_matrix_smoke.py`. Public direct MP3 fixture returned HTTP 200 `audio/mpeg`; async URL job `566c9b18c9a7` completed with record `125f03b51940`, method `local-whisper`, source_kind `url`, language `en`, 18 words, 2 segments. TikTok, Instagram, Facebook, and X/Twitter sample URLs each returned platform-specific helpful HTTP 422 guidance telling the user to upload the file. Evidence saved to `evidence/phase2-url-matrix-report.json`.
- Browser fallback regression: PASS. `test_browser_local_whisper_fallback_is_disclosed_and_wired` now checks disclosure, CDN import, WebGPU/WASM method markers, `canUseBrowserWhisper`, and `transcribeInBrowser` wiring.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 50 passed.
- Public Phase 2 release smoke: PASS. `scripts/phase2_release_gate_smoke.py https://epic-transcript.robyncrane.com` returned `all_ok=true`; root format copy passed, `/health` had required `missing: []`, `.exe` upload returned helpful HTTP 400, unsupported URL returned helpful HTTP 422, and owner cleanup readback returned transcript and analysis HTTP 404 for record `1623e1918e47` / analysis `1106b732f435`.
- Netlify review deploy: PASS. `netlify deploy --dir static --prod --json` deployed site `epic-transcript-machine-review`, deploy `6a95a49d4bcd595e06c116e6`; stable and immutable URLs both verified anonymously with production API base marker.

Run time: 2026-08-31 11:39 EDT.

- Public app root: PASS, HTTP 200, 46,373 bytes, no visitor login.
- Visible phase cards: PASS on public root, stable Netlify review, and immutable Netlify deploy `6a95a0c3cf34d705f2de4c9d`. Required markers present: `Version 1 / Phase 1`, `Version 2 / Phase 2`, `Version 3 / Phase 3`, `Bulletproof YouTube transcripts`, `Any video or audio`, and `Video intelligence`.
- Netlify review root: PASS, HTTP 200 at `https://epic-transcript-machine-review.netlify.app` and `https://6a95a0c3cf34d705f2de4c9d--epic-transcript-machine-review.netlify.app`, both with production API base marker.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 49 passed.
- Public Phase 1 health: PASS. Regression returned 1,460 segments / 15,744 words, cache hit; manual-caption control returned 61 segments / 366 words, cache hit.
- Public Phase 3 UI contract: PASS. Combined analysis returned 16 sections / 13,076 chars; Markdown download returned HTTP 200 / 13,960 bytes; ask-question returned 784 chars.
- Unsupported upload guidance: PASS after API reload. `.exe` upload returned HTTP 400 with the exact supported-format list instead of a dead-end error.

Run time: 2026-08-31 11:42 EDT.

- Phase 1 no-Chrome DOM/click/mobile/a11y smoke: PASS. `scripts/phase1_dom_click_mobile_a11y_smoke.py https://epic-transcript.robyncrane.com` fetched the public no-login root with HTTP 200 and 46,321 bytes, verified required DOM IDs and button labels, confirmed URL input uses `type=url` and `inputmode=url`, confirmed upload accept list includes MP4/MOV/WebM/MP3/M4A/WAV/TXT/MD/SRT/VTT, verified JS wiring for submit `preventDefault`, async `/api/transcribe-url-job` plus `/api/jobs/`, old sync URL submit absence, copy button/auto-copy clipboard handlers, TXT/Markdown/SRT click handlers, signed download-link API, and drop-zone touch/click file picker.
- Mobile/touch/static accessibility contracts: PASS. The same harness verified viewport meta, 760px and 420px mobile breakpoints, single-column URL row, full-width 56px mobile submit button, 58px desktop touch targets for URL/submit, `overflow-x:hidden`, `prefers-reduced-motion`, and `:focus-visible` focus ring.
- Contrast smoke: PASS. Critical static contrast ratios exceeded 4.5:1: white on dark 19.9, transcript text on light 10.01, primary white on purple 5.85, plain button 17.9, FAQ text 16.57, toast text 16.42.
- Public copy/download API path: PASS. Genuine Shorts job `5fcdb7daf293` completed with record `9336f51b2f45`, title `HOW TO: Edit with AI in YouTube Shorts`, method `local-whisper`, language `en`, cache hit, 13 segments, 151 words, 887 transcript chars. Copy source was the full transcript payload and signed downloads returned TXT HTTP 200 / 887 bytes, Markdown HTTP 200 / 1,096 bytes, and SRT HTTP 200 / 1,216 bytes. Report saved at `evidence/phase1-dom-click-mobile-a11y-report.json`.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 49 passed.
- Public Phase 1 matrix: PASS. `python3 scripts/phase1_matrix.py https://epic-transcript.robyncrane.com` returned `all_ok=true` across all 9 cases: regression, control/manual captions, automatic captions, French non-English, Shorts, moderate long cached video, private/unavailable helpful 422, and invalid URL helpful 422.

Run time: 2026-08-31 11:06 EDT.

- Hosted backend seeded-container validation: PASS. A Docker container at `http://127.0.0.1:8091` using a repo-local bind-mounted `/data` volume seeded from `data/transcripts.db` returned `/health` HTTP 200 with `ready: true` and required `missing: []`.
- Updated async Phase 1 matrix: PASS against the seeded container. `scripts/phase1_matrix.py` now tests YouTube links through `/api/transcribe-url-job` plus `/api/jobs/{id}`, matching the public UI path. All 9 cases passed: regression 1,460 segments / 15,744 words, manual-caption control 61 segments / 366 words, non-English French, Shorts, moderate long, private/unavailable helpful 422, and invalid URL helpful 422.
- Phase 2 seeded-container upload smoke: PASS. WAV, MP3, M4A, MP4, MOV, and WebM uploads returned HTTP 200 through `local-whisper`; repeat WAV cache returned `cache_hit=true`; TXT, Markdown, and SRT downloads returned HTTP 200.
- Phase 3 seeded-container UI contract: PASS. Root HTML returned HTTP 200 with required IDs and async wiring. Rick Astley transcript job completed from seeded cache. Combined analysis returned 16 sections and 13,076 chars; Markdown download returned HTTP 200 with 13,960 bytes; ask-question returned 784 chars.
- Cold-container finding: an empty `/data` volume is not release-parity under current YouTube/IP conditions. It can process uploads and some fresh YouTube audio through Whisper, but the regression and Shorts fixtures can fail if uncached. Hosted staging must migrate the existing SQLite cache before public release verification and DNS cutover.

Run time: 2026-08-31 10:06 EDT.

- Hosted backend migration spike: PASS. App supports `TRANSCRIPT_DATA_DIR` and `TRANSCRIPT_STATIC_DIR`; `Dockerfile` build succeeded; container run on `127.0.0.1:8091` returned `/health` HTTP 200 with `ready: true`, required `missing: []`, `local_whisper: true`; root returned HTTP 200 and 41,404 bytes; mounted data volume created `transcripts.db`.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 45 passed.
- Public Phase 1 health: PASS. Regression returned HTTP 200, cache hit, 1,460 segments, 15,744 words; manual-caption control returned HTTP 200, cache hit, 61 segments, 366 words.

Run time: 2026-08-31 09:32 EDT.

- Public Phase 3 no-Chrome UI contract: PASS. `scripts/phase3_ui_contract_smoke.py https://epic-transcript.robyncrane.com` verified public root HTTP 200, all required transcript and analysis control IDs present, button labels intact, async submit/job wiring present, old synchronous submit absent, `/api/analyze-all/` and `/api/analyze/` wiring present, analysis copy/download wiring present, transcript job HTTP 202 then done for `dQw4w9WgXcQ`, record `18cc682b7b51`, 366 words, 61 segments, cache hit, combined analysis `b8614a2d6247` with 16 sections and 13,076 chars, Markdown download HTTP 200 with 13,960 bytes, and ask-question analysis `b72d30a12ad0` with 784 chars.
- Automated suite: PASS. `./.venv/bin/python -m pytest -q` returned 44 passed.
- Script syntax: PASS. `python3 -m py_compile scripts/phase3_ui_contract_smoke.py` returned 0.

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
| Copy transcript | Public Chrome browser | PASS | Desktop browser submitted French fixture, rendered transcript, Copy showed `Copied to clipboard ✓`, and clipboard text matched the full transcript. |
| TXT download | Regression record | PASS | HTTP 200, 94,784 bytes. |
| Markdown download | Regression record | PASS | HTTP 200, 100,829 bytes. |
| SRT download | Regression record | PASS | HTTP 200, 134,557 bytes. |
| Mobile layout and touch-flow | Public Chrome mobile emulation 390x844 | PASS | No horizontal overflow. URL, Transcribe, upload, Copy, TXT, Markdown, and SRT controls visible. Mobile submitted genuine Shorts fixture and copied transcript successfully. |
| Button contrast and accessibility | No-Chrome DOM/mobile/a11y harness plus design tests | PASS smoke | Static contrast checks passed for critical text/control pairs at 5.85:1 or higher; viewport/meta, mobile breakpoints, full-width touch submit, reduced-motion, and visible focus-ring contracts passed. Full screen-reader/manual keyboard audit still pending. |

## Phase 2 release gate: Any video or audio

Current implementation evidence:
- 2026-08-31 14:58 EDT: browser-local fallback proof now includes non-stub real browser Whisper execution plus local browser-only TXT/Markdown/SRT/VTT download verification and full SRT/VTT timestamp formatting. Phase 2 public no-login media gate is release-clear; broader hosted durability remains tracked separately.
- 2026-08-31 14:25 EDT: browser-local fallback moved from marker-only to shipped failed-upload recovery wiring. Public root, stable Netlify review, and immutable deploy `6a95c6ef4bcd59c584c116de` verified `3.2.1`, `transcribeInBrowser(file)`, `Server upload failed, trying private browser transcription`, `Xenova/whisper-tiny.en`, `browser-whisper-webgpu`, and `browser-whisper-wasm`; visible fallback clutter remains absent. Full real-browser downloaded-model transcription proof is still OPEN and is the next Phase 2 action.
- 2026-08-31 11:58 EDT: direct/social URL matrix is now covered by `scripts/phase2_url_matrix_smoke.py`. PASS public evidence: direct public MP3 URL returned HTTP 200 `audio/mpeg` and completed through async `/api/transcribe-url-job` as `local-whisper`; TikTok, Instagram, Facebook, and X/Twitter sample links each returned helpful platform-specific HTTP 422 upload guidance instead of a dead-end. Evidence saved to `evidence/phase2-url-matrix-report.json`.
- 2026-08-31 11:58 EDT: browser-only fallback first moved from OPEN to marker-level implementation/disclosure, then was superseded by the 14:25 EDT shipped failed-upload recovery wiring above. Real-browser model execution proof remains a Phase 2 polish item.
- 2026-08-31 11:45 EDT: added `scripts/phase2_release_gate_smoke.py` and ran it against the public no-login product. PASS evidence saved to `evidence/phase2-release-gate-report.json`: public root HTTP 200 with exact supported upload extensions/labels; `/health` ready with required `missing: []` and `GEMINI_API_KEY` only optional; unsupported `.exe` upload returned HTTP 400 with full guidance `Upload one of: .aac, .avi, .flac, .m4a, .md, .mkv, .mov, .mp3, .mp4, .ogg, .opus, .srt, .txt, .vtt, .wav, .webm`; unsupported non-YouTube URL returned helpful HTTP 422 upload guidance; cleanup proof uploaded text, created analysis `4ce537cae294`, deleted transcript `d4c323e04d9f`, then verified transcript readback HTTP 404 and analysis download HTTP 404.
- 2026-08-31 11:45 EDT: reran `scripts/phase2_upload_smoke.py` publicly and saved `evidence/phase2-upload-smoke-latest.json`. WAV, MP3, M4A, MP4, MOV, and WebM returned HTTP 200 through `local-whisper`; repeat WAV returned `cache_hit=true`; TXT, Markdown, and SRT downloads returned HTTP 200 with expected markers.
- 2026-08-31 11:45 EDT: reran `scripts/phase2_public_url_smoke.py` publicly and saved `evidence/phase2-public-url-smoke-latest.json`. Public MP3 fixture returned HTTP 206 `audio/mpeg`; `/api/transcribe-url` returned HTTP 200 in 9.29s through `local-whisper`, source_kind `url`, language `en`, 2 segments, 18 words, cache miss.
- 2026-08-31 11:45 EDT: direct browser file-upload proof was attempted, but Browser Use stopped at macOS Chrome's `Allow remote debugging?` permission prompt before loading the page. API/no-Chrome evidence now covers exact formats, helpful failures, upload success, cache, downloads, and cleanup; direct browser upload UX remains retry-only after the prompt is approved.
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
- Unsupported upload file with helpful exact format guidance. Public `.exe` upload returns HTTP 400 with the complete supported list: `.aac`, `.avi`, `.flac`, `.m4a`, `.md`, `.mkv`, `.mov`, `.mp3`, `.mp4`, `.ogg`, `.opus`, `.srt`, `.txt`, `.vtt`, `.wav`, `.webm`.
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
- No required paid provider or surprise usage bills. PASS public `/health` on 2026-08-31 11:45 EDT reported required `missing: []`; `GEMINI_API_KEY` is optional and was not needed for the Phase 2 public smokes.
- Exact supported formats. PASS public root and unsupported-upload guidance list `.aac`, `.avi`, `.flac`, `.m4a`, `.md`, `.mkv`, `.mov`, `.mp3`, `.mp4`, `.ogg`, `.opus`, `.srt`, `.txt`, `.vtt`, `.wav`, `.webm`.
- Automatic deletion of temporary server media. PASS automated on 2026-08-31 08:18 EDT for upload work directories; public API uses per-request temp dirs and `finally` cleanup. Retention readback PASS on 2026-08-31 11:45 EDT for record `d4c323e04d9f` / analysis `4ce537cae294`: both returned HTTP 404 after owner-authorized delete.

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
- 2026-08-31 16:18 EDT: Phase 3 citation-coverage gate advanced with `scripts/phase3_citation_coverage_smoke.py https://epic-transcript.robyncrane.com`. PASS public no-login proof: regression transcript returned record `508da366d525`, method `native-caption-automatic_captions`, 15,744 words, 1,460 segments, cache hit; all 17 analysis outputs returned HTTP 200 with `AI-generated from the transcript`, timestamp evidence, and citations matching transcript segment starts; `content_assets_100` returned exactly 100 assets with 100 unique timestamps and early/middle/late coverage from 1s to 1,602s; combined analysis `c46c7e033f60` had 337 timestamp citations and Markdown download returned HTTP 200 / 47,364 bytes. Evidence saved to `evidence/phase3-citation-coverage-report.json`. Automated suite returned 66 passed.
- 2026-08-31 16:18 EDT: Production async worker recovery proof. One public async job failed with `unable to open database file`; Hermes restarted `com.epic.transcript-api`, verified local `/health` ready true, and verified public async job `060e02c3fbec` completed `done` with record `90018add194a`, 366 words, 61 segments.
- 2026-08-31 16:02 EDT: Phase 3 quote-integrity gate advanced with a new reusable public smoke script. `scripts/phase3_quote_integrity_smoke.py https://epic-transcript.robyncrane.com` passed against the public no-login product. Rick Astley transcript returned record `2109dab1aa1a`, 366 words, 61 segments, cache hit; Best Quotes analysis `1a38b3076011` returned 4 quote lines, every quoted string exactly matched its timestamped Source text, every Source text was found in the transcript record, and Markdown download returned HTTP 200 / 1,145 bytes. Evidence saved to `evidence/phase3-quote-integrity-report.json`.
- 2026-08-31 12:38 EDT: Phase 3 `content_assets_100` quality gate advanced. The deterministic generator now uses varied finished draft stems for hooks, email subjects, reel scripts, CTAs, quote cards, carousels, objection replies, and repurpose prompts. Regression coverage now requires distinct Hook and Email subject stems, not just distinct timestamps. Public quality smoke passed against `https://epic-transcript.robyncrane.com`: 100 assets, 100 unique bodies, 100 timestamped assets, no placeholder phrasing, early/middle/late coverage 24/30/24, full response saved at `evidence/phase3-100-assets-quality-response.md`. Full suite passed with 54 tests.
- 2026-08-31 11:43 EDT: added and ran `scripts/phase3_all_outputs_smoke.py` against the public no-login URL. PASS: `/api/analysis-outputs` returned exactly 17 definitions; Rick Astley transcript completed from cache with record `795537aa5f0d`, 366 words, 61 segments; all 17 individual `/api/analyze/{id}` outputs returned useful copy-ready text with `AI-generated` disclaimer and timestamp/evidence markers, including `ask_question` with Trevor context; individual Markdown analysis download returned HTTP 200, `text/markdown`, 907 bytes.
- 2026-08-31 11:43 EDT: reran public Phase 3 UI/copy/download and long-transcript smokes. PASS: UI contract root HTTP 200 with 46,321 bytes, required controls/IDs present, async transcript, all-output, single-output, ask-question, copy, and download wiring present, old sync path absent. Combined analysis returned 16 outputs / 13,076 copy-ready chars and Markdown download HTTP 200 / 13,960 bytes. Two-hour cached long fixture returned record `837a9891f74d`, 19,298 words, 1,446 segments, duration 7,244s, `queued-chunked-local-whisper`, cache hit; combined long analysis returned 16 outputs / 19,106 chars, latest cited timestamp 7,242s, and Markdown download HTTP 200 / 19,106 bytes.
- 2026-08-31 11:43 EDT: automated suite and Phase 3 smoke script syntax passed: `./.venv/bin/python -m pytest -q` returned 49 passed, and `python3 -m py_compile` passed for `phase3_all_outputs_smoke.py`, `phase3_ui_contract_smoke.py`, `phase3_combined_analysis_smoke.py`, and `phase3_long_analysis_smoke.py`.
- 2026-08-31 09:32 EDT: added and ran a public no-Chrome UI contract harness for the Phase 3 user flow.
- Public UI contract: PASS. Required analysis controls and labels are present, async transcript job wiring is present, old synchronous submit wiring is absent, all-outputs and ask-question analysis endpoints are wired, and copy/download wiring is present.
- Public API proof from the contract harness: PASS. Rick Astley cached transcript returned record `18cc682b7b51`, 366 words, 61 segments. `/api/analyze-all/{id}` returned analysis `b8614a2d6247`, 16 sections, 13,076 chars, `AI-generated` disclaimer, and timestamp evidence. Markdown download returned HTTP 200, 13,960 bytes. Ask-question returned analysis `b72d30a12ad0`, 784 chars.
- 2026-08-31 08:53 EDT: public root still contains Phase 3 analysis markers after the UX alignment pass, including `/api/analyze-all/`, `analysisMenu`, `analysisCopyBtn`, and the ask-a-question controls.
- 2026-08-31 06:32 EDT: Phase 3 starter backend and expanded full-menu UI are live on `https://epic-transcript.robyncrane.com/`.
- 2026-08-31 07:43 EDT: long-transcript Phase 3 public proof passed on the two-hour cached fixture. The backend now samples beginning, middle, and ending timestamp evidence for long records instead of only the opening segments.
- 2026-08-31 07:07 EDT: combined-output copy/download path is live on `https://epic-transcript.robyncrane.com/`.
- Public UI markers: PASS. Root HTML returned HTTP 200 and contains `AI Summary`, `Action Items`, `All Outputs`, `Copy Analysis`, the full output menu container `analysisMenu`, copy control `analysisCopyBtn`, ask-a-question input, `Download Analysis`, `/api/analyze/`, and `/api/analyze-all/` markers.
- Backend starter outputs: PASS. `tests/test_phase3.py` covers owner-protected `/api/analyze/{id}`, `/api/analyze-all/{id}`, every declared `ANALYSIS_OUTPUTS` type, beginning/middle/end evidence sampling for long records, original transcript preservation, Markdown analysis download, combined-output Markdown download, and migration of an older partial `analyses` table.
- Public API proof: PASS starter. Cached control transcript `dQw4w9WgXcQ` returned HTTP 200 with record `2f2b61d2ccf6`, method `native-caption-subtitles`, 366 words, cache hit. `/api/analysis-outputs` returned 17 definitions. All 17 `/api/analyze/{record_id}` calls returned HTTP 200 with useful nonempty text, `AI-generated` disclaimer, and transcript evidence, including `ask_question` with `What should Trevor do with this video?`.
- Public combined-output proof: PASS starter. `scripts/phase3_combined_analysis_smoke.py https://epic-transcript.robyncrane.com` passed at 2026-08-31 07:07 EDT. Cached control transcript returned record `1f5a2b16abd8`, 366 words, method `native-caption-subtitles`, cache hit. `/api/analyze-all/{id}` returned 16 combined starter outputs, 10,036 copy-ready characters, and analysis ID `bfb7ef1f1bab`. `/api/analysis/bfb7ef1f1bab/download` returned HTTP 200, `text/markdown`, 10,600 bytes.
- Public long-transcript combined-output proof: PASS starter. `scripts/phase3_long_analysis_smoke.py https://epic-transcript.robyncrane.com` passed at 2026-08-31 07:43 EDT. Async job `c345b34bc0ba` returned record `837a9891f74d` for the two-hour cached fixture with 19,298 words, 1,446 segments, duration 7,244s, method `queued-chunked-local-whisper`, cache hit. `/api/analyze-all/{id}` returned 16 outputs, 19,106 copy-ready characters, latest cited analysis timestamp 7,242s, and analysis ID `8215f62db5fa`. `/api/analysis/8215f62db5fa/download` returned HTTP 200, `text/markdown`, 19,106 bytes.
- Limit: this is deterministic provider-safe starter intelligence, not the full AI release gate. Fuller AI/provider-backed intelligence quality remains open until a free/no-surprise LLM/provider option is selected. Current fallback scope is extractive/deterministic: timestamp-cited summaries, ideas, actions, chapters, quotes selected from transcript evidence, content drafts, sales/Trevor-use angles, starter 100-asset map, and question answers grounded in sampled transcript lines. Browser/mobile interaction proof for core transcript copy/download has passed separately; no-Chrome Phase 3 UI contract covers the analysis wiring.

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


### Browser and mobile UX proof
Run time: 2026-08-31.

- Public app: `https://epic-transcript.robyncrane.com/`.
- Browser path: Chrome CDP against the actual public page after remote-debugging approval.
- Desktop viewport: 1440x950.
- Desktop URL fixture: `https://www.youtube.com/watch?v=vgIle-XrvQI`.
- Desktop result: `Avoir d'la broue dans l'toupèt!`, method `local-whisper`, 1,578 transcript chars.
- Desktop copy result: PASS. Toast `Copied to clipboard ✓`; clipboard matched the full transcript.
- Mobile viewport: 390x844.
- Mobile URL fixture: `https://www.youtube.com/shorts/1WW76Rz4nqM`.
- Mobile result: `HOW TO: Edit with AI in YouTube Shorts`, method `local-whisper`, 887 transcript chars.
- Mobile layout: PASS. `overflowX=false`; core controls visible and sized for touch.
- Mobile copy result: PASS. Toast `Copied to clipboard ✓`; clipboard matched the full transcript.
- API wiring observed from browser network: `/api/setup`, `/api/recent`, `/api/transcribe-url-job`, and `/api/jobs/...`.
- Static HTML check: async job markers present; old synchronous submit call absent.
- Screenshot/report evidence: `evidence/browser-mobile-qc/report.json`, `desktop-initial.png`, `desktop-result.png`, `mobile-initial.png`, `mobile-result.png`.


### Backend durability gate

Current status: in progress.

- iMac launchd plus Cloudflare Tunnel: PASS hardened bridge, not final durability.
- Hosted container readiness: PASS spike on 2026-08-31 10:06 EDT. Docker image built and local container health/root checks passed with persistent `/data` volume and local Whisper available.
- Hosted seeded release smoke: PASS on 2026-08-31 11:06 EDT for Phase 1 async matrix, Phase 2 uploads/downloads, and Phase 3 UI contract on `127.0.0.1:8091` with `/data` seeded from the current SQLite cache.
- Cache migration package and verifier: PASS prepared on 2026-08-31 13:21 EDT. `scripts/hosted_staging_pack.py` created `evidence/hosted-staging-seed.tar.gz`; `scripts/hosted_staging_verify.py` verified and extracted it locally. Proof: DB SHA-256 `d04607cef60c26f79eb2b52a5c076b51b476269d56ebe3cba5e9df8f7ceb5915`, source DB size 25,718,784 bytes, package size 4,412,918 bytes, 339 transcript rows, required cached media present and verified: `v34Eg12mhDM` 87 rows, `dQw4w9WgXcQ` 72 rows, `SXHMnicI6Pg` 15 rows, `aircAruvnKk` 15 rows. Local extraction proof: `evidence/hosted-staging-verify-data/transcripts.db`.
- Staging smoke runner: PASS prepared and hardened on 2026-08-31 13:53 EDT. Added `--out` to `scripts/hosted_staging_smoke.py`, covered it with a failing-first regression that proves the JSON report is saved, and regenerated the seed package manifest so the host runs one command after container start: `./.venv/bin/python scripts/hosted_staging_smoke.py http://<staging-host> --out evidence/hosted-staging-smoke-report.json`. Fresh seed verification passed with DB SHA-256 `ce83c5b88b91e7f1a44f293e47de2c8c62a707bd87894a284893e86c81b6f4f3`, source DB size 26,742,784 bytes, package size 4,583,649 bytes, 347 transcript rows, and required cached media verified: `v34Eg12mhDM` 91, `dQw4w9WgXcQ` 76, `SXHMnicI6Pg` 15, `aircAruvnKk` 15. Public proof report saved at `evidence/hosted-staging-smoke-report.json`: Phase 1 PASS 24.61s, Phase 2 PASS 11.99s, Phase 3 PASS 3.44s.
- Hosted transfer bundle: PASS prepared on 2026-08-31 14:08 EDT. Added `scripts/hosted_staging_bundle.py` and regression coverage. Created and inspected `evidence/hosted-staging-transfer-bundle.tar.gz`: 4,619,331 bytes, SHA-256 `04eaf8304d0c16bf02754e19338090186b60bfb0e8717ca2e7fa4b222a26a615`, 11 verified members including seed package, Docker/app files, verification/smoke scripts, Phase 1/2/3 scripts, migration guide, and `transfer-manifest.json`. The manifest includes the exact host verify command and smoke command.
- Hosted transfer-bundle preflight: PASS prepared on 2026-08-31 15:16 EDT. Added `scripts/hosted_staging_bundle_verify.py`, included it in the transfer bundle, regenerated `evidence/hosted-staging-transfer-bundle.tar.gz`, and saved `evidence/hosted-staging-transfer-verify-report.json`. Proof: bundle size 4,620,968 bytes, SHA-256 `887b72fe1e197ba54031f63c8687f2c244157ffcc63d8ff02ef1a7e98a6f5f37`, 12 required members verified, manifest list verified, seed package SHA-256 verified, extracted DB `evidence/hosted-staging-transfer-verify-data/transcripts.db`, 347 transcript rows verified, required cached media verified: `v34Eg12mhDM` 91, `dQw4w9WgXcQ` 76, `SXHMnicI6Pg` 15, `aircAruvnKk` 15.
- Hosted staging runbook: PASS prepared on 2026-08-31 15:32 EDT. Added `scripts/hosted_staging_runbook.py`, included it in `evidence/hosted-staging-transfer-bundle.tar.gz`, and added regression coverage proving the printed host plan includes seed verification, Docker build, detached container start, health wait, and Phase 1/2/3 smoke report. Fresh bundle preflight saved `evidence/hosted-staging-transfer-verify-report.json`: bundle size 5,062,917 bytes, 13 required members verified, runbook command present, seed package SHA-256 verified, extracted DB verified, 380 transcript rows, required cached media verified: `v34Eg12mhDM` 100, `dQw4w9WgXcQ` 91, `SXHMnicI6Pg` 16, `aircAruvnKk` 16.
- Hosted staging runbook execution: PASS locally on 2026-08-31 15:46 EDT. Executed `scripts/hosted_staging_runbook.py` against Docker staging on `http://127.0.0.1:8092`; it verified/extracted the seed into a persistent `/data` bind mount, built `epic-transcript-machine:hosted-staging`, started the container, waited for `/health` HTTP 200 with `ready=true` and required `missing=[]`, ran the full Phase 1/2/3 smoke suite, saved `evidence/hosted-staging-runbook-smoke-report.json`, saved summary `evidence/hosted-staging-runbook-execute-report.json`, and removed the container. Smoke proof: `ok=true`; Phase 1 matrix PASS 32.63s; Phase 2 upload smoke PASS 12.33s; Phase 3 UI contract PASS 2.64s; extracted DB SHA-256 `6e0db1c41d476ee036defd4f5882167dcb93344fbbbf6a032a7d0874ca347bd4`; 394 transcript rows after smoke; required cached media verified.
- Cache migration to host: OPEN. The first hosted staging target must receive the packaged `transcripts.db` in its persistent `/data` volume before release verification, because a cold empty cache currently fails selected YouTube fixtures under current provider/IP conditions.
- Staging hosted deployment: OPEN. Needs selected persistent host and public no-login staging URL.
- DNS cutover from iMac tunnel: OPEN. Do only after hosted staging passes Phase 1, Phase 2, and Phase 3 smoke tests.


### 2026-08-31 release-pack sprint evidence

- Immutable deploy: `https://6a95a4ee9dbf9a64e3232e0e--epic-transcript-machine-review.netlify.app`.
- Latest committed HEAD after Phase 3 and Phase 2 async URL work: `3af8b10247f12d83b62e800a6634228411390a00`.
- Automated suite: PASS, `53 passed in 4.40s`.
- Public root/health: PASS, HTTP 200; health ready true; required missing empty; local Whisper available; Gemini optional, not required.
- FAQ/UI: PASS. Public root has no `Generator` marker, has `Machine`, primary-gradient `accent-text`, all seven reference FAQ questions, `themeToggle`, persisted `epicTranscriptTheme`, mobile-visible 44px theme switch, async URL job markers, browser-local fallback disclosure, WebGPU marker, WASM marker, and Transformers.js browser Whisper marker.
- Phase 1 matrix: PASS. `scripts/phase1_matrix.py https://epic-transcript.robyncrane.com` returned `all_ok=true`.
- Browser/mobile CDP proof: PASS. Desktop submitted French fixture and Copy matched clipboard. Mobile 390x844 submitted genuine Shorts fixture and Copy matched clipboard. No horizontal overflow. Screenshots/report saved in `evidence/browser-mobile-qc/`.
- Static contrast/focus/touch proof: PASS. `scripts/phase1_dom_click_mobile_a11y_smoke.py` returned critical contrast ratios above 4.5:1, visible focus-ring contract, reduced-motion support, mobile breakpoints, full-width submit, and signed TXT/Markdown/SRT downloads.
- Phase 2 upload/download/cleanup proof: PASS. `scripts/phase2_upload_smoke.py` and `scripts/phase2_release_gate_smoke.py` passed publicly for WAV, MP3, M4A, MP4, MOV, WebM, cache repeat, signed downloads, unsupported upload guidance, unsupported URL guidance, and transcript/analysis cleanup readback.
- Phase 2 async URL/social matrix: PASS. `scripts/phase2_url_matrix_smoke.py` returned `all_ok=true`; direct public MP3 URL passed through `/api/transcribe-url-job`; TikTok, Instagram, Facebook, and X/Twitter returned helpful upload/direct-media guidance.
- Browser-local fallback: IMPLEMENTED, pending independent full model execution. UI exposes a browser-only fallback checkbox; code uses `navigator.gpu` for WebGPU when present and Transformers.js WASM when WebGPU is unavailable; disclosure says the file stays on-device and model progress is shown.
- Phase 3 all outputs: PASS for deterministic starter quality. `scripts/phase3_all_outputs_smoke.py` returned OK with 17/17 outputs, timestamp evidence, disclaimer, copy-ready output, and Markdown download. `content_assets_100` now returns exactly 100 numbered assets and no `starter map` language.
- Phase 3 long transcript coverage: PASS. `scripts/phase3_long_analysis_smoke.py` against the two-hour record returned 46,253 chars, 16 combined outputs, latest evidence timestamp 7,242 seconds, and Markdown download HTTP 200.


### 2026-08-31 visual correction gate evidence
- Commit under test: `198de6bb39ab2a0ad7537aa1a5620a16d1030b89` before evidence commit. Immutable deploy: `https://6a95aa4dd39478518111db2a--epic-transcript-machine-review.netlify.app`.
- Visual corrections: `FAST · FREE · V3` / `FAST. FREE. VERSION THREE.` removed; `Get Video Transcript` removed; CTA now says `Get Transcript`; upload box stripped to `Choose file` plus the actual file control; long extension list removed from visible copy; visible version/phase strip removed; theme switch is icon-only (`☀`/`☾`) with accessible labels and persisted `epicTranscriptTheme`; logo mark replaced with the original white-circle audio-wave SVG style from Trevor's reference.
- Light-mode contrast proof: CDP visual report measured input, upload/status, result card, and transcript text as dark accessible text (`rgb(23, 23, 25)`) in light mode.
- Browser/mobile screenshots: `evidence/visual-correction-gate/desktop-dark.png`, `desktop-light.png`, `desktop-light-result.png`, `mobile-dark.png`, `mobile-light.png`; report `evidence/visual-correction-gate/report.json` returned `ok=true`.
- Regression-video proof: public CDP run submitted French regression video `vgIle-XrvQI`, got status `Done`, method `local-whisper`, transcript length `1,578`, and result/transcript dark text in light mode. Browser-mobile acceptance rerun also passed desktop French copy and mobile Shorts copy with no horizontal overflow.
- Full suite: `53 passed in 5.71s` during post-deploy verification. Phase 1 DOM/mobile/a11y smoke passed, including VTT signed downloads.
