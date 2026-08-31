import os
import subprocess
import sys
from pathlib import Path


def test_hosted_backend_can_move_runtime_data_dir_without_code_changes(tmp_path):
    data_dir = tmp_path / "transcript-data"
    static_dir = Path(__file__).resolve().parents[1] / "static"
    code = """
import app
print(app.DATA_DIR)
print(app.DB_PATH)
print(app.setup_status()['ready'])
"""
    env = os.environ.copy()
    env["TRANSCRIPT_DATA_DIR"] = str(data_dir)
    env["TRANSCRIPT_STATIC_DIR"] = str(static_dir)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    lines = result.stdout.strip().splitlines()
    assert lines[0] == str(data_dir.resolve())
    assert lines[1] == str((data_dir / "transcripts.db").resolve())
    assert (data_dir / "transcripts.db").exists()
    assert lines[2] in {"True", "False"}
