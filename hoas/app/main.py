from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, HTTPException
from pydantic import BaseModel
from datetime import datetime
import uuid
import json

from .db import init_db, get_db
from .auth import generate_token
from .ws import register, unregister, send_command, get_clients

app = FastAPI()

def now_iso() -> str:
    return datetime.utcnow().isoformat()

@app.on_event("startup")
def startup():
    init_db()

# ----------------------------
# Health
# ----------------------------
@app.get("/")
def root():
    return {"ok": True, "service": "HOAS"}

@app.get("/health")
def health():
    return {"status": "ok"}

def ensure_devices_schema(db):
    # Prüfe vorhandene Spalten
    cols = [r[1] for r in db.execute("PRAGMA table_info(devices)").fetchall()]

    # Alte DB? Dann Spalten nachziehen
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

@app.post("/api/pair")
def pair(child_name: str):
    try:
        db = get_db()

        # ✅ Schema JETZT sicherstellen, egal ob Startup/Migration lief
        ensure_devices_schema(db)

        device_id = str(uuid.uuid4())
        token = generate_token()

        # ✅ Spaltenliste immer explizit
        db.execute(
            "INSERT INTO devices(device_id, child_name, token, created_at, last_seen, meta_json) VALUES (?,?,?,?,?,?)",
            (device_id, child_name, token, now_iso(), None, "{}")
        )
        db.commit()

        return {"device_id": device_id, "token": token, "ws_url": "/ws"}

    except Exception as e:
        print("PAIR ERROR:", repr(e))
        raise HTTPException(status_code=500, detail="pair failed (see addon logs)")

@app.get("/api/devices")
def devices():
    db = get_db()
    rows = db.execute("SELECT * FROM devices").fetchall()
    return [dict(r) for r in rows]

@app.get("/api/ws_clients")
async def ws_clients():
    return {"clients": await get_clients()}

# ----------------------------
# CMD Models
# ----------------------------
class CmdRequest(BaseModel):
    name: str
    params: dict = {}

# ----------------------------
# CMD API
# ----------------------------
@app.post("/api/cmd/{device_id}")
async def cmd_send(device_id: str, req: CmdRequest):
    """
    Erstellt Command, versucht sofort zu senden wenn WS online.
    Status:
      queued -> sent (wenn online) sonst queued
      später: received/running/done/failed via WS messages
    """
    cmd_id = str(uuid.uuid4())
    created = now_iso()

    db = get_db()

    # device existiert?
    dev = db.execute("SELECT 1 FROM devices WHERE device_id=?", (device_id,)).fetchone()
    if not dev:
        raise HTTPException(status_code=404, detail="device_id not found")

    db.execute("""
        INSERT INTO commands(cmd_id, device_id, name, params_json, status, created_at, updated_at, result_json, error_text)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        cmd_id,
        device_id,
        req.name,
        json.dumps(req.params or {}),
        "queued",
        created,
        created,
        None,
        None
    ))
    db.commit()

    payload = {
        "type": "cmd",
        "cmd_id": cmd_id,
        "name": req.name,
        "params": req.params or {}
    }

    sent = False
    try:
        sent = await send_command(device_id, payload)
    except Exception as e:
        # WS existiert vielleicht, aber send fehlgeschlagen -> bleibt queued
        sent = False

    if sent:
        db.execute("UPDATE commands SET status=?, updated_at=? WHERE cmd_id=?",
                   ("sent", now_iso(), cmd_id))
        db.commit()

    return {"cmd_id": cmd_id, "status": "sent" if sent else "queued"}

@app.get("/api/cmd/{cmd_id}")
def cmd_get(cmd_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM commands WHERE cmd_id=?", (cmd_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="cmd_id not found")
    d = dict(row)
    # JSON Felder hübsch
    d["params"] = json.loads(d["params_json"] or "{}")
    d["result"] = json.loads(d["result_json"] or "null") if d["result_json"] else None
    return d

@app.get("/api/device/{device_id}/commands")
def cmd_list(device_id: str, limit: int = 50):
    db = get_db()
    rows = db.execute("""
        SELECT * FROM commands WHERE device_id=?
        ORDER BY created_at DESC
        LIMIT ?
    """, (device_id, int(limit))).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["params"] = json.loads(d["params_json"] or "{}")
        d["result"] = json.loads(d["result_json"] or "null") if d["result_json"] else None
        out.append(d)
    return out

# ----------------------------
# WebSocket
# ----------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str):
    await ws.accept()

    db = get_db()
    device = db.execute("SELECT * FROM devices WHERE token=?", (token,)).fetchone()
    if not device:
        await ws.close()
        return

    device_id = device["device_id"]

    # ✅ Register (WS Instanz wird gemerkt)
    await register(device_id, ws)

    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")

            if t == "heartbeat":
                db.execute("UPDATE devices SET last_seen=? WHERE device_id=?",
                           (now_iso(), device_id))
                db.commit()

            elif t == "ack":
                # status z.B. received/running
                cmd_id = msg.get("cmd_id")
                status = msg.get("status", "received")
                db.execute("UPDATE commands SET status=?, updated_at=? WHERE cmd_id=?",
                           (status, now_iso(), cmd_id))
                db.commit()

            elif t == "result":
                cmd_id = msg.get("cmd_id")
                status = msg.get("status", "done")
                result = msg.get("result")
                err = None
                if status == "failed":
                    err = (result or {}).get("error") if isinstance(result, dict) else "failed"

                db.execute("""
                    UPDATE commands
                    SET status=?, updated_at=?, result_json=?, error_text=?
                    WHERE cmd_id=?
                """, (
                    status,
                    now_iso(),
                    json.dumps(result) if result is not None else None,
                    err,
                    cmd_id
                ))
                db.commit()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("WS error:", e)
    finally:
        await unregister(device_id, ws)
