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

## Seed package for first staging host

Build the cache seed package before any no-DNS-cutover hosted staging attempt:

```bash
./.venv/bin/python scripts/hosted_staging_pack.py --out evidence/hosted-staging-seed.tar.gz
```

The command writes `evidence/hosted-staging-seed.tar.gz` with:

- `transcripts.db` copied from the current production cache.
- `manifest.json` containing database size, SHA-256 checksum, transcript count, and counts for the required Phase 1 cached media IDs.
- a single hosted staging smoke command that runs Phase 1, Phase 2, and Phase 3 public-style tests against the staging URL.

Current package evidence from 2026-08-31 13:53 EDT:

- Package: `evidence/hosted-staging-seed.tar.gz`.
- Source DB: `data/transcripts.db`.
- DB size: 26,742,784 bytes.
- Package size: 4,583,649 bytes.
- SHA-256: `ce83c5b88b91e7f1a44f293e47de2c8c62a707bd87894a284893e86c81b6f4f3`.
- Transcript rows: 347.
- Required cached media present: `v34Eg12mhDM` 91 rows, `dQw4w9WgXcQ` 76 rows, `SXHMnicI6Pg` 15 rows, `aircAruvnKk` 15 rows.
- Manifest smoke command: `./.venv/bin/python scripts/hosted_staging_smoke.py http://<staging-host> --out evidence/hosted-staging-smoke-report.json`.

## Host-side seed verification

After copying `evidence/hosted-staging-seed.tar.gz` to the selected host, verify and extract it before starting the container:

```bash
python3 scripts/hosted_staging_verify.py evidence/hosted-staging-seed.tar.gz --extract-to /path/to/persistent-data
```

The command checks that:

- `manifest.json` and `transcripts.db` are present in the tarball.
- The extracted database SHA-256 matches the manifest.
- The transcript row count matches the manifest.
- Required cached Phase 1 media IDs are present.
- `transcripts.db` is copied into the chosen persistent data directory.

Current local verification evidence from 2026-08-31 13:21 EDT:

- Command: `./.venv/bin/python scripts/hosted_staging_verify.py evidence/hosted-staging-seed.tar.gz --extract-to evidence/hosted-staging-verify-data`.
- Result: PASS, `ok=true`.
- Extracted DB: `evidence/hosted-staging-verify-data/transcripts.db`.
- SHA-256 verified: `ce83c5b88b91e7f1a44f293e47de2c8c62a707bd87894a284893e86c81b6f4f3`.
- Transcript rows verified: 347.
- Required cached media verified: `v34Eg12mhDM` 91, `dQw4w9WgXcQ` 76, `SXHMnicI6Pg` 15, `aircAruvnKk` 15.

## Cutover checklist

1. Build container locally: `docker build -t epic-transcript-machine .`
2. Copy `evidence/hosted-staging-seed.tar.gz` to the selected persistent host.
3. Run `scripts/hosted_staging_verify.py` on the host with `--extract-to` pointed at the mounted persistent data directory.
4. Run with persistent data: `docker run --rm -p 8090:8090 -v "$PWD/data-hosted-test:/data" epic-transcript-machine`.
5. Verify `/health` returns HTTP 200 and required `missing: []`.
6. Run `./.venv/bin/python scripts/hosted_staging_smoke.py http://<staging-host> --out evidence/hosted-staging-smoke-report.json`. It runs the Phase 1 async matrix, Phase 2 upload smoke, and Phase 3 UI contract smoke in order, prints one JSON pass/fail report, and saves the same JSON as durable host proof.
9. Deploy to the selected host with a persistent `/data` volume.
10. Move DNS only after hosted `/health`, transcript, upload, download, and analysis evidence passes.
11. Keep the launchd iMac/tunnel path as rollback until the hosted domain has passed a 24-hour health window.

## Current status

- App code now supports `TRANSCRIPT_DATA_DIR` and `TRANSCRIPT_STATIC_DIR`, so the database and bundled static directory can be moved cleanly in a container without source edits.
- `Dockerfile` is present as the first hosted-backend spike. It installs ffmpeg, Python dependencies, and local Whisper, exposes port 8090, and defines `/data` as the persistent volume.
- Automated coverage includes `test_hosted_backend_can_move_runtime_data_dir_without_code_changes` to prove the hosted data path contract initializes SQLite outside the repo.
- Seeded local Docker validation passed on 2026-08-31: `/health`, Phase 1 async matrix, Phase 2 upload/download smoke, and Phase 3 UI contract all passed against `127.0.0.1:8091` when `/data` was seeded from the current SQLite cache.
- Staging cache packaging passed on 2026-08-31 13:06 EDT. `scripts/hosted_staging_pack.py` created the seed tarball and automated manifest, and `tests/test_hosted_staging_pack.py` covers the copy/manifest contract.
- Host-side seed verification tooling passed on 2026-08-31 13:21 EDT. `scripts/hosted_staging_verify.py` validates the package manifest, SHA-256, transcript count, and required cached media IDs, then extracts `transcripts.db` into the selected persistent data directory before container start.
- Host-side release-smoke runner passed on 2026-08-31 13:53 EDT. `scripts/hosted_staging_smoke.py` gives the selected host a one-command Phase 1/2/3 staging acceptance run after the seeded container is online and can save the proof with `--out evidence/hosted-staging-smoke-report.json`.
- Host transfer bundle passed on 2026-08-31 14:08 EDT. `scripts/hosted_staging_bundle.py` creates one handoff tarball with the seed package, Dockerfile, app entrypoint, requirements, host verification script, Phase 1/2/3 smoke scripts, and this migration guide.
- Transfer-bundle preflight passed on 2026-08-31 15:16 EDT. `scripts/hosted_staging_bundle_verify.py` now proves the actual host handoff tarball is self-contained before transfer: it safely extracts the bundle, verifies the manifest member list, verifies the embedded seed package SHA-256, runs `hosted_staging_verify.py`, and saves a JSON proof report.

## Host transfer bundle

Use this when the selected persistent host is ready but a full git checkout has not been prepared yet:

```bash
./.venv/bin/python scripts/hosted_staging_bundle.py --seed-package evidence/hosted-staging-seed.tar.gz --out evidence/hosted-staging-transfer-bundle.tar.gz
```

Current transfer-bundle evidence from 2026-08-31 15:32 EDT:

- Bundle: `evidence/hosted-staging-transfer-bundle.tar.gz`.
- Bundle size: 5,062,917 bytes.
- Seed DB SHA-256: `b88fd873fc2002d5aa0d3ee34a883888ef3f418397e90343e671c053da7c2571`.
- Seed DB rows: 380.
- Member count: 13.
- Required members verified: `Dockerfile`, `requirements.txt`, `app.py`, `scripts/hosted_staging_verify.py`, `scripts/hosted_staging_bundle_verify.py`, `scripts/hosted_staging_runbook.py`, `scripts/hosted_staging_smoke.py`, `scripts/phase1_matrix.py`, `scripts/phase2_upload_smoke.py`, `scripts/phase3_ui_contract_smoke.py`, `docs/HOSTED_BACKEND_MIGRATION.md`, `evidence/hosted-staging-seed.tar.gz`, and `transfer-manifest.json`.
- Transfer preflight command: `./.venv/bin/python scripts/hosted_staging_bundle_verify.py evidence/hosted-staging-transfer-bundle.tar.gz --extract-to evidence/hosted-staging-transfer-verify-data --out evidence/hosted-staging-transfer-verify-report.json`.
- Transfer preflight result: PASS, `ok=true`; manifest members verified, embedded seed package SHA-256 verified, `transcripts.db` extracted to `evidence/hosted-staging-transfer-verify-data/transcripts.db`, 380 transcript rows verified, required cached media verified: `v34Eg12mhDM` 100, `dQw4w9WgXcQ` 91, `SXHMnicI6Pg` 16, `aircAruvnKk` 16.
- Host runbook command: `python3 scripts/hosted_staging_runbook.py http://<staging-host> --data-dir <persistent-data-dir> --execute --keep-running`.
- Host runbook plan command: `python3 scripts/hosted_staging_runbook.py http://<staging-host> --data-dir <persistent-data-dir> --print-plan`.
- Host verify command in manifest: `python3 scripts/hosted_staging_verify.py evidence/hosted-staging-seed.tar.gz --extract-to <persistent-data-dir>`.
- Host smoke command in manifest: `python3 scripts/hosted_staging_smoke.py http://<staging-host> --out evidence/hosted-staging-smoke-report.json`.

## Latest smoke report persistence proof

- 2026-08-31 15:46 EDT: `scripts/hosted_staging_runbook.py` was executed end-to-end locally against Docker staging at `http://127.0.0.1:8092`. It verified/extracted the seed package into `evidence/hosted-staging-runbook-data`, built image `epic-transcript-machine:hosted-staging`, started a detached container with that directory mounted as `/data`, waited for `/health` HTTP 200 with required `missing=[]`, ran Phase 1/2/3 smokes, saved `evidence/hosted-staging-runbook-smoke-report.json`, saved summary `evidence/hosted-staging-runbook-execute-report.json`, and removed the container. Smoke summary: `ok=true`; Phase 1 PASS 32.63s; Phase 2 PASS 12.33s; Phase 3 PASS 2.64s.
- 2026-08-31 13:53 EDT: `scripts/hosted_staging_smoke.py` was run against the current public product with `--out evidence/hosted-staging-smoke-report.json`. The saved report returned `ok=true`; Phase 1 matrix passed in 24.61s, Phase 2 upload smoke passed in 11.99s, and Phase 3 UI contract passed in 3.44s.
- 2026-08-31 14:08 EDT: public Phase 1 health still passed after bundle work. Regression returned HTTP 200, cache hit, 1,460 segments / 15,744 words; manual-caption control returned HTTP 200, cache hit, 61 segments / 366 words. Full suite returned 60 passed.
