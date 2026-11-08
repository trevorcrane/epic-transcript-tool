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
during that section, including while `copy2` is replacing source files.
The backup uses a separate read-only connection, so the reservation does
not deadlock the snapshot. When the reservation closes, SQLite can
checkpoint a leftover WAL into `transcripts.db` and remove the WAL and
SHM files. The rows remain. That byte change is SQLite, not the installer
writing those files. The installer still does not write `.env`, the
transcript text files, or the two JSON files. `protected_unchanged` does
not mean the SHM bytes were identical. The script does not call launchctl.

Each run gets its own directory under `$HOME`, created with an exclusive
`mkdir`. The name includes the process id and random bytes. `date +%s%N`
is not used, because on BSD that format can print a literal N and a second
run would reopen the same folder. A folder that already exists is not reused.

Before the first source file is replaced, apply writes an intent into that
directory and flushes it. The intent names this run, this root, the manifest,
and one backup directory. That backup is the tree captured before the copy,
checked against the c943 baseline, and marked with this run's id. If the
apply process is killed after that point, there may be no `apply.json` and
the tree may be only partly replaced. Recovery still uses this intent. It
prints `RECOVERY=source-restored` only after every rollback path is the
c943 baseline again. Otherwise it prints `RECOVERY=failed`. It does not
print `RECOVERY=not-needed` once an intent or a receipt exists.
`RECOVERY=not-needed` is only a failure from before any replacement started.

The nine rollback paths are `app.py`, `static/index.html`, `Dockerfile`,
`README.md`, `screenshots.py`, `docs/SCREENSHOT_DEPLOY.md`,
`docs/screenshot-install-manifest.json`, `scripts/screenshot_host_preflight.py`,
and `scripts/screenshot_host_apply.py`. The first four must match the
manifest hashes. The other five must be absent. The manifest file is one of
those five even though the manifest does not hash itself. A backup is
eligible only when its resolved path stays inside this tree's `backups/`
directory with no symlink component and no `..` escape, its directory name
is `screenshots-<this run id>`, and its transaction file is this run. A
string prefix is not enough. Another directory of valid c943 bytes is not
this run's backup. Recovery does not read `$HOME/screenshot-apply.json`.

`SCREENSHOT_APPLY_CRASH_AT`, `SCREENSHOT_APPLY_COPY_PAUSE_SECONDS`, and
`SCREENSHOT_APPLY_TEST_HARNESS` are not operator controls. If any of them
is set, the script stops before backup and apply. It does not sleep and it
does not take the crash path. An isolated test may set the harness itself.
The pause, when that harness is on, cannot be longer than one second.

A stale plist hash or a program that no longer matches the plist stops
the script before backup and apply. It records queued and running job
ids in `$HOME/screenshot-interrupted-jobs.json` and does not modify the
live `url_jobs.json`. The script does not start the new code and it does
not run bootstrap. There is no second authorization step. Recovery does
not restore or delete data, `.env`, or the plist.

The scripts do not run launchctl. `BOOTSTRAP=not-run` plus the captured
plist path means this process did not start the service. `RESTART` is
only the permission for a person to do that later. `RESTART=not-run` is
not a receipt and is not printed.

`RESTART=allowed` is printed only with one of these, after the captured
identity is valid and this process did not start launchctl:
`INSTALL=verified-new` after `APPLY=ok`, `INSTALL=verified-c943` after
`RECOVERY=source-restored`, or `INSTALL=verified-untouched-c943` when no
replacement started and all nine c943 paths still match. `INSTALL=unverified`
is a tree that was checked and is not one of those. It is `RESTART=not-allowed`.
A drifted file and a clean tree are not the same result. Do not start the
service on `INSTALL=unverified`. A killed apply can exit 137 and still print
`RESTART=allowed` when the nine c943 paths were verified. The exit code
is not the permission.

`INSTALL` is omitted when the script stops before that classification.
Authorization, hook rejection, missing bindings, a bad identity, a service
that is still loaded, a busy port, and a live process are in that group.
They print `RESTART=not-allowed` and `BOOTSTRAP=not-run`. They do not print
`INSTALL=unchanged`.

The plist on that `BOOTSTRAP=not-run` line is the one captured in the
identity file. On this host that path was reported as
`/Users/tc-imac/Library/LaunchAgents/com.epic.transcript-api.plist`.
It is not hard-coded. Before using it, the file's sha256 must still equal
`plist_sha256` in the identity file. The manual command, which no script
runs, is:

`launchctl bootstrap gui/501 <plist>`

`AUTHORIZATION=original-window` means the script saw
`SCREENSHOT_OFFLINE_AUTHORIZATION=interruptible-offline-window-approved`.
That is the same original window string. It is not a second approval.

If the operator process group is killed after the first replacement, the
intent and the c943 backup remain in that run directory and the source
tree can be mixed. The next offline copy starts a new run, does not read
the old intent, and can print `RECOVERY=failed`. That refusal is not a
restore. The explicit command names the old directory:

```bash
# fixture: offline-recover
exec "$ARTIFACT/scripts/screenshot_host_offline_recover.sh"
```

Set `RUN_DIR` to that one directory, for example
`$HOME/screenshot-run-<id>`. The script does not search `$HOME` and does
not read `$HOME/screenshot-apply.json`. It checks the named intent's root,
manifest hash, confined backup, and transaction id, restores from that
backup only, then requires all nine baseline paths. Invalid evidence
prints `RECOVERY=failed` and `RESTART=not-allowed`.

A failure before any intent exists, such as the outside backup refusing
a destination, has nothing for that named-run restore to use. If the live
tree is still the nine-path c943 baseline, the same offline copy prints
`INSTALL=verified-untouched-c943` and `RESTART=allowed`. If any of those
nine paths differs, including a drifted `README.md` or a mixed `app.py`,
it prints `INSTALL=unverified` and `RESTART=not-allowed` and does not
roll anything back. The same check can be repeated without naming a run
and without restoring:

```bash
SCREENSHOT_RECOVER_UNTOUCHED=1 \
SCREENSHOT_OFFLINE_AUTHORIZATION=interruptible-offline-window-approved \
ROOT=<live tree> ARTIFACT=<pack> HOME=<home> \
"$ARTIFACT/scripts/screenshot_host_offline_recover.sh"
```

Leave `RUN_DIR` unset for that command. Setting both is refused. The
builtin runtime gate on either recover path is the sha256 of `.env`,
`data/url_jobs.json`, and `data/transcripts.db` around the check. It does
not hash `transcripts.db-wal`, `transcripts.db-shm`, transcript text, or
`phase3_gemini_usage.json`. A SQLite checkpoint can change the WAL and
SHM without those three files being restored or deleted.

On the next start the new process marks queued and running jobs
interrupted. A saved transcript is shown with the screenshot error and is
not downloaded again. A job with no saved transcript becomes an error.
That rewrite is process startup, not this copy.

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

The installer does not make this backup. Its `backups/screenshots-<run>/`
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

`scripts/screenshot_host_apply.py` is copied onto the host so its bytes
can be checked. Do not run that ROOT copy. It imports
`screenshot_host_offline_checks.py`, and that helper stays in the pack.
The supported command is `$ARTIFACT/scripts/screenshot_host_apply.py`.

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

`screenshot_host_deploy.sh` prints `RESTART=allowed` when apply exits 0
and the receipt has ok true and wrote true. Otherwise it prints
`RESTART=no`. It does not run launchctl. That script is the path used
while `launchctl print` still succeeds. The offline copy and
`screenshot_host_offline_recover.sh` use `RESTART=allowed` or
`RESTART=not-allowed` together with `INSTALL=` and `BOOTSTRAP=not-run`,
as written above. Do not treat `RESTART=no` and `RESTART=not-allowed` as
the same line, and do not wait for `RESTART=not-run`. The script does not
enforce that idle state. The
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
`$BACKUP` is the backup directory named by the verified intent, or the
`backup` path in an apply receipt from the same run. `ARTIFACT` is
required. `PY`, when it is set and executable, is the captured service
program. When `PY` is unset, the script uses `python3` on `PATH` for the
stdlib confinement check.

```bash
# fixture: rollback-code
exec "$ARTIFACT/scripts/screenshot_host_rollback.sh"
```

A failed rollback prints `RESTART=no` and does not grant a restart. A
successful rollback prints `ROLLBACK=ok` and `RESTART=no`. It never prints
`RESTART=allowed`. Rollback alone is not the verified-c943 permission.
That permission is `screenshot_host_offline_recover.sh` after the nine
paths match. Do not point `$BACKUP` at `$DEST`. Do not start or stop
launchd from this command.
