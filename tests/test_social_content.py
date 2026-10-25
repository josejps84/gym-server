"""Shared routines, featured routines, copies and the feed."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

from tests.conftest import T0, User, exercise_body, routine_body, session_body


async def _share_routine(user: User, name: str, visibility: str = "public", **kwargs: Any) -> str:
    routine_id = str(uuid4())
    response = await user.put(f"/me/routines/{routine_id}", json=routine_body(name, visibility=visibility, **kwargs))
    assert response.status_code == 200, response.text
    return routine_id


async def test_routine_visibility(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    stranger: User = await new_user("stranger")
    await ana.post(f"/users/{jose.id}/follow")
    public = await _share_routine(jose, "Pública")
    followers = await _share_routine(jose, "Seguidores", "followers")
    private = await _share_routine(jose, "Mía", "private")

    assert (await stranger.get(f"/routines/{public}")).status_code == 200
    assert (await stranger.get(f"/routines/{followers}")).status_code == 404
    assert (await ana.get(f"/routines/{followers}")).status_code == 200
    assert (await ana.get(f"/routines/{private}")).status_code == 404
    assert (await jose.get(f"/routines/{private}")).status_code == 200

    await jose.patch("/me", json={"isPrivate": True})
    assert (await stranger.get(f"/routines/{public}")).status_code == 404
    assert (await ana.get(f"/routines/{public}")).status_code == 200


async def test_featured_routines_with_custom_exercises(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    exercise_id = str(uuid4())
    await jose.put(f"/me/exercises/{exercise_id}", json=exercise_body())
    legs = await _share_routine(jose, "Pierna", exercise_ids=["seed-squat", exercise_id])
    arms = await _share_routine(jose, "Brazo")
    private = await _share_routine(jose, "Mía", "private")

    assert (await jose.put("/me/featured-routines", json={"routineIds": [private]})).status_code == 422
    assert (await jose.put("/me/featured-routines", json={"routineIds": [legs, legs]})).status_code == 422
    assert (await ana.put("/me/featured-routines", json={"routineIds": [legs]})).status_code == 422
    response = await jose.put("/me/featured-routines", json={"routineIds": [arms, legs]})
    assert response.json() == {"routineIds": [arms, legs]}
    assert (await jose.get("/me")).json()["featuredRoutineIds"] == [arms, legs]

    profile = (await ana.get("/users/jose")).json()
    assert [r["name"] for r in profile["featuredRoutines"]] == ["Brazo", "Pierna"]
    # Others see what the custom exercise is, but not the owner's personal note.
    assert profile["exercises"] == [
        {"id": exercise_id, "name": "Hip thrust en máquina", "primaryMuscle": "glutes", "equipment": "machine"}
    ]

    # Making a featured routine private takes it off the profile.
    await jose.put(
        f"/me/routines/{arms}", json=routine_body("Brazo", visibility="private", updated_at=T0 + timedelta(hours=1))
    )
    assert (await jose.get("/me")).json()["featuredRoutineIds"] == [legs]


async def test_copy_a_routine(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    exercise_id = str(uuid4())
    await jose.put(f"/me/exercises/{exercise_id}", json=exercise_body())
    legs = await _share_routine(jose, "Pierna", exercise_ids=["seed-squat", exercise_id])

    response = await ana.post(f"/routines/{legs}/copy")
    assert response.status_code == 201
    copied = response.json()
    assert copied["routine"]["id"] != legs
    assert copied["routine"]["ownerId"] == str(ana.id)
    assert copied["routine"]["visibility"] == "private"
    [exercise] = copied["exercises"]
    assert exercise["id"] != exercise_id
    assert exercise["note"] is None
    assert [e["exerciseId"] for e in copied["routine"]["exercises"]] == ["seed-squat", exercise["id"]]

    changes = (await ana.get("/me/changes")).json()
    assert [r["id"] for r in changes["routines"]] == [copied["routine"]["id"]]
    assert [e["id"] for e in changes["exercises"]] == [exercise["id"]]

    private = await _share_routine(jose, "Mía", "private")
    assert (await ana.post(f"/routines/{private}/copy")).status_code == 404


async def test_feed(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    luis: User = await new_user("luis")
    await ana.post(f"/users/{jose.id}/follow")
    await ana.post(f"/users/{luis.id}/follow")
    await luis.post(f"/users/{ana.id}/follow")
    await _share_routine(jose, "Pierna")
    await _share_routine(jose, "Secreta", "private")
    await jose.put(f"/me/sessions/{uuid4()}", json=session_body(visibility="followers"))
    await jose.put(f"/me/sessions/{uuid4()}", json=session_body())

    items = (await ana.get("/feed")).json()["items"]
    summary = sorted((i["actor"]["username"], i["type"]) for i in items)
    assert summary == [
        ("jose", "routine_shared"),
        ("jose", "workout_completed"),
        ("luis", "started_following"),
    ]
    following = next(i for i in items if i["type"] == "started_following")
    assert following["user"]["username"] == "ana"
    shared = next(i for i in items if i["type"] == "routine_shared")
    assert shared["routine"]["name"] == "Pierna"
    assert shared["routine"]["exerciseCount"] == 1

    # Not following anyone: empty feed.
    assert (await jose.get("/feed")).json()["items"] == []


async def test_feed_pages(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    await ana.post(f"/users/{jose.id}/follow")
    for hour in range(5):
        await jose.put(
            f"/me/sessions/{uuid4()}", json=session_body(visibility="public", ended_at=T0 + timedelta(hours=hour))
        )
    first = (await ana.get("/feed", params={"limit": 3})).json()
    second = (await ana.get("/feed", params={"limit": 3, "cursor": first["nextCursor"]})).json()
    ended = [i["workout"]["endedAt"] for i in first["items"] + second["items"]]
    assert ended == sorted(ended, reverse=True)
    assert len(ended) == 5
    assert second["nextCursor"] is None


async def test_user_activity_respects_privacy(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    stranger: User = await new_user("stranger")
    await ana.post(f"/users/{jose.id}/follow")
    await jose.put(f"/me/sessions/{uuid4()}", json=session_body(visibility="followers"))
    await _share_routine(jose, "Pierna")

    def types(response: Any) -> list[str]:
        return sorted(i["type"] for i in response.json()["items"])

    assert types(await jose.get("/users/jose/activity")) == ["routine_shared", "workout_completed"]
    assert types(await ana.get("/users/jose/activity")) == ["routine_shared", "workout_completed"]
    assert types(await stranger.get("/users/jose/activity")) == ["routine_shared"]
    await jose.patch("/me", json={"isPrivate": True})
    assert types(await stranger.get("/users/jose/activity")) == []
    assert types(await ana.get("/users/ana/activity")) == ["started_following"]


async def test_deleted_routine_leaves_the_feed(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    await ana.post(f"/users/{jose.id}/follow")
    legs = await _share_routine(jose, "Pierna")
    assert len((await ana.get("/feed")).json()["items"]) == 1
    await jose.put(f"/me/routines/{legs}", json=routine_body(updated_at=T0 + timedelta(hours=1), deleted=True))
    assert (await ana.get("/feed")).json()["items"] == []
    assert (await ana.get(f"/routines/{legs}")).status_code == 404
