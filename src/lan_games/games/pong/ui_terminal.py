"""Terminal control UI for the real-time Pong plugin."""

from __future__ import annotations

from typing import Any

from lan_games.client.ui_base import TerminalGameUI


class TerminalUI(TerminalGameUI):
    """Show a compact live score and send paddle direction intents."""

    def render(self, state: dict[str, Any]) -> None:
        scores = state.get("scores", [0, 0])
        you = state.get("you", 0)
        ball = state.get("ball", [0, 0])
        print(
            f"\rPong score {scores[0]}–{scores[1]} | You: player {you + 1} | "
            f"ball ({ball[0]:.2f}, {ball[1]:.2f}) | w/s or i/k; x stops",
            end="",
            flush=True,
        )
        print()

    def handle_command(self, command: str) -> None:
        with self._lock:
            player = self._state.get("you", 0)
        key = command.casefold()
        direction = 0
        if (player == 0 and key == "w") or (player == 1 and key == "i"):
            direction = 1
        elif (player == 0 and key == "s") or (player == 1 and key == "k"):
            direction = -1
        elif key not in {"x", "stop"}:
            print("Use w/s for player 1, i/k for player 2, or x to stop.")
            return
        self.send_action({"type": "move", "direction": direction})
