from typing import Any
from uuid import uuid4

from tests.conftest import User


async def test_follow_a_public_profile(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    response = await ana.post(f"/users/{jose.id}/follow")
    assert response.json() == {"status": "active"}
    # Following again changes nothing.
    assert (await ana.post(f"/users/{jose.id}/follow")).json() == {"status": "active"}
    followers = (await ana.get(f"/users/{jose.id}/followers")).json()
    assert [u["username"] for u in followers["items"]] == ["ana"]
    following = (await jose.get(f"/users/{ana.id}/following")).json()
    assert [u["username"] for u in following["items"]] == ["jose"]

    assert (await ana.delete(f"/users/{jose.id}/follow")).status_code == 204
    assert (await ana.get(f"/users/{jose.id}/followers")).json()["items"] == []


async def test_cannot_follow_yourself_or_nobody(new_user: Any) -> None:
    jose: User = await new_user("jose")
    assert (await jose.post(f"/users/{jose.id}/follow")).status_code == 422
    assert (await jose.post(f"/users/{uuid4()}/follow")).status_code == 404


async def test_private_profile_requests(new_user: Any) -> None:
    jose: User = await new_user("jose", private=True)
    ana: User = await new_user("ana")
    luis: User = await new_user("luis")
    assert (await ana.post(f"/users/{jose.id}/follow")).json() == {"status": "pending"}
    assert (await luis.post(f"/users/{jose.id}/follow")).json() == {"status": "pending"}

    profile = (await ana.get("/users/jose")).json()
    assert profile["relationship"]["following"] == "pending"
    assert profile["contentVisible"] is False
    assert profile["followersCount"] == 0
    assert (await ana.get(f"/users/{jose.id}/followers")).status_code == 403

    requests = (await jose.get("/me/follow-requests")).json()
    assert {u["username"] for u in requests["items"]} == {"ana", "luis"}

    assert (await jose.post(f"/me/follow-requests/{ana.id}/accept")).status_code == 204
    assert (await jose.delete(f"/me/follow-requests/{luis.id}")).status_code == 204
    assert (await jose.post(f"/me/follow-requests/{luis.id}/accept")).status_code == 404
    assert (await jose.get("/me/follow-requests")).json()["items"] == []

    assert (await ana.get("/users/jose")).json()["contentVisible"] is True
    assert (await ana.get(f"/users/{jose.id}/followers")).status_code == 200
    assert (await luis.get("/users/jose")).json()["relationship"]["following"] is None


async def test_going_public_accepts_pending_requests(new_user: Any) -> None:
    jose: User = await new_user("jose", private=True)
    ana: User = await new_user("ana")
    await ana.post(f"/users/{jose.id}/follow")
    await jose.patch("/me", json={"isPrivate": False})
    assert (await jose.get("/me")).json()["followersCount"] == 1
    assert (await ana.get("/users/jose")).json()["relationship"]["following"] == "active"
    assert (await jose.get("/me/follow-requests")).json()["items"] == []


async def test_followers_pagination(new_user: Any) -> None:
    jose: User = await new_user("jose")
    fans = [await new_user(f"fan{i}") for i in range(5)]
    for fan in fans:
        await fan.post(f"/users/{jose.id}/follow")
    first = (await jose.get(f"/users/{jose.id}/followers", params={"limit": 2})).json()
    second = (await jose.get(f"/users/{jose.id}/followers", params={"limit": 2, "cursor": first["nextCursor"]})).json()
    third = (await jose.get(f"/users/{jose.id}/followers", params={"limit": 2, "cursor": second["nextCursor"]})).json()
    names = [u["username"] for page in (first, second, third) for u in page["items"]]
    assert names == ["fan4", "fan3", "fan2", "fan1", "fan0"]
    assert third["nextCursor"] is None
    assert (await jose.get(f"/users/{jose.id}/followers", params={"cursor": "bad"})).status_code == 422


async def test_block_hides_both_users_and_removes_follows(new_user: Any) -> None:
    jose: User = await new_user("jose")
    troll: User = await new_user("troll")
    await troll.post(f"/users/{jose.id}/follow")
    await jose.post(f"/users/{troll.id}/follow")

    assert (await jose.post(f"/users/{troll.id}/block")).status_code == 204
    assert (await jose.get("/me")).json().items() >= {"followersCount": 0, "followingCount": 0}.items()
    assert (await troll.get("/users/jose")).status_code == 404
    assert (await jose.get("/users/troll")).status_code == 404
    assert (await troll.post(f"/users/{jose.id}/follow")).status_code == 404
    assert (await troll.get("/search/users", params={"q": "jo"})).json()["items"] == []
    assert [u["username"] for u in (await jose.get("/me/blocks")).json()["items"]] == ["troll"]

    assert (await jose.delete(f"/users/{troll.id}/block")).status_code == 204
    assert (await troll.get("/users/jose")).status_code == 200


async def test_report(new_user: Any) -> None:
    jose: User = await new_user("jose")
    troll: User = await new_user("troll")
    response = await jose.post(f"/users/{troll.id}/report", json={"reason": "harassment", "details": "Insultos"})
    assert response.status_code == 204
    assert (await jose.post(f"/users/{troll.id}/report", json={"reason": "nope"})).status_code == 422
    assert (await jose.post(f"/users/{jose.id}/report", json={"reason": "spam"})).status_code == 422
