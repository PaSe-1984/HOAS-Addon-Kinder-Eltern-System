from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from datetime import datetime
import uuid
import json

from .db import init_db, get_db
from .auth import generate_token
from .ws import register, unregister, send_command, list_clients

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True, "service": "HOAS"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.on_event("startup")
def startup():
    init_db()

@app.post("/api/pair")
def pair(child_name: str):
    device_id = str(uuid.uuid4())
    token = generate_token()

    db = get_db()
    db.execute(
        "INSERT INTO devices VALUES (?,?,?,?,?)",
        (device_id, child_name, token, datetime.utcnow().isoformat(), "{}")
    )
    db.commit()

    return {
        "device_id": device_id,
        "token": token,
        "ws_url": "/ws"
    }

@app.get("/api/devices")
def devices():
    db = get_db()
    rows = db.execute("SELECT * FROM devices").fetchall()
    return [dict(r) for r in rows]

@app.get("/api/commands")
def commands():
    db = get_db()
    rows = db.execute("SELECT * FROM commands ORDER BY created_at DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]

@app.get("/api/commands/{device_id}")
def commands_for_device(device_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM commands WHERE device_id=? ORDER BY created_at DESC LIMIT 50",
        (device_id,)
    ).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/cmd/{device_id}")
async def command(device_id: str, name: str, params: dict = {}):
    cmd_id = str(uuid.uuid4())

    db = get_db()
    db.execute(
        "INSERT INTO commands VALUES (?,?,?,?,?,?)",
        (cmd_id, device_id, name, json.dumps(params), "queued", datetime.utcnow().isoformat())
    )
    db.commit()

    await send_command(device_id, {
        "type": "cmd",
        "cmd_id": cmd_id,
        "name": name,
        "params": params
    })
    
        ok = await send_command(device_id, {
        "type": "cmd",
        "cmd_id": cmd_id,
        "name": name,
        "params": params
    })

    if not ok:
        db.execute(
            "UPDATE commands SET status=? WHERE cmd_id=?",
            ("no_client", cmd_id)
        )
        db.commit()
        return {"status": "no_client", "cmd_id": cmd_id}

    return {"status": "sent", "cmd_id": cmd_id}


    return {"status": "sent", "cmd_id": cmd_id}

@app.get("/api/ws_clients")
def ws_clients():
    return {"clients": list_clients()}

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

    try:
        while True:
            msg = await ws.receive_json()

            if msg["type"] == "heartbeat":
                db.execute(
                    "UPDATE devices SET last_seen=? WHERE device_id=?",
                    (datetime.utcnow().isoformat(), device_id)
                )
                db.commit()

            elif msg["type"] in ("ack", "result"):
                db.execute(
                    "UPDATE commands SET status=? WHERE cmd_id=?",
                    (msg["status"], msg["cmd_id"])
                )
                db.commit()

    except WebSocketDisconnect:
        unregister(device_id)
