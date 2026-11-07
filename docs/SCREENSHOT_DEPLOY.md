# Screenshot install for production commit c943233

This pack applies only to the existing Transcript Machine at:

`c943233222a021e91903e01fb626918e55b43ccc`

Do not install the older pack built from `28707a2` or commit `7246cbc`.
That pack is a different tree. `main` does not auto-deploy. Do not merge to ship.

The live process is launchd `gui/501/com.epic.transcript-api`. This repository
change does not start, stop, or edit that job. A person on the iMac restarts
that same job only after `--apply` exits 0.

Tracked files that already differ on the host, and must stay byte-for-byte
unless the running app itself writes them later, are:

- `data/phase3_gemini_usage.json`
- `data/url_jobs.json`
- `.env`
- `data/transcripts.db`
- everything under `data/transcripts/`

The installer hashes those paths before and after. A mismatch rolls the copy
back. It does not restart.

## Files this installer may write

- `app.py`
- `static/index.html`
- `screenshots.py` (new)
- `Dockerfile`
- `README.md`
- `docs/SCREENSHOT_DEPLOY.md`
- `docs/screenshot-install-manifest.json`
- `scripts/screenshot_host_preflight.py`
- `scripts/screenshot_host_apply.py`

It may append `data/screenshots/` and `backups/` to a regular `.gitignore`.
A symlink on any of those paths, including `static/`, `backups/`, and
`.gitignore`, stops the copy before any write.

## Preflight

Record the running command first. Do not stop it yet.

```bash
python3 /path/to/artifact/scripts/screenshot_host_preflight.py \
  --root /path/to/the/existing/epic-transcript-tool \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json \
  --port 8090 \
  --out /tmp/screenshot-preflight.json
```

Exit 0 means `app.py`, `static/index.html`, `Dockerfile`, and `README.md` match
commit `c943233`. Exit 3 means stop. Dirty `data/url_jobs.json` or
`data/phase3_gemini_usage.json` is reported and not a reason to overwrite them.

## Copy

```bash
python3 /path/to/artifact/scripts/screenshot_host_apply.py \
  --root /path/to/the/existing/epic-transcript-tool \
  --source /path/to/artifact \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json \
  --apply \
  --out /tmp/screenshot-apply.json
```

Restart the existing launchd job only when that command prints `"ok": true`
and `"wrote": true`. A non-zero exit already restored the files it changed.
Do not restart.

## Screenshot behavior on this tree

Transcript only is the current job. Transcript with screenshots runs after the
transcript. Only a rebuilt `https://www.youtube.com/watch?v=ID` is passed to
`yt-dlp --use-extractors youtube`. X, TikTok, Instagram, and Facebook stay on
the production refusal path. There is no new page-session login.

On timeout, yt-dlp and ffmpeg run in their own process group. The group gets
SIGTERM, then SIGKILL, one second apart. A same-group grandchild that ignores
SIGTERM is included. A descendant that calls `setsid` leaves the group and is
not searched for.

## Rollback

After a zero-exit copy and a restart, stop the same launchd job and restore:

```bash
cp backups/screenshots-<UTC>/app.py app.py
cp backups/screenshots-<UTC>/static/index.html static/index.html
cp backups/screenshots-<UTC>/Dockerfile Dockerfile
cp backups/screenshots-<UTC>/README.md README.md
rm -f screenshots.py
```

Start the same launchd job again. Do not delete `data/`.
