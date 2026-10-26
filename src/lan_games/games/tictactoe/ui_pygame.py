"""Optional pygame UI for Tic-Tac-Toe."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pygame

from lan_games.common.game_api import GameUI


class PygameUI(GameUI):
    """Render a clickable board; pygame is imported only when this UI is chosen."""

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
        screen = pygame.display.set_mode((480, 520))
        pygame.display.set_caption("LAN Games — Tic-Tac-Toe")
        font = pygame.font.Font(None, 80)
        small_font = pygame.font.Font(None, 30)
        clock = pygame.time.Clock()
        running = True
        while running and not self.finished:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    x, y = event.pos
                    if 0 <= x < 480 and 0 <= y < 480:
                        self.send_action(
                            {"type": "move", "row": y // 160, "col": x // 160}
                        )
            screen.fill((24, 28, 40))
            for index in (1, 2):
                pygame.draw.line(
                    screen, (225, 230, 240), (index * 160, 0), (index * 160, 480), 4
                )
                pygame.draw.line(
                    screen, (225, 230, 240), (0, index * 160), (480, index * 160), 4
                )
            board = self.state.get("board", [])
            for row, cells in enumerate(board):
                for col, mark in enumerate(cells):
                    if mark:
                        color = (245, 190, 70) if mark == "X" else (90, 190, 240)
                        text = font.render(mark, True, color)
                        screen.blit(text, text.get_rect(center=(col * 160 + 80, row * 160 + 80)))
            footer = small_font.render(f"You are {self.state.get('you', '?')}", True, "white")
            screen.blit(footer, (12, 488))
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()
