import sqlite3
from pathlib import Path

DB_PATH = Path("/data/hoas.db")
_conn = None

def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn

def init_db():
    db = get_db()

    db.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        device_id   TEXT PRIMARY KEY,
        child_name  TEXT NOT NULL,
        token       TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        last_seen   TEXT,
        meta_json   TEXT NOT NULL DEFAULT '{}'
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS commands (
        cmd_id       TEXT PRIMARY KEY,
        device_id    TEXT NOT NULL,
        name         TEXT NOT NULL,
        params_json  TEXT NOT NULL DEFAULT '{}',
        status       TEXT NOT NULL,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL,
        result_json  TEXT,
        error_text   TEXT,
        FOREIGN KEY(device_id) REFERENCES devices(device_id)
    )
    """)

    db.commit()
