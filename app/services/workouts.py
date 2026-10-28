from dataclasses import dataclass
from uuid import UUID

from app.domain.errors import NotFound
from app.domain.profile import Profile
from app.domain.sync import CustomExerciseRecord, PublicWorkoutExercise, SessionRecord, public_exercises
from app.domain.visibility import can_view
from app.services.access import relationship, visible_profile
from app.services.ports import UnitOfWork
from app.services.profiles import owned_custom_exercises


@dataclass(frozen=True, slots=True)
class WorkoutView:
    session: SessionRecord
    owner: Profile
    exercises: list[PublicWorkoutExercise]
    # The owner's custom exercises it uses, so the viewer's app can name them.
    custom_exercises: list[CustomExerciseRecord]


class WorkoutService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def get(self, viewer_id: UUID, session_id: UUID) -> WorkoutView:
        """A shared workout the viewer may see, without weights; any other case is a 404, so nothing leaks."""
        session = await self._uow.sessions.get(session_id)
        if session is None or session.deleted_at is not None:
            raise NotFound("workout.notFound", "Workout not found")
        try:
            owner = await visible_profile(self._uow, viewer_id, session.user_id)
        except NotFound:
            raise NotFound("workout.notFound", "Workout not found") from None
        rel = await relationship(self._uow, viewer_id, owner.id)
        if not can_view(
            session.visibility, is_owner=rel.is_owner, owner_is_private=owner.is_private, is_follower=rel.is_follower
        ):
            raise NotFound("workout.notFound", "Workout not found")
        exercises = public_exercises(session)
        custom = await owned_custom_exercises(self._uow, [(owner.id, e.exercise_id) for e in exercises])
        return WorkoutView(session, owner, exercises, custom)
