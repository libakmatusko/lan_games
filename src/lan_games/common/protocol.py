"""Length-prefixed JSON protocol implementation."""

from __future__ import annotations

import asyncio
import json
import struct
from enum import StrEnum
from typing import Any

from lan_games.common.constants import MAX_FRAME_SIZE, PROTOCOL_VERSION


class MessageType(StrEnum):
    """Supported protocol envelope types."""

    HELLO = "hello"
    WELCOME = "welcome"
    REJECT = "reject"
    LOBBY = "lobby"
    READY = "ready"
    START = "start"
    ACTION = "action"
    STATE = "state"
    EVENT = "event"
    ERROR = "error"
    GAME_OVER = "game_over"
    PING = "ping"
    PONG = "pong"
    BYE = "bye"


class ProtocolError(ValueError):
    """Raised when a frame or message violates the wire protocol."""


def encode_message(message_type: str | MessageType, data: dict[str, Any]) -> bytes:
    """Encode a validated protocol envelope with a four-byte length prefix."""
    try:
        normalized_type = MessageType(message_type).value
    except ValueError as exc:
        raise ProtocolError(f"unsupported message type: {message_type}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("message data must be a JSON object")
    envelope = {"v": PROTOCOL_VERSION, "type": normalized_type, "data": data}
    try:
        payload = json.dumps(
            envelope, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("message data is not JSON-serializable") from exc
    if not payload or len(payload) > MAX_FRAME_SIZE:
        raise ProtocolError("message exceeds the maximum frame size")
    return struct.pack("!I", len(payload)) + payload


def decode_payload(payload: bytes) -> dict[str, Any]:
    """Decode and validate one JSON envelope payload."""
    if not payload or len(payload) > MAX_FRAME_SIZE:
        raise ProtocolError("invalid frame size")
    try:
        envelope = json.loads(
            payload.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProtocolError("frame is not valid UTF-8 JSON") from exc
    if not isinstance(envelope, dict):
        raise ProtocolError("message envelope must be an object")
    if type(envelope.get("v")) is not int or envelope["v"] != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    try:
        message_type = MessageType(envelope.get("type")).value
    except (ValueError, TypeError) as exc:
        raise ProtocolError("unsupported message type") from exc
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise ProtocolError("message data must be an object")
    if set(envelope) != {"v", "type", "data"}:
        raise ProtocolError("message envelope has unexpected fields")
    return {"v": PROTOCOL_VERSION, "type": message_type, "data": data}


async def read_message(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Read one complete frame from an asyncio stream reader."""
    header = await reader.readexactly(4)
    (size,) = struct.unpack("!I", header)
    if size == 0 or size > MAX_FRAME_SIZE:
        raise ProtocolError("invalid frame size")
    return decode_payload(await reader.readexactly(size))


async def write_message(
    writer: asyncio.StreamWriter, message_type: str | MessageType, data: dict[str, Any]
) -> None:
    """Write one framed message and flush it to the stream."""
    writer.write(encode_message(message_type, data))
    await writer.drain()
