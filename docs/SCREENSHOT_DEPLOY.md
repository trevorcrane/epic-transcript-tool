# Screenshot install for the existing iMac Transcript Machine

This change is not deployed from the git branch. `main` does not auto-deploy.
Do not merge this PR to ship it, and do not point a new domain, tunnel, or
worker at it. The live path stays:

- folder on TCss-iMac.local (the existing app directory, port 8090)
- `python app.py`
- cloudflared to `https://epic-transcript.robyncrane.com`
- worker `epic-transcribe-domain-proxy` to `https://epicmachines.ai/transcribe`

Do not change `cloudflared.yml`, `.env`, `requirements.txt`, `data/transcripts.db`,
or `data/url_jobs.json`. No new Python package is required. `ffmpeg` and `yt-dlp`
are the same binaries the transcript path already uses.

The reviewed parent tree is `28707a2` (`Merge PR #1`). If the iMac copies of
`app.py`, `static/index.html`, `Dockerfile`, or `README.md` are not those bytes,
stop. Host-specific edits must be reviewed before anything is replaced.

## 1. Record the running process

On the iMac, from the production folder:

```bash
ps aux | grep '[a]pp.py'
lsof -nP -iTCP:8090 -sTCP:LISTEN
python3 --version
```

Save the pid, the full command, and the working directory. The restart later
has to use that same command. Do not stop the process yet.

## 2. Preflight (read only)

Unpack the artifact somewhere else, not on top of the app folder. Then:

```bash
python3 /path/to/artifact/scripts/screenshot_host_preflight.py \
  --root /path/to/the/existing/epic-transcript-tool \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json \
  --port 8090 \
  --out /tmp/screenshot-preflight.json
echo "preflight exit $?"
```

Exit 0: every file that would be replaced matches the reviewed baseline, or it
is already the reviewed new file. Exit 3: stop. Send `/tmp/screenshot-preflight.json`
back. Do not copy files over a drift result.

The report lists git HEAD, a dirty-file list, and the port 8090 command. Dirty
files outside the install list are left alone. A dirty `app.py` or
`static/index.html` whose bytes are not the baseline hash blocks the install.

## 3. Backup and copy

This still does not restart the app.

```bash
python3 /path/to/artifact/scripts/screenshot_host_apply.py \
  --root /path/to/the/existing/epic-transcript-tool \
  --source /path/to/artifact \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json
```

Read the plan. If it is right:

```bash
python3 /path/to/artifact/scripts/screenshot_host_apply.py \
  --root /path/to/the/existing/epic-transcript-tool \
  --source /path/to/artifact \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json \
  --apply \
  --out /tmp/screenshot-apply.json
```

`--apply` copies only:

- `app.py`
- `screenshots.py` (new)
- `static/index.html`
- `Dockerfile`
- `README.md`
- `docs/SCREENSHOT_DEPLOY.md`
- `docs/screenshot-install-manifest.json`
- `scripts/screenshot_host_preflight.py`
- `scripts/screenshot_host_apply.py`

It writes the previous bytes to `backups/screenshots-<UTC>/` inside the app
folder. It appends `data/screenshots/` and `backups/` to `.gitignore` only when
those lines are absent and `.gitignore` is a regular file. It does not delete
transcripts, `.env`, or the database.

The installer refuses the copy, before it creates or writes anything, if a
file it would write is a symlink or sits under a symlink. That includes
`app.py`, `static/`, `backups/`, and `.gitignore`. A refused copy leaves the
tree as it was.

If a copy fails part way through, the installer puts the files it changed back
to the bytes from before the copy and exits non-zero. Do not restart after a
non-zero installer exit. The process recorded in step 1 is still the one to
keep.

## 4. Restart, only after a zero exit

Restart only when `--apply` printed `"ok": true` and `"wrote": true`. A
non-zero exit means do not restart.

Stop the pid recorded in step 1. Wait until nothing is listening on 8090.
Start the app with the same command and the same virtualenv as before, from
the same folder. Then:

```bash
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1:8090/ | grep -E 'Transcript only|Transcript with screenshots'
```

The public page should show both buttons. Transcript only must still return a
transcript with no gallery. Transcript with screenshots must show timestamped
frames, Copy image, Copy transcript, and Download ZIP. If the screenshot step
fails, the transcript stays on screen and the page says screenshots could not
be captured. That is not a successful screenshot run.

Screenshot files are served only to the same page session or API token that
created the job. The page session is kept in memory, so a reload mints a new
session and the gallery is gone; the transcript text remains. Files are removed
after `SCREENSHOT_RETENTION_HOURS` (24).

Screenshot download is not a general file fetch. A YouTube link is reduced to
`https://www.youtube.com/watch?v=` plus the 11-character video id before any
DNS lookup or `yt-dlp` call. The command uses `--use-extractors youtube`.
Visitor hosts, credentials, open-redirect paths, and extra query parameters
are not passed through. A non-YouTube link still returns its transcript; the
screenshot step stops with `Screenshots could not be captured.` and does not
download that URL. Downloads are capped at 800 MB and 2 hours
(`SCREENSHOT_MAX_DOWNLOAD_MB`, `SCREENSHOT_MAX_SECONDS`). One screenshot
capture runs at a time. A capture that fails, including a busy slot, keeps the
transcript and does not report the screenshots as ready.

## Rollback

Use this only after a copy that exited zero and a restart. A failed copy has
already put the replaced files back; do not restart, and do not delete the
database.

Stop the new pid the same way. Restore the backup over the files that were
replaced, and remove `screenshots.py` if the backup does not contain it:

```bash
cd /path/to/the/existing/epic-transcript-tool
cp backups/screenshots-<UTC>/app.py app.py
cp backups/screenshots-<UTC>/static/index.html static/index.html
cp backups/screenshots-<UTC>/Dockerfile Dockerfile
cp backups/screenshots-<UTC>/README.md README.md
rm -f screenshots.py
```

Start the original command again. Confirm the page shows the previous button
and `/health` returns ok. Do not delete `data/transcripts.db`.

## What this agent did not do

No production restart, no Cloudflare change, no merge, and no message to Hermes.
Public runtime review still has to happen on the live URL after the iMac restart.
