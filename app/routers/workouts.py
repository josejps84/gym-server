from uuid import UUID

from fastapi import APIRouter

from app.dependencies import ProfileDep, WorkoutServiceDep
from app.routers.feed import workout_out
from app.routers.schemas import (
    ProfileCard,
    PublicExerciseOut,
    PublicSetOut,
    PublicWorkoutExerciseOut,
    WorkoutDetailOut,
)

router = APIRouter(prefix="/workouts", tags=["feed"])


@router.get("/{session_id}")
async def get_workout(session_id: UUID, profile: ProfileDep, service: WorkoutServiceDep) -> WorkoutDetailOut:
    """A shared workout: its exercises and the reps of each set, never the weights."""
    view = await service.get(profile.id, session_id)
    return WorkoutDetailOut(
        workout=workout_out(view.session),
        owner=ProfileCard.of(view.owner),
        exercises=[
            PublicWorkoutExerciseOut(
                exercise_id=e.exercise_id,
                sets=[PublicSetOut(reps=s.reps, kind=s.kind) for s in e.sets],
                group_id=e.group_id,
            )
            for e in view.exercises
        ],
        custom_exercises=[PublicExerciseOut.of(e) for e in view.custom_exercises],
    )
