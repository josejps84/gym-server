from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.activity import Activity, ActivityType
from app.domain.errors import Conflict
from app.domain.sync import Changes, CustomExerciseRecord, RoutineRecord, SessionRecord, should_replace
from app.services.ports import UnitOfWork

CHANGES_LIMIT = 200


class SyncService:
    """Uploads from the phone (idempotent PUTs) and downloads for the user's other devices."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def put_routine(self, user_id: UUID, incoming: RoutineRecord) -> RoutineRecord:
        stored = await self._uow.routines.get(incoming.id)
        if stored and stored.owner_id != user_id:
            raise Conflict("routine.idTaken", "That id belongs to another user's routine")
        if stored and not should_replace(stored.updated_at, incoming.updated_at):
            return stored
        saved = await self._uow.routines.save(incoming)
        if saved.is_shared:
            # Only the first share creates an activity; later uploads just update its visibility.
            await self._uow.activities.upsert(
                Activity(uuid4(), user_id, ActivityType.ROUTINE_SHARED, saved.id, saved.visibility, datetime.now(UTC))
            )
        else:
            await self._uow.activities.delete_for(user_id, ActivityType.ROUTINE_SHARED, saved.id)
            await self._uow.featured.remove(saved.id)
        await self._uow.commit()
        return saved

    async def put_session(self, user_id: UUID, incoming: SessionRecord) -> SessionRecord:
        stored = await self._uow.sessions.get(incoming.id)
        if stored and stored.user_id != user_id:
            raise Conflict("session.idTaken", "That id belongs to another user's session")
        if stored and not should_replace(stored.updated_at, incoming.updated_at):
            return stored
        saved = await self._uow.sessions.save(incoming)
        if saved.is_shared:
            # Dated when the workout ended, so a session shared later lands where it belongs.
            await self._uow.activities.upsert(
                Activity(uuid4(), user_id, ActivityType.WORKOUT_COMPLETED, saved.id, saved.visibility, saved.ended_at)
            )
        else:
            await self._uow.activities.delete_for(user_id, ActivityType.WORKOUT_COMPLETED, saved.id)
        await self._uow.commit()
        return saved

    async def put_exercise(self, user_id: UUID, incoming: CustomExerciseRecord) -> CustomExerciseRecord:
        stored = await self._uow.exercises.get(incoming.id)
        if stored and stored.owner_id != user_id:
            raise Conflict("exercise.idTaken", "That id belongs to another user's exercise")
        if stored and not should_replace(stored.updated_at, incoming.updated_at):
            return stored
        saved = await self._uow.exercises.save(incoming)
        await self._uow.commit()
        return saved

    async def changes(self, user_id: UUID, since: int, limit: int = CHANGES_LIMIT) -> Changes:
        """Everything changed after `since`, oldest first, at most `limit` records."""
        routines = await self._uow.routines.changed_since(user_id, since, limit + 1)
        sessions = await self._uow.sessions.changed_since(user_id, since, limit + 1)
        exercises = await self._uow.exercises.changed_since(user_id, since, limit + 1)
        # Each list holds its own `limit + 1` oldest changes, so the overall oldest `limit` are in them.
        seqs = sorted(
            [*(r.change_seq for r in routines), *(s.change_seq for s in sessions), *(e.change_seq for e in exercises)]
        )
        if len(seqs) <= limit:
            return Changes(routines, sessions, exercises, cursor=seqs[-1] if seqs else since, has_more=False)
        cursor = seqs[limit - 1]
        return Changes(
            routines=[r for r in routines if r.change_seq <= cursor],
            sessions=[s for s in sessions if s.change_seq <= cursor],
            exercises=[e for e in exercises if e.change_seq <= cursor],
            cursor=cursor,
            has_more=True,
        )
