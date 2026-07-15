"""프로젝트별 채팅 WebSocket 룸 (인메모리) — presence + typing 포함."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class ChatPeer:
    websocket: WebSocket
    client_id: str
    user_id: int
    nickname: str = ""
    typing: bool = False


@dataclass
class ChatRoom:
    project_id: int
    peers: dict[str, ChatPeer] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ChatHub:
    def __init__(self) -> None:
        self._rooms: dict[int, ChatRoom] = {}
        self._global_lock = asyncio.Lock()

    async def _room(self, project_id: int) -> ChatRoom:
        async with self._global_lock:
            room = self._rooms.get(project_id)
            if room is None:
                room = ChatRoom(project_id=project_id)
                self._rooms[project_id] = room
            return room

    @staticmethod
    def _presence_snapshot(room: ChatRoom) -> list[dict[str, Any]]:
        return [
            {"clientId": p.client_id, "userId": p.user_id, "nickname": p.nickname, "typing": p.typing}
            for p in room.peers.values()
        ]

    async def join(self, project_id: int, peer: ChatPeer) -> list[dict[str, Any]]:
        room = await self._room(project_id)
        async with room.lock:
            old = room.peers.get(peer.client_id)
            if old is not None and old.websocket is not peer.websocket:
                try:
                    await old.websocket.close(code=4000)
                except Exception:
                    pass
            room.peers[peer.client_id] = peer
            return self._presence_snapshot(room)

    async def leave(self, project_id: int, client_id: str) -> list[dict[str, Any]]:
        room = await self._room(project_id)
        async with room.lock:
            room.peers.pop(client_id, None)
            presence = self._presence_snapshot(room)
            empty = not room.peers
        if empty:
            async with self._global_lock:
                current = self._rooms.get(project_id)
                if current is not None and not current.peers:
                    self._rooms.pop(project_id, None)
        return presence

    async def set_typing(self, project_id: int, client_id: str, typing: bool) -> list[dict[str, Any]]:
        room = await self._room(project_id)
        async with room.lock:
            peer = room.peers.get(client_id)
            if peer is not None:
                peer.typing = typing
            return self._presence_snapshot(room)

    async def broadcast(
        self,
        project_id: int,
        message: dict[str, Any],
        *,
        exclude_client_id: str | None = None,
    ) -> None:
        room = await self._room(project_id)
        async with room.lock:
            peers = list(room.peers.values())
        dead: list[str] = []
        payload = json.dumps(message, ensure_ascii=False, default=str)
        for peer in peers:
            if exclude_client_id and peer.client_id == exclude_client_id:
                continue
            try:
                await peer.websocket.send_text(payload)
            except Exception:
                dead.append(peer.client_id)
        for client_id in dead:
            await self.leave(project_id, client_id)


chat_hub = ChatHub()
