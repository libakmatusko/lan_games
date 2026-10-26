"""Terminal UI for Tic-Tac-Toe."""

from __future__ import annotations

from typing import Any

from lan_games.client.ui_base import TerminalGameUI


class TerminalUI(TerminalGameUI):
    """Display the board and send row/column move intents."""

    def render(self, state: dict[str, Any]) -> None:
        board = state.get("board", [])
        print("\n  1 2 3")
        for row_index, row in enumerate(board, start=1):
            cells = [cell or "." for cell in row]
            print(f"{row_index} {'|'.join(cells)}")
            if row_index < 3:
                print("  -----")
        print(f"You are {state.get('you', '?')}. Enter row and column, e.g. 2 3.")

    def handle_command(self, command: str) -> None:
        parts = command.replace(",", " ").split()
        if len(parts) != 2:
            print("Enter two numbers: row column.")
            return
        try:
            row, col = (int(part) - 1 for part in parts)
        except ValueError:
            print("Row and column must be numbers.")
            return
        self.send_action({"type": "move", "row": row, "col": col})
