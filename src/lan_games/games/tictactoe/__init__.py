"""Tic-Tac-Toe game plugin metadata."""

from lan_games.common.game_api import GameInfo

GAME_INFO = GameInfo(
    id="tictactoe",
    name="Tic-Tac-Toe",
    min_players=2,
    max_players=2,
    tick_rate=None,
    logic_path="lan_games.games.tictactoe.logic:TicTacToeLogic",
    ui_paths={
        "terminal": "lan_games.games.tictactoe.ui_terminal:TerminalUI",
        "pygame": "lan_games.games.tictactoe.ui_pygame:PygameUI",
    },
)
