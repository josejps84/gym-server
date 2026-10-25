from typing import Any
from uuid import uuid4

import httpx

from tests.conftest import STORAGE_PREFIX, FakeIdentity, FakeStorage, User, make_token, routine_body


async def test_first_call_creates_the_profile_with_the_login_name(client: httpx.AsyncClient) -> None:
    user_id = uuid4()
    headers = {"Authorization": f"Bearer {make_token(user_id, name='  José   Piñeros ')}"}
    first = await client.get("/me", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert body["id"] == str(user_id)
    assert body["username"].startswith("user")
    assert body["displayName"] == "José Piñeros"
    assert body["isPrivate"] is False
    assert body["followersCount"] == 0
    assert body["featuredRoutineIds"] == []
    again = await client.get("/me", headers=headers)
    assert again.json()["username"] == body["username"]


async def test_edit_profile(new_user: Any) -> None:
    jose: User = await new_user("jose")
    response = await jose.patch("/me", json={"username": "Jose.Pi", "displayName": "José", "bio": " Pierna "})
    assert response.status_code == 200
    assert response.json().items() >= {"username": "jose.pi", "displayName": "José", "bio": "Pierna"}.items()


async def test_username_rules(new_user: Any) -> None:
    await new_user("ana")
    jose: User = await new_user("jose")
    taken = await jose.patch("/me", json={"username": "ANA"})
    assert taken.status_code == 409
    assert taken.json()["error"] == "username.taken"
    invalid = await jose.patch("/me", json={"username": "a b"})
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "username.format"
    assert (await jose.get("/me")).json()["username"] == "jose"


async def test_avatar_upload_and_replace(new_user: Any, storage: FakeStorage) -> None:
    jose: User = await new_user("jose")
    first = (await jose.post("/me/avatar-upload-url", json={"contentType": "image/jpeg"})).json()
    assert first["uploadUrl"].startswith("https://supabase.test/upload/")
    assert first["avatarUrl"].startswith(f"{STORAGE_PREFIX}{jose.id}/")
    assert first["avatarUrl"].endswith(".jpg")
    assert (await jose.patch("/me", json={"avatarUrl": first["avatarUrl"]})).json()["avatarUrl"] == first["avatarUrl"]

    second = (await jose.post("/me/avatar-upload-url", json={"contentType": "image/webp"})).json()
    await jose.patch("/me", json={"avatarUrl": second["avatarUrl"]})
    assert storage.deleted == [first["avatarUrl"].removeprefix(STORAGE_PREFIX)]

    cleared = await jose.patch("/me", json={"avatarUrl": None})
    assert cleared.json()["avatarUrl"] is None
    assert storage.deleted[-1] == second["avatarUrl"].removeprefix(STORAGE_PREFIX)


async def test_avatar_must_be_an_uploaded_photo_of_the_user(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    for url in [
        "https://evil.test/me.jpg",
        f"{STORAGE_PREFIX}{ana.id}/{'a' * 32}.jpg",
        f"{STORAGE_PREFIX}{jose.id}/../{ana.id}/{'a' * 32}.jpg",
    ]:
        response = await jose.patch("/me", json={"avatarUrl": url})
        assert response.status_code == 422, url
    assert (await jose.post("/me/avatar-upload-url", json={"contentType": "image/gif"})).status_code == 422


async def test_public_profile(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    await ana.post(f"/users/{jose.id}/follow")
    profile = (await ana.get("/users/JOSE")).json()
    assert profile["username"] == "jose"
    assert profile["followersCount"] == 1
    assert profile["relationship"] == {"following": "active", "followedBy": False}
    assert profile["contentVisible"] is True
    mine = (await jose.get("/users/jose")).json()
    assert mine["relationship"] == {"following": None, "followedBy": False}
    assert (await jose.get("/users/ana")).json()["relationship"]["followedBy"] is True
    assert (await jose.get("/users/nobody")).status_code == 404


async def test_search(new_user: Any) -> None:
    jose: User = await new_user("jose")
    await new_user("josefina")
    ana: User = await new_user("ana")
    await ana.patch("/me", json={"displayName": "Ana Josefa"})
    names = [u["username"] for u in (await jose.get("/search/users", params={"q": "@Jos"})).json()["items"]]
    # Username prefix matches first, then display-name matches.
    assert names == ["jose", "josefina", "ana"]
    assert (await jose.get("/search/users", params={"q": "j"})).status_code == 422
    assert (await jose.get("/search/users", params={"q": "%"})).status_code == 422
    assert (await jose.get("/search/users", params={"q": "_o"})).json()["items"] == []


async def test_delete_account(new_user: Any, storage: FakeStorage, identity: FakeIdentity) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    await ana.post(f"/users/{jose.id}/follow")
    await jose.put(f"/me/routines/{uuid4()}", json=routine_body())
    storage.objects[str(jose.id)] = [f"{jose.id}/a.jpg"]

    assert (await jose.delete("/me")).status_code == 204
    assert identity.deleted == [jose.id]
    assert storage.deleted == [f"{jose.id}/a.jpg"]
    assert (await ana.get("/users/jose")).status_code == 404
    assert (await ana.get("/me")).json()["followingCount"] == 0
    # Retrying is fine (e.g. after a Supabase failure).
    assert (await jose.delete("/me")).status_code == 204
