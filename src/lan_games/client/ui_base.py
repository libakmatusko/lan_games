"""Client-only UI base classes and terminal input coordination."""

from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from lan_games.common.game_api import GameUI


class TerminalGameUI(GameUI, ABC):
    """Run a terminal game's blocking input away from the asyncio event loop."""

    def __init__(
        self, my_player_id: str, send_action: Callable[[dict[str, Any]], None]
    ) -> None:
        self.my_player_id = my_player_id
        self.send_action = send_action
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._dirty = threading.Event()
        self._finished = threading.Event()
        self._commands: queue.Queue[str] = queue.Queue()
        self._result: dict[str, Any] | None = None

    def on_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._state = state
        self._dirty.set()

    def on_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "game_over":
            self._result = event.get("data", {})
            self._finished.set()

    def run(self) -> None:
        reader = threading.Thread(target=self._read_commands, daemon=True)
        reader.start()
        self._dirty.set()
        while not self._finished.is_set():
            if self._dirty.wait(0.1):
                self._dirty.clear()
                with self._lock:
                    state = dict(self._state)
                self.render(state)
            try:
                command = self._commands.get(timeout=0.1)
            except queue.Empty:
                continue
            if command:
                self.handle_command(command)
        print(f"Game over: {self._result}")

    @abstractmethod
    def render(self, state: dict[str, Any]) -> None:
        """Render a fresh authoritative state."""

    @abstractmethod
    def handle_command(self, command: str) -> None:
        """Parse one terminal command into an intent."""

    def _read_commands(self) -> None:
        while not self._finished.is_set():
            try:
                command = input("> ")
            except EOFError:
                return
            self._commands.put(command.strip())
