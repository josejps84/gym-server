from datetime import timedelta
from typing import Any
from uuid import uuid4

from tests.conftest import T0, User, exercise_body, routine_body, session_body


async def test_routine_upload_is_idempotent_and_last_writer_wins(new_user: Any) -> None:
    jose: User = await new_user("jose")
    routine_id = uuid4()
    first = await jose.put(f"/me/routines/{routine_id}", json=routine_body("Pierna"))
    assert first.status_code == 200
    body = first.json()
    assert body["id"] == str(routine_id)
    assert body["ownerId"] == str(jose.id)
    assert body["exercises"] == [{"exerciseId": "seed-squat", "targetSets": 3, "targetReps": 10, "restSeconds": 90}]
    assert body["data"] == {"type": "CUSTOM", "subtype": "GYM", "level": 2}

    newer = routine_body("Pierna pesada", updated_at=T0 + timedelta(minutes=5))
    assert (await jose.put(f"/me/routines/{routine_id}", json=newer)).json()["name"] == "Pierna pesada"
    # An older version from a device that was offline loses.
    stale = await jose.put(f"/me/routines/{routine_id}", json=routine_body("Vieja"))
    assert stale.json()["name"] == "Pierna pesada"


async def test_unknown_routine_exercise_fields_are_kept(new_user: Any) -> None:
    jose: User = await new_user("jose")
    body = routine_body()
    body["exercises"][0]["supersetGroup"] = "A"
    saved = (await jose.put(f"/me/routines/{uuid4()}", json=body)).json()
    assert saved["exercises"][0]["supersetGroup"] == "A"


async def test_ids_of_other_users_are_refused(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    routine_id, session_id, exercise_id = uuid4(), uuid4(), uuid4()
    await jose.put(f"/me/routines/{routine_id}", json=routine_body())
    await jose.put(f"/me/sessions/{session_id}", json=session_body())
    await jose.put(f"/me/exercises/{exercise_id}", json=exercise_body())
    later = T0 + timedelta(days=1)
    assert (await ana.put(f"/me/routines/{routine_id}", json=routine_body(updated_at=later))).status_code == 409
    assert (await ana.put(f"/me/sessions/{session_id}", json=session_body(updated_at=later))).status_code == 409
    assert (await ana.put(f"/me/exercises/{exercise_id}", json=exercise_body(updated_at=later))).status_code == 409


async def test_validation(new_user: Any) -> None:
    jose: User = await new_user("jose")
    bad_sets = routine_body()
    bad_sets["exercises"][0]["targetSets"] = 0
    assert (await jose.put(f"/me/routines/{uuid4()}", json=bad_sets)).status_code == 422
    naive = routine_body()
    naive["updatedAt"] = "2026-10-01T10:00:00"
    assert (await jose.put(f"/me/routines/{uuid4()}", json=naive)).status_code == 422
    backwards = session_body()
    backwards["startedAt"], backwards["endedAt"] = backwards["endedAt"], backwards["startedAt"]
    assert (await jose.put(f"/me/sessions/{uuid4()}", json=backwards)).status_code == 422
    assert (await jose.put("/me/routines/not-a-uuid", json=routine_body())).status_code == 422


async def test_changes_reach_other_devices(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    routine_id, session_id, exercise_id = uuid4(), uuid4(), uuid4()
    await jose.put(f"/me/routines/{routine_id}", json=routine_body())
    await jose.put(f"/me/sessions/{session_id}", json=session_body())
    await jose.put(f"/me/exercises/{exercise_id}", json=exercise_body())
    await ana.put(f"/me/routines/{uuid4()}", json=routine_body())

    everything = (await jose.get("/me/changes")).json()
    assert [r["id"] for r in everything["routines"]] == [str(routine_id)]
    assert [s["id"] for s in everything["sessions"]] == [str(session_id)]
    assert everything["sessions"][0]["data"]["status"] == "finished"
    assert [e["id"] for e in everything["exercises"]] == [str(exercise_id)]
    assert everything["exercises"][0]["note"] == "Asiento 4"
    assert everything["hasMore"] is False

    cursor = everything["cursor"]
    nothing = (await jose.get("/me/changes", params={"since": cursor})).json()
    assert nothing["routines"] == nothing["sessions"] == nothing["exercises"] == []
    assert nothing["cursor"] == cursor

    deleted = routine_body(updated_at=T0 + timedelta(hours=1), deleted=True)
    await jose.put(f"/me/routines/{routine_id}", json=deleted)
    after = (await jose.get("/me/changes", params={"since": cursor})).json()
    assert [r["deletedAt"] is not None for r in after["routines"]] == [True]


async def test_changes_are_paged_oldest_first(new_user: Any) -> None:
    jose: User = await new_user("jose")
    uploaded = []
    for i in range(5):
        if i % 2:
            uploaded.append(("sessions", (await jose.put(f"/me/sessions/{uuid4()}", json=session_body())).json()["id"]))
        else:
            uploaded.append(("routines", (await jose.put(f"/me/routines/{uuid4()}", json=routine_body())).json()["id"]))

    seen: list[tuple[str, str]] = []
    cursor = "0"
    pages = 0
    while True:
        page = (await jose.get("/me/changes", params={"since": cursor, "limit": 2})).json()
        pages += 1
        seen += [("routines", r["id"]) for r in page["routines"]] + [("sessions", s["id"]) for s in page["sessions"]]
        cursor = page["cursor"]
        if not page["hasMore"]:
            break
    assert pages == 3
    assert sorted(seen) == sorted(uploaded)


async def test_a_shared_session_creates_one_activity(new_user: Any) -> None:
    jose: User = await new_user("jose")
    ana: User = await new_user("ana")
    await ana.post(f"/users/{jose.id}/follow")
    session_id = uuid4()
    await jose.put(f"/me/sessions/{session_id}", json=session_body(visibility="followers"))
    await jose.put(
        f"/me/sessions/{session_id}",
        json=session_body(visibility="public", updated_at=T0 + timedelta(minutes=1)),
    )
    items = (await ana.get("/feed")).json()["items"]
    workouts = [i for i in items if i["type"] == "workout_completed"]
    assert len(workouts) == 1
    workout = workouts[0]["workout"]
    assert workout["sessionId"] == str(session_id)
    assert workout["summary"] == {"durationSeconds": 3600, "sets": 18}
    assert "data" not in workout

    await jose.put(
        f"/me/sessions/{session_id}",
        json=session_body(visibility="private", updated_at=T0 + timedelta(minutes=2)),
    )
    assert [i for i in (await ana.get("/feed")).json()["items"] if i["type"] == "workout_completed"] == []
