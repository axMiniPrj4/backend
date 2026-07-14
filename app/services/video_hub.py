"""프로젝트별 화상 WebRTC 시그널링 (WebSocket, 인메모리)."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class VideoPeerConn:
    websocket: WebSocket
    peer_id: str
    user_id: int
    nickname: str
    muted: bool = False
    camera_off: bool = False


@dataclass
class VideoRoom:
    project_id: int
    peers: dict[str, VideoPeerConn] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class VideoHub:
    def __init__(self) -> None:
        self._rooms: dict[int, VideoRoom] = {}
        self._global_lock = asyncio.Lock()

    async def _room(self, project_id: int) -> VideoRoom:
        async with self._global_lock:
            room = self._rooms.get(project_id)
            if room is None:
                room = VideoRoom(project_id=project_id)
                self._rooms[project_id] = room
            return room

    def peer_snapshot(self, room: VideoRoom) -> list[dict[str, Any]]:
        return [
            {
                "peerId": p.peer_id,
                "nickname": p.nickname,
                "muted": p.muted,
                "cameraOff": p.camera_off,
                "userId": p.user_id,
            }
            for p in room.peers.values()
        ]

    async def join(self, project_id: int, peer: VideoPeerConn) -> list[dict[str, Any]]:
        room = await self._room(project_id)
        async with room.lock:
            # 같은 peer_id 재접속 시 이전 소켓 정리
            old = room.peers.get(peer.peer_id)
            if old is not None and old.websocket is not peer.websocket:
                try:
                    await old.websocket.close(code=4000)
                except Exception:
                    pass
            room.peers[peer.peer_id] = peer
            return self.peer_snapshot(room)

    async def leave(self, project_id: int, peer_id: str) -> list[dict[str, Any]]:
        room = await self._room(project_id)
        async with room.lock:
            room.peers.pop(peer_id, None)
            presence = self.peer_snapshot(room)
            empty = not room.peers
        if empty:
            async with self._global_lock:
                current = self._rooms.get(project_id)
                if current is not None and not current.peers:
                    self._rooms.pop(project_id, None)
        return presence

    async def update_meta(
        self,
        project_id: int,
        peer_id: str,
        *,
        nickname: str | None = None,
        muted: bool | None = None,
        camera_off: bool | None = None,
    ) -> list[dict[str, Any]]:
        room = await self._room(project_id)
        async with room.lock:
            peer = room.peers.get(peer_id)
            if peer is None:
                return self.peer_snapshot(room)
            if nickname is not None:
                peer.nickname = nickname
            if muted is not None:
                peer.muted = muted
            if camera_off is not None:
                peer.camera_off = camera_off
            return self.peer_snapshot(room)

    async def send_to(
        self,
        project_id: int,
        to_peer_id: str,
        message: dict[str, Any],
    ) -> bool:
        room = await self._room(project_id)
        async with room.lock:
            peer = room.peers.get(to_peer_id)
        if peer is None:
            return False
        try:
            await peer.websocket.send_text(json.dumps(message, ensure_ascii=False))
            return True
        except Exception:
            await self.leave(project_id, to_peer_id)
            return False

    async def broadcast(
        self,
        project_id: int,
        message: dict[str, Any],
        *,
        exclude_peer_id: str | None = None,
    ) -> None:
        room = await self._room(project_id)
        async with room.lock:
            peers = list(room.peers.values())
        dead: list[str] = []
        payload = json.dumps(message, ensure_ascii=False)
        for peer in peers:
            if exclude_peer_id and peer.peer_id == exclude_peer_id:
                continue
            try:
                await peer.websocket.send_text(payload)
            except Exception:
                dead.append(peer.peer_id)
        for peer_id in dead:
            await self.leave(project_id, peer_id)

    async def list_peers(self, project_id: int) -> list[dict[str, Any]]:
        room = await self._room(project_id)
        async with room.lock:
            return self.peer_snapshot(room)


video_hub = VideoHub()
