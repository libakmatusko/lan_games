"""Generic game lifecycle and authoritative action/tick routing."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from lan_games.common.game_api import ActionResult, GameInfo, GameLogic

LOGGER = logging.getLogger(__name__)
SendOne = Callable[[str, str, dict[str, Any]], Awaitable[None]]
SendAll = Callable[[str, dict[str, Any]], Awaitable[None]]


class GameRunner:
    """Own a plugin logic instance and route all game mutations through it."""

    def __init__(
        self,
        info: GameInfo,
        logic_type: type[GameLogic],
        player_ids: list[str],
        options: dict[str, Any],
        send_one: SendOne,
        send_all: SendAll,
    ) -> None:
        self.info = info
        self.logic = logic_type(player_ids, options)
        self.player_ids = player_ids[:]
        self.options = options
        self.send_one = send_one
        self.send_all = send_all
        self._lock = asyncio.Lock()
        self._tick_task: asyncio.Task[None] | None = None
        self._finished = False

    async def start(self) -> None:
        """Start periodic server ticks for a real-time game."""
        if self.info.tick_rate is not None:
            self._tick_task = asyncio.create_task(self._tick_loop())

    async def handle_action(self, player_id: str, action: Any) -> None:
        """Validate and route one untrusted client action."""
        if self._finished:
            await self.send_one(player_id, "error", {"reason": "the game is over"})
            return
        if not isinstance(action, dict):
            await self.send_one(player_id, "error", {"reason": "action must be an object"})
            return
        async with self._lock:
            try:
                result = self.logic.handle_action(player_id, action)
                if not isinstance(result, ActionResult):
                    raise TypeError("game action handler must return ActionResult")
            except Exception:
                LOGGER.exception("Game plugin failed while handling an action")
                await self.send_one(player_id, "error", {"reason": "game rejected the action"})
                return
            if not result.accepted:
                await self.send_one(
                    player_id,
                    "error",
                    {"reason": result.reason or "action was rejected"},
                )
                return
            for event in result.events:
                if isinstance(event, dict):
                    await self.send_all("event", event)
            await self.publish_states()
            await self._finish_if_over()

    async def publish_states(self) -> None:
        """Send each player only the view intended for their seat."""
        for player_id in self.player_ids:
            try:
                state = self.logic.view_for(player_id)
                if not isinstance(state, dict):
                    raise TypeError("view_for must return an object")
                await self.send_one(player_id, "state", state)
            except Exception:
                LOGGER.exception("Game plugin failed while producing a player view")
                await self.send_one(player_id, "error", {"reason": "unable to produce game state"})

    async def player_disconnected(self, player_id: str) -> None:
        """Notify the plugin about a temporary player disconnect."""
        try:
            self.logic.on_player_disconnect(player_id)
        except Exception:
            LOGGER.exception("Game plugin failed on player disconnect")

    async def player_reconnected(self, player_id: str) -> None:
        """Notify the plugin about a resumed seat."""
        try:
            self.logic.on_player_reconnect(player_id)
        except Exception:
            LOGGER.exception("Game plugin failed on player reconnect")

    async def close(self) -> None:
        """Stop the real-time tick task."""
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None

    async def _tick_loop(self) -> None:
        assert self.info.tick_rate is not None
        period = 1.0 / self.info.tick_rate
        previous = time.monotonic()
        try:
            while not self._finished:
                await asyncio.sleep(period)
                now = time.monotonic()
                dt = min(now - previous, period * 2)
                previous = now
                async with self._lock:
                    try:
                        events = self.logic.tick(dt)
                        for event in events:
                            if isinstance(event, dict):
                                await self.send_all("event", event)
                        await self.publish_states()
                        await self._finish_if_over()
                    except Exception:
                        LOGGER.exception("Game plugin failed during a real-time tick")
                        self._finished = True
        except asyncio.CancelledError:
            raise

    async def _finish_if_over(self) -> None:
        if self._finished or not self.logic.is_over():
            return
        self._finished = True
        await self.send_all("game_over", self.logic.result())
        current = asyncio.current_task()
        if self._tick_task is not None and self._tick_task is not current:
            self._tick_task.cancel()
