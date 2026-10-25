from collections.abc import Collection, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy import insert as plain_insert
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.sync import CustomExerciseRecord, RoutineRecord, SessionRecord
from app.domain.visibility import Visibility
from app.repositories.tables import (
    CHANGE_SEQ,
    CustomExerciseRow,
    FeaturedRoutineRow,
    RoutineRow,
    WorkoutSessionRow,
)


def to_routine(row: RoutineRow) -> RoutineRecord:
    return RoutineRecord(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        exercises=row.exercises,
        data=row.data,
        visibility=Visibility(row.visibility),
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        change_seq=row.change_seq,
    )


def to_session(row: WorkoutSessionRow) -> SessionRecord:
    return SessionRecord(
        id=row.id,
        user_id=row.user_id,
        routine_id=row.routine_id,
        name=row.name,
        started_at=row.started_at,
        ended_at=row.ended_at,
        summary=row.summary,
        data=row.data,
        visibility=Visibility(row.visibility),
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        change_seq=row.change_seq,
    )


def to_exercise(row: CustomExerciseRow) -> CustomExerciseRecord:
    return CustomExerciseRecord(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        primary_muscle=row.primary_muscle,
        equipment=row.equipment,
        note=row.note,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        change_seq=row.change_seq,
    )


async def _upsert[RowT: RoutineRow | WorkoutSessionRow | CustomExerciseRow](
    session: AsyncSession, row_type: type[RowT], values: dict[str, Any]
) -> RowT:
    """Insert or replace by id, always taking a new change_seq so /me/changes sees it."""
    fields = {**values, "change_seq": CHANGE_SEQ.next_value()}
    stmt = (
        insert(row_type)
        .values(fields)
        .on_conflict_do_update(index_elements=["id"], set_={k: v for k, v in fields.items() if k != "id"})
        .returning(row_type)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one()


class SqlRoutineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, routine_id: UUID) -> RoutineRecord | None:
        row = await self._session.get(RoutineRow, routine_id)
        return to_routine(row) if row else None

    async def get_many(self, routine_ids: Collection[UUID]) -> dict[UUID, RoutineRecord]:
        if not routine_ids:
            return {}
        rows = await self._session.scalars(select(RoutineRow).where(RoutineRow.id.in_(routine_ids)))
        return {row.id: to_routine(row) for row in rows}

    async def save(self, routine: RoutineRecord) -> RoutineRecord:
        row = await _upsert(
            self._session,
            RoutineRow,
            {
                "id": routine.id,
                "owner_id": routine.owner_id,
                "name": routine.name,
                "exercises": routine.exercises,
                "data": routine.data,
                "visibility": routine.visibility,
                "created_at": routine.created_at,
                "updated_at": routine.updated_at,
                "deleted_at": routine.deleted_at,
            },
        )
        return to_routine(row)

    async def changed_since(self, owner_id: UUID, seq: int, limit: int) -> list[RoutineRecord]:
        rows = await self._session.scalars(
            select(RoutineRow)
            .where(RoutineRow.owner_id == owner_id, RoutineRow.change_seq > seq)
            .order_by(RoutineRow.change_seq)
            .limit(limit)
        )
        return [to_routine(row) for row in rows]


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: UUID) -> SessionRecord | None:
        row = await self._session.get(WorkoutSessionRow, session_id)
        return to_session(row) if row else None

    async def get_many(self, session_ids: Collection[UUID]) -> dict[UUID, SessionRecord]:
        if not session_ids:
            return {}
        rows = await self._session.scalars(select(WorkoutSessionRow).where(WorkoutSessionRow.id.in_(session_ids)))
        return {row.id: to_session(row) for row in rows}

    async def save(self, session: SessionRecord) -> SessionRecord:
        row = await _upsert(
            self._session,
            WorkoutSessionRow,
            {
                "id": session.id,
                "user_id": session.user_id,
                "routine_id": session.routine_id,
                "name": session.name,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "summary": session.summary,
                "data": session.data,
                "visibility": session.visibility,
                "updated_at": session.updated_at,
                "deleted_at": session.deleted_at,
            },
        )
        return to_session(row)

    async def changed_since(self, user_id: UUID, seq: int, limit: int) -> list[SessionRecord]:
        rows = await self._session.scalars(
            select(WorkoutSessionRow)
            .where(WorkoutSessionRow.user_id == user_id, WorkoutSessionRow.change_seq > seq)
            .order_by(WorkoutSessionRow.change_seq)
            .limit(limit)
        )
        return [to_session(row) for row in rows]


class SqlExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, exercise_id: UUID) -> CustomExerciseRecord | None:
        row = await self._session.get(CustomExerciseRow, exercise_id)
        return to_exercise(row) if row else None

    async def get_many(self, exercise_ids: Collection[UUID]) -> dict[UUID, CustomExerciseRecord]:
        if not exercise_ids:
            return {}
        rows = await self._session.scalars(select(CustomExerciseRow).where(CustomExerciseRow.id.in_(exercise_ids)))
        return {row.id: to_exercise(row) for row in rows}

    async def save(self, exercise: CustomExerciseRecord) -> CustomExerciseRecord:
        row = await _upsert(
            self._session,
            CustomExerciseRow,
            {
                "id": exercise.id,
                "owner_id": exercise.owner_id,
                "name": exercise.name,
                "primary_muscle": exercise.primary_muscle,
                "equipment": exercise.equipment,
                "note": exercise.note,
                "updated_at": exercise.updated_at,
                "deleted_at": exercise.deleted_at,
            },
        )
        return to_exercise(row)

    async def changed_since(self, owner_id: UUID, seq: int, limit: int) -> list[CustomExerciseRecord]:
        rows = await self._session.scalars(
            select(CustomExerciseRow)
            .where(CustomExerciseRow.owner_id == owner_id, CustomExerciseRow.change_seq > seq)
            .order_by(CustomExerciseRow.change_seq)
            .limit(limit)
        )
        return [to_exercise(row) for row in rows]


class SqlFeaturedRoutineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ids_of(self, user_id: UUID) -> list[UUID]:
        rows = await self._session.scalars(
            select(FeaturedRoutineRow.routine_id)
            .where(FeaturedRoutineRow.user_id == user_id)
            .order_by(FeaturedRoutineRow.position)
        )
        return list(rows)

    async def replace(self, user_id: UUID, routine_ids: Sequence[UUID]) -> None:
        await self._session.execute(delete(FeaturedRoutineRow).where(FeaturedRoutineRow.user_id == user_id))
        if routine_ids:
            await self._session.execute(
                plain_insert(FeaturedRoutineRow),
                [
                    {"user_id": user_id, "routine_id": routine_id, "position": position}
                    for position, routine_id in enumerate(routine_ids)
                ],
            )

    async def remove(self, routine_id: UUID) -> None:
        await self._session.execute(delete(FeaturedRoutineRow).where(FeaturedRoutineRow.routine_id == routine_id))
