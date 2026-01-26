from fastapi import WebSocket

connections = {}  # device_id -> websocket

async def register(device_id: str, ws: WebSocket):
    connections[device_id] = ws

def unregister(device_id: str):
    connections.pop(device_id, None)

async def send_command(device_id: str, payload: dict):
    ws = connections.get(device_id)
    if ws:
        await ws.send_json(payload)
