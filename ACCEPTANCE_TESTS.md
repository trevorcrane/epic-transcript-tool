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
Run time: 2026-08-30 23:24 EDT.

- Public app root: PASS, HTTP 200.
- Public setup endpoint: PASS, HTTP 200, `ready: true`, required `missing: []`, optional missing only SMTP config and `GEMINI_API_KEY`.
- Public release checker scripts now send a normal browser-style user agent so Cloudflare does not reject Python urllib checks with 1010.
- Backend durability step: `com.epic.transcript-api` and `com.epic.transcript-tunnel` are loaded under launchd with KeepAlive.
- Public Phase 1 health script still passes regression and manual-caption control.
- Full public matrix is not clean: invalid URL returned HTTP 500 from the currently running public API process, while local TestClient returns the intended helpful HTTP 422. Public API reload is needed after the latest hardening.

### Additional Phase 1 cases
Status: partially verified in production.

| Case | URL | Result | Evidence |
| --- | --- | --- | --- |
| Control video | `https://youtu.be/dQw4w9WgXcQ` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 61 segments, 366 words, language `en`. |
| Manual-caption video | `https://youtu.be/dQw4w9WgXcQ` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 61 segments, 366 words. |
| Automatic-caption video | `https://youtu.be/v34Eg12mhDM` | PASS | HTTP 200, `native-caption-automatic_captions`, cache hit, 1,460 segments, 15,744 words. |
| Non-English video | `https://youtu.be/kJQP7kiw5Fk` | FAIL, evidence not release-valid | Current public cache can return HTTP 200 with `en-US` subtitles for Despacito, which does not prove non-English transcription. Fresh non-English candidates tested this run returned helpful upload guidance under YouTube blocking/rate limiting. Needs a known-accessible original-language source or fallback coverage. |
| Shorts URL | `https://www.youtube.com/shorts/SXHMnicI6Pg` | PASS | HTTP 200, `native-caption-automatic_captions`, cache hit, 2 segments, 3 words. Low word count but accepted for URL-shape handling only. |
| Private/unavailable video | `https://www.youtube.com/watch?v=aaaaaaaaaaa` | PASS helpful failure | HTTP 422 with upload guidance. |
| Invalid URL | `https://not-a-real.example/video` | FAIL public, PASS local | Public matrix returned HTTP 500 from the currently running API process. Local TestClient returns helpful HTTP 422. Needs public API reload/retest. |
| Long video | `https://youtu.be/aircAruvnKk` | PASS | HTTP 200, `native-caption-subtitles`, cache hit, 286 segments, 3,360 words. |
| Repeated request confirms a cache hit | Regression and control videos | PASS | Public health script returned cache hit for both. |
| Copy transcript | UI marker present | Pending browser interaction evidence | Needs direct browser copy-flow verification. |
| TXT download | Regression record | PASS | HTTP 200, 94,784 bytes. |
| Markdown download | Regression record | PASS | HTTP 200, 100,829 bytes. |
| SRT download | Regression record | PASS | HTTP 200, 134,557 bytes. |
| Mobile layout | Redesign evidence | PASS visual smoke | Mobile screenshot evidence exists in `evidence/`; full touch-flow still pending. |
| Button contrast and accessibility | Automated design tests | PASS smoke | Design tests passed for dark presentation surface, light results workspace, and functional IDs. Full accessibility audit still pending. |

## Phase 2 release gate: Any video or audio

Current implementation evidence:
- 2026-08-30 23:24 EDT: local code now resolves `yt-dlp`, `ffmpeg`, and Whisper through configured or absolute binary paths when launchd has a minimal PATH.
- `com.epic.transcript-api.plist` now includes `YT_DLP_BIN=/usr/local/bin/yt-dlp`, `FFMPEG_BIN=/usr/local/bin/ffmpeg`, `WHISPER_BIN=/usr/local/bin/whisper`, and a known PATH for the next API restart.
- Generated MP3 upload passed locally through FastAPI TestClient with HTTP 200, method `local-whisper`, 2 segments, 18 words, and first text `Epic transcript machine phase 2 audio upload test.`
- Public generated MP3/WAV/M4A uploads still returned `Local Whisper is not installed on this server/browser path` before the public API process could be reloaded.

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
