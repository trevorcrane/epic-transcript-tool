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

## What Hermes verifies

These versions were reported for the live service. They were not executed
while this pack was built, and this procedure does not assume them:

- Python 3.14.3
- yt-dlp 2026.03.17
- ffmpeg 8.1.1

The live job label is `gui/501/com.epic.transcript-api`. Hermes reads
`launchctl print` for that label and uses the `program` and `path` lines
it prints. Those are the service interpreter and the service plist. This
procedure does not guess `$ROOT/.venv/bin/python` or
`~/Library/LaunchAgents/com.epic.transcript-api.plist`.

Hermes also confirms the service is not inside a transcript write before
the copy. This procedure does not stop, start, bootout, or delete that
job, and it does not delete WAL or SHM files. A WAL or SHM byte change
while SQLite is in use is runtime state. It does not roll the copied
source files back. A change to `transcripts.db`, the transcript files,
the two drift JSON files, or `.env` during the copy does roll those
source files back. It does not delete the live data. Do not start the
copy while a checkpoint is rewriting `transcripts.db`.

## Outside backup, before any copy

The installer does not make this backup. Its `backups/screenshots-<UTC>/`
folder only keeps the previous source files it replaces. It does not
contain `data/`, `.env`, or the launchd configuration.

The outside copy is insurance. It is not permission to restore or delete
live data. Nothing in the operator procedure copies `$DEST` back onto
`$ROOT`.

`cp -R data` while the service is running is not a consistent SQLite copy.
The command below uses the discovered interpreter's `sqlite3` backup API
to write one `transcripts.db` under `$DEST`. It does not copy the live WAL
or SHM next to that snapshot. It does not modify the live database file,
the WAL, the transcript files, `data/url_jobs.json`, or
`data/phase3_gemini_usage.json`. SQLite can update the
`transcripts.db-shm` reader mark while the snapshot is read. That mark is
not copied.

A later process start may rewrite `data/url_jobs.json` when it settles an
interrupted job. That is a runtime write by the app. The installer does
not write `data/` or `.env`.

Set `ROOT`, `ARTIFACT`, `DEST`, and `HOME` before the sequence. `ARTIFACT`
is the unpacked screenshot pack. The backup script stays in that pack. It
is not one of the files the installer copies onto the host. The sequence
does not use `set -e`, so a failed command still records `RESTART=no`
and leaves the receipt it already wrote. Do not pipe the hash listing
through `tee`.

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

## Deploy sequence

Dry run and apply write different receipts. A dry run can exit 0 with
`"wrote": false`. That is not a restart. Restart is allowed only when the
apply command exits 0 and its receipt has `"ok": true` and `"wrote": true`.
The receipt's own `"restart"` value stays false. The installer never
restarts the service.

```bash
# fixture: deploy-sequence
set -u
set -o pipefail
: "${ROOT:?}"
: "${ARTIFACT:?}"
: "${DEST:?}"
: "${HOME:?}"
LABEL="${LAUNCHD_LABEL:-gui/501/com.epic.transcript-api}"
discovered=$(launchctl print "$LABEL") || { echo "RESTART=no"; exit 1; }
PLIST=$(printf '%s\n' "$discovered" | sed -n 's/^[[:space:]]*path = //p' | head -n 1)
PY=$(printf '%s\n' "$discovered" | sed -n 's/^[[:space:]]*program = //p' | head -n 1)
test -n "$PLIST"
test -f "$PLIST"
test -n "$PY"
test -x "$PY"
mkdir -p "$(dirname "$DEST")"
"$PY" "$ARTIFACT/scripts/screenshot_outside_backup.py" --root "$ROOT" --dest "$DEST" --plist "$PLIST"
test -s "$DEST/SHA256SUMS"
"$PY" "$ARTIFACT/scripts/screenshot_outside_backup.py" --verify "$DEST"
preflight_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_preflight.py" \
  --root "$ROOT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --port 8090 \
  --out "$HOME/screenshot-preflight.json" || preflight_exit=$?
if [ "$preflight_exit" -ne 0 ]; then echo "RESTART=no"; exit "$preflight_exit"; fi
dry_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --out "$HOME/screenshot-apply-dry-run.json" || dry_exit=$?
if [ "$dry_exit" -ne 0 ]; then echo "RESTART=no"; exit "$dry_exit"; fi
apply_exit=0
"$PY" "$ARTIFACT/scripts/screenshot_host_apply.py" \
  --root "$ROOT" \
  --source "$ARTIFACT" \
  --manifest "$ARTIFACT/docs/screenshot-install-manifest.json" \
  --apply \
  --out "$HOME/screenshot-apply.json" || apply_exit=$?
ok=no
wrote=no
if [ -s "$HOME/screenshot-apply.json" ]; then
  read -r ok wrote < <("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("yes" if d.get("ok") is True else "no", "yes" if d.get("wrote") is True else "no")' "$HOME/screenshot-apply.json")
fi
if [ "$apply_exit" -eq 0 ] && [ "$ok" = "yes" ] && [ "$wrote" = "yes" ]; then
  echo "RESTART=allowed"
else
  echo "RESTART=no"
fi
exit "$apply_exit"
```

Hermes restarts `gui/501/com.epic.transcript-api` only after reading
`RESTART=allowed`. Any other line, a missing receipt, or a non-zero exit
means do not restart. The first start after a successful copy may rewrite
an interrupted job in `data/url_jobs.json`. That is a runtime write. The
copy itself leaves `data/` and `.env` byte for byte, aside from the SQLite
reader mark noted above.

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

Rollback restores the source files the installer replaced. It does not
restore `$DEST`, and it does not delete or replace live data, `.env`, the
WAL, the SHM, transcript files, the drift JSON files, or the plist.
`$BACKUP` is the `backup` path in the apply receipt.

```bash
# fixture: rollback-code
set -eu
set -o pipefail
: "${ROOT:?}"
: "${BACKUP:?}"
while IFS= read -r rel; do
  if [ -f "$BACKUP/$rel" ]; then
    mkdir -p "$ROOT/$(dirname "$rel")"
    cp "$BACKUP/$rel" "$ROOT/$rel"
  else
    rm -f "$ROOT/$rel"
  fi
done <<'FILES'
app.py
static/index.html
Dockerfile
README.md
screenshots.py
docs/SCREENSHOT_DEPLOY.md
docs/screenshot-install-manifest.json
scripts/screenshot_host_preflight.py
scripts/screenshot_host_apply.py
FILES
```

Do not point `$BACKUP` at `$DEST`. Do not start or stop launchd from this
command.
