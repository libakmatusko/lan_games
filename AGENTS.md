# AGENTS.md: LAN Multiplayer Games Framework

Instructions for the AI agent working on this repository. Read this file fully before writing any code.

## 1. Project summary

A Python framework for playing games with friends over LAN or a VPN (Radmin, ZeroTier).

- **Server**: hosts the match, owns the game state, enforces the rules (authoritative).
- **Client**: connects to the server, shows the UI, sends player input.
- **Games** are plugins. Adding a game means adding one folder under `games/`, with no changes to core code.
- Both programs start with a **terminal menu** where the user picks a game; the chosen game's module is then imported dynamically. The server can also take `--game ID` on the command line.
- Supports turn-based and real-time games through the same core (`tick_rate`).

Non-goals for now: internet matchmaking, accounts, databases, encryption, mobile/web clients.

## 2. Tech decisions (do not change without asking)

| Area | Decision |
|---|---|
| Language | Python 3.11+, full type hints |
| Networking | `asyncio` streams over TCP, single-threaded server |
| Wire format | 4-byte big-endian length prefix + UTF-8 JSON, max frame 64 KB |
| Envelope | `{"v": 1, "type": "...", "data": {...}}` |
| Authority | Server owns all state and randomness; clients send intents only |
| Core dependencies | Standard library only |
| UI | Terminal first; `pygame` as optional extra (`pip install -e .[ui]`) |
| Tests / lint | `pytest`, `pytest-asyncio`, `ruff` (optionally `mypy` on `common/` and `server/`) |
| Default port | 5555 (configurable, never hardcoded) |

## 3. Project structure

```
lan_games/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── docs/
│   ├── decisions.md          # log of design decisions you make
│   └── adding_a_game.md      # guide + template for new games (you write this)
├── src/lan_games/
│   ├── common/
│   │   ├── protocol.py       # message types, encode/decode, framing
│   │   ├── constants.py      # default port, protocol version, limits
│   │   ├── game_api.py       # GameInfo, GameLogic, GameUI base classes
│   │   ├── registry.py       # discovers and lazily loads games
│   │   └── menu.py           # terminal menu helpers
│   ├── server/
│   │   ├── __main__.py       # python -m lan_games.server
│   │   ├── app.py            # starts asyncio server, wires components
│   │   ├── connection.py     # one client: read loop + write queue
│   │   ├── session.py        # roster, ready states, reconnect
│   │   └── runner.py         # owns GameLogic, routes actions, tick loop
│   ├── client/
│   │   ├── __main__.py       # python -m lan_games.client
│   │   ├── app.py            # menu -> connect -> game UI
│   │   ├── network.py        # background network thread/task + queues
│   │   └── ui_base.py
│   └── games/
│       └── <game_id>/
│           ├── __init__.py   # exports GAME_INFO
│           ├── logic.py      # server side, pure rules
│           ├── ui_terminal.py
│           └── tests/
├── tests/                    # protocol, session, integration tests
└── scripts/show_ips.py       # prints local IPs (LAN / VPN adapters)
```

## 4. Non-negotiable rules

1. **Server is authoritative.** Clients send intents only. No rule logic, win conditions, or RNG in client code.
2. **Game logic is pure.** `games/*/logic.py` must not import networking, `asyncio`, `server`, `client`, or any UI library.
3. **No game-specific code in the core.** `common/`, `server/`, `client/` must never mention a specific game by name. Games are found only through the registry.
4. **JSON only on the wire.** Never `pickle`, `eval`, `exec`, or dynamic imports from unvalidated network input. A game ID received from a client is looked up in the registry's known IDs, never imported from a raw string.
5. **The server must not crash on bad input.** Isolate per-connection handling so one bad client cannot affect others. Malformed JSON, unknown types, oversize frames: log, send `error`, drop repeat offenders.
6. **Never block the event loop.** No `input()`, `time.sleep()`, or heavy computation in server coroutines. Terminal menus run before the loop starts.
7. **Standard library for the core.** Third-party packages only for UI and tests, declared in `pyproject.toml`.
8. **Quality baseline.** Type hints everywhere, dataclasses or `TypedDict` for messages, docstrings on public classes, `ruff` clean.
9. **UI files never import server code.**

## 5. Game plugin contract

Each game package exposes `GAME_INFO` in its `__init__.py`.

```python
# common/game_api.py (sketch)
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Any

@dataclass(frozen=True)
class GameInfo:
    id: str                  # "tictactoe", unique, lowercase
    name: str                # "Tic-Tac-Toe"
    min_players: int
    max_players: int
    tick_rate: float | None  # None = turn-based; 30.0 = real-time at 30 Hz
    logic_path: str          # "lan_games.games.tictactoe.logic:TicTacToeLogic"
    ui_paths: dict[str, str] # {"terminal": "...:TerminalUI", "pygame": "...:PygameUI"}
    version: str = "1.0"

class GameLogic(ABC):
    """Runs ONLY on the server. Pure rules, no I/O."""
    @abstractmethod
    def __init__(self, player_ids: list[str], options: dict[str, Any]): ...
    @abstractmethod
    def handle_action(self, player_id: str, action: dict) -> "ActionResult": ...
    @abstractmethod
    def view_for(self, player_id: str) -> dict: ...   # per-player view, no hidden info leaks
    def tick(self, dt: float) -> list[dict]: return [] # real-time games only
    @abstractmethod
    def is_over(self) -> bool: ...
    @abstractmethod
    def result(self) -> dict: ...
    def on_player_disconnect(self, player_id: str) -> None: ...
    def on_player_reconnect(self, player_id: str) -> None: ...

class GameUI(ABC):
    """Runs ONLY on the client. Renders state, produces actions."""
    @abstractmethod
    def __init__(self, my_player_id: str, send_action): ...
    @abstractmethod
    def on_state(self, state: dict) -> None: ...
    def on_event(self, event: dict) -> None: ...
    @abstractmethod
    def run(self) -> None: ...  # blocking UI loop; returns when the game ends
```

Registry behaviour: scan `games/*/`, import each package's `GAME_INFO`, skip broken games with a warning (never crash), reject duplicate IDs, load `logic` and `ui` modules lazily only for the chosen game.

Rules for game authors:

- All state and actions are JSON-serialisable.
- Never trust an action: validate type, range, turn order, legality.
- `view_for` must never leak hidden information.
- Real-time games advance in `tick`; turn-based games advance only in `handle_action`.

## 6. Network protocol

| Direction | Type | Purpose |
|---|---|---|
| C→S | `hello` | protocol version, player name, requested game id, optional reconnect token |
| S→C | `welcome` | player_id, session token, game info, roster |
| S→C | `reject` | wrong game, wrong version, room full, name taken |
| S→C | `lobby` | roster / ready states changed |
| C→S | `ready` | toggle ready |
| S→C | `start` | match begins, initial state, options |
| C→S | `action` | game-specific intent |
| S→C | `state` | the player's current view |
| S→C | `event` | one-off notifications |
| S→C | `error` | last action invalid, with reason |
| S→C | `game_over` | result payload |
| both | `ping` / `pong` | keepalive, latency |
| C→S | `bye` | graceful leave |

Lifecycle: connect → `hello` → `welcome`/`reject` → lobby → all ready → `start` → actions/states → `game_over` → lobby or quit.

Robustness requirements:

- `TCP_NODELAY` on both sides.
- Heartbeat about every 5 s; drop a peer silent for about 20 s.
- Session token: reconnect within about 60 s resumes the seat and sends a fresh `state`.
- Server binds to `0.0.0.0` and prints all local IPs on startup, with a hint that Radmin/ZeroTier users should use their VPN adapter address.

## 7. Menu and game selection flow

- **Server**: `python -m lan_games.server [--game ID] [--host 0.0.0.0] [--port 5555] [--players N]`. Without `--game`, show the terminal menu.
- **Client**: `python -m lan_games.client`. Menu: choose game and name, then enter host and port (remember the last used), connect, lobby, game UI.
- The handshake verifies the game ID. On mismatch the client says what the server is hosting and offers to switch automatically.
- If a game has several UIs, the client offers a choice; if `pygame` is missing, fall back to terminal or print the exact `pip install` hint.
- Manual IP:port is the primary connection method (works on LAN, Radmin, ZeroTier). LAN broadcast discovery is optional and must never be the only way.

## 8. Roadmap

Complete and verify one phase before starting the next. State your plan in a few lines before each phase; report afterwards.

| Phase | Scope | Done when |
|---|---|---|
| 0 | Skeleton: structure, `pyproject.toml` (extras `ui`, `dev`), README stub | `pip install -e .` works, `pytest` runs |
| 1 | `common/protocol.py`: framing, message types, limits | Tests: round-trip all types, fragmented reads, oversize and garbage rejected |
| 2 | `game_api.py` + `registry.py` | Tests: discovers dummy game, tolerates broken one, rejects duplicate IDs |
| 3 | Tic-Tac-Toe `logic.py`, no networking | Tests: legal/illegal moves, all win lines, draw, `view_for` |
| 4 | Server core: connection, session, runner, app, server menu + CLI | Socket integration tests on 127.0.0.1: full match, invalid action, wrong game, room full, mid-game disconnect |
| 5 | Client core + `ui_terminal.py` for Tic-Tac-Toe | 1 server + 2 clients play a full match |
| 6 | Robustness: heartbeat, timeouts, reconnect, graceful shutdown, clear error messages, logging | Kill/reconnect tests pass |
| 7 | Prove the architecture: Connect 4, then a real-time game (Pong or similar) | Both added **without editing `common/`, `server/`, or `client/`**. If an edit was needed, fix the plugin API and document why in `docs/decisions.md` |
| 8 | pygame UI for at least one game | Selectable from the client menu |
| 9 | Optional: chat, spectators, play again, game options, LAN discovery, replays, PyInstaller packaging | Only when asked |

## 9. Testing and quality

- Game logic tests need no network and cover every rule and every invalid input.
- Provide a reusable **fake client / bot** helper in `tests/` for scripted matches.
- `pytest` must pass and `ruff check` must be clean before any phase is declared done.

## 10. Working style

- Small, reviewable steps. Write tests together with the code.
- Prefer clear, boring code over clever code; humans and future agents will extend it.
- If the spec is ambiguous, choose the simplest option that keeps the architecture extensible, record it in `docs/decisions.md`, and continue. Ask the human only about choices that are costly to reverse (for example changing the wire protocol after Phase 4).
- Do not build Phase 9 features unless asked.
- Keep `README.md` current: install, run server, run client, playing over Radmin/ZeroTier (allow Python through the Windows firewall on the private profile, same port on both sides, verify with `ping` first), how to add a game.

## 11. Definition of done

**Per phase**

- Code written, type-checked, `ruff` clean.
- `pytest` passes, with new tests for new behaviour.
- Feature can be demonstrated with a documented command.
- README updated.

**Whole project (v1.0)**

- Two machines on a LAN or VPN can play Tic-Tac-Toe and Connect 4 through the terminal menus.
- A real-time game runs smoothly at its tick rate with two clients.
- A new game can be added by creating one folder and following `docs/adding_a_game.md` (you write it, including a minimal copy-paste template game).
- Disconnect and reconnect work; invalid input never crashes the server.

## 12. Things to avoid

- Sending the whole game object or Python-specific types to clients.
- Client-side prediction or lockstep simulation (out of scope for v1).
- Global mutable state shared between server and client modules.
- Hardcoded IPs or ports.
- Over-engineering: no plugin frameworks, ORMs, message brokers, or web servers.

## 13. Prompts for the human to use

**Kick-off**

> Read `AGENTS.md`. Execute Phase 0 and Phase 1 only. Show me the directory tree, the protocol design, and the test results. Do not start Phase 2 until I confirm.

**Per phase**

> Execute Phase N from the roadmap. Follow the non-negotiable rules. Write tests alongside the code. When finished, report what was built, how to run it, test results, and any deviation from the plan.

**Adding a game later**

> Add a new game `<name>` following `docs/adding_a_game.md`. Players: `<min>`-`<max>`. Turn-based or real-time: `<...>`. Rules: `<...>`. You may only create or edit files inside `games/<name>/` and its tests. If you believe core changes are required, stop and explain why.

## 14. Defaults for open questions

1. The host can also play: server and client are separate processes, the host starts both.
2. Max players per room comes from the game's `max_players`.
3. Switching games without restarting the server: later (Phase 9).
4. Default UI: terminal first, pygame from Phase 8.
5. Default port: 5555.
