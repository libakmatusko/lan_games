import asyncio
import struct

import pytest

from lan_games.client.app import _connect_with_resume
from lan_games.client.network import ClientNetwork
from lan_games.common.protocol import read_message
from lan_games.games.pong import GAME_INFO as PONG_INFO
from lan_games.games.pong.logic import PongLogic
from lan_games.games.tictactoe import GAME_INFO
from lan_games.games.tictactoe.logic import TicTacToeLogic
from lan_games.server.app import ServerApp
from tests.fake_client import FakeClient


async def _start_server():
    app = ServerApp(GAME_INFO, TicTacToeLogic, host="127.0.0.1", port=0)
    port = await app.start()
    return app, port


@pytest.mark.asyncio
async def test_full_match_invalid_action_and_wrong_game_are_isolated() -> None:
    app, port = await _start_server()
    first = second = third = wrong_game = None
    try:
        first, welcome_a = await FakeClient.connect("127.0.0.1", port, "Alice")
        second, welcome_b = await FakeClient.connect("127.0.0.1", port, "Bob")
        third, rejected = await FakeClient.connect("127.0.0.1", port, "Eve")
        assert rejected["type"] == "reject"
        assert rejected["data"]["reason"] == "room is full"

        wrong_game, mismatch = await FakeClient.connect(
            "127.0.0.1", port, "Mallory", game_id="connect4"
        )
        assert mismatch["type"] == "reject"
        assert mismatch["data"]["game_id"] == "tictactoe"

        await first.send("ready", {})
        await second.send("ready", {})
        await first.receive_type("start")
        await second.receive_type("start")

        await first.send("action", {"action": {"type": "move", "row": 8, "col": 0}})
        assert (await first.receive_type("error"))["data"]["reason"]

        moves = [
            (first, 0, 0),
            (second, 1, 0),
            (first, 0, 1),
            (second, 1, 1),
            (first, 0, 2),
        ]
        for client, row, col in moves:
            await client.send("action", {"action": {"type": "move", "row": row, "col": col}})
            await first.receive_type("state")
            await second.receive_type("state")
        result_a = await first.receive_type("game_over")
        result_b = await second.receive_type("game_over")
        assert result_a["data"]["winner"] == welcome_a["data"]["player_id"]
        assert result_b["data"]["winner"] == welcome_a["data"]["player_id"]
        assert welcome_a["data"]["player_id"] != welcome_b["data"]["player_id"]
    finally:
        for client in (first, second, third, wrong_game):
            if client is not None:
                await client.close()
        await app.close()


@pytest.mark.asyncio
async def test_reconnect_token_resumes_an_active_seat_and_state() -> None:
    app, port = await _start_server()
    first = second = resumed = None
    try:
        first, welcome = await FakeClient.connect("127.0.0.1", port, "Alice")
        second, _ = await FakeClient.connect("127.0.0.1", port, "Bob")
        await first.send("ready", {})
        await second.send("ready", {})
        await first.receive_type("start")
        await second.receive_type("start")
        await first.close()
        await asyncio.sleep(0.05)
        resumed, resumed_welcome = await FakeClient.connect(
            "127.0.0.1",
            port,
            "Alice",
            token=welcome["data"]["session_token"],
        )
        assert resumed_welcome["type"] == "welcome"
        assert resumed_welcome["data"]["player_id"] == welcome["data"]["player_id"]
        start = await resumed.receive_type("start")
        assert start["data"]["state"]["you"] == "X"
    finally:
        for client in (first, second, resumed):
            if client is not None:
                await client.close()
        await app.close()


@pytest.mark.asyncio
async def test_malformed_client_frame_does_not_stop_listener() -> None:
    app, port = await _start_server()
    first = second = None
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        payload = b"not json"
        writer.write(struct.pack("!I", len(payload)) + payload)
        await writer.drain()
        response = await asyncio.wait_for(read_message(reader), timeout=2)
        assert response["type"] == "error"
        writer.close()
        await writer.wait_closed()

        first, hello_a = await FakeClient.connect("127.0.0.1", port, "Alice")
        second, hello_b = await FakeClient.connect("127.0.0.1", port, "Bob")
        assert hello_a["type"] == hello_b["type"] == "welcome"
    finally:
        for client in (first, second):
            if client is not None:
                await client.close()
        await app.close()


@pytest.mark.asyncio
async def test_realtime_plugin_ticks_and_publishes_state() -> None:
    app = ServerApp(PONG_INFO, PongLogic, host="127.0.0.1", port=0)
    port = await app.start()
    first = second = None
    try:
        first, _ = await FakeClient.connect("127.0.0.1", port, "Alice", "pong")
        second, _ = await FakeClient.connect("127.0.0.1", port, "Bob", "pong")
        await first.send("ready", {})
        await second.send("ready", {})
        start = await first.receive_type("start")
        await second.receive_type("start")
        state = await first.receive_type("state")
        assert state["data"]["ball"] != start["data"]["state"]["ball"]
    finally:
        for client in (first, second):
            if client is not None:
                await client.close()
        await app.close()


@pytest.mark.asyncio
async def test_silent_peer_is_dropped(monkeypatch) -> None:
    import lan_games.server.app as server_module

    monkeypatch.setattr(server_module, "HEARTBEAT_INTERVAL", 0.02)
    monkeypatch.setattr(server_module, "PEER_TIMEOUT", 0.10)
    app, port = await _start_server()
    client = None
    try:
        client, _ = await FakeClient.connect("127.0.0.1", port, "Silent")
        with pytest.raises(asyncio.IncompleteReadError):
            while True:
                await client.receive(timeout=1.0)
    finally:
        if client is not None:
            await client.close()
        await app.close()


@pytest.mark.asyncio
async def test_expired_reconnect_seat_is_released(monkeypatch) -> None:
    import lan_games.server.session as session_module

    monkeypatch.setattr(session_module, "RECONNECT_WINDOW", 0.02)
    app, port = await _start_server()
    disconnected = replacement = None
    try:
        disconnected, welcome = await FakeClient.connect(
            "127.0.0.1", port, "Alice"
        )
        await disconnected.close()
        await asyncio.sleep(0.05)
        replacement, accepted = await FakeClient.connect(
            "127.0.0.1", port, "Alice"
        )
        assert accepted["type"] == "welcome"
        assert accepted["data"]["player_id"] != welcome["data"]["player_id"]
    finally:
        for client in (disconnected, replacement):
            if client is not None:
                await client.close()
        await app.close()


@pytest.mark.asyncio
async def test_client_transport_handshake_and_reconnect() -> None:
    app, port = await _start_server()
    network = ClientNetwork()
    resumed = ClientNetwork()
    try:
        welcome = await network.connect("127.0.0.1", port, "tictactoe", "Alice")
        await network.close(graceful=False)
        await asyncio.sleep(0.05)
        resumed, resumed_welcome, did_resume = await _connect_with_resume(
            "127.0.0.1",
            port,
            "tictactoe",
            "Alice",
            welcome["session_token"],
            fallback_on_expiry=False,
        )
        assert did_resume
        assert resumed_welcome["player_id"] == welcome["player_id"]
        await resumed.close()
    finally:
        await network.close(graceful=False)
        await resumed.close(graceful=False)
        await app.close()
