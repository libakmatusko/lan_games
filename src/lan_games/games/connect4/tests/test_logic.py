import pytest

from lan_games.games.connect4.logic import ConnectFourLogic


def drop(column: int) -> dict[str, object]:
    return {"type": "drop", "column": column}


def test_gravity_full_column_and_horizontal_win() -> None:
    game = ConnectFourLogic(["a", "b"], {})
    for column in [0, 6, 1, 6, 2, 5]:
        player = "a" if game.turn == 0 else "b"
        assert game.handle_action(player, drop(column)).accepted
    assert game.board[5] == ["R", "R", "R", None, None, "Y", "Y"]
    assert game.handle_action("a", drop(3)).accepted
    assert game.result() == {"winner": "a", "draw": False}
    assert not game.handle_action("b", drop(0)).accepted


def test_rejects_bad_column_and_detects_vertical_and_diagonal_wins() -> None:
    game = ConnectFourLogic(["a", "b"], {})
    assert not game.handle_action("a", drop(True)).accepted
    assert not game.handle_action("a", drop(7)).accepted
    for col in [0, 1, 0, 1, 0, 1, 0]:
        player = "a" if game.turn == 0 else "b"
        assert game.handle_action(player, drop(col)).accepted
    assert game.result()["winner"] == "a"


@pytest.mark.parametrize(
    "cells",
    [
        [(5, 0), (4, 1), (3, 2), (2, 3)],
        [(2, 0), (3, 1), (4, 2), (5, 3)],
    ],
)
def test_detects_both_diagonal_win_directions(
    cells: list[tuple[int, int]],
) -> None:
    game = ConnectFourLogic(["a", "b"], {})
    for row, column in cells:
        game.board[row][column] = "R"
    assert game._has_four(*cells[-1], "R")


def test_rejects_a_full_column_and_recognizes_a_full_board_draw() -> None:
    game = ConnectFourLogic(["a", "b"], {})
    game.board = [
        ["R", None, None, None, None, None, None],
        ["Y", None, None, None, None, None, None],
        ["R", None, None, None, None, None, None],
        ["Y", None, None, None, None, None, None],
        ["R", None, None, None, None, None, None],
        ["Y", None, None, None, None, None, None],
    ]
    assert not game.handle_action("a", drop(0)).accepted

    draw = ConnectFourLogic(["a", "b"], {})
    draw.board = [
        ["R" if (row + 2 * col) % 4 < 2 else "Y" for col in range(7)]
        for row in range(6)
    ]
    assert draw.is_over()
    assert draw.result() == {"winner": None, "draw": True}
