"""Async TCP server application."""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket

from lan_games.common.constants import (
    DEFAULT_PORT,
    HANDSHAKE_TIMEOUT,
    HEARTBEAT_INTERVAL,
    PEER_TIMEOUT,
)
from lan_games.common.game_api import GameInfo, GameLogic
from lan_games.common.menu import choose
from lan_games.common.protocol import ProtocolError
from lan_games.common.registry import GameRegistry
from lan_games.server.connection import Connection
from lan_games.server.session import GameSession, HandshakeRejected, PlayerSeat

LOGGER = logging.getLogger(__name__)


class ServerApp:
    """Host one selected game and isolate errors to individual connections."""

    def __init__(
        self,
        info: GameInfo,
        logic_type: type[GameLogic],
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        players: int | None = None,
    ) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        target_players = info.max_players if players is None else players
        if not info.min_players <= target_players <= info.max_players:
            raise ValueError(
                f"players must be between {info.min_players} and {info.max_players}"
            )
        self.info = info
        self.host = host
        self.port = port
        self.session = GameSession(info, logic_type, target_players)
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        """Bind the server and return its selected port (useful for tests)."""
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        address = self.server.sockets[0].getsockname()
        actual_port = int(address[1])
        print(f"Hosting {self.info.name} on {self.host}:{actual_port}")
        addresses = await asyncio.to_thread(local_addresses)
        for address_text in addresses:
            print(f"  Client address: {address_text}:{actual_port}")
        print("Radmin/ZeroTier users: use the address on your VPN adapter.")
        return actual_port

    async def serve_forever(self) -> None:
        """Start the listener and serve until cancelled."""
        if self.server is None:
            await self.start()
        assert self.server is not None
        async with self.server:
            await self.server.serve_forever()

    async def close(self) -> None:
        """Stop accepting clients and close the hosted session."""
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        await self.session.close()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = Connection(reader, writer)
        seat: PlayerSeat | None = None
        watchdog: asyncio.Task[None] | None = None
        try:
            try:
                first = await asyncio.wait_for(peer.receive(), timeout=HANDSHAKE_TIMEOUT)
            except TimeoutError:
                await peer.send("reject", {"reason": "handshake timed out"})
                return
            if first["type"] != "hello":
                await peer.send("reject", {"reason": "first message must be hello"})
                return
            try:
                seat = await self.session.attach(first["data"], peer)
            except HandshakeRejected as exc:
                await peer.send("reject", {"reason": exc.reason, **exc.details})
                return
            watchdog = asyncio.create_task(self._watch_peer(peer))
            while True:
                message = await peer.receive()
                if not await self.session.handle(seat, message):
                    seat = None
                    break
        except (ProtocolError, asyncio.IncompleteReadError, ConnectionError, OSError) as exc:
            LOGGER.info("Closing invalid or disconnected client: %s", exc)
            if not peer.closed:
                try:
                    await peer.send("error", {"reason": "invalid protocol message"})
                except (ConnectionError, OSError):
                    pass
        except Exception:
            LOGGER.exception("Unexpected failure in client handler")
        finally:
            if watchdog is not None:
                watchdog.cancel()
                try:
                    await watchdog
                except asyncio.CancelledError:
                    pass
            if seat is not None:
                await self.session.disconnected(seat, peer)
            await peer.close()

    async def _watch_peer(self, peer: Connection) -> None:
        while not peer.closed:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if asyncio.get_running_loop().time() - peer.last_seen >= PEER_TIMEOUT:
                LOGGER.info("Dropping a silent client")
                await peer.close()
                return
            try:
                await peer.send("ping", {})
            except (ConnectionError, OSError):
                await peer.close()
                return


def local_addresses() -> list[str]:
    """Return best-effort local IPv4 addresses for LAN/VPN connection hints."""
    addresses: set[str] = set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(result[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 80))
            addresses.add(str(probe.getsockname()[0]))
        finally:
            probe.close()
    except OSError:
        pass
    return sorted(address for address in addresses if not address.startswith("127."))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Host a LAN game")
    parser.add_argument("--game", help="game ID (omit to choose from a menu)")
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--players", type=int, help="target number of players")
    return parser.parse_args()


def main() -> None:
    """CLI entry point; synchronous menu selection happens before asyncio."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    registry = GameRegistry()
    games = registry.discover()
    if not games:
        raise SystemExit("No valid games were discovered.")
    if args.game is None:
        selected = choose(
            "Select a game to host:",
            list(games.values()),
            lambda info: f"{info.name} ({info.id})",
        )
        game_id = selected.id
    else:
        game_id = args.game
    try:
        info = registry.get(game_id)
        logic_type: type[GameLogic] = registry.load(game_id, "logic")
        app = ServerApp(info, logic_type, args.host, args.port, args.players)
    except (KeyError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    async def run() -> None:
        try:
            await app.serve_forever()
        finally:
            await app.close()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nServer stopped.")
