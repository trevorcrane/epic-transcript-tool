# EPIC Transcript Machine Version / Phase Status

Updated: 2026-08-31 11:39 EDT

## Version 1 / Phase 1: Bulletproof YouTube Transcripts
Status: Release-clear for the current public no-login fixture gate.

Current evidence:
- Public URL: https://epic-transcript.robyncrane.com/
- Regression video passes publicly with correct title, 1,460 segments, 15,744 words, increasing timestamps, and cache hit.
- Manual-caption control passes publicly with 61 segments and 366 words.
- Non-English YouTube, genuine Shorts, two-hour long-video async transcription, downloads, desktop copy-flow, and mobile touch-flow have public pass evidence.
- Latest 2026-08-31 11:39 EDT Phase 1 health run passed again after API reload.
- Visible phase cards are now live on the public root and Netlify review page.

Remaining:
- Keep monitoring YouTube provider volatility.
- Move from iMac plus Cloudflare Tunnel to a hosted durable backend after seeded staging passes.

## Version 2 / Phase 2: Any Video or Audio
Status: Advanced, not final-release complete.

Current evidence:
- Public generated WAV, MP3, M4A, MP4, MOV, and WebM uploads pass through local Whisper with repeat-cache and TXT/Markdown/SRT download proof.
- Public French non-English WAV upload passes through local Whisper.
- Public generated 31-minute MP3 upload passes with duration metadata.
- Public supported non-YouTube MP3 URL passes.
- Cleanup/retention regression and public delete cleanup proof pass.
- Unsupported upload guidance now lists every supported format publicly.

Remaining:
- Fuller browser UX proof for file upload and unsupported upload handling.
- Hosted staging verification with seeded cache before DNS cutover.

## Version 3 / Phase 3: Video Intelligence
Status: Advanced publicly, not final AI-release complete.

Current evidence:
- Starter intelligence routes and UI are live: summary, action items, all outputs, question answering, copy, and Markdown download.
- Public UI contract passed again on 2026-08-31 11:39 EDT with 16 combined sections, 13,076 chars, Markdown download HTTP 200, and ask-question output.
- Long-transcript analysis proof cites beginning, middle, and ending timestamp evidence for the two-hour fixture.

Remaining:
- Select and approve a free/no-surprise provider path before enabling fuller AI-backed intelligence.
- Add fuller browser/mobile click proof for intelligence controls.

## 30-minute loop
A recurring Hermes cron job is installed:
- Job ID: 26ac787743cc
- Name: EPIC Transcript Machine 30-minute progress loop
- Schedule: every 30m
- Delivery: back to origin chat
- Purpose: continue implementation, test, update docs, and post a concise progress report every run.
