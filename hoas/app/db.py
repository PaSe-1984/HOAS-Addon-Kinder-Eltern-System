import sqlite3
from pathlib import Path

DB_PATH = Path("/data/hoas.db")

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        child_name TEXT,
        token TEXT,
        last_seen TEXT,
        state TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS commands (
        cmd_id TEXT PRIMARY KEY,
        device_id TEXT,
        name TEXT,
        params TEXT,
        status TEXT,
        created_at TEXT
    )
    """)
    
    db.execute("""
    CREATE TABLE IF NOT EXISTS kids (
      child_name TEXT PRIMARY KEY,
      points INTEGER NOT NULL,
      time_seconds INTEGER NOT NULL
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
      id TEXT PRIMARY KEY,
      child_name TEXT NOT NULL,
      delta_points INTEGER NOT NULL,
      delta_seconds INTEGER NOT NULL,
      reason TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
    """)

    db.commit()
