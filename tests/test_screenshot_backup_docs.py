"""Run the documented deploy sequence on an isolated tree. Not a host install."""
from __future__ import annotations

import hashlib
import json
import os
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


def _service_bin(tmp: Path, plist: Path) -> Path:
    bindir = tmp / "bin"
    bindir.mkdir()
    python_log = tmp / "python-invocations.log"
    wrapper = tmp / "service-python-from-launchctl"
    wrapper.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$0\" >> \"$FIXTURE_PYTHON_LOG\"\n"
        "exec \"$REAL_PYTHON\" \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
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
    plist.write_text(
        "<?xml version=\"1.0\"?><plist><dict><key>Label</key><string>com.epic.transcript-api</string></dict></plist>\n",
        encoding="utf-8",
    )
    python_log.write_text("", encoding="utf-8")
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
        "FIXTURE_PYTHON": str(tmp / "service-python-from-launchctl"),
        "FIXTURE_PYTHON_LOG": str(tmp / "python-invocations.log"),
        "FIXTURE_LAUNCHCTL_LOG": str(tmp / "launchctl.log"),
        "REAL_PYTHON": sys.executable,
    }


def _baseline_tree(live: Path) -> None:
    for rel in BASELINE_FILES:
        target = live / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", f"{PARENT}:{rel}"], cwd=ROOT))


def test_deploy_sequence_succeeds_and_code_rollback_keeps_newer_data(tmp_path):
    doc = DOC.read_text(encoding="utf-8")
    commands = _fence("deploy-sequence") + _fence("rollback-code")
    assert "restore-database" not in doc
    assert "rm -rf \"$ROOT/data" not in doc
    assert "/path/to/artifact" not in doc
    assert "bootout" not in commands
    assert "kickstart" not in commands
    assert "launchctl print" in commands
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
    dry = json.loads((home / "screenshot-apply-dry-run.json").read_text(encoding="utf-8"))
    applied = json.loads((home / "screenshot-apply.json").read_text(encoding="utf-8"))
    assert dry["wrote"] is False
    assert applied["ok"] is True and applied["wrote"] is True and applied["restart"] is False
    assert "data/transcripts.db-wal" in applied["volatile_runtime_not_a_rollback_trigger"]
    launch_log = (tmp_path / "launchctl.log").read_text(encoding="utf-8")
    assert launch_log.splitlines() == ["print gui/501/com.epic.transcript-api"]
    assert str(tmp_path / "service-python-from-launchctl") in (tmp_path / "python-invocations.log").read_text(encoding="utf-8")

    (live / "data" / "url_jobs.json").write_text('{"drift":"after-install"}\n', encoding="utf-8")
    holder.execute("INSERT INTO transcripts VALUES ('3', 'after-install')")
    holder.commit()
    rolled = _run("rollback-code", {"ROOT": str(live), "BACKUP": applied["backup"]})
    assert rolled.returncode == 0, rolled.stderr
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
    assert (tmp_path / "home" / "screenshot-preflight.json").is_file()
    assert not (tmp_path / "home" / "screenshot-apply.json").exists()
    assert "bootout" not in (tmp_path / "launchctl.log").read_text(encoding="utf-8")
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
    assert not (dest / "SHA256SUMS").exists()
    assert (live / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    assert not (live / "screenshots.py").exists()
    holder.close()
