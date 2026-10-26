import importlib
import sys
from uuid import uuid4

from lan_games.common.registry import GameRegistry


def _create_plugin(root, package, folder, game_id, *, broken=False, marker=False):
    game_dir = root / package / folder
    game_dir.mkdir(parents=True)
    if broken:
        (game_dir / "__init__.py").write_text("raise RuntimeError('broken plugin')\n")
        return
    (game_dir / "__init__.py").write_text(
        "from lan_games.common.game_api import GameInfo\n"
        f"GAME_INFO = GameInfo(id={game_id!r}, name='Dummy', min_players=1, "
        "max_players=1, tick_rate=None, "
        f"logic_path='{package}.{folder}.logic:DummyLogic', ui_paths={{}})\n"
    )
    (game_dir / "logic.py").write_text(
        "class DummyLogic:\n"
        f"    marker = {marker!r}\n"
    )


def test_discovers_game_skips_broken_and_loads_logic_lazily(tmp_path) -> None:
    package = f"gameplugins_{uuid4().hex}"
    package_dir = tmp_path / package
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    _create_plugin(tmp_path, package, "dummy", "dummy", marker="loaded")
    _create_plugin(tmp_path, package, "broken", "broken", broken=True)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        registry = GameRegistry(package)
        assert list(registry.discover()) == ["dummy"]
        assert f"{package}.dummy.logic" not in sys.modules
        logic = registry.load("dummy", "logic")
        assert logic.marker == "loaded"
    finally:
        sys.path.remove(str(tmp_path))


def test_rejects_duplicate_game_ids(tmp_path, caplog) -> None:
    package = f"duplicateplugins_{uuid4().hex}"
    package_dir = tmp_path / package
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    _create_plugin(tmp_path, package, "first", "same")
    _create_plugin(tmp_path, package, "second", "same")
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        registry = GameRegistry(package)
        assert list(registry.discover()) == ["same"]
        assert "duplicate game ID" in caplog.text
    finally:
        sys.path.remove(str(tmp_path))
