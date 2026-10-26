import asyncio
import struct

import pytest

from lan_games.common.constants import MAX_FRAME_SIZE
from lan_games.common.protocol import (
    MessageType,
    ProtocolError,
    decode_payload,
    encode_message,
    read_message,
)


@pytest.mark.parametrize("message_type", list(MessageType))
def test_round_trip_every_message_type(message_type: MessageType) -> None:
    encoded = encode_message(message_type, {"sample": "✓"})
    size = struct.unpack("!I", encoded[:4])[0]
    assert size == len(encoded) - 4
    assert decode_payload(encoded[4:]) == {
        "v": 1,
        "type": message_type.value,
        "data": {"sample": "✓"},
    }


@pytest.mark.asyncio
async def test_read_handles_fragmented_header_and_payload() -> None:
    reader = asyncio.StreamReader()
    frame = encode_message("ping", {"at": 1})
    task = asyncio.create_task(read_message(reader))
    for part in (frame[:1], frame[1:3], frame[3:6], frame[6:]):
        reader.feed_data(part)
        await asyncio.sleep(0)
    assert await task == {"v": 1, "type": "ping", "data": {"at": 1}}


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, MAX_FRAME_SIZE + 1])
async def test_rejects_invalid_frame_lengths(size: int) -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(struct.pack("!I", size))
    with pytest.raises(ProtocolError):
        await read_message(reader)


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"\xff",
        b"[]",
        b'{"v":1,"type":"unknown","data":{}}',
        b'{"v":2,"type":"ping","data":{}}',
        b'{"v":1,"type":"ping","data":[]}',
        b'{"v":1,"type":"ping","data":{},"extra":true}',
        b'{"v":1,"type":"ping","data":{"value":NaN}}',
    ],
)
def test_rejects_malformed_or_unsupported_payloads(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_payload(payload)


def test_encode_rejects_unsupported_and_non_json_messages() -> None:
    with pytest.raises(ProtocolError):
        encode_message("nope", {})
    with pytest.raises(ProtocolError):
        encode_message("ping", {"not_json": object()})
    with pytest.raises(ProtocolError):
        encode_message("event", {"large": "x" * MAX_FRAME_SIZE})
