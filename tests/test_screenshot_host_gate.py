"""The host installer must refuse drifted files and must not touch transcript data."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import screenshot_host_apply as apply_mod  # noqa: E402
import screenshot_host_preflight as pre  # noqa: E402


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _use_small_gate(monkeypatch, baseline: str, new_app: str, new_shot: str) -> None:
    monkeypatch.setattr(pre, "BASELINE", {"app.py": baseline})
    monkeypatch.setattr(pre, "NEW_FILES", ("screenshots.py",))
    monkeypatch.setattr(apply_mod, "INSTALL_PATHS", ("app.py", "screenshots.py"))


def _manifest(source: Path, install: dict[str, str]) -> Path:
    path = source / "docs" / "screenshot-install-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"install": install}), encoding="utf-8")
    return path


def test_classify_states():
    assert pre.classify(False, None, "base", "new") == "missing"
    assert pre.classify(False, None, None, "new") == "ready_to_add"
    assert pre.classify(True, "base", "base", "new") == "ready_to_replace"
    assert pre.classify(True, "new", "base", "new") == "already_installed"
    assert pre.classify(True, "other", "base", "new") == "drift"


def test_apply_stops_when_host_bytes_differ(tmp_path, monkeypatch):
    baseline = _sha("reviewed baseline\n")
    _use_small_gate(monkeypatch, baseline, _sha("new app\n"), _sha("shots\n"))
    host = tmp_path / "host"
    source = tmp_path / "source"
    host.mkdir()
    (host / "app.py").write_text("host specific edit\n", encoding="utf-8")
    (host / "data").mkdir()
    (host / "data" / "transcripts.db").write_text("db", encoding="utf-8")
    (host / ".env").write_text("SECRET=keep\n", encoding="utf-8")
    source.mkdir()
    (source / "app.py").write_text("new app\n", encoding="utf-8")
    (source / "screenshots.py").write_text("shots\n", encoding="utf-8")
    manifest = _manifest(source, {"app.py": _sha("new app\n"), "screenshots.py": _sha("shots\n")})
    report = apply_mod.apply_tree(host, source, manifest, apply=True)
    assert report["ok"] is False
    assert report["wrote"] is False
    assert (host / "app.py").read_text(encoding="utf-8") == "host specific edit\n"
    assert not (host / "screenshots.py").exists()
    assert (host / "data" / "transcripts.db").read_text(encoding="utf-8") == "db"
    assert (host / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"


def test_apply_backs_up_baseline_and_leaves_database(tmp_path, monkeypatch):
    baseline = _sha("reviewed baseline\n")
    _use_small_gate(monkeypatch, baseline, _sha("new app\n"), _sha("shots\n"))
    host = tmp_path / "host"
    source = tmp_path / "source"
    host.mkdir()
    (host / "app.py").write_text("reviewed baseline\n", encoding="utf-8")
    (host / ".gitignore").write_text("data/*.db\n", encoding="utf-8")
    (host / "data").mkdir()
    (host / "data" / "transcripts.db").write_text("db", encoding="utf-8")
    (host / ".env").write_text("SECRET=keep\n", encoding="utf-8")
    source.mkdir()
    (source / "app.py").write_text("new app\n", encoding="utf-8")
    (source / "screenshots.py").write_text("shots\n", encoding="utf-8")
    manifest = _manifest(source, {"app.py": _sha("new app\n"), "screenshots.py": _sha("shots\n")})
    plan = apply_mod.apply_tree(host, source, manifest, apply=False)
    assert plan["ok"] is True
    assert plan["wrote"] is False
    assert (host / "app.py").read_text(encoding="utf-8") == "reviewed baseline\n"
    report = apply_mod.apply_tree(host, source, manifest, apply=True)
    assert report["ok"] is True
    assert report["wrote"] is True
    assert (host / "app.py").read_text(encoding="utf-8") == "new app\n"
    assert (host / "screenshots.py").read_text(encoding="utf-8") == "shots\n"
    backup = Path(report["backup"])
    assert (backup / "app.py").read_text(encoding="utf-8") == "reviewed baseline\n"
    assert (host / "data" / "transcripts.db").read_text(encoding="utf-8") == "db"
    assert (host / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    assert "data/screenshots/" in (host / ".gitignore").read_text(encoding="utf-8")
    assert "backups/" in (host / ".gitignore").read_text(encoding="utf-8")
    assert "data/*.db" in (host / ".gitignore").read_text(encoding="utf-8")
