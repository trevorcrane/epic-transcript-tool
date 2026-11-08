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

The live job label is `gui/501/com.epic.transcript-api`. The plist path is
whatever `launchctl print` reports for that label. Do not assume
`~/Library/LaunchAgents/com.epic.transcript-api.plist`. This pack does not
edit or restart the job.

## Outside backup, before any copy

The installer does not make this backup. Its `backups/screenshots-<UTC>/`
folder only keeps the previous source files it replaces. It does not contain
`data/`, `.env`, or the launchd configuration.

`cp -R data` while the service is running is not a consistent SQLite copy.
The live `transcripts.db-wal` and `transcripts.db-shm` belong to the open
database. Copying them next to a separate snapshot, or restoring them later
on top of that snapshot, mixes two states. The command below uses the
service interpreter's `sqlite3` backup API to write one `transcripts.db`.
It does not copy the live WAL or SHM. It does not modify the live database,
the transcript files, `data/url_jobs.json`, or `data/phase3_gemini_usage.json`.

Those JSON files and the transcript files are byte copies of what was read.
The live `transcripts.db` and `transcripts.db-wal` are not rewritten. SQLite
can update the `transcripts.db-shm` reader mark while the snapshot is taken.
That mark is not copied, and it is not an installer write. A later process
start may rewrite `data/url_jobs.json` when it settles an interrupted job.
That rewrite is a runtime write by the app. The installer does not write
`data/` or `.env`.

Set `ARTIFACT` to the unpacked screenshot pack. The backup script stays in
that pack. It is not one of the files the installer copies onto the host.
`set -o pipefail` is required because discovering the plist is a pipeline.
The script writes `SHA256SUMS` only after every listed file hashes again.
A failure leaves no hash listing. Do not pipe this through `tee`.

```bash
# fixture: outside-backup
set -euo pipefail
ROOT="${ROOT:-/Users/tc-imac/.openclaw/workspace/epic-transcript-tool}"
PY="${PY:-$ROOT/.venv/bin/python}"
ARTIFACT="${ARTIFACT:?set ARTIFACT to the unpacked screenshot pack}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST="${DEST:-$HOME/transcript-machine-backups/screenshots-$STAMP}"
LABEL="${LAUNCHD_LABEL:-gui/501/com.epic.transcript-api}"
mkdir -p "$(dirname "$DEST")"
PLIST=$(launchctl print "$LABEL" | "$PY" -c 'import sys
path = ""
for line in sys.stdin:
    stripped = line.strip()
    if stripped.startswith("path ="):
        path = stripped.split("=", 1)[1].strip().strip("\"")
        break
if not path:
    raise SystemExit("launchctl print did not report a path")
print(path)')
test -n "$PLIST"
test -f "$PLIST"
"$PY" "$ARTIFACT/scripts/screenshot_outside_backup.py" --root "$ROOT" --dest "$DEST" --plist "$PLIST"
test -s "$DEST/SHA256SUMS"
"$PY" "$ARTIFACT/scripts/screenshot_outside_backup.py" --verify "$DEST"
```

Stop if that command's exit code is not 0, if `SHA256SUMS` is missing or
empty, or if `--verify` fails. Do not continue to `--apply`. On macOS,
`shasum -a 256` can hash one file by hand. It is not a substitute for the
verified listing above. `sha256sum` is not the command on this Mac.

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

Dry run and apply write different receipt files. Do not reuse one `--out`
path for both. A dry run can exit 0 with `"wrote": false`. That receipt
must still be there after the apply receipt is written.

```bash
# fixture: apply-dry-run
set -euo pipefail
ROOT="${ROOT:-/Users/tc-imac/.openclaw/workspace/epic-transcript-tool}"
PY="${PY:-$ROOT/.venv/bin/python}"
ARTIFACT="${ARTIFACT:?set ARTIFACT to the unpacked screenshot pack}"
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --out "$HOME/screenshot-apply-dry-run.json"
```

Apply:

```bash
# fixture: apply
set -euo pipefail
ROOT="${ROOT:-/Users/tc-imac/.openclaw/workspace/epic-transcript-tool}"
PY="${PY:-$ROOT/.venv/bin/python}"
ARTIFACT="${ARTIFACT:?set ARTIFACT to the unpacked screenshot pack}"
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --apply \
  --out "$HOME/screenshot-apply.json"
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

Stop the service before restoring the database. Copy the single snapshot
`transcripts.db` into place and remove any live WAL and SHM first. Do not
copy a WAL or SHM from the live tree onto that snapshot.

```bash
# fixture: restore-database
set -euo pipefail
# The service must already be stopped. This command does not stop launchd.
rm -f "$ROOT/data/transcripts.db-wal" "$ROOT/data/transcripts.db-shm"
cp "$DEST/data/transcripts.db" "$ROOT/data/transcripts.db"
test ! -e "$ROOT/data/transcripts.db-wal"
test ! -e "$ROOT/data/transcripts.db-shm"
cp "$DEST/.env" "$ROOT/.env"
cp "$DEST/data/url_jobs.json" "$ROOT/data/url_jobs.json"
cp "$DEST/data/phase3_gemini_usage.json" "$ROOT/data/phase3_gemini_usage.json"
rm -rf "$ROOT/data/transcripts"
cp -R "$DEST/data/transcripts" "$ROOT/data/transcripts"
```

The launchd file in the backup is the one `launchctl print` named, saved as
`launchd.plist`. Put it back only at that same discovered path, and only
after the service is stopped. For the source files, after a zero-exit copy
that also had `ok` and `wrote`, restore:

```bash
cp backups/screenshots-<UTC>/app.py app.py
cp backups/screenshots-<UTC>/static/index.html static/index.html
cp backups/screenshots-<UTC>/Dockerfile Dockerfile
cp backups/screenshots-<UTC>/README.md README.md
rm -f screenshots.py
```

Start the same launchd job again. Do not delete `data/`.
