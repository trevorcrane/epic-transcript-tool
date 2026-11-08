"""Run the documented deploy sequence on an isolated tree. Not a host install."""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "SCREENSHOT_DEPLOY.md"
PARENT = "c943233222a021e91903e01fb626918e55b43ccc"
BASELINE_FILES = ("app.py", "static/index.html", "Dockerfile", "README.md")


def _fence(name: str) -> str:
    text = DOC.read_text(encoding="utf-8")
    marker = f"# fixture: {name}\n"
    start = text.index(marker)
    end = text.index("```", start)
    return text[start:end]


def _run(name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(["bash", "-c", _fence(name)], env=merged, text=True, capture_output=True, check=False)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _live_data(root: Path) -> sqlite3.Connection:
    data = root / "data"
    (data / "transcripts").mkdir(parents=True)
    (data / "transcripts" / "kept.txt").write_text("existing transcript text\n", encoding="utf-8")
    (data / "url_jobs.json").write_text('{"drift":"url-jobs"}\n', encoding="utf-8")
    (data / "phase3_gemini_usage.json").write_text('{"drift":"gemini"}\n', encoding="utf-8")
    (root / ".env").write_text("SECRET=keep\n", encoding="utf-8")
    db = data / "transcripts.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE transcripts (id TEXT PRIMARY KEY, transcript TEXT NOT NULL)")
    conn.execute("INSERT INTO transcripts VALUES ('1', 'already-in-main')")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("INSERT INTO transcripts VALUES ('2', 'only-in-wal')")
    conn.commit()
    return conn


def _venv_interpreter() -> Path:
    exe = Path(sys.executable)
    if not (exe.parent.parent / "pyvenv.cfg").is_file():
        raise AssertionError(f"{exe} is not a venv interpreter")
    return exe


def _write_plist(path: Path, python: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(
            {
                "Label": "com.epic.transcript-api",
                "ProgramArguments": [str(python), str(python.parent.parent / "app.py")],
            },
            handle,
        )


def _service_bin(tmp: Path, plist: Path, python: Path | None = None) -> Path:
    bindir = tmp / "bin"
    bindir.mkdir()
    interpreter = python or _venv_interpreter()
    _write_plist(plist, interpreter)
    launchctl = bindir / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FIXTURE_LAUNCHCTL_LOG\"\n"
        "if [ \"$1\" = \"print\" ] && [ \"$2\" = \"gui/501/com.epic.transcript-api\" ]; then\n"
        "  printf '\\tpath = %s\\n\\tprogram = %s\\n' \"$FIXTURE_PLIST_PATH\" \"$FIXTURE_PYTHON\"\n"
        "  exit 0\n"
        "fi\n"
        "echo \"launchctl refused $*\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)
    (tmp / "launchctl.log").write_text("", encoding="utf-8")
    return bindir


def _env(tmp: Path, live: Path, dest: Path, plist: Path) -> dict[str, str]:
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    return {
        "ROOT": str(live),
        "ARTIFACT": str(ROOT),
        "DEST": str(dest),
        "HOME": str(home),
        "PATH": str(tmp / "bin") + os.pathsep + os.environ["PATH"],
        "FIXTURE_PLIST_PATH": str(plist),
        "FIXTURE_PYTHON": str(_venv_interpreter()),
        "FIXTURE_LAUNCHCTL_LOG": str(tmp / "launchctl.log"),
    }


def _baseline_tree(live: Path) -> None:
    for rel in BASELINE_FILES:
        target = live / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", f"{PARENT}:{rel}"], cwd=ROOT))


def test_deploy_sequence_succeeds_and_code_rollback_keeps_newer_data(tmp_path):
    doc = DOC.read_text(encoding="utf-8")
    commands = _fence("deploy-sequence") + _fence("rollback-code")
    script = (ROOT / "scripts" / "screenshot_host_deploy.sh").read_text(encoding="utf-8")
    assert "restore-database" not in doc
    assert "rm -rf \"$ROOT/data" not in doc
    assert "/path/to/artifact" not in doc
    assert "bootout" not in commands and "bootout" not in script
    assert "kickstart" not in commands and "kickstart" not in script
    assert "launchctl print" in script
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    holder = _live_data(live)
    plist = tmp_path / "service-config" / "printed-by-launchctl.plist"
    plist.parent.mkdir()
    _service_bin(tmp_path, plist)
    dest = tmp_path / "outside" / "backup"
    unchanged = (
        ".env",
        "data/transcripts.db",
        "data/transcripts.db-wal",
        "data/url_jobs.json",
        "data/phase3_gemini_usage.json",
        "data/transcripts/kept.txt",
    )
    before = {rel: _sha(live / rel) for rel in unchanged}
    raw_only = tmp_path / "raw-main-only.db"
    raw_only.write_bytes((live / "data" / "transcripts.db").read_bytes())
    raw = sqlite3.connect(f"file:{raw_only}?mode=ro", uri=True)
    assert "only-in-wal" not in [row[0] for row in raw.execute("SELECT transcript FROM transcripts")]
    raw.close()

    proc = _run("deploy-sequence", _env(tmp_path, live, dest, plist))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "RESTART=allowed" in proc.stdout
    assert "RESTART=no" not in proc.stdout
    listing = (dest / "SHA256SUMS").read_text(encoding="utf-8")
    assert listing.strip()
    assert "data/transcripts.db-wal" not in listing
    solo = tmp_path / "opened-snapshot.db"
    solo.write_bytes((dest / "data" / "transcripts.db").read_bytes())
    snap = sqlite3.connect(f"file:{solo}?mode=ro", uri=True)
    assert [row[0] for row in snap.execute("SELECT transcript FROM transcripts ORDER BY id")] == ["already-in-main", "only-in-wal"]
    snap.close()
    assert (dest / "launchd.plist").read_bytes() == plist.read_bytes()
    assert "Library/LaunchAgents" not in str(plist)
    for rel, digest in before.items():
        assert _sha(live / rel) == digest
    assert (live / "screenshots.py").is_file()
    home = tmp_path / "home"
    preflight = json.loads((home / "screenshot-preflight.json").read_text(encoding="utf-8"))
    dry = json.loads((home / "screenshot-apply-dry-run.json").read_text(encoding="utf-8"))
    applied = json.loads((home / "screenshot-apply.json").read_text(encoding="utf-8"))
    assert preflight["ok"] is True
    assert dry["wrote"] is False and dry["restart"] is False
    assert applied["ok"] is True and applied["wrote"] is True and applied["restart"] is False
    trace = (home / "screenshot-deploy-trace").read_text(encoding="utf-8").splitlines()
    assert "backup-exit=0" in trace and "verify-exit=0" in trace and "apply" in trace
    assert applied["protected_unchanged"] is True
    assert "data/transcripts.db-wal" in applied["volatile_runtime_not_a_rollback_trigger"]
    assert "data/transcripts.db-shm" in applied["volatile_runtime_not_a_rollback_trigger"]
    interpreter = _venv_interpreter()
    assert "interpreter=" + str(interpreter) in trace
    assert str(interpreter) != "/usr/bin/python3"
    with plist.open("rb") as handle:
        configured = plistlib.load(handle)["ProgramArguments"][0]
    assert configured == str(interpreter)
    launch_log = (tmp_path / "launchctl.log").read_text(encoding="utf-8")
    assert launch_log.splitlines() == ["print gui/501/com.epic.transcript-api"]

    (live / "data" / "url_jobs.json").write_text('{"drift":"after-install"}\n', encoding="utf-8")
    holder.execute("INSERT INTO transcripts VALUES ('3', 'after-install')")
    holder.commit()
    rolled = _run("rollback-code", {"ROOT": str(live), "BACKUP": applied["backup"], "ARTIFACT": str(ROOT)})
    assert rolled.returncode == 0, rolled.stderr
    assert "ROLLBACK=ok" in rolled.stdout
    assert "RESTART=no" in rolled.stdout
    assert "RESTART=allowed" not in rolled.stdout
    for rel in BASELINE_FILES:
        assert (live / rel).read_bytes() == subprocess.check_output(["git", "show", f"{PARENT}:{rel}"], cwd=ROOT)
    assert not (live / "screenshots.py").exists()
    assert (live / "data" / "url_jobs.json").read_text(encoding="utf-8") == '{"drift":"after-install"}\n'
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    assert (live / "data" / "transcripts" / "kept.txt").read_text(encoding="utf-8") == "existing transcript text\n"
    check = sqlite3.connect(f"file:{live / 'data' / 'transcripts.db'}?mode=ro", uri=True)
    rows = [row[0] for row in check.execute("SELECT transcript FROM transcripts ORDER BY id")]
    check.close()
    assert "after-install" in rows
    assert "only-in-wal" in rows
    insurance = sqlite3.connect(f"file:{dest / 'data' / 'transcripts.db'}?mode=ro", uri=True)
    insured = [row[0] for row in insurance.execute("SELECT transcript FROM transcripts")]
    insurance.close()
    assert "after-install" not in insured
    assert (home / "screenshot-apply-dry-run.json").is_file()
    assert (home / "screenshot-apply.json").is_file()
    holder.close()


def test_deploy_sequence_failure_keeps_data_and_does_not_restart(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    (live / "app.py").write_text("host drifted\n", encoding="utf-8")
    holder = _live_data(live)
    before = (live / "data" / "url_jobs.json").read_bytes()
    plist = tmp_path / "service-config" / "printed-by-launchctl.plist"
    plist.parent.mkdir()
    _service_bin(tmp_path, plist)
    proc = _run("deploy-sequence", _env(tmp_path, live, tmp_path / "outside" / "backup", plist))
    assert proc.returncode != 0
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert not (live / "screenshots.py").exists()
    assert (live / "app.py").read_text(encoding="utf-8") == "host drifted\n"
    assert (live / "data" / "url_jobs.json").read_bytes() == before
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    assert (tmp_path / "home" / "screenshot-preflight.json").is_file(), proc.stdout + "\n" + proc.stderr
    preflight = json.loads((tmp_path / "home" / "screenshot-preflight.json").read_text(encoding="utf-8"))
    assert preflight["ok"] is False
    assert not (tmp_path / "home" / "screenshot-apply-dry-run.json").exists()
    assert not (tmp_path / "home" / "screenshot-apply.json").exists()
    trace = (tmp_path / "home" / "screenshot-deploy-trace").read_text(encoding="utf-8").splitlines()
    assert "apply" not in trace
    assert "bootout" not in (tmp_path / "launchctl.log").read_text(encoding="utf-8")
    holder.close()


def test_inconsistent_plist_and_interpreter_stop_before_backup(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    holder = _live_data(live)
    before_app = (live / "app.py").read_bytes()
    venv_python = _venv_interpreter()
    other = Path("/usr/bin/python3")
    assert other.is_file() and other != venv_python
    plist = tmp_path / "service-config" / "printed-by-launchctl.plist"
    _write_plist(plist, other)
    _service_bin(tmp_path, plist, python=venv_python)
    _write_plist(plist, other)
    proc = _run_script(_env(tmp_path, live, tmp_path / "outside" / "backup", plist))
    _stopped(proc, tmp_path / "home", live, before_app)
    trace = (tmp_path / "home" / "screenshot-deploy-trace").read_text(encoding="utf-8")
    assert "interpreter-mismatch" in trace
    assert "backup" not in trace.splitlines()
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    holder.close()


def test_launchctl_failure_writes_no_hash_listing(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    holder = _live_data(live)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    launchctl = bindir / "launchctl"
    launchctl.write_text("#!/bin/sh\necho 'launchctl unavailable' >&2\nexit 1\n", encoding="utf-8")
    launchctl.chmod(0o755)
    dest = tmp_path / "outside" / "failed"
    home = tmp_path / "home"
    home.mkdir()
    proc = _run("deploy-sequence", {
        "ROOT": str(live),
        "ARTIFACT": str(ROOT),
        "DEST": str(dest),
        "HOME": str(home),
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "FIXTURE_PLIST_PATH": str(tmp_path / "missing.plist"),
        "FIXTURE_PYTHON": sys.executable,
        "FIXTURE_PYTHON_LOG": str(tmp_path / "python.log"),
        "FIXTURE_LAUNCHCTL_LOG": str(tmp_path / "launch.log"),
        "REAL_PYTHON": sys.executable,
    })
    assert proc.returncode != 0
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert not (dest / "SHA256SUMS").exists()
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    assert not (live / "screenshots.py").exists()
    assert not (home / "screenshot-deploy-trace").exists()
    holder.close()


def _run_script(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / "screenshot_host_deploy.sh")],
        env=merged, text=True, capture_output=True, check=False,
    )


def _stopped(proc: subprocess.CompletedProcess[str], home: Path, live: Path, before_app: bytes) -> None:
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert (live / "app.py").read_bytes() == before_app
    assert not (live / "screenshots.py").exists()
    marker = home / "apply-marker.txt"
    if marker.exists():
        assert "--apply" not in marker.read_text(encoding="utf-8")
    trace = (home / "screenshot-deploy-trace").read_text(encoding="utf-8") if (home / "screenshot-deploy-trace").exists() else ""
    assert "\napply\n" not in f"\n{trace}\n"


def _stage(tmp: Path, backup_mode: str, apply_mode: str) -> Path:
    artifact = tmp / "artifact"
    (artifact / "scripts").mkdir(parents=True)
    (artifact / "docs").mkdir()
    (artifact / "scripts" / "screenshot_host_preflight.py").write_bytes((ROOT / "scripts" / "screenshot_host_preflight.py").read_bytes())
    (artifact / "docs" / "screenshot-install-manifest.json").write_bytes((ROOT / "docs" / "screenshot-install-manifest.json").read_bytes())
    (artifact / "scripts" / "screenshot_outside_backup.py").write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "log = Path(os.environ['BACKUP_LOG'])\n"
        "log.parent.mkdir(parents=True, exist_ok=True)\n"
        "log.write_text(log.read_text(encoding='utf-8') + ' '.join(sys.argv) + '\\n' if log.exists() else ' '.join(sys.argv) + '\\n', encoding='utf-8')\n"
        f"mode = {backup_mode!r}\n"
        "dest = Path(os.environ['DEST'])\n"
        "if '--verify' in sys.argv:\n"
        "    raise SystemExit(2 if mode == 'bad-verify' else 0)\n"
        "if mode == 'fail':\n"
        "    raise SystemExit(4)\n"
        "dest.mkdir(parents=True, exist_ok=True)\n"
        "sums = dest / 'SHA256SUMS'\n"
        "if mode == 'missing':\n"
        "    raise SystemExit(0)\n"
        "if mode == 'empty':\n"
        "    sums.write_text('', encoding='utf-8')\n"
        "    raise SystemExit(0)\n"
        "if mode == 'bad-verify':\n"
        "    sums.write_text('deadbeef  .env\\n', encoding='utf-8')\n"
        "    raise SystemExit(0)\n"
        "sums.write_text('unused  .env\\n', encoding='utf-8')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    (artifact / "scripts" / "screenshot_host_apply.py").write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "marker = Path(os.environ['APPLY_MARKER'])\n"
        "marker.parent.mkdir(parents=True, exist_ok=True)\n"
        "with marker.open('a', encoding='utf-8') as handle:\n"
        "    handle.write(' '.join(sys.argv) + '\\n')\n"
        f"mode = {apply_mode!r}\n"
        "args = sys.argv[1:]\n"
        "out = args[args.index('--out') + 1] if '--out' in args else ''\n"
        "applied = '--apply' in args\n"
        "failed = mode == 'fail-dry' or applied\n"
        "payload = {'ok': not failed, 'wrote': False, 'restart': False}\n"
        "if out:\n"
        "    Path(out).write_text(json.dumps(payload) + '\\n', encoding='utf-8')\n"
        "raise SystemExit(3 if failed else 0)\n",
        encoding="utf-8",
    )
    return artifact


def _negative_env(tmp: Path, live: Path, dest: Path, plist: Path, artifact: Path) -> dict[str, str]:
    env = _env(tmp, live, dest, plist)
    env["ARTIFACT"] = str(artifact)
    env["APPLY_MARKER"] = str(tmp / "home" / "apply-marker.txt")
    env["BACKUP_LOG"] = str(tmp / "backup-log.txt")
    return env


def test_each_gate_stops_before_apply(tmp_path):
    cases = ("fail", "missing", "empty", "bad-verify")
    for mode in cases:
        case = tmp_path / mode
        live = case / "live"
        live.mkdir(parents=True)
        _baseline_tree(live)
        holder = _live_data(live)
        before_app = (live / "app.py").read_bytes()
        plist = case / "service-config" / "printed-by-launchctl.plist"
        plist.parent.mkdir(parents=True)
        _service_bin(case, plist)
        (case / "home").mkdir()
        artifact = _stage(case, mode, "fail-dry")
        proc = _run_script(_negative_env(case, live, case / "outside" / "backup", plist, artifact))
        _stopped(proc, case / "home", live, before_app)
        log = (case / "backup-log.txt").read_text(encoding="utf-8")
        assert "--root" in log
        if mode in {"missing", "empty"}:
            assert "--verify" not in log
        if mode == "bad-verify":
            assert "--verify" in log
        if mode == "fail":
            assert "backup-exit=4" in (case / "home" / "screenshot-deploy-trace").read_text(encoding="utf-8")
        assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
        holder.close()


def test_missing_and_nonexecutable_service_files_stop(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    holder = _live_data(live)
    before_app = (live / "app.py").read_bytes()
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "launchctl").write_text(
        "#!/bin/sh\n"
        "printf '\\tpath = %s\\n\\tprogram = %s\\n' \"$FIXTURE_PLIST_PATH\" \"$FIXTURE_PYTHON\"\n",
        encoding="utf-8",
    )
    (bindir / "launchctl").chmod(0o755)
    missing_plist = _env(tmp_path, live, outside / "backup", tmp_path / "no-such.plist")
    missing_plist["PATH"] = str(bindir) + os.pathsep + os.environ["PATH"]
    missing_plist["FIXTURE_PLIST_PATH"] = str(tmp_path / "no-such.plist")
    proc = _run_script(missing_plist)
    _stopped(proc, home, live, before_app)

    plain = tmp_path / "not-executable-python"
    plain.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    bad_py = dict(missing_plist)
    bad_py["FIXTURE_PLIST_PATH"] = str(tmp_path / "service.plist")
    (tmp_path / "service.plist").write_text("plist\n", encoding="utf-8")
    bad_py["FIXTURE_PYTHON"] = str(plain)
    proc = _run_script(bad_py)
    _stopped(proc, home, live, before_app)

    empty_py = dict(bad_py)
    empty_py["FIXTURE_PYTHON"] = ""
    proc = _run_script(empty_py)
    _stopped(proc, home, live, before_app)
    holder.close()


def test_unwritable_destination_and_missing_binding_stop(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    holder = _live_data(live)
    before_app = (live / "app.py").read_bytes()
    plist = tmp_path / "service.plist"
    plist.write_text("plist\n", encoding="utf-8")
    parent = tmp_path / "locked"
    parent.mkdir()
    parent.chmod(0o555)
    try:
        env = _env(tmp_path, live, parent / "backup", plist)
        proc = _run_script(env)
        _stopped(proc, tmp_path / "home", live, before_app)
    finally:
        parent.chmod(0o755)
    env = _env(tmp_path, live, tmp_path / "outside" / "backup", plist)
    del env["HOME"]
    proc = _run_script(env)
    assert proc.returncode != 0
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert (live / "app.py").read_bytes() == before_app
    holder.close()


def test_dry_run_and_apply_failures_keep_source(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    holder = _live_data(live)
    before_app = (live / "app.py").read_bytes()

    dry_root = tmp_path / "dry"
    plist = dry_root / "service-config" / "printed-by-launchctl.plist"
    plist.parent.mkdir(parents=True)
    _service_bin(dry_root, plist)
    dry_artifact = _stage(dry_root, "unused", "fail-dry")
    proc = _run_script(_negative_env(dry_root, live, dry_root / "outside" / "backup", plist, dry_artifact))
    dry_home = dry_root / "home"
    _stopped(proc, dry_home, live, before_app)
    assert (dry_home / "screenshot-apply-dry-run.json").is_file()
    assert not (dry_home / "screenshot-apply.json").exists()
    dry_receipt = json.loads((dry_home / "screenshot-apply-dry-run.json").read_text(encoding="utf-8"))
    assert dry_receipt["wrote"] is False and dry_receipt["restart"] is False
    assert "--apply" not in (dry_home / "apply-marker.txt").read_text(encoding="utf-8")

    apply_root = tmp_path / "applycase"
    plist = apply_root / "service-config" / "printed-by-launchctl.plist"
    plist.parent.mkdir(parents=True)
    _service_bin(apply_root, plist)
    apply_artifact = _stage(apply_root, "unused", "fail-apply")
    proc = _run_script(_negative_env(apply_root, live, apply_root / "outside" / "backup", plist, apply_artifact))
    apply_home = apply_root / "home"
    assert proc.returncode != 0, proc.stderr
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert (live / "app.py").read_bytes() == before_app
    assert not (live / "screenshots.py").exists()
    marker = (apply_home / "apply-marker.txt").read_text(encoding="utf-8")
    assert "--apply" in marker
    applied = json.loads((apply_home / "screenshot-apply.json").read_text(encoding="utf-8"))
    assert applied["ok"] is False and applied["wrote"] is False and applied["restart"] is False
    holder.close()


def test_failed_rollback_does_not_allow_restart_or_touch_data(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    _baseline_tree(live)
    holder = _live_data(live)
    before = {rel: (live / rel).read_bytes() for rel in (".env", "data/url_jobs.json", "data/phase3_gemini_usage.json", "data/transcripts/kept.txt", "app.py")}
    proc = _run("rollback-code", {"ROOT": str(live), "BACKUP": str(tmp_path / "missing-backup"), "ARTIFACT": str(ROOT)})
    assert proc.returncode != 0
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert "ROLLBACK=ok" not in proc.stdout
    for rel, data in before.items():
        assert (live / rel).read_bytes() == data
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "app.py").write_text("insurance\n", encoding="utf-8")
    proc = _run("rollback-code", {"ROOT": str(live), "BACKUP": str(outside), "DEST": str(outside), "ARTIFACT": str(ROOT)})
    assert proc.returncode != 0
    assert "RESTART=no" in proc.stdout
    assert (live / "app.py").read_bytes() == before["app.py"]
    assert (live / ".env").read_bytes() == before[".env"]
    holder.close()
