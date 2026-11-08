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
        ready = tmp_path / "home" / "screenshot-critical-open"
        (tmp_path / "home" / "screenshot-critical-open.wait").write_text("1\n", encoding="utf-8")
        writer = subprocess.Popen(
            [sys.executable, "-c",
             "import sqlite3,sys,time\n"
             "from pathlib import Path\n"
             "db, ready, out = sys.argv[1:]\n"
             "deadline=time.time()+30\n"
             "while not Path(ready).exists():\n"
             "    if time.time()>deadline:\n"
             "        Path(out).write_text('missed\\n'); raise SystemExit(2)\n"
             "    time.sleep(0.01)\n"
             "seen=False\n"
             "blocked=False\n"
             "committed=False\n"
             "while time.time()<deadline:\n"
             "    if not Path(ready).exists():\n"
             "        if seen: break\n"
             "        time.sleep(0.005); continue\n"
             "    seen=True\n"
             "    w=sqlite3.connect(db, timeout=0.2)\n"
             "    try:\n"
             "        w.execute(\"INSERT INTO transcripts VALUES ('9','intruder')\")\n"
             "        w.commit(); committed=True; break\n"
             "    except sqlite3.OperationalError:\n"
             "        blocked=True; break\n"
             "    finally:\n"
             "        w.close()\n"
             "if not seen: Path(out).write_text('missed\\n')\n"
             "elif committed: Path(out).write_text('committed\\n')\n"
             "else: Path(out).write_text('blocked\\n')\n"
             "Path(str(ready) + '.attempted').write_text('1\\n')\n",
             str(live / "data" / "transcripts.db"),
             str(tmp_path / "home" / "screenshot-critical-open"),
             str(tmp_path / "writer-result.txt")],
        )
        try:
            deployed = _run("screenshot_host_offline_deploy.sh", env)
        finally:
            writer.wait(timeout=40)
        assert deployed.returncode == 0, deployed.stderr + deployed.stdout
        assert "APPLY=ok" in deployed.stdout
        assert "RESTART=not-run" in deployed.stdout
        assert "RESTART=allowed" not in deployed.stdout
        assert (live / "data" / "url_jobs.json").read_bytes() == jobs_before
        assert (live / ".env").read_bytes() == env_before
        recorded = json.loads((tmp_path / "home" / "screenshot-interrupted-jobs.json").read_text(encoding="utf-8"))
        assert recorded["old_process_can_resume"] is False
        assert recorded["live_jobs_rewritten"] is False
        assert recorded["jobs"] == [{"id": "abc123abc123", "status": "running", "stage": "transcribing"}]
        assert (live / "screenshots.py").is_file()
        home = tmp_path / "home"
        preflight = json.loads((home / "screenshot-preflight.json").read_text(encoding="utf-8"))
        dry = json.loads((home / "screenshot-apply-dry-run.json").read_text(encoding="utf-8"))
        applied = json.loads((home / "screenshot-apply.json").read_text(encoding="utf-8"))
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
    live.mkdir()
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
    env["RECOVERY_BACKUP"] = str(tmp_path / "known-good-c943")
    proc = _run("screenshot_host_offline_deploy.sh", env)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert "RECOVERY=source-restored" in proc.stdout
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
    assert "RECOVERY=failed" in proc.stdout
    assert "RESTART=no" in proc.stdout
    assert "RESTART=allowed" not in proc.stdout
    assert "APPLY=ok" not in proc.stdout
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
        "import json, os, shutil, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.environ['ROOT'])\n"
        "home = Path(os.environ['HOME'])\n"
        "args = sys.argv[1:]\n"
        "out = args[args.index('--out') + 1]\n"
        "if '--apply' not in args:\n"
        "    Path(out).write_text(json.dumps({'ok': True, 'wrote': False, 'restart': False}) + '\\n')\n"
        "    raise SystemExit(0)\n"
        "backup = Path(os.environ['RECOVERY_BACKUP'])\n"
        f"fail = {fail!r}\n"
        "if not fail:\n"
        "    backup.mkdir(parents=True, exist_ok=True)\n"
        "    for rel in ('app.py', 'static/index.html', 'Dockerfile', 'README.md'):\n"
        "        src = root / rel\n"
        "        if src.is_file():\n"
        "            dest = backup / rel\n"
        "            dest.parent.mkdir(parents=True, exist_ok=True)\n"
        "            shutil.copy2(src, dest)\n"
        "(root / 'app.py').write_text('replaced-during-failed-apply\\n')\n"
        "(root / 'screenshots.py').write_text('new\\n')\n"
        "Path(out).write_text(json.dumps({'ok': False, 'wrote': False, 'restored': False, 'restart': False, 'backup': str(backup)}) + '\\n')\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    return artifact


def _replace_field(text: str, key: str, value: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith(key + "\t"):
            lines.append(f"{key}\t{value}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"
