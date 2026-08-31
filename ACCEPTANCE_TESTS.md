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
Run time: 2026-08-31 01:34 EDT.

- Public app root: PASS, HTTP 200.
- Public setup endpoint: PASS, HTTP 200, `ready: true`, required `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public release checker scripts now send a normal browser-style user agent so Cloudflare does not reject Python urllib checks with 1010.
- Backend durability step: `com.epic.transcript-api` and `com.epic.transcript-tunnel` are loaded under launchd with KeepAlive.
- Public Phase 1 health script now accepts a CLI base URL, and the public run passed regression plus manual-caption control.
- Public Phase 1 bounded scripted matrix now passes all 9 cases. Regression, manual-caption control, automatic captions, short French non-English fixture, genuine Shorts, moderate long cached transcript, private/unavailable helpful failure, invalid URL helpful failure, privacy/history, service health, and public upload smoke pass. The stricter two-hour/long-video release gate remains open until a true long source returns a transcript.

### Additional Phase 1 cases
Status: bounded scripted matrix passing in production. Full release gate still open for two-hour/long-video transcription plus browser copy/touch-flow evidence.

| Case | URL | Result | Evidence |
| --- | --- | --- | --- |
| Control video | `https://youtu.be/dQw4w9WgXcQ` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 61 segments, 366 words, language `en`. |
| Manual-caption video | `https://youtu.be/dQw4w9WgXcQ` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 61 segments, 366 words. |
| Automatic-caption video | `https://youtu.be/v34Eg12mhDM` | PASS | HTTP 200, `native-caption-automatic_captions`, cache hit, 1,460 segments, 15,744 words. |
| Non-English video | `https://youtu.be/kv92eqcZVxs` plus async fixture `https://www.youtube.com/watch?v=vgIle-XrvQI` | PASS | Short French fixture returned HTTP 200, `local-whisper`, cache hit on repeated matrix run, 2 segments, 37 words, language `fr`, credible French text. Separate fresh uncached async French fixture returned 31 segments, 228 words, language `fr`. |
| Genuine Shorts URL | `https://www.youtube.com/shorts/SXHMnicI6Pg` plus `https://www.youtube.com/shorts/1WW76Rz4nqM` | PASS | Scripted Shorts fixture returned HTTP 200, `native-caption-automatic_captions`, cache hit, 2 segments, 3 words. Stronger exact Shorts fixture `1WW76Rz4nqM` returns HTTP 200 from cache via `local-whisper`, 13 segments, 151 words. Needs periodic fresh-cache-miss recheck. |
| Private/unavailable video | `https://www.youtube.com/watch?v=aaaaaaaaaaa` | PASS helpful failure | HTTP 422 with upload guidance. |
| Invalid URL | `https://not-a-real.example/video` | PASS helpful failure | Public matrix returned HTTP 422 with upload guidance after API reload. |
| Moderate long video | `https://youtu.be/aircAruvnKk` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 286 segments, 3,360 words. Does not clear the stricter two-hour/long-video release gate. |
| Repeated request confirms a cache hit | Regression and control videos | PASS | Public health script returned cache hit for both. |
| Copy transcript | UI marker present | Pending browser interaction evidence | Needs direct browser copy-flow verification. |
| TXT download | Regression record | PASS | HTTP 200, 94,784 bytes. |
| Markdown download | Regression record | PASS | HTTP 200, 100,829 bytes. |
| SRT download | Regression record | PASS | HTTP 200, 134,557 bytes. |
| Mobile layout | Redesign evidence | PASS visual smoke | Mobile screenshot evidence exists in `evidence/`; full touch-flow still pending. |
| Button contrast and accessibility | Automated design tests | PASS smoke | Design tests passed for dark presentation surface, light results workspace, and functional IDs. Full accessibility audit still pending. |

## Phase 2 release gate: Any video or audio

Current implementation evidence:
- 2026-08-31 01:34 EDT: reran `scripts/phase2_upload_smoke.py` against the public no-login API.
- Public generated WAV upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
- Public generated MP3 upload: PASS, HTTP 200, method `local-whisper`, 2 segments, 18 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
- Public generated MP4 upload: PASS, HTTP 200, method `local-whisper`, 1 segment, 12 words, credible text begins `Epic transcript machine phase 2 public upload test...`.
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
- 30+ minute recording.
- Non-English recording.
- Supported non-YouTube URL.
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
- Automatic deletion of temporary server media.

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

| Two-hour / long video | CS50 long fixture | OPEN / FAIL | Returns bounded helpful HTTP 422 instead of hanging. This is not release-valid long-video transcription support. |

| Exact French YouTube async fallback | `https://www.youtube.com/watch?v=vgIle-XrvQI` | PASS | Fresh uncached public async job. HTTP 202 start in 0.08s, final done after polling, `language=fr`, `local-whisper`, `cache_hit=false`, 31 segments, 228 words. Provider attempts recorded through metadata, subtitle failures/skips, Gemini unavailable, and local Whisper success. |
| Genuine Shorts URL | `https://www.youtube.com/shorts/1WW76Rz4nqM` | PASS, cached evidence | HTTP 200 in 3.57s, `local-whisper`, `language=en`, `cache_hit=true`, 13 segments, 151 words. Needs periodic fresh-cache-miss recheck, but the exact genuine Shorts fixture now returns a transcript. |
| Long-video transcription | CS50 two-hour fixture | OPEN / FAIL | Bounded helpful 422 prevents hangs. Not release-valid until a long video returns a transcript. |
