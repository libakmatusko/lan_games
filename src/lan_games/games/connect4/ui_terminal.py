"""Terminal UI for Connect Four."""

from __future__ import annotations

from typing import Any

from lan_games.client.ui_base import TerminalGameUI


class TerminalUI(TerminalGameUI):
    """Display the board and send column drop intents."""

    def render(self, state: dict[str, Any]) -> None:
        print("\n  1 2 3 4 5 6 7")
        for row in state.get("board", []):
            print("  " + " ".join(cell or "." for cell in row))
        print(f"You are {state.get('you', '?')}. Enter a column number.")

    def handle_command(self, command: str) -> None:
        try:
            column = int(command) - 1
        except ValueError:
            print("Enter a column from 1 to 7.")
            return
        self.send_action({"type": "drop", "column": column})
