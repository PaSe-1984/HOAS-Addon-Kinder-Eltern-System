from __future__ import annotations

from typing import Dict, Optional
from fastapi import WebSocket

_clients: Dict[str, WebSocket] = {}


async def register(device_id: str, ws: WebSocket) -> None:
    _clients[device_id] = ws


def unregister(device_id: str) -> None:
    _clients.pop(device_id, None)


def list_clients() -> list[str]:
    return list(_clients.keys())


async def send_command(device_id: str, payload: dict) -> bool:
    ws: Optional[WebSocket] = _clients.get(device_id)
    if not ws:
        return False
    try:
        await ws.send_json(payload)
        return True
    except Exception:
        # Verbindung ist tot / send failed → aus Registry entfernen
        unregister(device_id)
        return False
