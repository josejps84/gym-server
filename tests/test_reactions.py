from typing import Any
from uuid import uuid4

from tests.conftest import User, session_body


async def _shared_workout(owner: User, visibility: str = "followers") -> str:
    """Shares a workout and returns its activity id, as the owner's feed shows it."""
    await owner.put(f"/me/sessions/{uuid4()}", json=session_body(visibility=visibility))
    items = (await owner.get("/feed")).json()["items"]
    return str(next(i["id"] for i in items if i["type"] == "workout_completed"))


async def test_followers_cheer_a_workout_once_and_can_take_it_back(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    luis: User = await new_user("luis")
    await ana.post(f"/users/{jose.id}/follow")
    await luis.post(f"/users/{jose.id}/follow")
    activity = await _shared_workout(jose)

    assert (await ana.put(f"/feed/{activity}/reaction")).status_code == 204
    assert (await ana.put(f"/feed/{activity}/reaction")).status_code == 204
    await luis.put(f"/feed/{activity}/reaction")

    def item(feed: dict[str, Any]) -> dict[str, Any]:
        return next(i for i in feed["items"] if i["id"] == activity)

    seen = item((await ana.get("/feed")).json())
    assert (seen["reactions"], seen["reacted"]) == (2, True)
    assert item((await jose.get("/feed")).json())["reacted"] is False

    assert (await ana.delete(f"/feed/{activity}/reaction")).status_code == 204
    assert item((await ana.get("/feed")).json())["reactions"] == 1


async def test_only_people_who_can_see_it_and_never_the_owner(new_user: Any) -> None:
    jose: User = await new_user("jose")
    stranger: User = await new_user("stranger")
    activity = await _shared_workout(jose, visibility="followers")

    assert (await jose.put(f"/feed/{activity}/reaction")).status_code == 403
    assert (await stranger.put(f"/feed/{activity}/reaction")).status_code == 404
    assert (await stranger.put(f"/feed/{uuid4()}/reaction")).status_code == 404

    await stranger.post(f"/users/{jose.id}/follow")
    assert (await stranger.put(f"/feed/{activity}/reaction")).status_code == 204
    await jose.post(f"/users/{stranger.id}/block")
    assert (await stranger.put(f"/feed/{activity}/reaction")).status_code == 404
