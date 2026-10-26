"""Pong game plugin metadata."""

from lan_games.common.game_api import GameInfo

GAME_INFO = GameInfo(
    id="pong",
    name="Pong",
    min_players=2,
    max_players=2,
    tick_rate=30.0,
    logic_path="lan_games.games.pong.logic:PongLogic",
    ui_paths={
        "terminal": "lan_games.games.pong.ui_terminal:TerminalUI",
        "pygame": "lan_games.games.pong.ui_pygame:PygameUI",
    },
)
