"""Reusable scripted TCP client for socket-level tests and bot matches."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from lan_games.common.constants import PROTOCOL_VERSION
from lan_games.common.protocol import read_message, write_message


class FakeClient:
    """A tiny protocol-speaking client suitable for deterministic tests."""

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.messages: deque[dict[str, Any]] = deque()

    @classmethod
    async def connect(
        cls,
        host: str,
        port: int,
        name: str,
        game_id: str = "tictactoe",
        token: str | None = None,
    ) -> tuple[FakeClient, dict[str, Any]]:
        reader, writer = await asyncio.open_connection(host, port)
        client = cls(reader, writer)
        data: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "player_name": name,
            "game_id": game_id,
        }
        if token is not None:
            data["session_token"] = token
        await client.send("hello", data)
        response = await client.receive()
        if response["type"] == "reject":
            return client, response
        if response["type"] != "welcome":
            raise AssertionError(f"expected welcome, received {response['type']}")
        return client, response

    async def send(self, message_type: str, data: dict[str, Any]) -> None:
        await write_message(self.writer, message_type, data)

    async def receive(self, timeout: float = 3.0) -> dict[str, Any]:
        return await asyncio.wait_for(read_message(self.reader), timeout=timeout)

    async def receive_type(self, message_type: str, timeout: float = 3.0) -> dict[str, Any]:
        for message in list(self.messages):
            if message["type"] == message_type:
                self.messages.remove(message)
                return message
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"did not receive message type {message_type}")
            message = await self.receive(remaining)
            if message["type"] == message_type:
                return message
            self.messages.append(message)

    async def close(self, graceful: bool = False) -> None:
        if graceful:
            try:
                await self.send("bye", {})
            except (ConnectionError, OSError):
                pass
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, OSError):
            pass
