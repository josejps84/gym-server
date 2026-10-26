from collections.abc import Collection
from uuid import UUID

from sqlalchemy import Select, delete, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.activity import Activity, ActivityType
from app.domain.pagination import Cursor
from app.domain.visibility import FollowStatus, Visibility
from app.repositories.tables import ActivityRow, FollowRow


def to_activity(row: ActivityRow) -> Activity:
    return Activity(
        id=row.id,
        user_id=row.user_id,
        type=ActivityType(row.type),
        ref_id=row.ref_id,
        visibility=Visibility(row.visibility),
        created_at=row.created_at,
    )


class SqlActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, activity: Activity) -> None:
        await self._session.execute(
            insert(ActivityRow)
            .values(
                id=activity.id,
                user_id=activity.user_id,
                type=activity.type,
                ref_id=activity.ref_id,
                visibility=activity.visibility,
                created_at=activity.created_at,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "type", "ref_id"], set_={"visibility": activity.visibility}
            )
        )

    async def delete_for(self, user_id: UUID, type_: ActivityType, ref_id: UUID) -> None:
        await self._session.execute(
            delete(ActivityRow).where(
                ActivityRow.user_id == user_id, ActivityRow.type == type_, ActivityRow.ref_id == ref_id
            )
        )

    async def by_user(
        self, user_id: UUID, levels: Collection[Visibility], cursor: Cursor | None, limit: int
    ) -> list[Activity]:
        if not levels:
            return []
        stmt = select(ActivityRow).where(ActivityRow.user_id == user_id, ActivityRow.visibility.in_(levels))
        return await self._page(stmt, cursor, limit)

    async def feed(self, viewer_id: UUID, cursor: Cursor | None, limit: int) -> list[Activity]:
        followed = select(FollowRow.followee_id).where(
            FollowRow.follower_id == viewer_id, FollowRow.status == FollowStatus.ACTIVE
        )
        # The viewer's own shared activity too, so they see what their followers see.
        stmt = select(ActivityRow).where(
            or_(ActivityRow.user_id.in_(followed), ActivityRow.user_id == viewer_id),
            ActivityRow.visibility.in_([Visibility.FOLLOWERS, Visibility.PUBLIC]),
        )
        return await self._page(stmt, cursor, limit)

    async def _page(self, stmt: Select[ActivityRow], cursor: Cursor | None, limit: int) -> list[Activity]:
        if cursor:
            stmt = stmt.where(tuple_(ActivityRow.created_at, ActivityRow.id) < tuple_(cursor.created_at, cursor.id))
        rows = await self._session.scalars(
            stmt.order_by(ActivityRow.created_at.desc(), ActivityRow.id.desc()).limit(limit)
        )
        return [to_activity(row) for row in rows]
