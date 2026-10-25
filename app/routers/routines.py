from uuid import UUID

from fastapi import APIRouter, status

from app.dependencies import ProfileDep, RoutineServiceDep
from app.routers.schemas import (
    CopiedRoutineOut,
    ExerciseOut,
    ProfileCard,
    PublicExerciseOut,
    RoutineDetailOut,
    RoutineOut,
)

router = APIRouter(prefix="/routines", tags=["routines"])


@router.get("/{routine_id}")
async def get_routine(routine_id: UUID, profile: ProfileDep, service: RoutineServiceDep) -> RoutineDetailOut:
    view = await service.get(profile.id, routine_id)
    return RoutineDetailOut(
        routine=RoutineOut.of(view.routine),
        owner=ProfileCard.of(view.owner),
        exercises=[PublicExerciseOut.of(e) for e in view.exercises],
    )


@router.post("/{routine_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy_routine(routine_id: UUID, profile: ProfileDep, service: RoutineServiceDep) -> CopiedRoutineOut:
    """A private copy in my routines, plus copies of the owner's custom exercises it uses.

    The app saves both locally; they also arrive through /me/changes on my other devices.
    """
    copied = await service.copy(profile.id, routine_id)
    return CopiedRoutineOut(
        routine=RoutineOut.of(copied.routine), exercises=[ExerciseOut.of(e) for e in copied.exercises]
    )
