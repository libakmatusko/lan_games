"""Client menus, handshake, lobby, and game UI orchestration."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lan_games.client.network import ClientNetwork, ServerRejected
from lan_games.common.constants import DEFAULT_PORT, RECONNECT_WINDOW
from lan_games.common.menu import choose
from lan_games.common.registry import GameRegistry

LOGGER = logging.getLogger(__name__)
CONFIG_PATH = Path.home() / ".lan_games.json"


def _schedule_action(network_ref: list[ClientNetwork], action: dict[str, Any]) -> None:
    asyncio.create_task(network_ref[0].send("action", {"action": action}))


def _make_action_sender(
    loop: asyncio.AbstractEventLoop, network_ref: list[ClientNetwork]
) -> Callable[[dict[str, Any]], None]:
    def send_action(action: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(_schedule_action, network_ref, action)

    return send_action


def _read_config() -> dict[str, Any]:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(
    host: str,
    port: int,
    game_id: str | None = None,
    player_name: str | None = None,
    session_token: str | None = None,
) -> None:
    config: dict[str, Any] = {"host": host, "port": port}
    if game_id is not None and player_name is not None and session_token is not None:
        config.update(
            {
                "game_id": game_id,
                "player_name": player_name,
                "session_token": session_token,
            }
        )
    try:
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("Could not save connection settings: %s", exc)


async def _prompt(prompt: str, default: str = "") -> str:
    answer = await asyncio.to_thread(input, prompt)
    answer = answer.strip()
    return answer or default


async def _play(
    registry: GameRegistry,
    game_id: str,
    player_name: str,
    host: str,
    port: int,
    session_token: str | None = None,
) -> None:
    """Connect and run lobby/game UI until the match ends or disconnects."""
    try:
        network, welcome, resumed = await _connect_with_resume(
            host, port, game_id, player_name, session_token, fallback_on_expiry=True
        )
    except ServerRejected as exc:
        if exc.data.get("game_id") and exc.data["game_id"] in registry.games:
            server_id = exc.data["game_id"]
            print(f"Server is hosting {exc.data.get('game_name', server_id)}, not {game_id}.")
            answer = await _prompt("Switch to the server's game? [Y/n] ", "y")
            if answer.casefold() not in {"n", "no"}:
                await _play(registry, server_id, player_name, host, port)
                return
        raise
    except (OSError, TimeoutError) as exc:
        raise ConnectionError(f"could not connect to {host}:{port}: {exc}") from exc

    player_id = welcome["player_id"]
    token = welcome["session_token"]
    remote_game_id = welcome.get("game", {}).get("id")
    if not isinstance(remote_game_id, str) or remote_game_id not in registry.games:
        await network.close()
        raise ConnectionError("server selected a game not available in this client")
    await asyncio.to_thread(
        _write_config, host, port, remote_game_id, player_name, token
    )
    info = registry.get(remote_game_id)
    ui_names = list(info.ui_paths)
    if not ui_names:
        await network.close()
        raise ConnectionError(f"{info.name} does not have a client UI")
    requested_ui = "terminal"
    if len(ui_names) > 1:
        requested_ui = await asyncio.to_thread(choose, "Select a UI:", ui_names)
    try:
        ui_type = await asyncio.to_thread(registry.load, remote_game_id, requested_ui)
    except (ImportError, ModuleNotFoundError) as exc:
        if requested_ui == "pygame" and "terminal" in ui_names:
            print(
                f"pygame is unavailable ({exc}). "
                "Install it with: python -m pip install -e '.[ui]'"
            )
            print("Falling back to the terminal UI.")
            ui_type = await asyncio.to_thread(registry.load, remote_game_id, "terminal")
        else:
            await network.close()
            raise

    print(f"Connected as {player_name} ({info.name}).")
    for entry in welcome.get("roster", []):
        print(f"  {entry['name']}: {'ready' if entry['ready'] else 'not ready'}")
    already_ready = any(
        entry.get("player_id") == player_id and entry.get("ready")
        for entry in welcome.get("roster", [])
    )
    if not resumed or not already_ready:
        await _prompt("Press Enter when ready (Ctrl+C to leave): ")
        await network.send("ready", {})
    network_ref = [network]
    ui: Any = None
    ui_thread: threading.Thread | None = None
    while True:
        message = await network.receive()
        message_type, data = message["type"], message["data"]
        if message_type == "lobby":
            names = [
                f"{entry['name']} ({'ready' if entry['ready'] else 'not ready'}"
                f"{'' if entry['connected'] else ', reconnecting'})"
                for entry in data.get("roster", [])
            ]
            print("Lobby: " + ", ".join(names))
        elif message_type == "start":
            if ui is None:
                loop = asyncio.get_running_loop()
                ui = ui_type(player_id, _make_action_sender(loop, network_ref))
                ui.on_state(data.get("state", {}))
                ui_thread = threading.Thread(target=ui.run, daemon=True)
                ui_thread.start()
                print("Match started. Use the controls shown in the game UI.")
            else:
                ui.on_state(data.get("state", {}))
        elif message_type == "state" and ui is not None:
            ui.on_state(data)
        elif message_type == "event" and ui is not None:
            ui.on_event(data)
        elif message_type == "game_over":
            print(f"Match result: {data}")
            if ui is not None:
                ui.on_event({"type": "game_over", "data": data})
            break
        elif message_type == "error":
            print(f"Server: {data.get('reason', 'request failed')}")
        elif message_type == "disconnect":
            print(f"Connection lost: {data.get('reason', 'connection lost')}")
            await network.close(graceful=False)
            network = await _reconnect(
                registry, remote_game_id, player_name, host, port, token
            )
            network_ref[0] = network
            print("Reconnected to the match.")
    await network.close()
    if ui_thread is not None:
        ui_thread.join(timeout=1.0)
    await asyncio.to_thread(_write_config, host, port)


async def _reconnect(
    registry: GameRegistry,
    game_id: str,
    player_name: str,
    host: str,
    port: int,
    token: str,
) -> ClientNetwork:
    """Retry a seat resume until the server's reconnect window expires."""
    try:
        network, welcome, _ = await _connect_with_resume(
            host, port, game_id, player_name, token, fallback_on_expiry=False
        )
    except ServerRejected as exc:
        raise ConnectionError(f"could not resume session: {exc}") from exc
    if welcome.get("game", {}).get("id") not in registry.games:
        await network.close(graceful=False)
        raise ConnectionError("server resumed an unavailable game")
    return network


async def _connect_with_resume(
    host: str,
    port: int,
    game_id: str,
    player_name: str,
    token: str | None,
    *,
    fallback_on_expiry: bool,
) -> tuple[ClientNetwork, dict[str, Any], bool]:
    """Connect once or retry a previous seat until the reconnect window closes."""
    if token is None:
        network = ClientNetwork()
        return network, await network.connect(host, port, game_id, player_name), False

    loop = asyncio.get_running_loop()
    deadline = loop.time() + RECONNECT_WINDOW
    notified = False
    while loop.time() < deadline:
        network = ClientNetwork()
        try:
            welcome = await network.connect(host, port, game_id, player_name, token)
            return network, welcome, True
        except ServerRejected as exc:
            await network.close(graceful=False)
            if exc.data.get("reason") == "seat is still connected":
                if not notified:
                    print("Waiting for the previous connection to close before resuming…")
                    notified = True
                await asyncio.sleep(1.0)
                continue
            if (
                fallback_on_expiry
                and "reconnect token" in str(exc.data.get("reason", ""))
            ):
                print("The saved match has expired; joining as a new player.")
                fresh_network = ClientNetwork()
                try:
                    welcome = await fresh_network.connect(host, port, game_id, player_name)
                except Exception:
                    await fresh_network.close(graceful=False)
                    raise
                return fresh_network, welcome, False
            raise
        except (OSError, TimeoutError, ConnectionError):
            await network.close(graceful=False)
            if not notified:
                print("Waiting for the server to become available for reconnection…")
                notified = True
            await asyncio.sleep(1.0)
    raise ConnectionError("reconnect window expired")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Join a LAN game")
    parser.add_argument("--host", help="server address")
    parser.add_argument("--port", type=int, help="server port")
    parser.add_argument("--game", help="game ID (omit to choose from a menu)")
    parser.add_argument("--name", help="player name")
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    registry = GameRegistry()
    games = registry.discover()
    if not games:
        raise SystemExit("No valid games were discovered.")
    if args.game:
        try:
            info = registry.get(args.game)
        except KeyError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        info = choose(
            "Select a game:",
            list(games.values()),
            lambda game: f"{game.name} ({game.id})",
        )
    config = _read_config()
    player_name = args.name or input("Player name: ").strip() or "Player"
    host = args.host or input(f"Server address [{config.get('host', '127.0.0.1')}]: ").strip()
    host = host or str(config.get("host", "127.0.0.1"))
    port_text = str(args.port) if args.port is not None else input(
        f"Server port [{config.get('port', DEFAULT_PORT)}]: "
    ).strip()
    try:
        port = int(port_text or config.get("port", DEFAULT_PORT))
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise SystemExit("Port must be an integer from 1 to 65535.") from exc
    saved_token = config.get("session_token")
    if (
        not isinstance(saved_token, str)
        or config.get("game_id") != info.id
        or config.get("player_name") != player_name
    ):
        saved_token = None
    try:
        asyncio.run(_play(registry, info.id, player_name, host, port, saved_token))
    except (ConnectionError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    except KeyboardInterrupt:
        print("\nLeaving game.")
