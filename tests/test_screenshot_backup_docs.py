"""Run the documented backup and receipt commands on an isolated fixture."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "SCREENSHOT_DEPLOY.md"


def _fence(name: str) -> str:
    text = DOC.read_text(encoding="utf-8")
    marker = f"# fixture: {name}\n"
    start = text.index(marker)
    end = text.index("```", start)
    return text[start:end]


def _run(name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        ["bash", "-c", _fence(name)],
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _live_tree(root: Path) -> sqlite3.Connection:
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


def _launchctl(bin_dir: Path, plist: Path) -> None:
    script = bin_dir / "launchctl"
    script.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"print\" ] && [ \"$2\" = \"gui/501/com.epic.transcript-api\" ]; then\n"
        "  printf '\\tpath = %s\\n' \"$FIXTURE_PLIST_PATH\"\n"
        "  exit 0\n"
        "fi\n"
        "echo \"launchctl refused $*\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    plist.write_text("<?xml version=\"1.0\"?><plist><dict><key>Label</key><string>com.epic.transcript-api</string></dict></plist>\n", encoding="utf-8")


def test_documented_backup_snapshots_wal_and_verifies_hashes(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    holder = _live_tree(live)
    plist = tmp_path / "service-config" / "from-launchctl-print.plist"
    plist.parent.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _launchctl(bindir, plist)
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
    raw_rows = [row[0] for row in raw.execute("SELECT transcript FROM transcripts")]
    raw.close()
    assert "only-in-wal" not in raw_rows

    proc = _run("outside-backup", {
        "ROOT": str(live),
        "PY": sys.executable,
        "ARTIFACT": str(ROOT),
        "DEST": str(dest),
        "HOME": str(tmp_path / "home"),
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "FIXTURE_PLIST_PATH": str(plist),
    })
    assert proc.returncode == 0, proc.stderr
    listing = (dest / "SHA256SUMS").read_text(encoding="utf-8")
    assert listing.strip()
    assert proc.stdout == listing + listing
    assert "data/transcripts.db-wal" not in listing
    assert "data/transcripts.db-shm" not in listing
    assert not (dest / "data" / "transcripts.db-wal").exists()
    assert not (dest / "data" / "transcripts.db-shm").exists()
    solo = tmp_path / "opened-snapshot.db"
    solo.write_bytes((dest / "data" / "transcripts.db").read_bytes())
    snap = sqlite3.connect(f"file:{solo}?mode=ro", uri=True)
    snap_rows = [row[0] for row in snap.execute("SELECT transcript FROM transcripts ORDER BY id")]
    snap.close()
    assert not (dest / "data" / "transcripts.db-wal").exists()
    assert not (dest / "data" / "transcripts.db-shm").exists()
    assert snap_rows == ["already-in-main", "only-in-wal"]
    assert (dest / "launchd.plist").read_bytes() == plist.read_bytes()
    assert "Library/LaunchAgents" not in str(plist)
    for rel, digest in before.items():
        assert _sha(live / rel) == digest
    assert (live / "data" / "transcripts.db-shm").is_file()
    holder.close()

    restore = tmp_path / "restore"
    subprocess.check_call(["cp", "-a", str(live), str(restore)])
    restored = _run("restore-database", {"ROOT": str(restore), "DEST": str(dest)})
    assert restored.returncode == 0, restored.stderr
    assert not (restore / "data" / "transcripts.db-wal").exists()
    assert not (restore / "data" / "transcripts.db-shm").exists()
    opened = sqlite3.connect(f"file:{restore / 'data' / 'transcripts.db'}?mode=ro", uri=True)
    restored_rows = [row[0] for row in opened.execute("SELECT transcript FROM transcripts ORDER BY id")]
    opened.close()
    assert restored_rows == ["already-in-main", "only-in-wal"]
    assert (restore / "data" / "url_jobs.json").read_text(encoding="utf-8") == '{"drift":"url-jobs"}\n'
    assert (restore / "data" / "transcripts" / "kept.txt").read_text(encoding="utf-8") == "existing transcript text\n"


def test_backup_command_fails_closed_without_a_hash_listing(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    holder = _live_tree(live)
    dest = tmp_path / "outside" / "failed-backup"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    launchctl = bindir / "launchctl"
    launchctl.write_text("#!/bin/sh\necho 'launchctl unavailable' >&2\nexit 1\n", encoding="utf-8")
    launchctl.chmod(0o755)
    proc = _run("outside-backup", {
        "ROOT": str(live),
        "PY": sys.executable,
        "ARTIFACT": str(ROOT),
        "DEST": str(dest),
        "HOME": str(tmp_path / "home"),
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "FIXTURE_PLIST_PATH": str(tmp_path / "missing.plist"),
    })
    assert proc.returncode != 0
    assert not (dest / "SHA256SUMS").exists()
    assert "SECRET=keep" in (live / ".env").read_text(encoding="utf-8")
    holder.close()
    assert "tee \"$DEST/SHA256SUMS\"" not in DOC.read_text(encoding="utf-8")
    assert "not path.is_symlink" not in DOC.read_text(encoding="utf-8")


def test_dry_run_and_apply_receipts_stay_separate(tmp_path):
    home = tmp_path / "home"
    host = tmp_path / "host"
    home.mkdir()
    host.mkdir()
    env = {
        "ROOT": str(host),
        "PY": sys.executable,
        "ARTIFACT": str(ROOT),
        "HOME": str(home),
    }
    dry = _run("apply-dry-run", env)
    apply = _run("apply", env)
    dry_path = home / "screenshot-apply-dry-run.json"
    apply_path = home / "screenshot-apply.json"
    assert dry.returncode != 0
    assert apply.returncode != 0
    assert dry_path.is_file()
    assert apply_path.is_file()
    dry_bytes = dry_path.read_bytes()
    assert b'"wrote": false' in dry_bytes
    assert b'"wrote": false' in apply_path.read_bytes()
    assert dry_path.read_bytes() == dry_bytes
    doc = DOC.read_text(encoding="utf-8")
    assert "screenshot-apply-dry-run.json" in doc
    assert "screenshot-apply.json" in doc
    assert doc.count("--out \"$HOME/screenshot-apply.json\"") == 1
