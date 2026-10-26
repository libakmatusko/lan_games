# LAN Games

A Python 3.11+ framework for playing small multiplayer games with friends over a
LAN or VPN. The server is authoritative; games are plugins, and the core uses
only the Python standard library.

## Install and run

```powershell
python -m pip install -e .
python -m lan_games.server
```

Choose a game in the server menu (or use `--game tictactoe`), then start the
client on each player machine:

```powershell
python -m lan_games.client
```

The server defaults to port 5555 and binds to all network interfaces. Choose
the same game on both sides, enter the server's address, and ready up in the
lobby. Useful server options:

```powershell
python -m lan_games.server --game connect4 --host 0.0.0.0 --port 5555
python -m lan_games.server --help
```

For the optional graphical Tic-Tac-Toe and Pong UIs:

```powershell
python -m pip install -e ".[ui]"
```

The available plugins are Tic-Tac-Toe, Connect Four, and real-time Pong.
Pong has responsive pygame controls; the client falls back to terminal if the
optional extra is not installed. Restart the server to host another match
after a game is complete.

## Development checks

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

## Playing over LAN, Radmin, or ZeroTier

Use the server machine's LAN or VPN adapter address in the client. Both
computers must use the same port. On Windows, allow Python through the firewall
on the **Private** profile. Verify VPN connectivity with `ping <server-ip>`
before troubleshooting the game. Radmin/ZeroTier users should choose the VPN
adapter address printed by the server, not an unrelated public address.
The client remembers the last connection and stores a short-lived reconnect
token in `~/.lan_games.json`; keep that local settings file private.

## Adding a game

Create a package under `src/lan_games/games/` and export its `GAME_INFO`; see
[`docs/adding_a_game.md`](docs/adding_a_game.md) for the plugin contract and
copy-paste template. Rule logic belongs in `logic.py` and must remain pure:
the server owns state and randomness, while client UIs send intents only.

The protocol uses length-prefixed JSON frames. Do not expose the server to
untrusted public networks: the protocol is intended for trusted LAN/VPN play
and does not provide encryption or user authentication.
