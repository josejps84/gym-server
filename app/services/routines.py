from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.errors import Invalid, NotFound
from app.domain.profile import Profile
from app.domain.sync import FEATURED_MAX, CustomExerciseRecord, RoutineRecord, copy_routine
from app.domain.visibility import can_view
from app.services.access import relationship, visible_profile
from app.services.ports import UnitOfWork
from app.services.profiles import custom_exercises_of


@dataclass(frozen=True, slots=True)
class RoutineView:
    routine: RoutineRecord
    owner: Profile
    # The owner's custom exercises the routine uses.
    exercises: list[CustomExerciseRecord]


@dataclass(frozen=True, slots=True)
class CopiedRoutine:
    routine: RoutineRecord
    exercises: list[CustomExerciseRecord]


class RoutineService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def get(self, viewer_id: UUID, routine_id: UUID) -> RoutineView:
        """A routine the viewer may see; any other case is a 404, so nothing leaks."""
        routine = await self._uow.routines.get(routine_id)
        if routine is None or routine.deleted_at is not None:
            raise NotFound("routine.notFound", "Routine not found")
        try:
            owner = await visible_profile(self._uow, viewer_id, routine.owner_id)
        except NotFound:
            raise NotFound("routine.notFound", "Routine not found") from None
        rel = await relationship(self._uow, viewer_id, owner.id)
        if not can_view(
            routine.visibility, is_owner=rel.is_owner, owner_is_private=owner.is_private, is_follower=rel.is_follower
        ):
            raise NotFound("routine.notFound", "Routine not found")
        return RoutineView(routine, owner, await custom_exercises_of(self._uow, [routine]))

    async def copy(self, viewer_id: UUID, routine_id: UUID) -> CopiedRoutine:
        """Adds a private copy to the viewer's routines, with copies of the custom exercises it uses."""
        view = await self.get(viewer_id, routine_id)
        now = datetime.now(UTC)
        new_ids: dict[str, str] = {}
        copied_exercises: list[CustomExerciseRecord] = []
        for exercise in view.exercises:
            copy = replace(exercise, id=uuid4(), owner_id=viewer_id, note=None, updated_at=now, change_seq=0)
            copied_exercises.append(await self._uow.exercises.save(copy))
            new_ids[str(exercise.id)] = str(copy.id)
        routine = await self._uow.routines.save(
            copy_routine(view.routine, new_id=uuid4(), owner_id=viewer_id, now=now, new_exercise_ids=new_ids)
        )
        await self._uow.commit()
        return CopiedRoutine(routine, copied_exercises)

    async def set_featured(self, user_id: UUID, routine_ids: list[UUID]) -> list[UUID]:
        if len(routine_ids) > FEATURED_MAX:
            raise Invalid("featured.tooMany", f"At most {FEATURED_MAX} routines")
        if len(set(routine_ids)) != len(routine_ids):
            raise Invalid("featured.duplicated", "A routine is repeated")
        routines = await self._uow.routines.get_many(routine_ids)
        for routine_id in routine_ids:
            routine = routines.get(routine_id)
            if routine is None or routine.owner_id != user_id or routine.deleted_at is not None:
                raise Invalid("featured.notFound", f"Routine {routine_id} is not one of yours")
            if not routine.is_shared:
                raise Invalid("featured.private", "Share a routine before featuring it")
        await self._uow.featured.replace(user_id, routine_ids)
        await self._uow.commit()
        return routine_ids
