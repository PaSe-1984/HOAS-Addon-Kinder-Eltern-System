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

def _has_column(db: sqlite3.Connection, table: str, col: str) -> bool:
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)

def _add_column_if_missing(db: sqlite3.Connection, table: str, ddl: str):
    col = ddl.split()[0]
    if not _has_column(db, table, col):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

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

    # ✅ Migration (alte DBs)
    _add_column_if_missing(db, "devices", "last_seen TEXT")
    _add_column_if_missing(db, "devices", "meta_json TEXT NOT NULL DEFAULT '{}'")

    _add_column_if_missing(db, "commands", "params_json TEXT NOT NULL DEFAULT '{}'")
    _add_column_if_missing(db, "commands", "updated_at TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(db, "commands", "result_json TEXT")
    _add_column_if_missing(db, "commands", "error_text TEXT")

    db.commit()
