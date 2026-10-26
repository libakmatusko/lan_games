# Adding a game

1. Create `src/lan_games/games/<game_id>/`.
2. Export a unique lowercase `GAME_INFO` from `__init__.py`.
3. Implement pure rules in `logic.py`; validate every action and return only
   JSON-serializable views/results.
4. Add at least one client UI in `ui_terminal.py`. UIs send intents and render
   server-provided state; they never implement rules.
5. Add rule tests in `tests/`, then run `pytest` and `ruff check`.

The registry discovers direct child packages automatically. Implementation
paths are trusted plugin metadata; never derive a Python import from a value
received over the network. The server calls `handle_action` and `tick`, while
the client receives `view_for` snapshots.

## Minimal copy-paste template

Replace `samplegame` and the package paths consistently:

```python
# src/lan_games/games/samplegame/__init__.py
from lan_games.common.game_api import GameInfo

GAME_INFO = GameInfo(
    id="samplegame",
    name="Sample Game",
    min_players=2,
    max_players=2,
    tick_rate=None,  # Use a positive rate (e.g. 30.0) for real-time games.
    logic_path="lan_games.games.samplegame.logic:SampleLogic",
    ui_paths={"terminal": "lan_games.games.samplegame.ui_terminal:TerminalUI"},
)
```

```python
# src/lan_games/games/samplegame/logic.py
from typing import Any

from lan_games.common.game_api import ActionResult, GameLogic


class SampleLogic(GameLogic):
    def __init__(self, player_ids: list[str], options: dict[str, Any]) -> None:
        if len(player_ids) != 2:
            raise ValueError("Sample Game requires two players")
        self.players = player_ids[:]
        self.moves: list[str] = []
        self.winner: str | None = None

    def handle_action(self, player_id: str, action: dict[str, Any]) -> ActionResult:
        if self.is_over():
            return ActionResult(False, "game is over")
        if not isinstance(action, dict) or player_id not in self.players:
            return ActionResult(False, "invalid move")
        if action.get("type") != "move":
            return ActionResult(False, "invalid move")
        self.moves.append(player_id)
        self.winner = player_id
        return ActionResult(True)

    def view_for(self, player_id: str) -> dict[str, Any]:
        if player_id not in self.players:
            raise ValueError("unknown player")
        return {"moves": self.moves[:], "winner": self.winner}

    def is_over(self) -> bool:
        return self.winner is not None

    def result(self) -> dict[str, Any]:
        return {"winner": self.winner}
```

```python
# src/lan_games/games/samplegame/ui_terminal.py
from typing import Any

from lan_games.client.ui_base import TerminalGameUI


class TerminalUI(TerminalGameUI):
    def render(self, state: dict[str, Any]) -> None:
        print(f"Moves so far: {len(state.get('moves', []))}")

    def handle_command(self, command: str) -> None:
        if command:
            self.send_action({"type": "move"})
```

```python
# src/lan_games/games/samplegame/tests/test_logic.py
from lan_games.games.samplegame.logic import SampleLogic


def test_first_valid_move_wins() -> None:
    game = SampleLogic(["alice", "bob"], {})
    assert game.handle_action("alice", {"type": "move"}).accepted
    assert not game.handle_action("bob", {"type": "move"}).accepted
    assert game.result() == {"winner": "alice"}
```

Start this plugin with `python -m lan_games.server --game samplegame`.
