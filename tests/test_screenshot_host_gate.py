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


SENTINELS = {
    ".env": b"SECRET=keep\n",
    "data/transcripts.db": b"sqlite-bytes",
    "data/url_jobs.json": b'{"drift":"url-jobs"}\n',
    "data/phase3_gemini_usage.json": b'{"drift":"gemini"}\n',
    "data/transcripts/kept.txt": b"existing transcript text\n",
}


def _write_sentinels(root: Path) -> dict[str, str]:
    hashes = {}
    for rel, data in SENTINELS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        hashes[rel] = hashlib.sha256(data).hexdigest()
    return hashes


def test_env_symlink_is_refused_before_write(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / ".env"
    secret.write_bytes(SENTINELS[".env"])
    before = secret.read_bytes()
    (host / ".env").unlink()
    (host / ".env").symlink_to(secret)
    report = apply_mod.apply_tree(host, source, manifest, True)
    assert report["ok"] is False
    assert report["wrote"] is False
    assert report["restart"] is False
    assert ".env" in report["symlink_blocked"]
    assert secret.read_bytes() == before
    assert not (host / "screenshots.py").exists()
    assert (host / "app.py").read_text(encoding="utf-8") == "reviewed baseline\n"
    assert report["protected_before"][".env"]["kind"] == "symlink"


def test_data_directory_symlink_is_refused_before_write(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    outside = tmp_path / "outside-data"
    hashes = _write_sentinels(outside)
    before = {rel: (outside / rel).read_bytes() for rel in SENTINELS}
    (host / "data").rename(tmp_path / "unused-data")
    (host / "data").symlink_to(outside, target_is_directory=True)
    report = apply_mod.apply_tree(host, source, manifest, False)
    assert report["wrote"] is False
    assert report["restart"] is False
    assert report["ok"] is False
    assert "data" in report["symlink_blocked"]
    assert not (host / "screenshots.py").exists()
    for rel, data in before.items():
        assert (outside / rel).read_bytes() == data
        assert hashlib.sha256(data).hexdigest() == hashes[rel]
    assert report["protected_before"]["data"]["kind"] == "symlink"
    assert "sha256" not in report["protected_before"]["data"]


def test_nested_data_symlinks_are_refused_before_write(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    outside = tmp_path / "outside-nested"
    outside.mkdir()
    jobs = outside / "url_jobs.json"
    usage = outside / "phase3_gemini_usage.json"
    transcripts = outside / "transcripts"
    transcripts.mkdir()
    kept = transcripts / "kept.txt"
    jobs.write_bytes(SENTINELS["data/url_jobs.json"])
    usage.write_bytes(SENTINELS["data/phase3_gemini_usage.json"])
    kept.write_bytes(SENTINELS["data/transcripts/kept.txt"])
    before = {path: path.read_bytes() for path in (jobs, usage, kept)}
    db_before = (host / "data" / "transcripts.db").read_bytes()
    (host / "data" / "url_jobs.json").symlink_to(jobs)
    (host / "data" / "phase3_gemini_usage.json").symlink_to(usage)
    (host / "data" / "transcripts").rename(tmp_path / "unused-transcripts")
    (host / "data" / "transcripts").symlink_to(transcripts, target_is_directory=True)
    report = apply_mod.apply_tree(host, source, manifest, True)
    assert report["ok"] is False
    assert report["wrote"] is False
    assert report["restart"] is False
    assert "data/url_jobs.json" in report["symlink_blocked"]
    assert "data/phase3_gemini_usage.json" in report["symlink_blocked"]
    assert "data/transcripts" in report["symlink_blocked"]
    assert not (host / "screenshots.py").exists()
    assert (host / "app.py").read_text(encoding="utf-8") == "reviewed baseline\n"
    assert (host / "data" / "transcripts.db").read_bytes() == db_before
    for path, data in before.items():
        assert path.read_bytes() == data


def test_real_protected_sentinels_survive_success_and_crash(tmp_path, monkeypatch):
    host, source, manifest = _small_host(tmp_path, monkeypatch)
    hashes = _write_sentinels(host)
    report = apply_mod.apply_tree(host, source, manifest, True)
    assert report["ok"] is True
    assert report["wrote"] is True
    assert report["restart"] is False
    for rel, digest in hashes.items():
        finger = report["protected_before"][rel]
        assert finger["kind"] == "file"
        assert finger["sha256"] == digest
        assert report["protected_after"][rel]["sha256"] == digest
        assert hashlib.sha256((host / rel).read_bytes()).hexdigest() == digest

    crash_root = tmp_path / "crash"
    crash_root.mkdir()
    host2, source2, manifest2 = _small_host(crash_root, monkeypatch)
    hashes2 = _write_sentinels(host2)
    before_app = (host2 / "app.py").read_bytes()
    original = apply_mod.shutil.copy2

    def crash(src, dst, *args, **kwargs):
        if Path(dst).name == "screenshots.py" and "backups" not in Path(dst).parts:
            raise RuntimeError("simulated crash during copy")
        return original(src, dst, *args, **kwargs)

    monkeypatch.setattr(apply_mod.shutil, "copy2", crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        apply_mod.apply_tree(host2, source2, manifest2, True)
    assert (host2 / "app.py").read_bytes() == before_app
    assert not (host2 / "screenshots.py").exists()
    for rel, digest in hashes2.items():
        assert hashlib.sha256((host2 / rel).read_bytes()).hexdigest() == digest


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
