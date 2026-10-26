"""A single client's framed stream connection."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

from lan_games.common.protocol import MessageType, read_message, write_message


class Connection:
    """Serialize writes and track liveness for one connected peer."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self._write_lock = asyncio.Lock()
        self.closed = False
        self.last_seen = asyncio.get_running_loop().time()
        raw_socket = writer.get_extra_info("socket")
        if raw_socket is not None:
            raw_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    async def receive(self) -> dict[str, Any]:
        """Read a message and refresh the peer activity timestamp."""
        message = await read_message(self.reader)
        self.last_seen = asyncio.get_running_loop().time()
        return message

    async def send(self, message_type: str | MessageType, data: dict[str, Any]) -> None:
        """Send one message without allowing concurrent frame interleaving."""
        if self.closed:
            return
        async with self._write_lock:
            if not self.closed:
                await write_message(self.writer, message_type, data)

    async def close(self) -> None:
        """Close this stream safely and idempotently."""
        if self.closed:
            return
        self.closed = True
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, OSError):
            pass
