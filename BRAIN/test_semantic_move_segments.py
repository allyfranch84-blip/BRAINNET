import json
import pytest

from motor_intent import parse_semantic_response


def movement(distance):
    return json.dumps({
        "intent_type": "atomic",
        "step": {
            "action": "move",
            "direction": "up",
            "distance": distance,
        },
    })


@pytest.mark.parametrize("distance,expected", [
    (1, [1]),
    (150, [150]),
    (151, [150, 1]),
    (300, [150, 150]),
    (301, [150, 150, 1]),
    (1200, [150] * 8),
])
def test_atomic_move_segments(distance, expected):
    plan = parse_semantic_response(movement(distance))
    assert plan["status"] == "execute"
    assert [s["distance"] for s in plan["steps"]] == expected
    assert all(s["direction"] == "up" for s in plan["steps"])


@pytest.mark.parametrize("distance", [
    0, -1, 1201, True, 150.5, "300"
])
def test_invalid_distance(distance):
    with pytest.raises(ValueError):
        parse_semantic_response(movement(distance))
