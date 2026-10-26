"""Optional responsive pygame controls and display for Pong."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pygame

from lan_games.common.game_api import GameUI


class PygameUI(GameUI):
    """Render the authoritative ball and send paddle movement intents."""

    def __init__(
        self, my_player_id: str, send_action: Callable[[dict[str, Any]], None]
    ) -> None:
        self.my_player_id = my_player_id
        self.send_action = send_action
        self.state: dict[str, Any] = {}
        self.finished = False

    def on_state(self, state: dict[str, Any]) -> None:
        self.state = state

    def on_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "game_over":
            self.finished = True

    def run(self) -> None:
        pygame.init()
        width, height = 900, 560
        screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("LAN Games — Pong")
        font = pygame.font.Font(None, 40)
        clock = pygame.time.Clock()
        direction = 0
        player = 0
        running = True
        while running and not self.finished:
            player = self.state.get("you", player)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
                    pressed = event.type == pygame.KEYDOWN
                    key = event.key
                    up = pygame.K_w if player == 0 else pygame.K_UP
                    down = pygame.K_s if player == 0 else pygame.K_DOWN
                    new_direction = (
                        1 if pressed and key == up else -1 if pressed and key == down else 0
                    )
                    if key in (up, down):
                        direction = new_direction if pressed else 0
                        self.send_action({"type": "move", "direction": direction})
            screen.fill((18, 24, 36))
            pygame.draw.line(screen, (95, 110, 135), (width // 2, 0), (width // 2, height), 2)
            paddles = self.state.get("paddles", [0.0, 0.0])
            for index, x in enumerate((35, width - 35)):
                y = int((0.5 - paddles[index] / 2) * height)
                pygame.draw.rect(screen, (230, 235, 245), (x - 8, y - 48, 16, 96))
            ball = self.state.get("ball", [0.0, 0.0])
            ball_x = int((ball[0] + 1) * width / 2)
            ball_y = int((0.5 - ball[1] / 2) * height)
            pygame.draw.circle(screen, (255, 195, 75), (ball_x, ball_y), 10)
            scores = self.state.get("scores", [0, 0])
            score = font.render(f"{scores[0]}      {scores[1]}", True, "white")
            screen.blit(score, score.get_rect(center=(width // 2, 35)))
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()
