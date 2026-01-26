from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from datetime import datetime
import uuid
import json

from .db import init_db, get_db
from .auth import generate_token
from .ws import register, unregister, send_command

app = FastAPI()

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

    return {"status": "sent", "cmd_id": cmd_id}

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
