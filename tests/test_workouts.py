from typing import Any
from uuid import uuid4

from tests.conftest import User, exercise_body, session_body


def workout_body(custom_exercise_id: str, visibility: str = "followers") -> dict[str, Any]:
    body = session_body(visibility=visibility)
    body["data"] = {
        "exercises": [
            {
                "exerciseId": "seed-squat",
                "groupId": "g1",
                "sets": [
                    {"id": "a", "weightKg": 100, "reps": 8, "completed": True, "kind": "warmup", "rpe": 6},
                    {"id": "b", "weightKg": 140, "reps": 5, "completed": True, "rpe": 9},
                    {"id": "c", "weightKg": 140, "reps": 5, "completed": False},
                ],
            },
            {"exerciseId": custom_exercise_id, "sets": [{"id": "d", "weightKg": 50, "reps": 12, "completed": True}]},
            {"exerciseId": "seed-curl", "sets": []},
            "not an exercise",
        ]
    }
    return body


async def test_followers_see_exercises_and_reps_but_never_weights(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    await ana.post(f"/users/{jose.id}/follow")
    custom_id = uuid4()
    await jose.put(f"/me/exercises/{custom_id}", json=exercise_body())
    session_id = uuid4()
    await jose.put(f"/me/sessions/{session_id}", json=workout_body(str(custom_id)))

    response = await ana.get(f"/workouts/{session_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["owner"]["username"] == "jose"
    assert body["workout"]["summary"] == {"durationSeconds": 3600, "sets": 18}
    # Only done sets; no weights, no RPE; exercises without done sets and junk are left out.
    assert body["exercises"] == [
        {
            "exerciseId": "seed-squat",
            "groupId": "g1",
            "sets": [{"reps": 8, "kind": "warmup"}, {"reps": 5, "kind": None}],
        },
        {"exerciseId": str(custom_id), "groupId": None, "sets": [{"reps": 12, "kind": None}]},
    ]
    assert [e["name"] for e in body["customExercises"]] == ["Hip thrust en máquina"]
    assert "weightKg" not in response.text and "rpe" not in response.text and "Asiento" not in response.text


async def test_a_workout_is_only_seen_by_who_may_see_it(new_user: Any) -> None:
    jose: User = await new_user("jose")
    stranger: User = await new_user("stranger")
    shared, private = uuid4(), uuid4()
    await jose.put(f"/me/sessions/{shared}", json=workout_body("seed-x", visibility="followers"))
    await jose.put(f"/me/sessions/{private}", json=workout_body("seed-x", visibility="private"))

    assert (await stranger.get(f"/workouts/{shared}")).status_code == 404
    assert (await stranger.get(f"/workouts/{uuid4()}")).status_code == 404
    assert (await jose.get(f"/workouts/{private}")).status_code == 200

    await stranger.post(f"/users/{jose.id}/follow")
    assert (await stranger.get(f"/workouts/{shared}")).status_code == 200
    assert (await stranger.get(f"/workouts/{private}")).status_code == 404
    await jose.post(f"/users/{stranger.id}/block")
    assert (await stranger.get(f"/workouts/{shared}")).status_code == 404
