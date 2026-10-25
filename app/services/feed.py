from dataclasses import dataclass
from uuid import UUID

from app.domain.activity import Activity, ActivityType
from app.domain.pagination import Cursor, Page
from app.domain.profile import Profile
from app.domain.sync import RoutineRecord, SessionRecord
from app.domain.visibility import visible_levels
from app.services.access import relationship, visible_profile_by_username
from app.services.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class ActivityView:
    activity: Activity
    actor: Profile
    session: SessionRecord | None = None
    routine: RoutineRecord | None = None
    # The followed user, for started_following.
    user: Profile | None = None


def _activity_cursor(activity: Activity) -> Cursor:
    return Cursor(activity.created_at, activity.id)


class FeedService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def feed(self, viewer_id: UUID, cursor: Cursor | None, limit: int) -> Page[ActivityView]:
        """Computed on read: what the people the viewer follows did, newest first."""
        activities = await self._uow.activities.feed(viewer_id, cursor, limit + 1)
        return await self._page(activities, limit)

    async def user_activity(
        self, viewer_id: UUID, username: str, cursor: Cursor | None, limit: int
    ) -> Page[ActivityView]:
        owner = await visible_profile_by_username(self._uow, viewer_id, username)
        rel = await relationship(self._uow, viewer_id, owner.id)
        levels = visible_levels(is_owner=rel.is_owner, owner_is_private=owner.is_private, is_follower=rel.is_follower)
        activities = await self._uow.activities.by_user(owner.id, levels, cursor, limit + 1)
        return await self._page(activities, limit)

    async def _page(self, activities: list[Activity], limit: int) -> Page[ActivityView]:
        # The cursor follows the raw rows, so items dropped below never shift the next page.
        page = activities[:limit]
        next_cursor = _activity_cursor(page[-1]).encode() if len(activities) > limit else None
        return Page(await self._hydrate(page), next_cursor)

    async def _hydrate(self, activities: list[Activity]) -> list[ActivityView]:
        def refs(type_: ActivityType) -> set[UUID]:
            return {a.ref_id for a in activities if a.type == type_}

        sessions = await self._uow.sessions.get_many(refs(ActivityType.WORKOUT_COMPLETED))
        routines = await self._uow.routines.get_many(refs(ActivityType.ROUTINE_SHARED))
        profiles = await self._uow.profiles.get_many(
            {a.user_id for a in activities} | refs(ActivityType.STARTED_FOLLOWING)
        )

        views: list[ActivityView] = []
        for activity in activities:
            actor = profiles.get(activity.user_id)
            if actor is None:
                continue
            match activity.type:
                case ActivityType.WORKOUT_COMPLETED:
                    session = sessions.get(activity.ref_id)
                    if session and session.deleted_at is None:
                        views.append(ActivityView(activity, actor, session=session))
                case ActivityType.ROUTINE_SHARED:
                    routine = routines.get(activity.ref_id)
                    if routine and routine.deleted_at is None:
                        views.append(ActivityView(activity, actor, routine=routine))
                case ActivityType.STARTED_FOLLOWING:
                    if user := profiles.get(activity.ref_id):
                        views.append(ActivityView(activity, actor, user=user))
        return views
