# Hosted Backend Migration

Goal: remove the current iMac plus Cloudflare Tunnel dependency without adding surprise paid transcription providers or visitor login.

## Target architecture

- FastAPI backend runs as a container on a host with CPU, ffmpeg, yt-dlp, and local Whisper available.
- Persistent volume is mounted at `/data` and mapped with `TRANSCRIPT_DATA_DIR=/data` so SQLite transcript/cache data survives restarts and redeploys.
- Static UI remains public and no-login. It can be served by the same FastAPI container or by the existing Netlify/static front end pointed at the hosted API base.
- Custom domain stays `https://epic-transcript.robyncrane.com/` after DNS is moved from the iMac tunnel to the hosted service.

## Environment contract

Required:

- `PORT=8090` or the platform-provided port.
- `TRANSCRIPT_DATA_DIR=/data` backed by a persistent disk or volume.
- `TRANSCRIPT_STATIC_DIR=/app/static` for the bundled UI.
- `YT_DLP_BIN`, `FFMPEG_BIN`, and `WHISPER_BIN` only if the host installs binaries outside PATH.

Optional and intentionally non-blocking:

- SMTP settings for Email to Me.
- `GEMINI_API_KEY` for future optional intelligence. Do not enable this as a required paid path without approval.

## First provider candidates

1. Existing owned Mac/iMac plus named Cloudflare Tunnel. Current hardened bridge, not final durability.
2. Orgo or a small persistent Linux VM with Docker and a mounted disk. Best fit for free/local Whisper, ffmpeg, long jobs, and no API surprise billing. This is the preferred first no-DNS-cutover staging path.
3. Fly.io, Render, Railway, or similar container host only if a persistent disk and predictable spend cap are configured first.
4. Cloudflare Workers/Pages are not a fit for local Whisper or long ffmpeg jobs by themselves. They can remain the static/API front door later.

## Data migration requirement

- Seed the hosted persistent volume before release verification: copy the current `data/transcripts.db` to the host volume as `/data/transcripts.db` before the container starts.
- Do not rely on an empty volume for release parity. A cold empty container can process uploads and some fresh YouTube audio through local Whisper, but current YouTube/IP conditions can block uncached regression and Shorts pulls.
- Verify the seed inside the container before running the matrix:

```bash
docker exec <container> python - <<'PY'
import sqlite3, os
p='/data/transcripts.db'
print(os.path.exists(p), os.stat(p).st_size)
con=sqlite3.connect(p)
print(con.execute('select count(*) from transcripts').fetchone()[0])
print(con.execute("select count(*) from transcripts where media_id='v34Eg12mhDM'").fetchone()[0])
PY
```

- On Docker Desktop, avoid using `/tmp/...` as the seed path for bind-mount proof. A repo-local or real host volume path exposed the expected SQLite file reliably.

## Cutover checklist

1. Build container locally: `docker build -t epic-transcript-machine .`
2. Run with persistent data: `docker run --rm -p 8090:8090 -v "$PWD/data-hosted-test:/data" epic-transcript-machine`.
3. Verify `/health` returns HTTP 200 and required `missing: []`.
4. Run public-style Phase 1 matrix against the container URL. The matrix uses the async UI path for YouTube links so long YouTube sources do not depend on the older synchronous endpoint.
5. Run Phase 2 upload smoke against the container URL with generated spoken fixtures.
6. Run Phase 3 UI contract smoke against the container URL.
7. Deploy to the selected host with a persistent `/data` volume.
8. Move DNS only after hosted `/health`, transcript, upload, download, and analysis evidence passes.
9. Keep the launchd iMac/tunnel path as rollback until the hosted domain has passed a 24-hour health window.

## Current status

- App code now supports `TRANSCRIPT_DATA_DIR` and `TRANSCRIPT_STATIC_DIR`, so the database and bundled static directory can be moved cleanly in a container without source edits.
- `Dockerfile` is present as the first hosted-backend spike. It installs ffmpeg, Python dependencies, and local Whisper, exposes port 8090, and defines `/data` as the persistent volume.
- Automated coverage includes `test_hosted_backend_can_move_runtime_data_dir_without_code_changes` to prove the hosted data path contract initializes SQLite outside the repo.
- Seeded local Docker validation passed on 2026-08-31: `/health`, Phase 1 async matrix, Phase 2 upload/download smoke, and Phase 3 UI contract all passed against `127.0.0.1:8091` when `/data` was seeded from the current SQLite cache.
