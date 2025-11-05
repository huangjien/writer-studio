import os

import writer_studio.persistence.db as db


def test_ensure_dir_fallback(monkeypatch, tmp_path):
    # Point DB_PATH to a non-existent directory to trigger makedirs
    target = tmp_path / "no_write" / "evals.db"
    monkeypatch.setattr(db, "DB_PATH", str(target))

    # Simulate OSError on os.makedirs to force fallback path
    # Allow fallback ./data creation but fail for the tmp_path base
    original_makedirs = os.makedirs

    def _mock_makedirs(path, exist_ok=False):
        if str(path).startswith(str(tmp_path)):
            raise OSError("permission denied")
        return original_makedirs(path, exist_ok=exist_ok)

    monkeypatch.setattr(os, "makedirs", _mock_makedirs)

    # Call init_db which invokes _ensure_dir and handles fallback
    db.init_db()

    # After fallback, DB_PATH should point to local ./data with preserved filename
    assert db.DB_PATH.endswith(os.path.join("data", "evals.db"))