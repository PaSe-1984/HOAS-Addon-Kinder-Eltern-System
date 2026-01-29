from typing import Dict, List
from fastapi import WebSocket
import asyncio

_clients: Dict[str, WebSocket] = {}
_lock = asyncio.Lock()

async def register(device_id: str, ws: WebSocket):
    async with _lock:
        _clients[device_id] = ws

async def unregister(device_id: str):
    async with _lock:
        _clients.pop(device_id, None)

async def get_clients() -> List[str]:
    async with _lock:
        return list(_clients.keys())

async def send_command(device_id: str, payload: dict):
    async with _lock:
        ws = _clients.get(device_id)
    if ws:
        await ws.send_json(payload)
