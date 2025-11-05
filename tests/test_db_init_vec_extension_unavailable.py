import types
import writer_studio.persistence.db as db


def test_init_db_logs_when_vec_extension_unavailable(tmp_path, monkeypatch):
    db_file = tmp_path / "db_init_vec_unavailable.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))

    # Provide a fake sqlite_vec module whose load() raises
    fake_mod = types.SimpleNamespace()
    def fake_load(con):
        raise RuntimeError("fail to load vec0")
    fake_mod.load = fake_load
    monkeypatch.setitem(__import__("sys").modules, "sqlite_vec", fake_mod)

    # init_db should catch the load error and also fail to create virtual table
    db.init_db()