"""Pure authoritative rules for a compact two-player Pong game."""

from __future__ import annotations

from typing import Any

from lan_games.common.game_api import ActionResult, GameLogic


class PongLogic(GameLogic):
    """Fixed-rate Pong with server-simulated paddles, ball, and scoring."""

    def __init__(self, player_ids: list[str], options: dict[str, Any]) -> None:
        if len(player_ids) != 2 or len(set(player_ids)) != 2:
            raise ValueError("Pong requires two unique players")
        self.player_ids = list(player_ids)
        self.paddles = [-0.0, -0.0]
        self.directions = [0, 0]
        self.ball = [0.0, 0.0]
        self.velocity = [0.75, 0.38]
        self.scores = [0, 0]
        self.winner: str | None = None
        self.paddle_speed = 1.3
        self.ball_speed = 0.9

    def handle_action(self, player_id: str, action: dict[str, Any]) -> ActionResult:
        if self.is_over():
            return ActionResult(False, "the game is over")
        if player_id not in self.player_ids:
            return ActionResult(False, "unknown player")
        if not isinstance(action, dict) or action.get("type") != "move":
            return ActionResult(False, "expected a move action")
        direction = action.get("direction")
        if (
            not isinstance(direction, int)
            or isinstance(direction, bool)
            or direction not in (-1, 0, 1)
        ):
            return ActionResult(False, "direction must be -1, 0, or 1")
        self.directions[self.player_ids.index(player_id)] = direction
        return ActionResult(True)

    def tick(self, dt: float) -> list[dict[str, Any]]:
        if self.is_over() or not isinstance(dt, (int, float)) or dt <= 0:
            return []
        for index in range(2):
            self.paddles[index] = max(
                -0.85,
                min(0.85, self.paddles[index] + self.directions[index] * self.paddle_speed * dt),
            )
        x, y = self.ball
        vx, vy = self.velocity
        x += vx * dt
        y += vy * dt
        if y >= 0.96 or y <= -0.96:
            y = max(-0.96, min(0.96, y))
            vy = -vy
        if vx < 0 and x <= -0.88:
            if abs(y - self.paddles[0]) <= 0.25:
                x = -0.88
                vx = abs(vx) + 0.08
                vy += (y - self.paddles[0]) * 0.7
            else:
                self._score(1)
                return [{"type": "point", "player": self.player_ids[1]}]
        elif vx > 0 and x >= 0.88:
            if abs(y - self.paddles[1]) <= 0.25:
                x = 0.88
                vx = -(abs(vx) + 0.08)
                vy += (y - self.paddles[1]) * 0.7
            else:
                self._score(0)
                return [{"type": "point", "player": self.player_ids[0]}]
        self.ball = [x, y]
        self.velocity = [vx, max(-1.5, min(1.5, vy))]
        return []

    def view_for(self, player_id: str) -> dict[str, Any]:
        if player_id not in self.player_ids:
            raise ValueError("unknown player")
        return {
            "you": self.player_ids.index(player_id),
            "paddles": self.paddles[:],
            "ball": self.ball[:],
            "scores": self.scores[:],
            "winner": self.winner,
            "over": self.is_over(),
        }

    def is_over(self) -> bool:
        return self.winner is not None

    def result(self) -> dict[str, Any]:
        return {"winner": self.winner, "scores": self.scores[:]}

    def _score(self, player_index: int) -> None:
        self.scores[player_index] += 1
        if self.scores[player_index] >= 5:
            self.winner = self.player_ids[player_index]
            return
        direction = 1 if player_index == 0 else -1
        self.ball = [0.0, 0.0]
        self.velocity = [direction * 0.75, 0.38]
