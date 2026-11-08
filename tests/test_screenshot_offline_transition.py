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
        deployed = _run("screenshot_host_offline_deploy.sh", env)
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
        assert "backup-exit=0" in _trace(tmp_path) and "exclusive-exit=0" in _trace(tmp_path)
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


def _replace_field(text: str, key: str, value: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith(key + "\t"):
            lines.append(f"{key}\t{value}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"
