"""Lobby roster, ready state, and short-window seat reconnection."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

from lan_games.common.constants import PROTOCOL_VERSION, RECONNECT_WINDOW
from lan_games.common.game_api import GameInfo, GameLogic
from lan_games.server.connection import Connection
from lan_games.server.runner import GameRunner

LOGGER = logging.getLogger(__name__)


class HandshakeRejected(ValueError):
    """A connection was rejected before joining the lobby."""

    def __init__(self, reason: str, **details: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details


@dataclass
class PlayerSeat:
    """A player identity that can outlive a network connection briefly."""

    player_id: str
    token: str
    name: str
    peer: Connection | None
    ready: bool = False
    disconnected_at: float | None = None


class GameSession:
    """Manage a single hosted game session."""

    def __init__(
        self,
        info: GameInfo,
        logic_type: type[GameLogic],
        target_players: int,
    ) -> None:
        self.info = info
        self.logic_type = logic_type
        self.target_players = target_players
        self.seats: dict[str, PlayerSeat] = {}
        self.runner: GameRunner | None = None

    async def attach(self, hello: Any, peer: Connection) -> PlayerSeat:
        """Validate a hello and attach a new or reconnecting seat."""
        self._prune_expired_seats()
        if not isinstance(hello, dict):
            raise HandshakeRejected("hello data must be an object")
        if (
            type(hello.get("protocol_version")) is not int
            or hello["protocol_version"] != PROTOCOL_VERSION
        ):
            raise HandshakeRejected(
                "protocol version mismatch",
                protocol_version=PROTOCOL_VERSION,
            )
        requested_game = hello.get("game_id")
        if requested_game != self.info.id:
            raise HandshakeRejected(
                "game mismatch",
                game_id=self.info.id,
                game_name=self.info.name,
            )
        token = hello.get("session_token")
        if token is not None:
            if not isinstance(token, str):
                raise HandshakeRejected("reconnect token is invalid or expired")
            seat = next((item for item in self.seats.values() if item.token == token), None)
            if seat is None:
                raise HandshakeRejected("reconnect token is invalid or expired")
            if seat.peer is not None:
                raise HandshakeRejected("seat is still connected")
            if (
                seat.disconnected_at is None
                or time.monotonic() - seat.disconnected_at > RECONNECT_WINDOW
            ):
                raise HandshakeRejected("reconnect token is invalid or expired")
            seat.peer = peer
            seat.disconnected_at = None
            try:
                if self.runner is not None:
                    await self.runner.player_reconnected(seat.player_id)
                await self._send_welcome(seat)
                await self._send_lobby()
                if self.runner is not None:
                    await peer.send(
                        "start",
                        {
                            "game_id": self.info.id,
                            "options": {},
                            "state": self.runner.logic.view_for(seat.player_id),
                        },
                    )
                    if self.runner.logic.is_over():
                        await peer.send("game_over", self.runner.logic.result())
                else:
                    await self._maybe_start()
            except Exception:
                seat.peer = None
                seat.disconnected_at = time.monotonic()
                raise
            return seat

        name = hello.get("player_name")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > 24
            or not name.strip().isprintable()
        ):
            raise HandshakeRejected("player name must contain 1 to 24 characters")
        name = name.strip()
        if any(seat.name.casefold() == name.casefold() for seat in self.seats.values()):
            raise HandshakeRejected("that player name is already in use")
        if self.runner is not None:
            raise HandshakeRejected("the match is already in progress")
        if len(self.seats) >= self.target_players:
            raise HandshakeRejected("room is full")
        seat = PlayerSeat(
            player_id=uuid.uuid4().hex,
            token=secrets.token_urlsafe(32),
            name=name,
            peer=peer,
        )
        self.seats[seat.player_id] = seat
        try:
            await self._send_welcome(seat)
        except Exception:
            self.seats.pop(seat.player_id, None)
            raise
        await self._send_lobby()
        return seat

    def _prune_expired_seats(self) -> None:
        now = time.monotonic()
        expired = [
            player_id
            for player_id, seat in self.seats.items()
            if seat.peer is None
            and seat.disconnected_at is not None
            and now - seat.disconnected_at > RECONNECT_WINDOW
        ]
        for player_id in expired:
            self.seats.pop(player_id, None)

    async def handle(self, seat: PlayerSeat, message: dict[str, Any]) -> bool:
        """Process an authenticated message; return false for graceful leave."""
        message_type = message["type"]
        data = message["data"]
        if message_type == "ping":
            await self._send_to(seat, "pong", data)
        elif message_type == "pong":
            pass
        elif message_type == "ready":
            if self.runner is not None:
                await self._send_to(seat, "error", {"reason": "the match has already started"})
            else:
                seat.ready = not seat.ready
                await self._send_lobby()
                await self._maybe_start()
        elif message_type == "action":
            if self.runner is None:
                await self._send_to(seat, "error", {"reason": "the match has not started"})
            else:
                await self.runner.handle_action(seat.player_id, data.get("action"))
        elif message_type == "bye":
            await self.leave(seat)
            return False
        else:
            await self._send_to(seat, "error", {"reason": "message is not valid in this state"})
        return True

    async def disconnected(self, seat: PlayerSeat, peer: Connection) -> None:
        """Retain a dropped seat only if this is still its active connection."""
        if seat.peer is not peer:
            return
        seat.peer = None
        seat.disconnected_at = time.monotonic()
        if self.runner is not None:
            await self.runner.player_disconnected(seat.player_id)
        await self._send_lobby()

    async def leave(self, seat: PlayerSeat) -> None:
        """Release a seat after a graceful client bye."""
        self.seats.pop(seat.player_id, None)
        if self.runner is not None:
            await self.runner.player_disconnected(seat.player_id)
        await self._send_lobby()

    async def close(self) -> None:
        """Stop match tasks and close every attached peer."""
        if self.runner is not None:
            await self.runner.close()
        await asyncio.gather(
            *(seat.peer.close() for seat in self.seats.values() if seat.peer is not None),
            return_exceptions=True,
        )

    async def _send_welcome(self, seat: PlayerSeat) -> None:
        await self._send_to(
            seat,
            "welcome",
            {
                "player_id": seat.player_id,
                "session_token": seat.token,
                "game": {
                    "id": self.info.id,
                    "name": self.info.name,
                    "min_players": self.info.min_players,
                    "max_players": self.info.max_players,
                    "tick_rate": self.info.tick_rate,
                    "version": self.info.version,
                },
                "roster": self._roster(),
            },
        )

    def _roster(self) -> list[dict[str, Any]]:
        return [
            {
                "player_id": seat.player_id,
                "name": seat.name,
                "ready": seat.ready,
                "connected": seat.peer is not None,
            }
            for seat in self.seats.values()
        ]

    async def _send_lobby(self) -> None:
        await self._broadcast("lobby", {"roster": self._roster()})

    async def _maybe_start(self) -> None:
        seats = list(self.seats.values())
        if (
            self.runner is not None
            or len(seats) != self.target_players
            or any(not seat.ready or seat.peer is None for seat in seats)
        ):
            return
        player_ids = [seat.player_id for seat in seats]
        self.runner = GameRunner(
            self.info,
            self.logic_type,
            player_ids,
            {},
            self._send_player,
            self._broadcast,
        )
        for seat in seats:
            await self._send_to(
                seat,
                "start",
                {
                    "game_id": self.info.id,
                    "options": {},
                    "state": self.runner.logic.view_for(seat.player_id),
                },
            )
        await self.runner.start()

    async def _send_to(
        self, seat: PlayerSeat, message_type: str, data: dict[str, Any]
    ) -> None:
        if seat.peer is not None:
            await seat.peer.send(message_type, data)

    async def _send_player(
        self, player_id: str, message_type: str, data: dict[str, Any]
    ) -> None:
        seat = self.seats.get(player_id)
        if seat is not None:
            await self._send_to(seat, message_type, data)

    async def _broadcast(self, message_type: str, data: dict[str, Any]) -> None:
        await asyncio.gather(
            *(
                seat.peer.send(message_type, data)
                for seat in self.seats.values()
                if seat.peer is not None
            ),
            return_exceptions=True,
        )
