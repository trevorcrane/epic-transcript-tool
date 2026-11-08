# Screenshot install for production commit c943233

Reviewed parent, and the diff baseline, is:

`c943233222a021e91903e01fb626918e55b43ccc`

GitHub PR #4 is opened against `main`. That base is
`28707a20b25d42ac52e38021cc1053ad42057ec2`, not `c943233`.
Do not merge PR #4 into `main`. A merge would be a different change from
the file copy described here. `main` does not auto-deploy.

The older packs `e20e5dc`, `06c57d7`, and `7246cbc` are not for this host.

This document is the install instruction. Commands below are for the host
owner to run on the iMac. Nothing in this repository run executed them, and
a passing test on another machine is not host proof.

## What the host owner reported

These versions were reported for the live service. They were not executed
while this pack was built:

- Python 3.14.3 at `/Users/tc-imac/.openclaw/workspace/epic-transcript-tool/.venv/bin/python`
- yt-dlp 2026.03.17
- ffmpeg 8.1.1

Use that virtualenv interpreter for the preflight and the copy. Do not
substitute a different `python3`.

The live job is launchd `gui/501/com.epic.transcript-api`. Find its plist
from that label and copy the plist as part of the backup below. This pack
does not edit or restart the job.

## Outside backup, before any copy

The installer does not make this backup. Its `backups/screenshots-<UTC>/`
folder only keeps the previous source files it replaces. It does not contain
`data/`, `.env`, or the launchd plist.

Put the backup outside the repository. One example location, which the owner
must choose and create, is a new directory under the home folder and not
inside the app tree:

```bash
ROOT=/Users/tc-imac/.openclaw/workspace/epic-transcript-tool
PY="$ROOT/.venv/bin/python"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST="$HOME/transcript-machine-backups/screenshots-$STAMP"
mkdir -p "$DEST"
cp -R "$ROOT/data" "$DEST/data"
cp "$ROOT/.env" "$DEST/.env"
# Copy the plist that belongs to gui/501/com.epic.transcript-api.
# The owner locates that file. A user agent often lives at
# $HOME/Library/LaunchAgents/com.epic.transcript-api.plist
cp "$HOME/Library/LaunchAgents/com.epic.transcript-api.plist" "$DEST/launchd.plist"
```

That `data` copy has to include `transcripts.db`, everything under
`data/transcripts/`, `data/url_jobs.json`, and
`data/phase3_gemini_usage.json`. Hash the backup with the service
interpreter, or with `shasum -a 256` on macOS. Keep the listing next to
the backup. `sha256sum` is not the command on this Mac.

```bash
"$PY" - "$DEST" <<'PY' | tee "$DEST/SHA256SUMS"
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
for path in sorted(p for p in root.rglob("*") if p.is_file() and not path.is_symlink()):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{digest}  {path.relative_to(root).as_posix()}")
PY
shasum -a 256 "$DEST/.env" "$DEST/launchd.plist" \
  "$DEST/data/transcripts.db" \
  "$DEST/data/url_jobs.json" \
  "$DEST/data/phase3_gemini_usage.json"
```

Stop if that backup is incomplete. Do not continue to `--apply`.

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
It refuses the copy, before writing, when an install path, `.env`, `data`,
or anything already under `data/` is a symlink. A symlink fingerprint is the
link text, not the target's bytes. The installer does not follow those links.

The manifest's `baseline` hashes are the `c943233` parent bytes. Its
`install` hashes are the files in this pack, excluding the manifest file
itself. `github_pr_base_commit` records the PR base and is not the parent.

## Preflight

```bash
ROOT=/Users/tc-imac/.openclaw/workspace/epic-transcript-tool
PY="$ROOT/.venv/bin/python"
"$PY" /path/to/artifact/scripts/screenshot_host_preflight.py \
  --root "$ROOT" \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json \
  --port 8090 \
  --out "$HOME/screenshot-preflight.json"
```

Exit 0 means `app.py`, `static/index.html`, `Dockerfile`, and `README.md`
match commit `c943233` and the protected paths are not symlinks. Exit 3
means stop. Dirty `data/url_jobs.json` or `data/phase3_gemini_usage.json`
is reported and is not a reason to overwrite them.

## Copy

Dry run (no `--apply`) does not install. Exit 0 on a dry run is not a
restart signal.

```bash
"$PY" /path/to/artifact/scripts/screenshot_host_apply.py \
  --root "$ROOT" \
  --source /path/to/artifact \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json \
  --out "$HOME/screenshot-apply.json"
```

Apply:

```bash
"$PY" /path/to/artifact/scripts/screenshot_host_apply.py \
  --root "$ROOT" \
  --source /path/to/artifact \
  --manifest /path/to/artifact/docs/screenshot-install-manifest.json \
  --apply \
  --out "$HOME/screenshot-apply.json"
echo "apply_exit=$?"
```

Restart `gui/501/com.epic.transcript-api` only when all three are true:

- the apply command's exit code is 0
- the JSON says `"ok": true`
- the JSON says `"wrote": true`

`"restart"` in that JSON stays false. The installer never restarts the
service. A non-zero exit means the source files it changed were restored.
Do not restart. Compare the outside backup hashes again before doing
anything else. The first start after a successful copy rewrites an
interrupted transcript job in `data/url_jobs.json` so the page can show
the saved transcript. That is a runtime write, not part of the file copy.
The copy itself leaves `data/` and `.env` byte for byte.

## Screenshot behavior on this tree

Transcript only is the current job. Transcript with screenshots runs after
the transcript. Only a rebuilt `https://www.youtube.com/watch?v=ID` is
passed to `yt-dlp --use-extractors youtube`. X, TikTok, Instagram, and
Facebook stay on the production refusal path. There is no new page-session
login.

If capture fails, or the process is stopped after the transcript was saved
and before capture finishes, the transcript stays and the page says
`Screenshots could not be captured.` The next process start does not
download the video again. The page stops polling after 150 attempts.

On timeout, yt-dlp and ffmpeg run in their own process group. The group
gets SIGTERM, then SIGKILL, one second apart. A same-group grandchild that
ignores SIGTERM is included. A descendant that calls `setsid` leaves the
group and is not searched for.

## Rollback

Use the outside backup for `data/`, `.env`, and the plist. For the source
files, after a zero-exit copy that also had `ok` and `wrote`, stop the same
launchd job and restore:

```bash
cp backups/screenshots-<UTC>/app.py app.py
cp backups/screenshots-<UTC>/static/index.html static/index.html
cp backups/screenshots-<UTC>/Dockerfile Dockerfile
cp backups/screenshots-<UTC>/README.md README.md
rm -f screenshots.py
```

Start the same launchd job again. Do not delete `data/`.
