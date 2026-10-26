"""Connect Four game plugin metadata."""

from lan_games.common.game_api import GameInfo

GAME_INFO = GameInfo(
    id="connect4",
    name="Connect Four",
    min_players=2,
    max_players=2,
    tick_rate=None,
    logic_path="lan_games.games.connect4.logic:ConnectFourLogic",
    ui_paths={"terminal": "lan_games.games.connect4.ui_terminal:TerminalUI"},
)
