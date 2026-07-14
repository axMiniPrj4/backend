"""프로젝트별 코드 워크스페이스 WebSocket 룸 (인메모리)."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class WorkspacePeer:
    websocket: WebSocket
    user_id: int
    nickname: str
    client_id: str
    editing_file_id: int | None = None


@dataclass
class WorkspaceRoom:
    project_id: int
    peers: dict[str, WorkspacePeer] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class WorkspaceHub:
    def __init__(self) -> None:
        self._rooms: dict[int, WorkspaceRoom] = {}
        self._global_lock = asyncio.Lock()

    async def _get_room(self, project_id: int) -> WorkspaceRoom:
        async with self._global_lock:
            room = self._rooms.get(project_id)
            if room is None:
                room = WorkspaceRoom(project_id=project_id)
                self._rooms[project_id] = room
            return room

    async def join(self, project_id: int, peer: WorkspacePeer) -> list[dict[str, Any]]:
        room = await self._get_room(project_id)
        async with room.lock:
            room.peers[peer.client_id] = peer
            return self._presence_snapshot(room)

    async def leave(self, project_id: int, client_id: str) -> list[dict[str, Any]]:
        room = await self._get_room(project_id)
        async with room.lock:
            room.peers.pop(client_id, None)
            presence = self._presence_snapshot(room)
            if not room.peers:
                async with self._global_lock:
                    if project_id in self._rooms and not self._rooms[project_id].peers:
                        self._rooms.pop(project_id, None)
            return presence

    async def set_editing(self, project_id: int, client_id: str, file_id: int | None) -> list[dict[str, Any]]:
        room = await self._get_room(project_id)
        async with room.lock:
            peer = room.peers.get(client_id)
            if peer is not None:
                peer.editing_file_id = file_id
            return self._presence_snapshot(room)

    async def broadcast(
        self,
        project_id: int,
        message: dict[str, Any],
        *,
        exclude_client_id: str | None = None,
    ) -> None:
        room = await self._get_room(project_id)
        async with room.lock:
            peers = list(room.peers.values())
        dead: list[str] = []
        payload = json.dumps(message, ensure_ascii=False)
        for peer in peers:
            if exclude_client_id and peer.client_id == exclude_client_id:
                continue
            try:
                await peer.websocket.send_text(payload)
            except Exception:
                dead.append(peer.client_id)
        for client_id in dead:
            await self.leave(project_id, client_id)

    @staticmethod
    def _presence_snapshot(room: WorkspaceRoom) -> list[dict[str, Any]]:
        return [
            {
                "clientId": peer.client_id,
                "userId": peer.user_id,
                "nickname": peer.nickname,
                "editingFileId": peer.editing_file_id,
            }
            for peer in room.peers.values()
        ]


workspace_hub = WorkspaceHub()
