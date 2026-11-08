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
it prints. The script then reads that plist. The printed program must be
the `Program` value, or the first `ProgramArguments` value, in the plist.
If they differ, the script stops before backup and apply. This procedure
does not guess `$ROOT/.venv/bin/python` or
`~/Library/LaunchAgents/com.epic.transcript-api.plist`.

Hermes runs the deploy script only when the service is not inside a
transcript write. The script checks `ROOT`, `ARTIFACT`, `DEST`, `HOME`,
the printed plist, and the printed interpreter. It does not prove the
service is idle, and it does not stop the job. A test double for
`launchctl` does not prove the Mac's print format. Hermes confirms the
printed `program` and `path` on the machine. This procedure does not
bootout or delete the job, and it does not delete WAL or SHM files. A WAL or SHM byte change
while SQLite is in use is runtime state. It does not roll the copied
source files back. A change to `transcripts.db`, the transcript files,
the two drift JSON files, or `.env` during the copy does roll those
source files back. It does not delete the live data. Do not start the
copy while a checkpoint is rewriting `transcripts.db`.

## Conditional offline transition

This route is prepared and not approved. Merlin has asked Trevor for
permission to interrupt an in-flight job. There is no such approval.
Nothing here is host clearance. The scripts do not run `launchctl bootout`
or `launchctl bootstrap`. A fixture does not prove the Mac's launchctl
output, that port 8090 is free on the host, or that every possible writer
descendant was found.

The running c943 process cannot be drained in place. Capture its identity
while `launchctl print` still succeeds. Do not bootout and then run
`scripts/screenshot_host_deploy.sh`: that script fail-closes when print
fails, and this packet does not weaken that check.

When approval exists, the operator stop is:

`launchctl bootout gui/501/com.epic.transcript-api`

That stops writers. It does not finish jobs. The old daemon threads are
gone and c943 has no resume. The offline script then requires the
pre-stop identity, a failed `launchctl print` for that label, a definite
refusal from `127.0.0.1` on port 8090, the recorded pid gone, and no
process left in the recorded process group. A same-group survivor is
detected. A descendant that called `setsid` leaves that group and is not
found. This is not proof that every process on the machine has stopped.
A timeout or any other socket error is not treated as a free port. The
check is IPv4 `127.0.0.1` only.

Across backup, verify, preflight, dry run, and apply, the script holds
`BEGIN IMMEDIATE` on `data/transcripts.db`. Another writer cannot commit
during that section. The backup uses a separate read-only connection, so
the reservation does not deadlock the snapshot. When the reservation
closes, SQLite can checkpoint a leftover WAL into `transcripts.db` and
remove the WAL and SHM files. The rows remain. That byte change is
SQLite, not the installer writing those files. The installer still does
not write `.env`, the transcript text files, or the two JSON files.
`protected_unchanged` does not mean the SHM bytes were identical.

A stale plist hash or a program that no longer matches the plist stops
the script before backup and apply. It records queued and running job
ids in `$HOME/screenshot-interrupted-jobs.json` and does not modify the
live `url_jobs.json`. If apply fails, the same run restores the known-good
source files from the apply receipt's backup when that backup exists,
then prints `RECOVERY=source-restored` or `RECOVERY=failed`. It does not
start the new code and it does not run bootstrap. There is no second
authorization step. Recovery does not restore or delete data, `.env`, or
the plist.

The operator restart, also not run by the script, uses the plist path
captured in the identity file. On this host that path was reported as
`/Users/tc-imac/Library/LaunchAgents/com.epic.transcript-api.plist`.
The script prints `BOOTSTRAP=not-run` and that captured path. It does
not hard-code the path, and it does not run the command:

`launchctl bootstrap gui/501 <captured-plist>`

On the next start the new process marks queued and running jobs
interrupted. A saved transcript is shown with the screenshot error and is
not downloaded again. A job with no saved transcript becomes an error.
That rewrite is process startup, not this copy. Errors print `RESTART=no`.
Success prints `APPLY=ok` and `RESTART=not-run`.

```bash
# fixture: capture-identity
exec "$ARTIFACT/scripts/screenshot_host_capture_identity.sh"
```

```bash
# fixture: offline-deploy
exec "$ARTIFACT/scripts/screenshot_host_offline_deploy.sh"
```

`screenshot_host_offline_deploy.sh` refuses to run unless
`SCREENSHOT_OFFLINE_AUTHORIZATION` is
`interruptible-offline-window-approved`. Setting that string is the
operator saying approval exists. This repository does not assert that it
does.

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

Set `ROOT`, `ARTIFACT`, `DEST`, and `HOME`. `ARTIFACT` is the unpacked
screenshot pack. The backup script and `scripts/screenshot_host_deploy.sh`
stay in that pack. They are not files the installer copies onto the host.
The deploy script is the sequence. A failed binding, plist, interpreter,
backup, hash listing, verify, preflight, or dry run exits before apply and
prints `RESTART=no`. Do not pipe the hash listing through `tee`.

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
exec "$ARTIFACT/scripts/screenshot_host_deploy.sh"
```

Hermes restarts `gui/501/com.epic.transcript-api` only after reading
`RESTART=allowed`. Any other line, a missing receipt, or a non-zero exit
means do not restart. The script does not enforce that idle state. The
first start after a successful copy may rewrite an interrupted job in
`data/url_jobs.json`. That is a runtime write. The installer does not
write `.env`, `transcripts.db`, the WAL, the SHM, the transcript files, or
the two drift JSON files. A WAL-only commit need not change the
`transcripts.db` bytes. The receipt field `protected_unchanged` compares
the stable files only. `transcripts.db-shm` can change while that field is
true. It is not a claim that every live data byte was identical.

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
exec "$ARTIFACT/scripts/screenshot_host_rollback.sh"
```

A failed rollback prints `RESTART=no` and does not grant a restart. A
successful rollback prints `ROLLBACK=ok` and `RESTART=no`. It never prints
`RESTART=allowed`. Do not point `$BACKUP` at `$DEST`. Do not start or stop
launchd from this command.
