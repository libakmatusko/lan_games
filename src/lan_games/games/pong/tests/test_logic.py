from lan_games.games.pong.logic import PongLogic


def test_actions_and_server_ticks_are_authoritative() -> None:
    game = PongLogic(["a", "b"], {})
    assert not game.handle_action("a", {"type": "move", "direction": 2}).accepted
    assert game.handle_action("a", {"type": "move", "direction": 1}).accepted
    game.tick(0.1)
    assert game.paddles[0] > 0
    assert game.view_for("a")["you"] == 0


def test_scoring_and_game_over() -> None:
    game = PongLogic(["a", "b"], {})
    for _ in range(5):
        game.ball = [-0.89, 0.9]
        game.velocity = [-1.0, 0.0]
        game.tick(0.01)
    assert game.is_over()
    assert game.result() == {"winner": "b", "scores": [0, 5]}
