from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from datetime import datetime
import uuid
import json

from .db import init_db, get_db
from .auth import generate_token
from .ws import register, unregister, send_command, ws_clients

app = FastAPI()


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def now_iso() -> str:
    return datetime.utcnow().isoformat()


def ensure_devices_schema(db):
    cols = [r[1] for r in db.execute("PRAGMA table_info(devices)").fetchall()]

    if "child_name" not in cols:
        db.execute("ALTER TABLE devices ADD COLUMN child_name TEXT NOT NULL DEFAULT ''")
    if "token" not in cols:
        db.execute("ALTER TABLE devices ADD COLUMN token TEXT NOT NULL DEFAULT ''")
    if "created_at" not in cols:
        db.execute("ALTER TABLE devices ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    if "last_seen" not in cols:
        db.execute("ALTER TABLE devices ADD COLUMN last_seen TEXT")
    if "meta_json" not in cols:
        db.execute("ALTER TABLE devices ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}'")

    db.commit()


async def flush_queued_commands(device_id: str):
    db = get_db()
    rows = db.execute("""
        SELECT cmd_id, name, params_json
        FROM commands
        WHERE device_id=? AND status='queued'
        ORDER BY created_at ASC
        LIMIT 50
    """, (device_id,)).fetchall()

    for r in rows:
        payload = {
            "type": "cmd",
            "cmd_id": r["cmd_id"],
            "name": r["name"],
            "params": json.loads(r["params_json"] or "{}")
        }

        try:
            sent = await send_command(device_id, payload)
        except Exception:
            sent = False

        if sent:
            db.execute(
                "UPDATE commands SET status=?, updated_at=? WHERE cmd_id=?",
                ("sent", now_iso(), r["cmd_id"])
            )
            db.commit()
        else:
            break


# -------------------------------------------------
# Startup
# -------------------------------------------------
@app.on_event("startup")
def startup():
    init_db()


# -------------------------------------------------
# Health / Debug
# -------------------------------------------------
@app.get("/")
def root():
    return {"ok": True, "service": "HOAS"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/ws_clients")
def ws_clients_api():
    return {"clients": list(ws_clients.keys())}


# -------------------------------------------------
# Pairing
# -------------------------------------------------
@app.post("/api/pair")
def pair(child_name: str):
    try:
        db = get_db()
        ensure_devices_schema(db)

        device_id = str(uuid.uuid4())
        token = generate_token()

        db.execute(
            """
            INSERT INTO devices(device_id, child_name, token, created_at, last_seen, meta_json)
            VALUES (?,?,?,?,?,?)
            """,
            (device_id, child_name, token, now_iso(), None, "{}")
        )
        db.commit()

        return {
            "device_id": device_id,
            "token": token,
            "ws_url": "/ws"
        }

    except Exception as e:
        print("PAIR ERROR:", repr(e))
        raise HTTPException(status_code=500, detail="pair failed")


# -------------------------------------------------
# Devices
# -------------------------------------------------
@app.get("/api/devices")
def devices():
    db = get_db()
    rows = db.execute("SELECT * FROM devices").fetchall()
    return [dict(r) for r in rows]


# -------------------------------------------------
# CMD API (JSON: name + params)
# -------------------------------------------------
@app.post("/api/cmd/{device_id}")
async def command(device_id: str, body: dict):
    name = body.get("name")
    params = body.get("params", {})

    if not name:
        raise HTTPException(status_code=400, detail="name missing")

    cmd_id = str(uuid.uuid4())
    db = get_db()

    db.execute(
        """
        INSERT INTO commands
        (cmd_id, device_id, name, params_json, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            cmd_id,
            device_id,
            name,
            json.dumps(params),
            "queued",
            now_iso(),
            now_iso(),
        )
    )
    db.commit()

    payload = {
        "type": "cmd",
        "cmd_id": cmd_id,
        "name": name,
        "params": params
    }

    sent = False
    try:
        sent = await send_command(device_id, payload)
    except Exception:
        sent = False

    if sent:
        db.execute(
            "UPDATE commands SET status=?, updated_at=? WHERE cmd_id=?",
            ("sent", now_iso(), cmd_id)
        )
        db.commit()
        return {"cmd_id": cmd_id, "status": "sent"}

    return {"cmd_id": cmd_id, "status": "queued"}


# -------------------------------------------------
# WebSocket
# -------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str):
    await ws.accept()

    db = get_db()
    device = db.execute(
        "SELECT * FROM devices WHERE token=?",
        (token,)
    ).fetchone()

    if not device:
        await ws.close()
        return

    device_id = device["device_id"]
    await register(device_id, ws)

    # 🔥 queued CMDs sofort senden
    await flush_queued_commands(device_id)

    try:
        while True:
            msg = await ws.receive_json()

            if msg.get("type") == "heartbeat":
                db.execute(
                    "UPDATE devices SET last_seen=? WHERE device_id=?",
                    (now_iso(), device_id)
                )
                db.commit()

            elif msg.get("type") in ("ack", "result"):
                db.execute(
                    "UPDATE commands SET status=?, updated_at=? WHERE cmd_id=?",
                    (msg.get("status"), now_iso(), msg.get("cmd_id"))
                )
                db.commit()

    except WebSocketDisconnect:
        unregister(device_id)
