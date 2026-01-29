from typing import Dict, List, Optional
from fastapi import WebSocket
import asyncio

_clients: Dict[str, WebSocket] = {}
_lock = asyncio.Lock()

async def register(device_id: str, ws: WebSocket):
    async with _lock:
        _clients[device_id] = ws

async def unregister(device_id: str, ws: WebSocket):
    """
    Entfernt den Client nur, wenn die gespeicherte WS-Instanz IDENTISCH ist.
    Damit kann eine alte, schließende Verbindung nicht eine neue Verbindung 'weg-löschen'.
    """
    async with _lock:
        current = _clients.get(device_id)
        if current is ws:
            _clients.pop(device_id, None)

async def get_clients() -> List[str]:
    async with _lock:
        return list(_clients.keys())

async def send_command(device_id: str, payload: dict) -> bool:
    async with _lock:
        ws = _clients.get(device_id)

    if not ws:
        return False

    await ws.send_json(payload)
    return True
