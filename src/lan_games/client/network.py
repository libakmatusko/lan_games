"""Async client transport with heartbeat and a message queue."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

from lan_games.common.constants import HEARTBEAT_INTERVAL, PEER_TIMEOUT, PROTOCOL_VERSION
from lan_games.common.protocol import read_message, write_message


class ServerRejected(ConnectionError):
    """Raised when the server rejects the initial handshake."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(str(data.get("reason", "server rejected the connection")))
        self.data = data


class ClientNetwork:
    """Connection-level client networking; it does not import game code."""

    def __init__(self) -> None:
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._messages: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._last_seen = 0.0
        self._closed = False

    async def connect(
        self,
        host: str,
        port: int,
        game_id: str,
        player_name: str,
        session_token: str | None = None,
    ) -> dict[str, Any]:
        """Connect, perform hello, and return the welcome payload."""
        self.reader, self.writer = await asyncio.open_connection(host, port)
        raw_socket = self.writer.get_extra_info("socket")
        if raw_socket is not None:
            raw_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._last_seen = asyncio.get_running_loop().time()
        hello: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "player_name": player_name,
            "game_id": game_id,
        }
        if session_token is not None:
            hello["session_token"] = session_token
        try:
            await self.send("hello", hello)
            response = await asyncio.wait_for(read_message(self.reader), timeout=10.0)
        except Exception:
            await self.close(graceful=False)
            raise
        self._last_seen = asyncio.get_running_loop().time()
        if response["type"] == "reject":
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self._closed = True
            raise ServerRejected(response["data"])
        if response["type"] != "welcome":
            await self.close(graceful=False)
            raise ConnectionError("server did not send a welcome message")
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return response["data"]

    async def send(self, message_type: str, data: dict[str, Any]) -> None:
        """Send one client message."""
        if self.writer is None or self._closed:
            raise ConnectionError("not connected")
        async with self._write_lock:
            await write_message(self.writer, message_type, data)

    async def receive(self) -> dict[str, Any]:
        """Return the next server message."""
        return await self._messages.get()

    async def close(self, graceful: bool = True) -> None:
        """Stop background tasks and close the TCP stream."""
        if not self._closed and graceful and self.writer is not None:
            try:
                await self.send("bye", {})
            except (ConnectionError, OSError):
                pass
        self._closed = True
        current = asyncio.current_task()
        tasks = [self._reader_task, self._heartbeat_task]
        for task in tasks:
            if task is not None and task is not current:
                task.cancel()
        for task in tasks:
            if task is not None and task is not current:
                try:
                    await task
                except (asyncio.CancelledError, OSError, ConnectionError):
                    pass
        if self.writer is not None:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _reader_loop(self) -> None:
        try:
            assert self.reader is not None
            while not self._closed:
                message = await read_message(self.reader)
                self._last_seen = asyncio.get_running_loop().time()
                if message["type"] == "ping":
                    await self.send("pong", message["data"])
                else:
                    await self._messages.put(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closed:
                await self._messages.put(
                    {"type": "disconnect", "data": {"reason": str(exc)}}
                )
                self._closed = True

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if asyncio.get_running_loop().time() - self._last_seen >= PEER_TIMEOUT:
                    await self._messages.put(
                        {"type": "disconnect", "data": {"reason": "server timed out"}}
                    )
                    self._closed = True
                    if self.writer is not None:
                        self.writer.close()
                    return
                await self.send("ping", {})
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError):
            if not self._closed:
                await self._messages.put(
                    {"type": "disconnect", "data": {"reason": "connection lost"}}
                )
                self._closed = True
