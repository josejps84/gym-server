from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import ProfileDep, SyncServiceDep
from app.domain.sync import CustomExerciseRecord, RoutineRecord, SessionRecord
from app.routers.schemas import (
    ChangesOut,
    ExerciseIn,
    ExerciseOut,
    RoutineIn,
    RoutineOut,
    SessionIn,
    SessionOut,
)

router = APIRouter(prefix="/me", tags=["sync"])


@router.put("/routines/{routine_id}")
async def put_routine(routine_id: UUID, body: RoutineIn, profile: ProfileDep, service: SyncServiceDep) -> RoutineOut:
    """Idempotent upload; if the server already has a newer updatedAt, it keeps (and returns) that one."""
    incoming = RoutineRecord(
        id=routine_id,
        owner_id=profile.id,
        name=body.name,
        exercises=[e.model_dump(by_alias=True) for e in body.exercises],
        data=body.data,
        visibility=body.visibility,
        created_at=body.created_at,
        updated_at=body.updated_at,
        deleted_at=body.deleted_at,
    )
    return RoutineOut.of(await service.put_routine(profile.id, incoming))


@router.put("/sessions/{session_id}")
async def put_session(session_id: UUID, body: SessionIn, profile: ProfileDep, service: SyncServiceDep) -> SessionOut:
    """A finished workout. Private unless visibility says otherwise; shared ones show in the feed."""
    incoming = SessionRecord(
        id=session_id,
        user_id=profile.id,
        routine_id=body.routine_id,
        name=body.name,
        started_at=body.started_at,
        ended_at=body.ended_at,
        summary=body.summary.model_dump(by_alias=True),
        data=body.data,
        visibility=body.visibility,
        updated_at=body.updated_at,
        deleted_at=body.deleted_at,
    )
    return SessionOut.of(await service.put_session(profile.id, incoming))


@router.put("/exercises/{exercise_id}")
async def put_exercise(
    exercise_id: UUID, body: ExerciseIn, profile: ProfileDep, service: SyncServiceDep
) -> ExerciseOut:
    incoming = CustomExerciseRecord(
        id=exercise_id,
        owner_id=profile.id,
        name=body.name,
        primary_muscle=body.primary_muscle,
        equipment=body.equipment,
        note=body.note,
        updated_at=body.updated_at,
        deleted_at=body.deleted_at,
    )
    return ExerciseOut.of(await service.put_exercise(profile.id, incoming))


@router.get("/changes")
async def changes(
    profile: ProfileDep,
    service: SyncServiceDep,
    since: Annotated[int, Query(ge=0, description="cursor from the previous call; 0 = everything")] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ChangesOut:
    """What changed on my other devices (deletions come as records with deletedAt)."""
    result = await service.changes(profile.id, since, limit)
    return ChangesOut(
        routines=[RoutineOut.of(r) for r in result.routines],
        sessions=[SessionOut.of(s) for s in result.sessions],
        exercises=[ExerciseOut.of(e) for e in result.exercises],
        cursor=str(result.cursor),
        has_more=result.has_more,
    )
