from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, delete, exists, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.errors import Conflict
from app.domain.pagination import Cursor
from app.domain.profile import Profile
from app.domain.social import Connection, Follow, Report
from app.domain.visibility import FollowStatus
from app.repositories.tables import BlockRow, FollowRow, ProfileRow, ReportRow


def to_profile(row: ProfileRow) -> Profile:
    return Profile(
        id=row.id,
        username=row.username,
        display_name=row.display_name,
        bio=row.bio,
        avatar_url=row.avatar_url,
        is_private=row.is_private,
        created_at=row.created_at,
    )


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> Profile | None:
        row = await self._session.get(ProfileRow, user_id)
        return to_profile(row) if row else None

    async def get_by_username(self, username: str) -> Profile | None:
        row = await self._session.scalar(select(ProfileRow).where(ProfileRow.username == username))
        return to_profile(row) if row else None

    async def get_many(self, user_ids: Collection[UUID]) -> dict[UUID, Profile]:
        if not user_ids:
            return {}
        rows = await self._session.scalars(select(ProfileRow).where(ProfileRow.id.in_(user_ids)))
        return {row.id: to_profile(row) for row in rows}

    async def insert_if_absent(self, profile: Profile) -> bool:
        inserted = await self._session.scalar(
            insert(ProfileRow)
            .values(
                id=profile.id,
                username=profile.username,
                display_name=profile.display_name,
                bio=profile.bio,
                avatar_url=profile.avatar_url,
                is_private=profile.is_private,
                created_at=profile.created_at,
            )
            .on_conflict_do_nothing()
            .returning(ProfileRow.id)
        )
        return inserted is not None

    async def update(self, profile: Profile) -> None:
        try:
            async with self._session.begin_nested():
                await self._session.execute(
                    update(ProfileRow)
                    .where(ProfileRow.id == profile.id)
                    .values(
                        username=profile.username,
                        display_name=profile.display_name,
                        bio=profile.bio,
                        avatar_url=profile.avatar_url,
                        is_private=profile.is_private,
                    )
                )
        except IntegrityError as error:
            raise Conflict("username.taken", "Username already taken") from error

    async def delete(self, user_id: UUID) -> None:
        await self._session.execute(delete(ProfileRow).where(ProfileRow.id == user_id))

    async def search(self, query: str, viewer_id: UUID, limit: int) -> list[Profile]:
        pattern = escape_like(query.lower())
        by_username = ProfileRow.username.like(f"{pattern}%", escape="\\")
        blocked = exists().where(
            or_(
                and_(BlockRow.blocker_id == viewer_id, BlockRow.blocked_id == ProfileRow.id),
                and_(BlockRow.blocker_id == ProfileRow.id, BlockRow.blocked_id == viewer_id),
            )
        )
        rows = await self._session.scalars(
            select(ProfileRow)
            .where(
                or_(by_username, func.lower(ProfileRow.display_name).like(f"%{pattern}%", escape="\\")),
                ~blocked,
            )
            .order_by(by_username.desc(), ProfileRow.username)
            .limit(limit)
        )
        return [to_profile(row) for row in rows]

    async def counts(self, user_id: UUID) -> tuple[int, int]:
        active = FollowRow.status == FollowStatus.ACTIVE
        followers = select(func.count()).where(FollowRow.followee_id == user_id, active)
        following = select(func.count()).where(FollowRow.follower_id == user_id, active)
        row = (await self._session.execute(select(followers.scalar_subquery(), following.scalar_subquery()))).one()
        return int(row[0]), int(row[1])


class SqlFollowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, follower_id: UUID, followee_id: UUID) -> Follow | None:
        row = await self._session.get(FollowRow, (follower_id, followee_id))
        if row is None:
            return None
        return Follow(row.follower_id, row.followee_id, FollowStatus(row.status), row.created_at)

    async def save(self, follow: Follow) -> None:
        await self._session.execute(
            insert(FollowRow)
            .values(
                follower_id=follow.follower_id,
                followee_id=follow.followee_id,
                status=follow.status,
                created_at=follow.created_at,
            )
            .on_conflict_do_update(index_elements=["follower_id", "followee_id"], set_={"status": follow.status})
        )

    async def delete(self, follower_id: UUID, followee_id: UUID) -> bool:
        deleted = await self._session.scalar(
            delete(FollowRow)
            .where(FollowRow.follower_id == follower_id, FollowRow.followee_id == followee_id)
            .returning(FollowRow.follower_id)
        )
        return deleted is not None

    async def accept_all_pending(self, followee_id: UUID) -> list[UUID]:
        rows = await self._session.scalars(
            update(FollowRow)
            .where(FollowRow.followee_id == followee_id, FollowRow.status == FollowStatus.PENDING)
            .values(status=FollowStatus.ACTIVE)
            .returning(FollowRow.follower_id)
        )
        return list(rows)

    async def followers(
        self, user_id: UUID, status: FollowStatus, cursor: Cursor | None, limit: int
    ) -> list[Connection]:
        stmt = (
            select(ProfileRow, FollowRow.created_at)
            .join(FollowRow, FollowRow.follower_id == ProfileRow.id)
            .where(FollowRow.followee_id == user_id, FollowRow.status == status)
        )
        return await self._page(stmt, FollowRow.follower_id, cursor, limit)

    async def following(self, user_id: UUID, cursor: Cursor | None, limit: int) -> list[Connection]:
        stmt = (
            select(ProfileRow, FollowRow.created_at)
            .join(FollowRow, FollowRow.followee_id == ProfileRow.id)
            .where(FollowRow.follower_id == user_id, FollowRow.status == FollowStatus.ACTIVE)
        )
        return await self._page(stmt, FollowRow.followee_id, cursor, limit)

    async def _page(
        self,
        stmt: Select[ProfileRow, datetime],
        other_id: InstrumentedAttribute[UUID],
        cursor: Cursor | None,
        limit: int,
    ) -> list[Connection]:
        if cursor:
            stmt = stmt.where(tuple_(FollowRow.created_at, other_id) < tuple_(cursor.created_at, cursor.id))
        rows = await self._session.execute(stmt.order_by(FollowRow.created_at.desc(), other_id.desc()).limit(limit))
        return [Connection(to_profile(profile), since) for profile, since in rows]


class SqlBlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, blocker_id: UUID, blocked_id: UUID) -> None:
        await self._session.execute(
            insert(BlockRow).values(blocker_id=blocker_id, blocked_id=blocked_id).on_conflict_do_nothing()
        )

    async def remove(self, blocker_id: UUID, blocked_id: UUID) -> None:
        await self._session.execute(
            delete(BlockRow).where(BlockRow.blocker_id == blocker_id, BlockRow.blocked_id == blocked_id)
        )

    async def between(self, a: UUID, b: UUID) -> bool:
        found = await self._session.scalar(
            select(
                exists().where(
                    or_(
                        and_(BlockRow.blocker_id == a, BlockRow.blocked_id == b),
                        and_(BlockRow.blocker_id == b, BlockRow.blocked_id == a),
                    )
                )
            )
        )
        return bool(found)

    async def blocked_by(self, blocker_id: UUID) -> list[Profile]:
        rows = await self._session.scalars(
            select(ProfileRow)
            .join(BlockRow, BlockRow.blocked_id == ProfileRow.id)
            .where(BlockRow.blocker_id == blocker_id)
            .order_by(ProfileRow.username)
        )
        return [to_profile(row) for row in rows]


class SqlReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, report: Report) -> None:
        self._session.add(
            ReportRow(
                id=report.id,
                reporter_id=report.reporter_id,
                target_user_id=report.target_user_id,
                reason=report.reason,
                details=report.details,
                created_at=report.created_at,
            )
        )
        await self._session.flush()
