"""Public interfaces implemented by game plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GameInfo:
    """Metadata used to list and load a game plugin."""

    id: str
    name: str
    min_players: int
    max_players: int
    tick_rate: float | None
    logic_path: str
    ui_paths: dict[str, str] = field(default_factory=dict)
    version: str = "1.0"


@dataclass(frozen=True)
class ActionResult:
    """Result of validating and applying a player intent."""

    accepted: bool
    reason: str = ""
    events: tuple[dict[str, Any], ...] = ()


class GameLogic(ABC):
    """Pure game rules owned and executed by the server."""

    @abstractmethod
    def __init__(self, player_ids: list[str], options: dict[str, Any]) -> None:
        """Initialize a match for the supplied player IDs and options."""

    @abstractmethod
    def handle_action(self, player_id: str, action: dict[str, Any]) -> ActionResult:
        """Validate and apply one player intent."""

    @abstractmethod
    def view_for(self, player_id: str) -> dict[str, Any]:
        """Return a JSON-safe view for one player."""

    def tick(self, dt: float) -> list[dict[str, Any]]:
        """Advance a real-time game by ``dt`` seconds."""
        return []

    @abstractmethod
    def is_over(self) -> bool:
        """Return whether the match has ended."""

    @abstractmethod
    def result(self) -> dict[str, Any]:
        """Return the public match result."""

    def on_player_disconnect(self, player_id: str) -> None:
        """Notify the game that a player has disconnected."""
        return None

    def on_player_reconnect(self, player_id: str) -> None:
        """Notify the game that a player has reconnected."""
        return None


class GameUI(ABC):
    """Client-side game UI; it must not depend on server code."""

    @abstractmethod
    def __init__(
        self, my_player_id: str, send_action: Callable[[dict[str, Any]], None]
    ) -> None:
        """Create a UI with a callback for sending player intents."""

    @abstractmethod
    def on_state(self, state: dict[str, Any]) -> None:
        """Receive the current per-player view."""

    def on_event(self, event: dict[str, Any]) -> None:
        """Receive a one-off event from the server."""
        return None

    @abstractmethod
    def run(self) -> None:
        """Run the UI until the game ends."""
