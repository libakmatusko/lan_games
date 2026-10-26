"""Pure rules for Tic-Tac-Toe."""

from __future__ import annotations

from typing import Any

from lan_games.common.game_api import ActionResult, GameLogic


class TicTacToeLogic(GameLogic):
    """A standard two-player Tic-Tac-Toe match."""

    def __init__(self, player_ids: list[str], options: dict[str, Any]) -> None:
        if len(player_ids) != 2 or len(set(player_ids)) != 2:
            raise ValueError("Tic-Tac-Toe requires two unique players")
        self.player_ids = list(player_ids)
        self.board: list[list[str | None]] = [[None] * 3 for _ in range(3)]
        self.turn = 0
        self.winner: str | None = None

    def handle_action(self, player_id: str, action: dict[str, Any]) -> ActionResult:
        if self.is_over():
            return ActionResult(False, "the game is over")
        if player_id not in self.player_ids:
            return ActionResult(False, "unknown player")
        if player_id != self.player_ids[self.turn]:
            return ActionResult(False, "it is not your turn")
        if not isinstance(action, dict) or action.get("type") != "move":
            return ActionResult(False, "expected a move action")
        row, col = action.get("row"), action.get("col")
        if (
            not isinstance(row, int)
            or isinstance(row, bool)
            or not isinstance(col, int)
            or isinstance(col, bool)
            or not 0 <= row < 3
            or not 0 <= col < 3
        ):
            return ActionResult(False, "row and column must be between 0 and 2")
        if self.board[row][col] is not None:
            return ActionResult(False, "that square is occupied")
        self.board[row][col] = self.symbol_for(player_id)
        if self._has_won(self.symbol_for(player_id)):
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
        return "X" if self.player_ids.index(player_id) == 0 else "O"

    def _has_won(self, symbol: str) -> bool:
        lines = [
            *self.board,
            *[[self.board[row][col] for row in range(3)] for col in range(3)],
            [self.board[i][i] for i in range(3)],
            [self.board[i][2 - i] for i in range(3)],
        ]
        return any(all(cell == symbol for cell in line) for line in lines)
