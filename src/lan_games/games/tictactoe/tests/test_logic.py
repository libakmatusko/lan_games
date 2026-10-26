from lan_games.games.tictactoe.logic import TicTacToeLogic


def move(row: int, col: int) -> dict[str, object]:
    return {"type": "move", "row": row, "col": col}


def test_rejects_invalid_moves_and_enforces_turns() -> None:
    game = TicTacToeLogic(["a", "b"], {})
    assert not game.handle_action("b", move(0, 0)).accepted
    assert not game.handle_action("a", move(3, 0)).accepted
    assert not game.handle_action("a", move(True, 0)).accepted
    assert game.handle_action("a", move(0, 0)).accepted
    assert not game.handle_action("b", move(0, 0)).accepted
    assert game.handle_action("b", move(1, 0)).accepted
    assert game.view_for("a")["board"][0][0] == "X"


def test_all_win_lines() -> None:
    wins = [
        [(0, 0), (0, 1), (0, 2)],
        [(1, 0), (1, 1), (1, 2)],
        [(2, 0), (2, 1), (2, 2)],
        [(0, 0), (1, 0), (2, 0)],
        [(0, 1), (1, 1), (2, 1)],
        [(0, 2), (1, 2), (2, 2)],
        [(0, 0), (1, 1), (2, 2)],
        [(0, 2), (1, 1), (2, 0)],
    ]
    for winning_line in wins:
        game = TicTacToeLogic(["a", "b"], {})
        other_moves = iter(
            (row, col)
            for row in range(3)
            for col in range(3)
            if (row, col) not in winning_line
        )
        for index, position in enumerate(winning_line):
            assert game.handle_action("a", move(*position)).accepted
            if index < 2:
                assert game.handle_action("b", move(*next(other_moves))).accepted
        assert game.is_over()
        assert game.result() == {"winner": "a", "draw": False}


def test_draw_and_rejects_actions_after_game_over() -> None:
    game = TicTacToeLogic(["a", "b"], {})
    sequence = [
        ("a", 0, 0),
        ("b", 0, 1),
        ("a", 0, 2),
        ("b", 1, 1),
        ("a", 1, 0),
        ("b", 1, 2),
        ("a", 2, 1),
        ("b", 2, 0),
        ("a", 2, 2),
    ]
    for player, row, col in sequence:
        assert game.handle_action(player, move(row, col)).accepted
    assert game.is_over()
    assert game.result() == {"winner": None, "draw": True}
    assert not game.handle_action("b", move(0, 0)).accepted
