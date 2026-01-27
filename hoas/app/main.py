from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from datetime import datetime
import uuid
import json

from .db import init_db, get_db
from .auth import generate_token
from .ws import register, unregister, send_command, list_clients

app = FastAPI()


# ✅ Root + Health (damit du immer testen kannst)
@app.get("/")
def root():
    return {"ok": True, "service": "HOAS"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def startup():
    init_db()


# ✅ Pairing: erstellt device_id + token
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


# ✅ Devices anzeigen
@app.get("/api/devices")
def devices():
    db = get_db()
    rows = db.execute("SELECT * FROM devices").fetchall()
    return [dict(r) for r in rows]


# ✅ Debug: Welche Geräte sind wirklich per WebSocket verbunden?
@app.get("/api/ws_clients")
def ws_clients():
    return {"clients": list_clients()}


# ✅ Commands anzeigen (Debug/Monitoring)
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


# ✅ Command an Gerät senden
@app.post("/api/cmd/{device_id}")
async def command(
    device_id: str,
    name: str,
    params: dict = Body(default={})
):
    cmd_id = str(uuid.uuid4())

    db = get_db()
    db.execute(
        "INSERT INTO commands VALUES (?,?,?,?,?,?)",
        (cmd_id, device_id, name, json.dumps(params), "queued", datetime.utcnow().isoformat())
    )
    db.commit()

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

@app.post("/api/kid/points")
def kid_points(child_name: str, delta: int, reason: str = ""):
    # Regel: 1 Punkt = 60 Sekunden (kannst du später konfigurieren)
    delta_seconds = delta * 60

    db = get_db()
    db.execute("INSERT OR IGNORE INTO kids VALUES (?,?,?)", (child_name, 0, 0))
    db.execute("UPDATE kids SET points = points + ?, time_seconds = time_seconds + ? WHERE child_name=?",
               (delta, delta_seconds, child_name))

    tx_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO transactions VALUES (?,?,?,?,?,?)",
        (tx_id, child_name, delta, delta_seconds, reason, datetime.utcnow().isoformat())
    )
    db.commit()

    kid = db.execute("SELECT * FROM kids WHERE child_name=?", (child_name,)).fetchone()
    return dict(kid)

@app.post("/api/kid/start_time")
async def kid_start_time(device_id: str, child_name: str, reason: str = "Zeit läuft"):
    db = get_db()
    row = db.execute("SELECT time_seconds FROM kids WHERE child_name=?", (child_name,)).fetchone()
    if not row:
        return {"error": "kid_not_found"}

    seconds = int(row["time_seconds"])
    if seconds <= 0:
        return {"error": "no_time"}

    # Zeit “verbrauchen” (MVP: direkt auf 0 setzen)
    db.execute("UPDATE kids SET time_seconds=0 WHERE child_name=?", (child_name,))
    db.commit()

    # Command an App
    # nutzt deinen /api/cmd Endpoint:
    # name=START_TIMER params={"seconds":seconds,"reason":reason}
    # -> du kannst hier direkt command() aufrufen, aber sauberer: HTTP intern oder Funktion auslagern
    return {"device_id": device_id, "seconds": seconds, "reason": reason}

# ✅ WebSocket: App verbindet sich so:
# ws://IP:8080/ws?token=TOKEN
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

            if msg.get("type") == "heartbeat":
                state = msg.get("state") or {}
                db.execute(
                    "UPDATE devices SET last_seen=?, state_json=? WHERE device_id=?",
                    (datetime.utcnow().isoformat(), json.dumps(state), device_id)
                )

                db.commit()

            elif msg.get("type") in ("ack", "result"):
                db.execute(
                    "UPDATE commands SET status=? WHERE cmd_id=?",
                    (msg.get("status"), msg.get("cmd_id"))
                )
                db.commit()

    except WebSocketDisconnect:
        unregister(device_id)
    except Exception:
        unregister(device_id)
        try:
            await ws.close()
        except Exception:
            pass

