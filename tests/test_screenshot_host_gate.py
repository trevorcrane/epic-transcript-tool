"""The host installer must refuse drifted files and must not touch transcript data."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

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
    assert report["protected_unchanged"] is True
    assert report["protected_before"][".env"]["sha256"] == report["protected_after"][".env"]["sha256"]
    assert report["restart"] is False


def _small_host(tmp_path, monkeypatch, app_text="reviewed baseline\n", shots_text="shots\n", new_app="new app\n"):
    baseline = _sha(app_text)
    _use_small_gate(monkeypatch, baseline, _sha(new_app), _sha(shots_text))
    host = tmp_path / "host"
    source = tmp_path / "source"
    host.mkdir()
    (host / "app.py").write_text(app_text, encoding="utf-8")
    (host / ".gitignore").write_text("data/*.db\n", encoding="utf-8")
    (host / "data").mkdir()
    (host / "data" / "transcripts.db").write_text("db", encoding="utf-8")
    (host / "data" / "transcripts").mkdir()
    (host / "data" / "transcripts" / "kept.txt").write_text("existing transcript text\n", encoding="utf-8")
    (host / ".env").write_text("SECRET=keep\n", encoding="utf-8")
    source.mkdir()
    (source / "app.py").write_text(new_app, encoding="utf-8")
    (source / "screenshots.py").write_text(shots_text, encoding="utf-8")
    manifest = _manifest(source, {"app.py": _sha(new_app), "screenshots.py": _sha(shots_text)})
    return host, source, manifest


def test_gitignore_symlink_does_not_change_env(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    fake_env = outside / "fake.env"
    fake_env.write_text("SENTINEL\n", encoding="utf-8")
    before_fake = fake_env.read_bytes()
    before_env = (host / ".env").read_bytes()
    (host / ".gitignore").unlink()
    (host / ".gitignore").symlink_to(host / ".env")
    outside_names = sorted(path.name for path in outside.iterdir())
    report = apply_mod.apply_tree(host, source, manifest, True)
    assert report["wrote"] is False
    assert report["restart"] is False
    assert (host / ".env").read_bytes() == before_env
    assert fake_env.read_bytes() == before_fake
    assert report["protected_before"][".env"] == report["protected_after"][".env"]
    assert report["protected_unchanged"] is True
    assert not (host / "screenshots.py").exists()
    assert sorted(path.name for path in outside.iterdir()) == outside_names


def test_ancestor_and_backup_symlinks_do_not_write_outside(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    new_index = "new index\n"
    monkeypatch.setattr(apply_mod, "INSTALL_PATHS", ("app.py", "screenshots.py", "static/index.html"))
    (source / "static").mkdir()
    (source / "static" / "index.html").write_text(new_index, encoding="utf-8")
    manifest.write_text(json.dumps({"install": {
        "app.py": _sha("new app\n"),
        "screenshots.py": _sha("shots\n"),
        "static/index.html": _sha(new_index),
    }}), encoding="utf-8")
    outside = tmp_path / "outside-static"
    outside.mkdir()
    outside_index = outside / "index.html"
    outside_index.write_text("baseline index\n", encoding="utf-8")
    outside_backup = tmp_path / "outside-backup"
    outside_backup.mkdir()
    (host / "static").symlink_to(outside, target_is_directory=True)
    (host / "backups").symlink_to(outside_backup, target_is_directory=True)
    before_index = outside_index.read_bytes()
    report = apply_mod.apply_tree(host, source, manifest, True)
    assert report["wrote"] is False
    assert report["restart"] is False
    assert "static" in report["symlink_blocked"]
    assert outside_index.read_bytes() == before_index
    assert list(outside_backup.iterdir()) == []
    assert (host / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"
    assert (host / "data" / "transcripts.db").read_text(encoding="utf-8") == "db"
    assert (host / "data" / "transcripts" / "kept.txt").read_text(encoding="utf-8") == "existing transcript text\n"
    assert report["protected_unchanged"] is True


def test_leaf_symlink_is_not_followed(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_app = outside / "app.py"
    outside_app.write_text("reviewed baseline\n", encoding="utf-8")
    (host / "app.py").unlink()
    (host / "app.py").symlink_to(outside_app)
    before = outside_app.read_bytes()
    report = apply_mod.apply_tree(host, source, manifest, True)
    assert report["wrote"] is False
    assert outside_app.read_bytes() == before
    assert (host / ".env").read_text(encoding="utf-8") == "SECRET=keep\n"


def test_copy_failure_restores_every_replaced_file(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    before_app = (host / "app.py").read_bytes()
    before_env = (host / ".env").read_bytes()
    before_db = (host / "data" / "transcripts.db").read_bytes()
    before_text = (host / "data" / "transcripts" / "kept.txt").read_bytes()
    before_ignore = (host / ".gitignore").read_bytes()
    original = apply_mod.shutil.copy2

    def crash(src, dst, *args, **kwargs):
        if Path(dst).name == "screenshots.py" and "backups" not in Path(dst).parts:
            raise RuntimeError("simulated crash during copy")
        return original(src, dst, *args, **kwargs)

    monkeypatch.setattr(apply_mod.shutil, "copy2", crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        apply_mod.apply_tree(host, source, manifest, True)
    assert (host / "app.py").read_bytes() == before_app
    assert not (host / "screenshots.py").exists()
    assert (host / ".env").read_bytes() == before_env
    assert (host / "data" / "transcripts.db").read_bytes() == before_db
    assert (host / "data" / "transcripts" / "kept.txt").read_bytes() == before_text
    assert (host / ".gitignore").read_bytes() == before_ignore


def test_empty_manifest_does_not_copy(tmp_path, monkeypatch):
    host, source, _manifest = _small_host(tmp_path, monkeypatch)
    empty = source / "empty.json"
    empty.write_text(json.dumps({"install": {}}), encoding="utf-8")
    (source / "app.py").write_text("MALICIOUS APP\n", encoding="utf-8")
    report = apply_mod.apply_tree(host, source, empty, True)
    assert report["wrote"] is False
    assert report["ok"] is False
    assert (host / "app.py").read_text(encoding="utf-8") == "reviewed baseline\n"
    assert not (host / "screenshots.py").exists()
