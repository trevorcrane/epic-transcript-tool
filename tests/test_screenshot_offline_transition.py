"""Conditional offline transition. The fixture is not a Mac and does not stop launchd."""
from __future__ import annotations

import json
import os
import plistlib
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = "c943233222a021e91903e01fb626918e55b43ccc"
AUTH = "interruptible-offline-window-approved"
LABEL = "gui/501/com.epic.transcript-api"
BASELINE_FILES = ("app.py", "static/index.html", "Dockerfile", "README.md")


def _venv() -> Path:
    exe = Path(sys.executable)
    if not (exe.parent.parent / "pyvenv.cfg").is_file():
        raise AssertionError(f"{exe} is not a venv interpreter")
    if str(exe) == "/usr/bin/python3":
        raise AssertionError("refusing the system interpreter as the service python")
    return exe


def _write_plist(path: Path, python: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump({"Label": "com.epic.transcript-api", "ProgramArguments": [str(python), "app.py"]}, handle)


def _live(root: Path) -> None:
    for rel in BASELINE_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", f"{PARENT}:{rel}"], cwd=ROOT))
    data = root / "data"
    (data / "transcripts").mkdir(parents=True)
    (data / "transcripts" / "kept.txt").write_text("existing transcript text\n", encoding="utf-8")
    (data / "phase3_gemini_usage.json").write_text('{"drift":"gemini"}\n', encoding="utf-8")
    (data / "url_jobs.json").write_text(json.dumps({
        "abc123abc123": {"id": "abc123abc123", "status": "running", "stage": "transcribing", "url": "https://www.youtube.com/watch?v=abcdefghijk"}
    }), encoding="utf-8")
    (root / ".env").write_text("SECRET=keep\n", encoding="utf-8")
    conn = sqlite3.connect(data / "transcripts.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE transcripts (id TEXT PRIMARY KEY, transcript TEXT NOT NULL)")
    conn.execute("INSERT INTO transcripts VALUES ('1', 'saved')")
    conn.commit()
    conn.close()


def _launchctl(tmp: Path) -> None:
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    (tmp / "launchctl-state").write_text("up\n", encoding="utf-8")
    (tmp / "launchctl.log").write_text("", encoding="utf-8")
    script = bindir / "launchctl"
    script.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FIXTURE_LAUNCHCTL_LOG\"\n"
        "state=$(cat \"$FIXTURE_LAUNCHCTL_STATE_FILE\")\n"
        "if [ \"$1\" = \"bootout\" ] || [ \"$1\" = \"bootstrap\" ]; then\n"
        "  exit 99\n"
        "fi\n"
        "if [ \"$1\" = \"print\" ] && [ \"$2\" = \"gui/501/com.epic.transcript-api\" ] && [ \"$state\" = \"up\" ]; then\n"
        "  printf '\\tpath = %s\\n\\tprogram = %s\\n\\tpid = %s\\n' \"$FIXTURE_PLIST_PATH\" \"$FIXTURE_PYTHON\" \"$FIXTURE_SERVICE_PID\"\n"
        "  exit 0\n"
        "fi\n"
        "echo 'service not found' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _env(tmp: Path, live: Path, dest: Path, plist: Path, pid: str) -> dict[str, str]:
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    (tmp / "outside").mkdir(exist_ok=True)
    return {
        "ROOT": str(live),
        "ARTIFACT": str(ROOT),
        "DEST": str(dest),
        "HOME": str(home),
        "IDENTITY": str(home / "screenshot-prestop-identity.json"),
        "PATH": str(tmp / "bin") + os.pathsep + os.environ.get("PATH", ""),
        "FIXTURE_PLIST_PATH": str(plist),
        "FIXTURE_PYTHON": str(_venv()),
        "FIXTURE_SERVICE_PID": pid,
        "FIXTURE_LAUNCHCTL_LOG": str(tmp / "launchctl.log"),
        "FIXTURE_LAUNCHCTL_STATE_FILE": str(tmp / "launchctl-state"),
        "SCREENSHOT_PORT": "8090",
    }


def _run(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("SCREENSHOT_OFFLINE_AUTHORIZATION", None)
    merged.pop("SCREENSHOT_APPLY_CRASH_AT", None)
    merged.pop("SCREENSHOT_APPLY_COPY_PAUSE_SECONDS", None)
    merged.pop("SCREENSHOT_APPLY_TEST_HARNESS", None)
    merged.update(env)
    return subprocess.run(["bash", str(ROOT / "scripts" / script)], env=merged, text=True, capture_output=True, check=False)


def _service() -> tuple[subprocess.Popen[str], str, str]:
    code = "import os,subprocess,sys,time; print(os.getpid(), os.getpgid(0), flush=True); subprocess.Popen(['sleep','120']); time.sleep(120)"
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, start_new_session=True)
    assert proc.stdout is not None
    pid, pgid = proc.stdout.readline().strip().split()
    return proc, pid, pgid


def _kill(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, 9)
    except OSError:
        proc.kill()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _trace(tmp: Path) -> str:
    path = tmp / "home" / "screenshot-offline-trace"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _no_apply(proc: subprocess.CompletedProcess[str], tmp: Path, live: Path) -> None:
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert "APPLY=ok" not in proc.stdout
    assert "apply\n" not in _trace(tmp)
    assert not (live / "screenshots.py").exists()
    log = (tmp / "launchctl.log").read_text(encoding="utf-8")
    assert "bootout" not in log and "bootstrap" not in log


def test_initial_transition_captures_then_copies_only_after_stop(tmp_path):
    doc = (ROOT / "docs" / "SCREENSHOT_DEPLOY.md").read_text(encoding="utf-8")
    offline = (ROOT / "scripts" / "screenshot_host_offline_deploy.sh").read_text(encoding="utf-8")
    capture = (ROOT / "scripts" / "screenshot_host_capture_identity.sh").read_text(encoding="utf-8")
    assert "not approved" in doc.lower() or "not approved" in doc
    assert "launchctl bootout" not in offline and "launchctl bootstrap" not in offline
    assert "launchctl bootout" not in capture and "launchctl bootstrap" not in capture
    live = tmp_path / "live"
    live.mkdir()
    _live(live)
    jobs_before = (live / "data" / "url_jobs.json").read_bytes()
    env_before = (live / ".env").read_bytes()
    plist = tmp_path / "LaunchAgents" / "com.epic.transcript-api.plist"
    _write_plist(plist, _venv())
    _launchctl(tmp_path)
    proc, pid, pgid = _service()
    try:
        env = _env(tmp_path, live, tmp_path / "outside" / "backup", plist, pid)
        assert env["FIXTURE_PYTHON"] != "/usr/bin/python3"
        captured = _run("screenshot_host_capture_identity.sh", env)
        assert captured.returncode == 0, captured.stderr + captured.stdout
        assert "CAPTURE=ok" in captured.stdout and "RESTART=no" in captured.stdout
        identity = (tmp_path / "home" / "screenshot-prestop-identity.json").read_text(encoding="utf-8")
        assert f"program\t{env['FIXTURE_PYTHON']}" in identity
        assert f"pid\t{pid}" in identity
        assert f"pgid\t{pgid}" in identity
        assert not (tmp_path / "outside" / "backup").exists()
        (tmp_path / "launchctl-state").write_text("down\n", encoding="utf-8")
        _kill(proc)
        proc = None
        time.sleep(0.2)
        env["SCREENSHOT_OFFLINE_AUTHORIZATION"] = AUTH
        writer = subprocess.Popen(
            [sys.executable, "-c",
             "import sqlite3,sys,time\n"
             "from pathlib import Path\n"
             "db, ready, out = sys.argv[1:]\n"
             "deadline=time.time()+30\n"
             "while not Path(ready).exists():\n"
             "    if time.time()>deadline:\n"
             "        Path(out).write_text('missed\\n'); raise SystemExit(2)\n"
             "    time.sleep(0.005)\n"
             "blocked=0\n"
             "committed=False\n"
             "while time.time()<deadline and Path(ready).exists():\n"
             "    w=sqlite3.connect(db, timeout=0.05)\n"
             "    try:\n"
             "        w.execute(\"INSERT INTO transcripts VALUES ('9','intruder')\")\n"
             "        w.commit()\n"
             "        if Path(ready).exists():\n"
             "            committed=True\n"
             "        break\n"
             "    except sqlite3.OperationalError:\n"
             "        blocked += 1\n"
             "    finally:\n"
             "        w.close()\n"
             "Path(out).write_text('committed\\n' if committed else 'blocked\\n' if blocked else 'missed\\n')\n",
             str(live / "data" / "transcripts.db"),
             str(tmp_path / "home" / "screenshot-critical-open"),
             str(tmp_path / "writer-result.txt")],
        )
        try:
            deployed = _run("screenshot_host_offline_deploy.sh", env)
        finally:
            writer.wait(timeout=40)
        assert deployed.returncode == 0, deployed.stderr + deployed.stdout
        assert "APPLY=ok" in deployed.stdout.splitlines()
        assert "INSTALL=verified-new" in deployed.stdout.splitlines()
        assert "RESTART=allowed" in deployed.stdout.splitlines()
        assert "RESTART=not-run" not in deployed.stdout.splitlines()
        assert "RESTART=not-allowed" not in deployed.stdout.splitlines()
        assert "AUTHORIZATION=original-window" in deployed.stdout.splitlines()
        assert (live / "data" / "url_jobs.json").read_bytes() == jobs_before
        assert (live / ".env").read_bytes() == env_before
        recorded = json.loads((tmp_path / "home" / "screenshot-interrupted-jobs.json").read_text(encoding="utf-8"))
        assert recorded["old_process_can_resume"] is False
        assert recorded["live_jobs_rewritten"] is False
        assert recorded["jobs"] == [{"id": "abc123abc123", "status": "running", "stage": "transcribing"}]
        assert (live / "screenshots.py").is_file()
        receipt = _printed(deployed.stdout, "APPLY_RECEIPT")
        run_dir = receipt.parent
        preflight = json.loads((run_dir / "preflight.json").read_text(encoding="utf-8"))
        dry = json.loads((run_dir / "dry-run.json").read_text(encoding="utf-8"))
        applied = json.loads(receipt.read_text(encoding="utf-8"))
        assert preflight["ok"] is True
        assert dry["wrote"] is False and dry["restart"] is False
        assert applied["ok"] is True and applied["wrote"] is True and applied["restart"] is False
        assert "backup-exit=0" in _trace(tmp_path)
        assert (tmp_path / "writer-result.txt").read_text(encoding="utf-8") == "blocked\n"
        snap = sqlite3.connect(f"file:{tmp_path / 'outside' / 'backup' / 'data' / 'transcripts.db'}?mode=ro", uri=True)
        bodies = [row[0] for row in snap.execute("SELECT transcript FROM transcripts")]
        snap.close()
        assert "saved" in bodies and "intruder" not in bodies
        log = (tmp_path / "launchctl.log").read_text(encoding="utf-8")
        assert "bootout" not in log and "bootstrap" not in log
        (live / "data" / "url_jobs.json").write_text('{"drift":"after-install"}\n', encoding="utf-8")
        rolled = _run("screenshot_host_rollback.sh", {"ROOT": str(live), "BACKUP": applied["backup"], "ARTIFACT": str(ROOT), "DEST": str(tmp_path / "outside" / "backup")})
        assert rolled.returncode == 0, rolled.stderr
        assert "ROLLBACK=ok" in rolled.stdout and "RESTART=no" in rolled.stdout
        assert "RESTART=allowed" not in rolled.stdout
        assert not (live / "screenshots.py").exists()
        assert (live / "data" / "url_jobs.json").read_text(encoding="utf-8") == '{"drift":"after-install"}\n'
        assert (live / ".env").read_bytes() == env_before
    finally:
        if proc is not None:
            _kill(proc)


def _prepare_stopped(tmp: Path) -> tuple[Path, dict[str, str]]:
    live = tmp / "live"
    live.mkdir(parents=True)
    _live(live)
    plist = tmp / "LaunchAgents" / "com.epic.transcript-api.plist"
    _write_plist(plist, _venv())
    _launchctl(tmp)
    proc, pid, _pgid = _service()
    env = _env(tmp, live, tmp / "outside" / "backup", plist, pid)
    captured = _run("screenshot_host_capture_identity.sh", env)
    assert captured.returncode == 0, captured.stderr + captured.stdout
    _kill(proc)
    time.sleep(0.2)
    (tmp / "launchctl-state").write_text("down\n", encoding="utf-8")
    env["SCREENSHOT_OFFLINE_AUTHORIZATION"] = AUTH
    return live, env


def test_missing_authorization_and_loaded_service_block_apply(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before = (live / "app.py").read_bytes()
    del env["SCREENSHOT_OFFLINE_AUTHORIZATION"]
    refused = _run("screenshot_host_offline_deploy.sh", env)
    _no_apply(refused, tmp_path, live)
    assert (live / "app.py").read_bytes() == before
    env["SCREENSHOT_OFFLINE_AUTHORIZATION"] = AUTH
    (tmp_path / "launchctl-state").write_text("up\n", encoding="utf-8")
    loaded = _run("screenshot_host_offline_deploy.sh", env)
    _no_apply(loaded, tmp_path, live)
    assert "service-still-loaded" in _trace(tmp_path)


def test_bound_port_live_pid_and_descendant_block_apply(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    port = 8765
    env["SCREENSHOT_PORT"] = str(port)
    sock = socket.socket()
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    try:
        bound = _run("screenshot_host_offline_deploy.sh", env)
        _no_apply(bound, tmp_path, live)
        assert "port-exit=20" in _trace(tmp_path)
    finally:
        sock.close()
    (tmp_path / "home" / "screenshot-offline-trace").unlink()
    proc, pid, pgid = _service()
    try:
        identity = tmp_path / "home" / "screenshot-prestop-identity.json"
        text = identity.read_text(encoding="utf-8")
        text = _replace_field(text, "pid", pid)
        text = _replace_field(text, "pgid", pgid)
        identity.write_text(text, encoding="utf-8")
        alive = _run("screenshot_host_offline_deploy.sh", env)
        _no_apply(alive, tmp_path, live)
        assert "process-exit=21" in _trace(tmp_path)
        os.kill(int(pid), 9)
        proc.wait(timeout=2)
        proc = None
        time.sleep(0.2)
        (tmp_path / "home" / "screenshot-offline-trace").unlink()
        descendant = _run("screenshot_host_offline_deploy.sh", env)
        _no_apply(descendant, tmp_path, live)
        assert "process-exit=22" in _trace(tmp_path)
    finally:
        if proc is not None:
            _kill(proc)
        subprocess.run(["pkill", "-f", "sleep 120"], check=False)


def test_database_lock_stale_plist_and_mismatch_block_apply(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    holder = sqlite3.connect(live / "data" / "transcripts.db", timeout=0.2)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        locked = _run("screenshot_host_offline_deploy.sh", env)
        _no_apply(locked, tmp_path, live)
        assert "exclusive-exit=23" in _trace(tmp_path)
    finally:
        holder.close()
    (tmp_path / "home" / "screenshot-offline-trace").unlink()
    plist = Path(env["FIXTURE_PLIST_PATH"])
    plist.write_bytes(plist.read_bytes() + b"\n")
    stale = _run("screenshot_host_offline_deploy.sh", env)
    _no_apply(stale, tmp_path, live)
    assert "identity-exit=10" in _trace(tmp_path)
    _write_plist(plist, Path("/usr/bin/python3"))
    # Hash now matches the tampered file only if we also update the identity hash.
    identity = Path(env["IDENTITY"])
    import hashlib
    digest = hashlib.sha256(plist.read_bytes()).hexdigest()
    text = _replace_field(identity.read_text(encoding="utf-8"), "plist_sha256", digest)
    identity.write_text(text, encoding="utf-8")
    (tmp_path / "home" / "screenshot-offline-trace").unlink()
    mismatched = _run("screenshot_host_offline_deploy.sh", env)
    _no_apply(mismatched, tmp_path, live)
    assert "identity-exit=11" in _trace(tmp_path)
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"


def test_port_timeout_fails_closed_and_only_refusal_passes():
    import argparse
    import importlib.util
    spec = importlib.util.spec_from_file_location("offline_checks", ROOT / "scripts" / "screenshot_host_offline_checks.py")
    checks = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(checks)
    refused = socket.socket()
    refused.bind(("127.0.0.1", 0))
    port = refused.getsockname()[1]
    refused.close()
    assert checks.port_free(argparse.Namespace(port=port)) == 0
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        assert checks.port_free(argparse.Namespace(port=listener.getsockname()[1])) == 20
    finally:
        listener.close()

    class TimingOut:
        def settimeout(self, _seconds: float) -> None:
            return None
        def connect(self, _addr: tuple[str, int]) -> None:
            raise TimeoutError("timed out")
        def close(self) -> None:
            return None

    original = checks.socket.socket
    checks.socket.socket = lambda *args, **kwargs: TimingOut()  # type: ignore[assignment]
    try:
        assert checks.port_free(argparse.Namespace(port=9)) == 20
    finally:
        checks.socket.socket = original


def test_setsid_orphan_is_outside_the_recorded_group():
    import argparse
    import importlib.util
    spec = importlib.util.spec_from_file_location("offline_checks", ROOT / "scripts" / "screenshot_host_offline_checks.py")
    checks = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(checks)
    parent = subprocess.Popen(
        [sys.executable, "-c", "import os,subprocess,time; print(os.getpid(), os.getpgid(0), flush=True); subprocess.Popen(['sleep','30']); time.sleep(30)"],
        stdout=subprocess.PIPE, text=True, start_new_session=True,
    )
    assert parent.stdout is not None
    pid, pgid = parent.stdout.readline().strip().split()
    time.sleep(0.2)
    try:
        os.kill(int(pid), 9)
        parent.wait(timeout=2)
        assert checks.processes_gone(argparse.Namespace(pid=pid, pgid=pgid)) == 22
        orphan = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            assert str(os.getpgid(orphan.pid)) != pgid
            assert checks.processes_gone(argparse.Namespace(pid=pid, pgid=pgid)) == 22
            subprocess.run(["pkill", "-f", "sleep 30"], check=False)
            time.sleep(0.2)
            assert checks.processes_gone(argparse.Namespace(pid=pid, pgid=pgid)) == 0
        finally:
            orphan.kill()
            orphan.wait(timeout=2)
    finally:
        try:
            os.killpg(int(pgid), 9)
        except OSError:
            pass


def test_failed_apply_restores_source_and_stays_stopped(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before_env = (live / ".env").read_bytes()
    before_app = (live / "app.py").read_bytes()
    artifact = _recovery_artifact(tmp_path / "restore-art", live, fail=False)
    env["ARTIFACT"] = str(artifact)
    env["RECOVERY_BACKUP"] = str(live / "backups" / "known-good-c943")
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "RECOVERY=source-restored" in proc.stdout.splitlines()
    assert "INSTALL=verified-c943" in proc.stdout.splitlines()
    assert "RESTART=allowed" in proc.stdout.splitlines()
    assert "RESTART=not-allowed" not in proc.stdout.splitlines()
    assert "RESTART=not-run" not in proc.stdout.splitlines()
    assert "BOOTSTRAP=not-run" in proc.stdout
    assert env["FIXTURE_PLIST_PATH"] in proc.stdout
    assert (live / "app.py").read_bytes() == before_app
    assert not (live / "screenshots.py").exists()
    assert (live / ".env").read_bytes() == before_env
    assert "bootstrap" not in (tmp_path / "launchctl.log").read_text(encoding="utf-8")


def test_recovery_failure_stays_stopped(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before_env = (live / ".env").read_bytes()
    artifact = _recovery_artifact(tmp_path / "fail-art", live, fail=True)
    env["ARTIFACT"] = str(artifact)
    env["RECOVERY_BACKUP"] = str(tmp_path / "missing-known-good")
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert proc.returncode != 0
    assert "RECOVERY=failed" in proc.stdout.splitlines()
    assert "INSTALL=incomplete" in proc.stdout.splitlines()
    assert "RESTART=not-allowed" in proc.stdout.splitlines()
    assert "RESTART=allowed" not in proc.stdout.splitlines()
    assert "APPLY=ok" not in proc.stdout.splitlines()
    assert (live / ".env").read_bytes() == before_env
    assert "bootstrap" not in (tmp_path / "launchctl.log").read_text(encoding="utf-8")


def _recovery_artifact(tmp: Path, live: Path, fail: bool) -> Path:
    artifact = tmp
    (artifact / "scripts").mkdir(parents=True)
    (artifact / "docs").mkdir()
    for name in (
        "screenshot_host_offline_checks.py",
        "screenshot_outside_backup.py",
        "screenshot_host_preflight.py",
        "screenshot_host_rollback.sh",
    ):
        (artifact / "scripts" / name).write_bytes((ROOT / "scripts" / name).read_bytes())
        if name.endswith(".sh"):
            (artifact / "scripts" / name).chmod(0o755)
    (artifact / "docs" / "screenshot-install-manifest.json").write_bytes((ROOT / "docs" / "screenshot-install-manifest.json").read_bytes())
    marker = artifact / "scripts" / "screenshot_host_apply.py"
    marker.write_text(
        "import hashlib, json, os, shutil, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.path.realpath(os.environ['ROOT']))\n"
        "args = sys.argv[1:]\n"
        "out = Path(args[args.index('--out') + 1])\n"
        "if '--apply' not in args:\n"
        "    out.write_text(json.dumps({'ok': True, 'wrote': False, 'restart': False}) + '\\n')\n"
        "    raise SystemExit(0)\n"
        "run_dir = Path(os.path.realpath(out.parent))\n"
        "run_id = run_dir.name\n"
        f"fail = {fail!r}\n"
        "if fail:\n"
        "    backup = Path(os.environ['RECOVERY_BACKUP'])\n"
        "else:\n"
        "    backup = root / 'backups' / f'screenshots-{run_id}'\n"
        "    backup.mkdir(parents=True, exist_ok=True)\n"
        "    for rel in ('app.py', 'static/index.html', 'Dockerfile', 'README.md'):\n"
        "        src = root / rel\n"
        "        dest = backup / rel\n"
        "        dest.parent.mkdir(parents=True, exist_ok=True)\n"
        "        shutil.copy2(src, dest)\n"
        "    (backup / '.screenshot-transaction').write_text(run_id + '\\n')\n"
        "manifest = Path(os.environ['ARTIFACT']) / 'docs' / 'screenshot-install-manifest.json'\n"
        "intent = {\n"
        "    'phase': 'replacing',\n"
        "    'run_id': run_id,\n"
        "    'run_dir': str(run_dir),\n"
        "    'root': str(root),\n"
        "    'backup': str(Path(os.path.realpath(backup)) if backup.exists() else backup),\n"
        "    'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),\n"
        "}\n"
        "(run_dir / 'intent.json').write_text(json.dumps(intent) + '\\n')\n"
        "(root / 'app.py').write_text('replaced-during-failed-apply\\n')\n"
        "(root / 'screenshots.py').write_text('new\\n')\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    return artifact


def _printed(stdout: str, key: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return Path(line.split("=", 1)[1])
    raise AssertionError(stdout)


def test_stale_receipt_and_other_drift_do_not_restore(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    wrong = tmp_path / "wrong-backup"
    (wrong / "app.py").parent.mkdir(parents=True)
    (wrong / "app.py").write_text("WRONG-SOURCE\n", encoding="utf-8")
    (tmp_path / "home" / "screenshot-apply.json").write_text(
        json.dumps({"ok": False, "wrote": False, "restored": False, "restart": False, "backup": str(wrong)}) + "\n",
        encoding="utf-8",
    )
    (live / "app.py").write_text("preflight-drift\n", encoding="utf-8")
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert proc.returncode != 0
    assert "RECOVERY=not-needed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert "RESTART=no" in proc.stdout
    assert (live / "app.py").read_text(encoding="utf-8") == "preflight-drift\n"
    assert "WRONG-SOURCE" not in (live / "app.py").read_text(encoding="utf-8")

    live2, env2 = _prepare_stopped(tmp_path / "other")
    (tmp_path / "other" / "home" / "screenshot-apply.json").write_text(
        json.dumps({"ok": False, "wrote": False, "backup": str(wrong)}) + "\n",
        encoding="utf-8",
    )
    (live2 / "static" / "index.html").write_text("drifted index\n", encoding="utf-8")
    (live2 / "Dockerfile").write_text("drifted docker\n", encoding="utf-8")
    proc = _run("screenshot_host_offline_deploy.sh", env2)
    assert "RECOVERY=not-needed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert (live2 / "static" / "index.html").read_text(encoding="utf-8") == "drifted index\n"
    assert (live2 / "Dockerfile").read_text(encoding="utf-8") == "drifted docker\n"
    assert "WRONG-SOURCE" not in (live2 / "app.py").read_text(encoding="utf-8")


def test_backup_that_disagrees_on_any_baseline_file_is_not_used(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before_index = (live / "static" / "index.html").read_bytes()
    before_docker = (live / "Dockerfile").read_bytes()
    artifact = _recovery_artifact(tmp_path / "bad-hash-art", live, fail=True)
    marker = artifact / "scripts" / "screenshot_host_apply.py"
    marker.write_text(
        "import hashlib, json, os, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.path.realpath(os.environ['ROOT']))\n"
        "args = sys.argv[1:]\n"
        "out = Path(args[args.index('--out') + 1])\n"
        "if '--apply' not in args:\n"
        "    out.write_text(json.dumps({'ok': True, 'wrote': False, 'restart': False}) + '\\n')\n"
        "    raise SystemExit(0)\n"
        "run_dir = Path(os.path.realpath(out.parent))\n"
        "run_id = run_dir.name\n"
        "backup = root / 'backups' / f'screenshots-{run_id}'\n"
        "(backup / 'static').mkdir(parents=True)\n"
        "(backup / 'app.py').write_bytes((root / 'app.py').read_bytes())\n"
        "(backup / 'static' / 'index.html').write_text('WRONG-SOURCE\\n')\n"
        "(backup / 'Dockerfile').write_text('WRONG-SOURCE\\n')\n"
        "(backup / 'README.md').write_bytes((root / 'README.md').read_bytes())\n"
        "(backup / '.screenshot-transaction').write_text(run_id + '\\n')\n"
        "manifest = Path(os.environ['ARTIFACT']) / 'docs' / 'screenshot-install-manifest.json'\n"
        "intent = {\n"
        "    'phase': 'replacing', 'run_id': run_id, 'run_dir': str(run_dir), 'root': str(root),\n"
        "    'backup': str(backup.resolve()),\n"
        "    'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),\n"
        "}\n"
        "(run_dir / 'intent.json').write_text(json.dumps(intent) + '\\n')\n"
        "(root / 'app.py').write_text('replaced-during-failed-apply\\n')\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    env["ARTIFACT"] = str(artifact)
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert proc.returncode != 0
    assert "RECOVERY=failed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert (live / "app.py").read_text(encoding="utf-8") == "replaced-during-failed-apply\n"
    assert (live / "static" / "index.html").read_bytes() == before_index
    assert (live / "Dockerfile").read_bytes() == before_docker
    assert "WRONG-SOURCE" not in (live / "static" / "index.html").read_text(encoding="utf-8")
    assert "WRONG-SOURCE" not in (live / "Dockerfile").read_text(encoding="utf-8")


def test_copy_crash_restores_every_baseline_file(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before = {rel: (live / rel).read_bytes() for rel in ("app.py", "static/index.html", "Dockerfile", "README.md", ".env", "data/url_jobs.json")}
    run_id = f"screenshot-run-{os.getpid()}-{'cd' * 8}"
    run_dir = Path(env["HOME"]) / run_id
    run_dir.mkdir()
    proc = subprocess.run(
        [
            env["FIXTURE_PYTHON"],
            str(ROOT / "scripts" / "screenshot_host_apply.py"),
            "--root", str(live),
            "--source", str(ROOT),
            "--manifest", str(ROOT / "docs" / "screenshot-install-manifest.json"),
            "--apply",
            "--intent", str(run_dir / "intent.json"),
            "--run-id", run_id,
            "--out", str(run_dir / "apply.json"),
        ],
        env={**os.environ, "SCREENSHOT_APPLY_TEST_HARNESS": "1", "SCREENSHOT_APPLY_CRASH_AT": "screenshots.py"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    for rel, data in before.items():
        assert (live / rel).read_bytes() == data
    assert not (live / "screenshots.py").exists()
    assert not (live / "docs" / "SCREENSHOT_DEPLOY.md").exists()
    body = json.loads((run_dir / "apply.json").read_text(encoding="utf-8"))
    assert body["restored"] is True
    assert body["backup"]
    assert (run_dir / "intent.json").is_file()


def test_restored_flag_without_every_baseline_file_is_not_success(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    original_index = (live / "static" / "index.html").read_bytes()
    artifact = _recovery_artifact(tmp_path / "drift-art", live, fail=False)
    marker = artifact / "scripts" / "screenshot_host_apply.py"
    marker.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.environ['ROOT'])\n"
        "args = sys.argv[1:]\n"
        "out = args[args.index('--out') + 1]\n"
        "if '--apply' not in args:\n"
        "    Path(out).write_text(json.dumps({'ok': True, 'wrote': False, 'restart': False}) + '\\n')\n"
        "    raise SystemExit(0)\n"
        "(root / 'static' / 'index.html').write_text('still drifted\\n')\n"
        "(root / 'Dockerfile').write_text('still drifted\\n')\n"
        "Path(out).write_text(json.dumps({'ok': False, 'wrote': False, 'restored': True, 'restart': False}) + '\\n')\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    (tmp_path / "home" / "screenshot-apply.json").write_text(
        json.dumps({"ok": False, "wrote": False, "restored": False, "backup": str(tmp_path / "wrong-backup")}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "wrong-backup").mkdir()
    (tmp_path / "wrong-backup" / "app.py").write_text("WRONG-SOURCE\n", encoding="utf-8")
    env["ARTIFACT"] = str(artifact)
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert "RECOVERY=failed" in proc.stdout
    assert "WRONG-SOURCE" not in (live / "app.py").read_text(encoding="utf-8")
    assert "RECOVERY=source-restored" not in proc.stdout
    assert "RESTART=no" in proc.stdout
    assert (live / "static" / "index.html").read_text(encoding="utf-8") == "still drifted\n"
    assert (live / "Dockerfile").read_text(encoding="utf-8") == "still drifted\n"
    assert original_index != (live / "static" / "index.html").read_bytes()


def _checks():
    import importlib.util
    spec = importlib.util.spec_from_file_location("offline_checks_recovery", ROOT / "scripts" / "screenshot_host_offline_checks.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_each_of_the_nine_rollback_paths_blocks_baseline(tmp_path):
    checks = _checks()
    assert checks.ROLLBACK_RELS == (
        "app.py",
        "static/index.html",
        "Dockerfile",
        "README.md",
        "screenshots.py",
        "docs/SCREENSHOT_DEPLOY.md",
        "docs/screenshot-install-manifest.json",
        "scripts/screenshot_host_preflight.py",
        "scripts/screenshot_host_apply.py",
    )
    rollback = (ROOT / "scripts" / "screenshot_host_rollback.sh").read_text(encoding="utf-8")
    for rel in checks.ROLLBACK_RELS:
        assert rel in rollback
    live = tmp_path / "tree"
    for rel in checks.BASELINE_RELS:
        target = live / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", f"{PARENT}:{rel}"], cwd=ROOT))
    manifest = ROOT / "docs" / "screenshot-install-manifest.json"
    assert checks.baseline_problem(live, manifest) is None
    for rel in checks.BASELINE_RELS:
        original = (live / rel).read_bytes()
        (live / rel).write_bytes(original + b"\n")
        assert checks.baseline_problem(live, manifest) == rel
        (live / rel).write_bytes(original)
        assert checks.baseline_problem(live, manifest) is None
    for rel in checks.ADDED_RELS:
        path = live / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("present\n", encoding="utf-8")
        assert checks.baseline_problem(live, manifest) == rel
        path.unlink()
        assert checks.baseline_problem(live, manifest) is None


def test_create_run_skips_an_existing_directory(tmp_path):
    checks = _checks()
    existing = "screenshot-run-4242-" + ("ab" * 8)
    fresh = "screenshot-run-4242-" + ("cd" * 8)
    (tmp_path / existing).mkdir()
    (tmp_path / existing / "apply.json").write_text("stale\n", encoding="utf-8")
    created = checks.create_run_dir(tmp_path, names=[existing, existing, fresh])
    assert created.name == fresh
    assert (tmp_path / existing / "apply.json").read_text(encoding="utf-8") == "stale\n"
    assert not (tmp_path / existing / "intent.json").exists()


def test_backup_confinement_rejects_parent_escape_and_symlink(tmp_path):
    checks = _checks()
    live = tmp_path / "live"
    (live / "backups").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "app.py").write_text("valid-looking\n", encoding="utf-8")
    escaped = str(live) + "/backups/../../outside"
    assert checks.confine_backup(live, escaped) is None
    link = live / "backups" / "via-link"
    link.symlink_to(outside)
    assert checks.confine_backup(live, str(link)) is None
    inside = live / "backups" / "screenshots-kept"
    inside.mkdir()
    assert checks.confine_backup(live, str(inside)) == Path(os.path.realpath(inside))


def test_repeated_bsd_date_does_not_reuse_a_stale_receipt(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    original_readme = (live / "README.md").read_bytes()
    (live / "README.md").write_text("CURRENT-README\n", encoding="utf-8")
    stale = Path(env["HOME"]) / "screenshot-run-100N"
    stale.mkdir()
    backup = live / "backups" / "screenshots-screenshot-run-100N"
    (backup / "static").mkdir(parents=True)
    for rel in ("app.py", "static/index.html", "Dockerfile"):
        target = backup / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((live / rel).read_bytes())
    (backup / "README.md").write_bytes(original_readme)
    (backup / ".screenshot-transaction").write_text("screenshot-run-100N\n", encoding="utf-8")
    intent = {
        "phase": "replacing",
        "run_id": "screenshot-run-100N",
        "run_dir": str(stale),
        "root": str(live.resolve()),
        "backup": str(backup.resolve()),
        "manifest_sha256": "stale",
    }
    (stale / "intent.json").write_text(json.dumps(intent) + "\n", encoding="utf-8")
    (stale / "apply.json").write_text(json.dumps({"ok": False, "backup": str(backup.resolve())}) + "\n", encoding="utf-8")
    stale_intent = (stale / "intent.json").read_bytes()
    date_dir = tmp_path / "datebin"
    date_dir.mkdir()
    date_bin = date_dir / "date"
    date_bin.write_text("#!/bin/sh\nprintf '%s\\n' '100N'\n", encoding="utf-8")
    date_bin.chmod(0o755)
    env["PATH"] = str(date_dir) + os.pathsep + env["PATH"]
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert proc.returncode != 0
    assert "RECOVERY=not-needed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert (live / "README.md").read_text(encoding="utf-8") == "CURRENT-README\n"
    assert (stale / "intent.json").read_bytes() == stale_intent
    created = [path for path in Path(env["HOME"]).glob("screenshot-run-*") if path != stale]
    assert created
    assert all("100N" not in path.name for path in created)
    assert all(not (path / "intent.json").exists() for path in created)


def test_manifest_only_drift_is_removed_before_source_restored(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    artifact = _recovery_artifact(tmp_path / "manifest-art", live, fail=False)
    marker = artifact / "scripts" / "screenshot_host_apply.py"
    marker.write_text(
        "import hashlib, json, os, shutil, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.path.realpath(os.environ['ROOT']))\n"
        "args = sys.argv[1:]\n"
        "out = Path(args[args.index('--out') + 1])\n"
        "if '--apply' not in args:\n"
        "    out.write_text(json.dumps({'ok': True, 'wrote': False, 'restart': False}) + '\\n')\n"
        "    raise SystemExit(0)\n"
        "run_dir = Path(os.path.realpath(out.parent))\n"
        "run_id = run_dir.name\n"
        "backup = root / 'backups' / f'screenshots-{run_id}'\n"
        "backup.mkdir(parents=True)\n"
        "for rel in ('app.py', 'static/index.html', 'Dockerfile', 'README.md'):\n"
        "    dest = backup / rel\n"
        "    dest.parent.mkdir(parents=True, exist_ok=True)\n"
        "    shutil.copy2(root / rel, dest)\n"
        "(backup / '.screenshot-transaction').write_text(run_id + '\\n')\n"
        "manifest = Path(os.environ['ARTIFACT']) / 'docs' / 'screenshot-install-manifest.json'\n"
        "intent = {\n"
        "    'phase': 'replacing', 'run_id': run_id, 'run_dir': str(run_dir), 'root': str(root),\n"
        "    'backup': str(os.path.realpath(backup)),\n"
        "    'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),\n"
        "}\n"
        "(run_dir / 'intent.json').write_text(json.dumps(intent) + '\\n')\n"
        "drift = root / 'docs' / 'screenshot-install-manifest.json'\n"
        "drift.parent.mkdir(parents=True, exist_ok=True)\n"
        "drift.write_text('manifest-only drift\\n')\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    env["ARTIFACT"] = str(artifact)
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert "RECOVERY=source-restored" in proc.stdout, proc.stdout
    assert not (live / "docs" / "screenshot-install-manifest.json").exists()
    assert "manifest-only drift" not in proc.stdout


def test_escaped_backup_is_not_used_even_when_bytes_match(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    outside = tmp_path / "outside-tree"
    outside.mkdir()
    for rel in ("app.py", "static/index.html", "Dockerfile", "README.md"):
        target = outside / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((live / rel).read_bytes())
    artifact = _recovery_artifact(tmp_path / "escape-art", live, fail=True)
    marker = artifact / "scripts" / "screenshot_host_apply.py"
    marker.write_text(
        "import hashlib, json, os, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.path.realpath(os.environ['ROOT']))\n"
        "outside = Path(os.environ['OUTSIDE'])\n"
        "args = sys.argv[1:]\n"
        "out = Path(args[args.index('--out') + 1])\n"
        "if '--apply' not in args:\n"
        "    out.write_text(json.dumps({'ok': True, 'wrote': False, 'restart': False}) + '\\n')\n"
        "    raise SystemExit(0)\n"
        "run_dir = Path(os.path.realpath(out.parent))\n"
        "run_id = run_dir.name\n"
        "(outside / '.screenshot-transaction').write_text(run_id + '\\n')\n"
        "link = root / 'backups' / f'screenshots-{run_id}'\n"
        "link.parent.mkdir(parents=True, exist_ok=True)\n"
        "if os.environ['ESCAPE'] == 'link':\n"
        "    link.symlink_to(outside)\n"
        "    backup_text = str(link)\n"
        "else:\n"
        "    backup_text = str(root) + '/backups/../../escaped-tree'\n"
        "manifest = Path(os.environ['ARTIFACT']) / 'docs' / 'screenshot-install-manifest.json'\n"
        "intent = {\n"
        "    'phase': 'replacing', 'run_id': run_id, 'run_dir': str(run_dir), 'root': str(root),\n"
        "    'backup': backup_text,\n"
        "    'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),\n"
        "}\n"
        "(run_dir / 'intent.json').write_text(json.dumps(intent) + '\\n')\n"
        "(root / 'app.py').write_text('replaced-during-failed-apply\\n')\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    env["ARTIFACT"] = str(artifact)
    env["OUTSIDE"] = str(outside)
    env["ESCAPE"] = "link"
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert "RECOVERY=failed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert (live / "app.py").read_text(encoding="utf-8") == "replaced-during-failed-apply\n"

    live2, env2 = _prepare_stopped(tmp_path / "dotdot")
    outside2 = tmp_path / "dotdot" / "escaped-tree"
    outside2.mkdir()
    for rel in ("app.py", "static/index.html", "Dockerfile", "README.md"):
        target = outside2 / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((live2 / rel).read_bytes())
    artifact2 = _recovery_artifact(tmp_path / "dotdot-art", live2, fail=True)
    (artifact2 / "scripts" / "screenshot_host_apply.py").write_text(marker.read_text(encoding="utf-8"), encoding="utf-8")
    env2["ARTIFACT"] = str(artifact2)
    env2["OUTSIDE"] = str(outside2)
    env2["ESCAPE"] = "dotdot"
    proc = _run("screenshot_host_offline_deploy.sh", env2)
    assert "RECOVERY=failed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert (live2 / "app.py").read_text(encoding="utf-8") == "replaced-during-failed-apply\n"


def test_other_runs_valid_backup_is_not_this_transaction(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    artifact = _recovery_artifact(tmp_path / "other-run-art", live, fail=True)
    marker = artifact / "scripts" / "screenshot_host_apply.py"
    marker.write_text(
        "import hashlib, json, os, shutil, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.path.realpath(os.environ['ROOT']))\n"
        "args = sys.argv[1:]\n"
        "out = Path(args[args.index('--out') + 1])\n"
        "if '--apply' not in args:\n"
        "    out.write_text(json.dumps({'ok': True, 'wrote': False, 'restart': False}) + '\\n')\n"
        "    raise SystemExit(0)\n"
        "run_dir = Path(os.path.realpath(out.parent))\n"
        "run_id = run_dir.name\n"
        "backup = root / 'backups' / f'screenshots-{run_id}'\n"
        "backup.mkdir(parents=True)\n"
        "for rel in ('app.py', 'static/index.html', 'Dockerfile', 'README.md'):\n"
        "    dest = backup / rel\n"
        "    dest.parent.mkdir(parents=True, exist_ok=True)\n"
        "    shutil.copy2(root / rel, dest)\n"
        "(backup / '.screenshot-transaction').write_text('screenshot-run-9-' + ('ab' * 8) + '\\n')\n"
        "manifest = Path(os.environ['ARTIFACT']) / 'docs' / 'screenshot-install-manifest.json'\n"
        "intent = {\n"
        "    'phase': 'replacing', 'run_id': run_id, 'run_dir': str(run_dir), 'root': str(root),\n"
        "    'backup': str(os.path.realpath(backup)),\n"
        "    'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),\n"
        "}\n"
        "(run_dir / 'intent.json').write_text(json.dumps(intent) + '\\n')\n"
        "(root / 'app.py').write_text('replaced-during-failed-apply\\n')\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    env["ARTIFACT"] = str(artifact)
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert "RECOVERY=failed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert (live / "app.py").read_text(encoding="utf-8") == "replaced-during-failed-apply\n"


def test_ambient_crash_and_unbounded_pause_are_rejected(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before = (live / "app.py").read_bytes()
    env["SCREENSHOT_APPLY_CRASH_AT"] = "app.py"
    started = time.time()
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert time.time() - started < 2
    assert proc.returncode != 0
    assert "HOOKS=rejected" in proc.stdout
    assert "RECOVERY=not-needed" in proc.stdout
    assert "RECOVERY=source-restored" not in proc.stdout
    assert (live / "app.py").read_bytes() == before
    assert not (live / "screenshots.py").exists()

    live2, env2 = _prepare_stopped(tmp_path / "pause")
    before2 = (live2 / "app.py").read_bytes()
    env2["SCREENSHOT_APPLY_COPY_PAUSE_SECONDS"] = "99999"
    started = time.time()
    proc = _run("screenshot_host_offline_deploy.sh", env2)
    assert time.time() - started < 2
    assert "HOOKS=rejected" in proc.stdout
    assert (live2 / "app.py").read_bytes() == before2


def test_harness_pause_cannot_exceed_one_second(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before = (live / "app.py").read_bytes()
    run_id = f"screenshot-run-{os.getpid()}-{'ef' * 8}"
    run_dir = Path(env["HOME"]) / run_id
    run_dir.mkdir()
    started = time.time()
    proc = subprocess.run(
        [
            env["FIXTURE_PYTHON"], str(ROOT / "scripts" / "screenshot_host_apply.py"),
            "--root", str(live), "--source", str(ROOT),
            "--manifest", str(ROOT / "docs" / "screenshot-install-manifest.json"),
            "--apply", "--intent", str(run_dir / "intent.json"), "--run-id", run_id,
            "--out", str(run_dir / "apply.json"),
        ],
        env={**os.environ, "SCREENSHOT_APPLY_TEST_HARNESS": "1", "SCREENSHOT_APPLY_COPY_PAUSE_SECONDS": "30"},
        capture_output=True, text=True, check=False,
    )
    assert time.time() - started < 2
    assert proc.returncode != 0
    assert (live / "app.py").read_bytes() == before
    assert not (live / "screenshots.py").exists()


def test_apply_ignores_crash_hook_without_harness(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before = (live / "app.py").read_bytes()
    run_id = f"screenshot-run-{os.getpid()}-{'a1' * 8}"
    run_dir = Path(env["HOME"]) / run_id
    run_dir.mkdir()
    proc = subprocess.run(
        [
            env["FIXTURE_PYTHON"], str(ROOT / "scripts" / "screenshot_host_apply.py"),
            "--root", str(live), "--source", str(ROOT),
            "--manifest", str(ROOT / "docs" / "screenshot-install-manifest.json"),
            "--apply", "--intent", str(run_dir / "intent.json"), "--run-id", run_id,
            "--out", str(run_dir / "apply.json"),
        ],
        env={**os.environ, "SCREENSHOT_APPLY_CRASH_AT": "app.py"},
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (live / "screenshots.py").is_file()
    assert (live / "app.py").read_bytes() != before


def test_kill_after_first_copy_restores_from_the_intent(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before = {rel: (live / rel).read_bytes() for rel in ("app.py", "static/index.html", "Dockerfile", "README.md", ".env", "data/url_jobs.json")}
    hook = tmp_path / "pyhook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(
        "import os, signal, shutil\n"
        "_real = shutil.copy2\n"
        "def _copy2(src, dst, *args, **kwargs):\n"
        "    _real(src, dst, *args, **kwargs)\n"
        "    live = os.environ.get('SCREENSHOT_KILL_LIVE_ROOT', '')\n"
        "    if os.environ.get('SCREENSHOT_KILL_AFTER_FIRST_COPY') == '1' and live:\n"
        "        if os.path.realpath(dst) == os.path.realpath(os.path.join(live, 'app.py')):\n"
        "            os.kill(os.getpid(), signal.SIGKILL)\n"
        "shutil.copy2 = _copy2\n",
        encoding="utf-8",
    )
    env["PYTHONPATH"] = str(hook)
    env["SCREENSHOT_KILL_AFTER_FIRST_COPY"] = "1"
    env["SCREENSHOT_KILL_LIVE_ROOT"] = str(live)
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert proc.returncode == 137, proc.stdout + proc.stderr
    assert "RECOVERY=source-restored" in proc.stdout.splitlines()
    assert "RECOVERY=not-needed" not in proc.stdout.splitlines()
    assert "INSTALL=verified-c943" in proc.stdout.splitlines()
    assert "RESTART=allowed" in proc.stdout.splitlines()
    assert "RESTART=not-run" not in proc.stdout.splitlines()
    assert "AUTHORIZATION=original-window" in proc.stdout.splitlines()
    assert any(line.startswith("BOOTSTRAP=not-run ") for line in proc.stdout.splitlines())
    for rel, data in before.items():
        assert (live / rel).read_bytes() == data
    assert not (live / "screenshots.py").exists()
    assert not (live / "docs" / "screenshot-install-manifest.json").exists()
    runs = [path for path in Path(env["HOME"]).glob("screenshot-run-*") if (path / "intent.json").is_file()]
    assert len(runs) == 1
    assert not (runs[0] / "apply.json").exists()
    assert "bootstrap" not in (tmp_path / "launchctl.log").read_text(encoding="utf-8")


def _merged(env: dict[str, str]) -> dict[str, str]:
    merged = os.environ.copy()
    for key in (
        "SCREENSHOT_OFFLINE_AUTHORIZATION",
        "SCREENSHOT_APPLY_CRASH_AT",
        "SCREENSHOT_APPLY_COPY_PAUSE_SECONDS",
        "SCREENSHOT_APPLY_TEST_HARNESS",
        "PYTHONPATH",
        "SCREENSHOT_KILL_AFTER_FIRST_COPY",
        "SCREENSHOT_KILL_LIVE_ROOT",
    ):
        merged.pop(key, None)
    merged.update(env)
    return merged


def _doc_fence(name: str) -> str:
    text = (ROOT / "docs" / "SCREENSHOT_DEPLOY.md").read_text(encoding="utf-8")
    marker = f"# fixture: {name}\n"
    start = text.index(marker)
    end = text.index("```", start)
    return text[start:end]


def test_operator_group_kill_then_explicit_old_intent_recovery(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    before = {rel: (live / rel).read_bytes() for rel in ("app.py", "static/index.html", "Dockerfile", "README.md", ".env", "data/url_jobs.json")}
    new_app = (ROOT / "app.py").read_bytes()
    hook = tmp_path / "stop-hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(
        "import os, signal, shutil\n"
        "_real = shutil.copy2\n"
        "def _copy2(src, dst, *args, **kwargs):\n"
        "    _real(src, dst, *args, **kwargs)\n"
        "    live = os.environ.get('SCREENSHOT_KILL_LIVE_ROOT', '')\n"
        "    if os.environ.get('SCREENSHOT_KILL_AFTER_FIRST_COPY') == '1' and live:\n"
        "        if os.path.realpath(dst) == os.path.realpath(os.path.join(live, 'app.py')):\n"
        "            os.kill(os.getpid(), signal.SIGSTOP)\n"
        "shutil.copy2 = _copy2\n",
        encoding="utf-8",
    )
    stopped = dict(env)
    stopped["PYTHONPATH"] = str(hook)
    stopped["SCREENSHOT_KILL_AFTER_FIRST_COPY"] = "1"
    stopped["SCREENSHOT_KILL_LIVE_ROOT"] = str(live)
    proc = subprocess.Popen(
        ["bash", str(ROOT / "scripts" / "screenshot_host_offline_deploy.sh")],
        env=_merged(stopped),
        start_new_session=True,
        text=True,
    )
    intent = None
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if (live / "app.py").read_bytes() == new_app:
                found = list(Path(env["HOME"]).glob("screenshot-run-*/intent.json"))
                if found:
                    intent = found[0]
                    break
            time.sleep(0.01)
        assert intent is not None
        os.killpg(os.getpgid(proc.pid), 9)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except OSError:
            pass
        proc.wait(timeout=5)
    assert (live / "app.py").read_bytes() == new_app
    assert (live / "Dockerfile").read_bytes() == before["Dockerfile"]
    assert not (live / "screenshots.py").exists()
    assert not (intent.parent / "apply.json").exists()
    wrong = tmp_path / "wrong-backup"
    wrong.mkdir()
    (wrong / "app.py").write_text("WRONG-SOURCE\n", encoding="utf-8")
    (Path(env["HOME"]) / "screenshot-apply.json").write_text(
        json.dumps({"ok": False, "backup": str(wrong)}) + "\n",
        encoding="utf-8",
    )
    env_again = dict(env)
    env_again["DEST"] = str(tmp_path / "outside" / "second-backup")
    again = _run("screenshot_host_offline_deploy.sh", env_again)
    assert "RECOVERY=failed" in again.stdout.splitlines(), again.stdout + again.stderr
    assert "RESTART=not-allowed" in again.stdout.splitlines()
    assert "RESTART=allowed" not in again.stdout.splitlines()
    assert (live / "app.py").read_bytes() == new_app
    refused = _run("screenshot_host_offline_recover.sh", env)
    assert refused.returncode != 0
    assert "RECOVERY=failed" in refused.stdout.splitlines()
    assert "RESTART=not-allowed" in refused.stdout.splitlines()
    assert (live / "app.py").read_bytes() == new_app
    recover_env = dict(env)
    recover_env["RUN_DIR"] = str(intent.parent)
    recovered = subprocess.run(["bash", "-c", _doc_fence("offline-recover")], env=_merged(recover_env), text=True, capture_output=True, check=False)
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    lines = recovered.stdout.splitlines()
    assert "RECOVERY=source-restored" in lines
    assert "INSTALL=verified-c943" in lines
    assert "RESTART=allowed" in lines
    assert "RESTART=not-run" not in lines
    assert "RESTART=not-allowed" not in lines
    assert "AUTHORIZATION=original-window" in lines
    assert f"RUN_DIR={intent.parent.resolve()}" in lines or f"RUN_DIR={intent.parent}" in lines
    assert any(line == f"BOOTSTRAP=not-run {env['FIXTURE_PLIST_PATH']}" for line in lines)
    for rel in ("app.py", "static/index.html", "Dockerfile", "README.md", ".env", "data/url_jobs.json"):
        assert (live / rel).read_bytes() == before[rel]
    assert not (live / "screenshots.py").exists()
    assert not (live / "docs" / "screenshot-install-manifest.json").exists()
    assert "WRONG-SOURCE" not in (live / "app.py").read_text(encoding="utf-8")
    connection = sqlite3.connect(f"file:{live / 'data' / 'transcripts.db'}?mode=ro", uri=True)
    bodies = [row[0] for row in connection.execute("SELECT transcript FROM transcripts")]
    connection.close()
    assert bodies == ["saved"]
    assert "bootstrap" not in (tmp_path / "launchctl.log").read_text(encoding="utf-8")


def test_documented_rollback_accepts_explicit_py_and_path_python3(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    for rel in ("app.py", "static/index.html", "Dockerfile", "README.md"):
        target = live / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", f"{PARENT}:{rel}"], cwd=ROOT))
    (live / ".env").write_text("SECRET=keep\n", encoding="utf-8")
    backup = live / "backups" / "screenshots-documented"
    for rel in ("app.py", "static/index.html", "Dockerfile", "README.md"):
        dest = backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((live / rel).read_bytes())
    (live / "app.py").write_text("replaced\n", encoding="utf-8")
    base = {"ROOT": str(live), "BACKUP": str(backup), "ARTIFACT": str(ROOT), "HOME": str(tmp_path / "home")}
    (tmp_path / "home").mkdir()
    with_py = subprocess.run(["bash", "-c", _doc_fence("rollback-code")], env=_merged({**base, "PY": str(_venv())}), text=True, capture_output=True, check=False)
    assert with_py.returncode == 0, with_py.stdout + with_py.stderr
    assert "ROLLBACK=ok" in with_py.stdout.splitlines()
    assert "RESTART=no" in with_py.stdout.splitlines()
    assert "RESTART=allowed" not in with_py.stdout.splitlines()
    assert (live / "app.py").read_bytes() == (backup / "app.py").read_bytes()
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    (live / "app.py").write_text("replaced-again\n", encoding="utf-8")
    without_py = _merged(base)
    without_py.pop("PY", None)
    fallback = subprocess.run(["bash", "-c", _doc_fence("rollback-code")], env=without_py, text=True, capture_output=True, check=False)
    assert fallback.returncode == 0, fallback.stdout + fallback.stderr
    assert "ROLLBACK=ok" in fallback.stdout.splitlines()
    assert (live / "app.py").read_bytes() == (backup / "app.py").read_bytes()
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    pack = subprocess.run([str(_venv()), str(ROOT / "scripts" / "screenshot_host_apply.py"), "--help"], text=True, capture_output=True, check=False)
    assert pack.returncode == 0, pack.stderr
    isolated = tmp_path / "installed"
    (isolated / "scripts").mkdir(parents=True)
    (isolated / "scripts" / "screenshot_host_apply.py").write_bytes((ROOT / "scripts" / "screenshot_host_apply.py").read_bytes())
    bare = subprocess.run([str(_venv()), str(isolated / "scripts" / "screenshot_host_apply.py"), "--help"], text=True, capture_output=True, check=False)
    assert bare.returncode != 0
    assert "screenshot_host_offline_checks" in bare.stderr


def test_copy_loop_blocks_four_intruder_writes(tmp_path):
    live, env = _prepare_stopped(tmp_path)
    run_id = f"screenshot-run-{os.getpid()}-{'b2' * 8}"
    run_dir = Path(env["HOME"]) / run_id
    run_dir.mkdir()
    ready = Path(env["HOME"]) / "screenshot-critical-open"
    out = tmp_path / "copy-writer.txt"
    writer = subprocess.Popen(
        [sys.executable, "-c",
         "import sqlite3,sys,time\n"
         "from pathlib import Path\n"
         "db, ready, backups, out = sys.argv[1:]\n"
         "deadline=time.time()+30\n"
         "while not Path(ready).exists():\n"
         "    if time.time()>deadline:\n"
         "        Path(out).write_text('blocked=0\\n'); raise SystemExit(2)\n"
         "    time.sleep(0.005)\n"
         "blocked=0\n"
         "while time.time()<deadline and Path(ready).exists():\n"
         "    copying=any(Path(backups).glob('screenshots-*'))\n"
         "    connection=sqlite3.connect(db, timeout=0.05)\n"
         "    try:\n"
         "        connection.execute(\"INSERT INTO transcripts VALUES ('9','intruder')\")\n"
         "        connection.commit()\n"
         "        if copying and Path(ready).exists():\n"
         "            Path(out).write_text('committed\\n'); raise SystemExit(3)\n"
         "        break\n"
         "    except sqlite3.OperationalError:\n"
         "        if copying and Path(ready).exists():\n"
         "            blocked += 1\n"
         "    finally:\n"
         "        connection.close()\n"
         "Path(out).write_text(f'blocked={blocked}\\n')\n",
         str(live / "data" / "transcripts.db"),
         str(ready),
         str(live / "backups"),
         str(out)],
    )
    try:
        proc = subprocess.run(
            [
                env["FIXTURE_PYTHON"], str(ROOT / "scripts" / "screenshot_host_offline_checks.py"),
                "guard", "--db", str(live / "data" / "transcripts.db"), "--ready", str(ready),
                "--", env["FIXTURE_PYTHON"], str(ROOT / "scripts" / "screenshot_host_apply.py"),
                "--root", str(live), "--source", str(ROOT),
                "--manifest", str(ROOT / "docs" / "screenshot-install-manifest.json"),
                "--apply", "--intent", str(run_dir / "intent.json"), "--run-id", run_id,
                "--out", str(run_dir / "apply.json"),
            ],
            env={**os.environ, "SCREENSHOT_APPLY_TEST_HARNESS": "1", "SCREENSHOT_APPLY_COPY_PAUSE_SECONDS": "0.8"},
            capture_output=True, text=True, check=False,
        )
    finally:
        writer.wait(timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = out.read_text(encoding="utf-8")
    assert text.startswith("blocked=")
    assert int(text.split("=", 1)[1]) >= 4
    snap = sqlite3.connect(f"file:{live / 'data' / 'transcripts.db'}?mode=ro", uri=True)
    bodies = [row[0] for row in snap.execute("SELECT transcript FROM transcripts")]
    snap.close()
    assert "saved" in bodies


def _replace_field(text: str, key: str, value: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith(key + "\t"):
            lines.append(f"{key}\t{value}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"
