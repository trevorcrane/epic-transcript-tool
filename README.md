# Epic Transcript Tool

> Drop a link or file. Grab the transcript.

A brutally simple FastAPI app that turns any URL or media file into clean text.
Native captions first (via `yt-dlp`), OpenAI Whisper as fallback. SQLite
history, dark Epic styling, single page.

---

## Install

```bash
cd /Users/tc-imac/.openclaw/workspace/epic-transcript-tool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

System binaries required (already installed on this machine):

- `yt-dlp` — `brew install yt-dlp`
- `ffmpeg` — `brew install ffmpeg`

## Configure

Copy `.env.example` to `.env` and fill in what you have. The app loads with
missing keys and shows a setup banner instead of crashing.

```
OPENAI_API_KEY=sk-...        # required for Whisper fallback (no captions)
OWNER_EMAIL=you@epic.media   # destination for "Email to Me"
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587                # 465 for SSL, anything else uses STARTTLS
SMTP_USER=you@epic.media
SMTP_PASS=app-password
PORT=8090                    # FastAPI port; suite server proxies /epic-transcript -> here
```

## Run

```bash
source .venv/bin/activate
python app.py
```

The FastAPI server listens on `PORT` (default 8090).

## Access via the Epic suite server

The Epic suite server (`workspace/serve.js`, port 8080) proxies
`/epic-transcript` and `/epic-transcript/*` to this FastAPI app, so the tool is
reachable at:

- **http://localhost:8080/epic-transcript**

If you want to hit FastAPI directly (no suite server), open
**http://localhost:8090/**.

## Smoke test

With both servers running:

```bash
./smoke.sh
```

Verifies `/health`, `/api/setup`, `/api/recent`, suite-server routing, and a
text upload roundtrip.

## How it works

- **URL submit** → `yt-dlp --write-auto-sub --skip-download` first; if captions
  exist, parse and return. Otherwise download audio (`-x --audio-format mp3`)
  and POST to OpenAI Whisper.
- **File upload** → `txt`/`md` returned as-is, `srt`/`vtt` stripped to clean
  text, audio/video sent to Whisper.
- Files >25 MB are auto-transcoded to mono 16 kHz 32 kbps mp3 before Whisper.
- Successful transcripts are saved to `data/transcripts.db` and surfaced in
  the "Recent" drawer.

## API

```
GET  /                                    serves the SPA (no visitor login)
GET  /health                              status + setup info + auth counters (no secrets)
GET  /api/setup                           missing-keys list
POST /api/session                         mint a 12 h page session (the page does this itself)
POST /api/transcribe-url-job  form: url   → 202 { job }      [guarded]
GET  /api/jobs/{id}                       → { job }          [guarded, creator only]
POST /api/transcribe-url   form: url      → { record }       [guarded; media > 6 min → 422, use the job API]
POST /api/transcribe-upload file: <file>  → { record }       [guarded]
POST /api/analyze/{id}, /api/analyze-all/{id}                [guarded + owner]
GET  /api/recent?limit=20                 → { items: [...] } [X-Transcript-Owner]
GET  /api/transcripts/{id}                full record        [X-Transcript-Owner]
POST /api/transcripts/{id}/download-link  signed 5-min link  [X-Transcript-Owner]
DELETE /api/transcripts/{id}              remove             [X-Transcript-Owner]
POST /api/email/{id}                      SMTP send to OWNER_EMAIL
```

### Auth for guarded routes
- Bots and scripts: `Authorization: Bearer <token>` (or `X-Transcript-Api-Token`).
  Server tokens: `TRANSCRIPT_API_TOKENS` (comma list, for rotation) in `.env`. Never commit them.
- The public page: `POST /api/session`, then `X-Transcript-Session` on every call
  (kept in memory, never localStorage). Page limits: 2 active jobs per IP, 5 queued page jobs.
- `TRANSCRIPT_AUTH_MODE=log` lets missing credentials through and counts them in
  `/health` (`auth.auth_missing`); use it for the first deploy hour, then `enforce` (default).

### Long audio
Job-API media longer than `SINGLE_AUDIO_MAX_SECONDS` (360), or of unknown length, is split
into `LONG_VIDEO_CHUNK_SECONDS` (600) chunks and transcribed one chunk at a time
(`CHUNK_TIMEOUT_SECONDS` ≥ 1800 per chunk, `MEDIA_DOWNLOAD_TIMEOUT_SECONDS` 1800,
`JOB_MAX_SECONDS` 14400, `MAX_CONCURRENT_LONG_JOBS` 1). Jobs left running by a restart
are marked as errors at startup.

Live long-podcast gate: `scripts/long_podcast_e2e.py BASE_URL` (see ACCEPTANCE_TESTS.md).

## What's intentionally not here

No visitor login (bots use an API token, the page a signed session), no multi-user, no AI rewriting, no context dropdowns, no v2 page.
The point is: drop a link, grab the transcript.
