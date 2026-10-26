from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.activity import Activity, ActivityType
from app.domain.errors import Forbidden, Invalid, NotFound
from app.domain.pagination import Cursor, Page, page_of
from app.domain.profile import Profile
from app.domain.social import REPORT_DETAILS_MAX, Connection, Follow, Report, ReportReason
from app.domain.visibility import FollowStatus, Visibility, can_view_connections, follow_status_for
from app.services.access import visible_profile
from app.services.ports import UnitOfWork


def _connection_cursor(connection: Connection) -> Cursor:
    return Cursor(connection.since, connection.profile.id)


class FollowService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def follow(self, viewer_id: UUID, target_id: UUID) -> FollowStatus:
        if viewer_id == target_id:
            raise Invalid("follow.self", "You can't follow yourself")
        target = await visible_profile(self._uow, viewer_id, target_id)
        existing = await self._uow.follows.get(viewer_id, target_id)
        if existing:
            return existing.status
        now = datetime.now(UTC)
        status = follow_status_for(target.is_private)
        await self._uow.follows.save(Follow(viewer_id, target_id, status, now))
        if status == FollowStatus.ACTIVE:
            await self._started_following(viewer_id, target_id, now)
        await self._uow.commit()
        return status

    async def unfollow(self, viewer_id: UUID, target_id: UUID) -> None:
        """Also cancels a pending request."""
        await self._uow.follows.delete(viewer_id, target_id)
        await self._uow.activities.delete_for(viewer_id, ActivityType.STARTED_FOLLOWING, target_id)
        await self._uow.commit()

    async def followers(self, viewer_id: UUID, user_id: UUID, cursor: Cursor | None, limit: int) -> Page[Connection]:
        await self._check_connections_visible(viewer_id, user_id)
        items = await self._uow.follows.followers(user_id, FollowStatus.ACTIVE, cursor, limit + 1)
        return page_of(items, limit, _connection_cursor)

    async def following(self, viewer_id: UUID, user_id: UUID, cursor: Cursor | None, limit: int) -> Page[Connection]:
        await self._check_connections_visible(viewer_id, user_id)
        items = await self._uow.follows.following(user_id, cursor, limit + 1)
        return page_of(items, limit, _connection_cursor)

    async def requests(self, user_id: UUID, cursor: Cursor | None, limit: int) -> Page[Connection]:
        items = await self._uow.follows.followers(user_id, FollowStatus.PENDING, cursor, limit + 1)
        return page_of(items, limit, _connection_cursor)

    async def accept(self, user_id: UUID, follower_id: UUID) -> None:
        request = await self._pending_request(user_id, follower_id)
        now = datetime.now(UTC)
        await self._uow.follows.save(Follow(follower_id, user_id, FollowStatus.ACTIVE, request.created_at))
        await self._started_following(follower_id, user_id, now)
        await self._uow.commit()

    async def decline(self, user_id: UUID, follower_id: UUID) -> None:
        await self._pending_request(user_id, follower_id)
        await self._uow.follows.delete(follower_id, user_id)
        await self._uow.commit()

    async def _pending_request(self, user_id: UUID, follower_id: UUID) -> Follow:
        request = await self._uow.follows.get(follower_id, user_id)
        if request is None or request.status != FollowStatus.PENDING:
            raise NotFound("followRequest.notFound", "No pending request from that user")
        return request

    async def _check_connections_visible(self, viewer_id: UUID, user_id: UUID) -> None:
        await visible_profile(self._uow, viewer_id, user_id)
        if not can_view_connections(is_owner=viewer_id == user_id):
            raise Forbidden("connections.ownerOnly", "Only the owner can see these lists")

    async def _started_following(self, follower_id: UUID, followee_id: UUID, now: datetime) -> None:
        await self._uow.activities.upsert(
            Activity(uuid4(), follower_id, ActivityType.STARTED_FOLLOWING, followee_id, Visibility.PUBLIC, now)
        )


class ModerationService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def block(self, user_id: UUID, target_id: UUID) -> None:
        """Hides each user from the other and removes any follow between them."""
        if user_id == target_id:
            raise Invalid("block.self", "You can't block yourself")
        await self._existing(target_id)
        await self._uow.blocks.add(user_id, target_id)
        for follower, followee in ((user_id, target_id), (target_id, user_id)):
            await self._uow.follows.delete(follower, followee)
            await self._uow.activities.delete_for(follower, ActivityType.STARTED_FOLLOWING, followee)
        await self._uow.commit()

    async def unblock(self, user_id: UUID, target_id: UUID) -> None:
        await self._uow.blocks.remove(user_id, target_id)
        await self._uow.commit()

    async def blocked(self, user_id: UUID) -> list[Profile]:
        return await self._uow.blocks.blocked_by(user_id)

    async def report(self, user_id: UUID, target_id: UUID, reason: ReportReason, details: str) -> None:
        if user_id == target_id:
            raise Invalid("report.self", "You can't report yourself")
        details = details.strip()
        if len(details) > REPORT_DETAILS_MAX:
            raise Invalid("report.details", f"Details are longer than {REPORT_DETAILS_MAX}")
        # Reporting works even after blocking, so no visibility check here.
        await self._existing(target_id)
        await self._uow.reports.add(Report(uuid4(), user_id, target_id, reason, details, datetime.now(UTC)))
        await self._uow.commit()

    async def _existing(self, user_id: UUID) -> Profile:
        profile = await self._uow.profiles.get(user_id)
        if profile is None:
            raise NotFound("user.notFound", "User not found")
        return profile
