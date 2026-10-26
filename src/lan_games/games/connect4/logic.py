"""Pure rules for Connect Four."""

from __future__ import annotations

from typing import Any

from lan_games.common.game_api import ActionResult, GameLogic

ROWS = 6
COLUMNS = 7


class ConnectFourLogic(GameLogic):
    """A standard two-player Connect Four match."""

    def __init__(self, player_ids: list[str], options: dict[str, Any]) -> None:
        if len(player_ids) != 2 or len(set(player_ids)) != 2:
            raise ValueError("Connect Four requires two unique players")
        self.player_ids = list(player_ids)
        self.board: list[list[str | None]] = [[None] * COLUMNS for _ in range(ROWS)]
        self.turn = 0
        self.winner: str | None = None

    def handle_action(self, player_id: str, action: dict[str, Any]) -> ActionResult:
        if self.is_over():
            return ActionResult(False, "the game is over")
        if player_id not in self.player_ids:
            return ActionResult(False, "unknown player")
        if player_id != self.player_ids[self.turn]:
            return ActionResult(False, "it is not your turn")
        if not isinstance(action, dict) or action.get("type") != "drop":
            return ActionResult(False, "expected a drop action")
        column = action.get("column")
        if not isinstance(column, int) or isinstance(column, bool) or not 0 <= column < COLUMNS:
            return ActionResult(False, f"column must be between 0 and {COLUMNS - 1}")
        row = next((r for r in range(ROWS - 1, -1, -1) if self.board[r][column] is None), None)
        if row is None:
            return ActionResult(False, "that column is full")
        symbol = self.symbol_for(player_id)
        self.board[row][column] = symbol
        if self._has_four(row, column, symbol):
            self.winner = player_id
        else:
            self.turn = 1 - self.turn
        return ActionResult(True)

    def view_for(self, player_id: str) -> dict[str, Any]:
        if player_id not in self.player_ids:
            raise ValueError("unknown player")
        return {
            "board": [row[:] for row in self.board],
            "you": self.symbol_for(player_id),
            "current_player": self.player_ids[self.turn] if not self.is_over() else None,
            "winner": self.winner,
            "over": self.is_over(),
        }

    def is_over(self) -> bool:
        return self.winner is not None or all(
            cell is not None for row in self.board for cell in row
        )

    def result(self) -> dict[str, Any]:
        return {"winner": self.winner, "draw": self.winner is None}

    def symbol_for(self, player_id: str) -> str:
        if player_id not in self.player_ids:
            raise ValueError("unknown player")
        return "R" if self.player_ids.index(player_id) == 0 else "Y"

    def _has_four(self, row: int, column: int, symbol: str) -> bool:
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            count = 1
            for direction in (-1, 1):
                r, c = row + direction * dr, column + direction * dc
                while (
                    0 <= r < ROWS
                    and 0 <= c < COLUMNS
                    and self.board[r][c] == symbol
                ):
                    count += 1
                    r += direction * dr
                    c += direction * dc
            if count >= 4:
                return True
        return False
