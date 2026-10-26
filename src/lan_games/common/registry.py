"""Game discovery and lazy plugin loading."""

from __future__ import annotations

import importlib
import logging
import math
import pkgutil
import re
from collections.abc import Iterable
from types import ModuleType
from typing import Any

from lan_games.common.game_api import GameInfo

LOGGER = logging.getLogger(__name__)
_GAME_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class GameRegistry:
    """Discover trusted game packages and load their implementations lazily."""

    def __init__(self, package: str = "lan_games.games") -> None:
        self.package = package
        self.games: dict[str, GameInfo] = {}
        self._modules: dict[str, ModuleType] = {}

    def discover(self) -> dict[str, GameInfo]:
        """Scan direct child packages, warning and skipping broken plugins."""
        self.games.clear()
        self._modules.clear()
        try:
            package_module = importlib.import_module(self.package)
            paths = list(package_module.__path__)
        except (ImportError, AttributeError) as exc:
            LOGGER.warning("Unable to scan game package %s: %s", self.package, exc)
            return self.games
        for entry in pkgutil.iter_modules(paths):
            if not entry.ispkg:
                continue
            module_name = f"{self.package}.{entry.name}"
            try:
                module = importlib.import_module(module_name)
                info = module.GAME_INFO
                self._validate_info(info)
                if info.id in self.games:
                    LOGGER.warning("Skipping duplicate game ID %s from %s", info.id, module_name)
                    continue
                self.games[info.id] = info
                self._modules[info.id] = module
            except Exception:
                LOGGER.exception("Skipping broken game package %s", module_name)
        return dict(self.games)

    @staticmethod
    def _validate_info(info: Any) -> None:
        if not isinstance(info, GameInfo):
            raise ValueError("GAME_INFO must be a GameInfo instance")
        if not isinstance(info.id, str) or not _GAME_ID.fullmatch(info.id):
            raise ValueError(f"invalid game ID: {info.id!r}")
        if (
            not isinstance(info.name, str)
            or not info.name
            or type(info.min_players) is not int
            or type(info.max_players) is not int
            or not 1 <= info.min_players <= info.max_players
        ):
            raise ValueError(f"invalid player limits for {info.id}")
        if info.tick_rate is not None and (
            not isinstance(info.tick_rate, (int, float))
            or not math.isfinite(info.tick_rate)
            or info.tick_rate <= 0
        ):
            raise ValueError(f"invalid tick rate for {info.id}")
        if not isinstance(info.ui_paths, dict):
            raise ValueError(f"invalid UI paths for {info.id}")
        for path in [info.logic_path, *info.ui_paths.values()]:
            if not isinstance(path, str) or ":" not in path:
                raise ValueError(f"invalid implementation path for {info.id}")

    def get(self, game_id: str) -> GameInfo:
        """Get known metadata without importing implementation modules."""
        try:
            return self.games[game_id]
        except KeyError as exc:
            raise KeyError(f"unknown game ID: {game_id}") from exc

    def load(self, game_id: str, kind: str) -> Any:
        """Load a selected plugin implementation from trusted registered metadata."""
        info = self.get(game_id)
        if kind == "logic":
            path = info.logic_path
        else:
            try:
                path = info.ui_paths[kind]
            except KeyError as exc:
                raise KeyError(f"game {game_id} has no {kind!r} UI") from exc
        module_name, separator, attribute = path.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError(f"invalid implementation path: {path!r}")
        module = importlib.import_module(module_name)
        return getattr(module, attribute)

    def ids(self) -> Iterable[str]:
        """Return discovered game IDs in insertion order."""
        return self.games.keys()
