from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.dependencies import (
    FeedServiceDep,
    FollowServiceDep,
    ModerationServiceDep,
    PageDep,
    ProfileDep,
    ProfileServiceDep,
)
from app.domain.pagination import Page
from app.domain.social import Connection
from app.routers.feed import activity_page
from app.routers.schemas import (
    ActivityOut,
    ConnectionOut,
    FollowOut,
    Paged,
    ProfileCard,
    PublicExerciseOut,
    PublicProfileOut,
    RelationshipOut,
    ReportIn,
    RoutineOut,
    UserList,
)

router = APIRouter(tags=["users"])


def _connections(page: Page[Connection]) -> Paged[ConnectionOut]:
    return Paged(items=[ConnectionOut.of_connection(c) for c in page.items], next_cursor=page.next_cursor)


@router.get("/search/users")
async def search_users(
    q: Annotated[str, Query(min_length=1, max_length=50)], profile: ProfileDep, service: ProfileServiceDep
) -> UserList:
    """By username prefix or any part of the display name."""
    return UserList(items=[ProfileCard.of(p) for p in await service.search(profile.id, q)])


@router.get("/users/{username}")
async def public_profile(username: str, profile: ProfileDep, service: ProfileServiceDep) -> PublicProfileOut:
    """Profile, counters, how I relate to them and their featured routines (if I may see them)."""
    view = await service.public_profile(profile.id, username)
    return PublicProfileOut(
        **ProfileCard.of(view.profile).model_dump(),
        bio=view.profile.bio,
        is_private=view.profile.is_private,
        followers_count=view.followers_count,
        following_count=view.following_count,
        relationship=RelationshipOut(following=view.relationship.following, followed_by=view.relationship.followed_by),
        content_visible=view.content_visible,
        featured_routines=[RoutineOut.of(r) for r in view.featured_routines],
        exercises=[PublicExerciseOut.of(e) for e in view.exercises],
    )


@router.get("/users/{username}/activity")
async def user_activity(
    username: str, profile: ProfileDep, page: PageDep, service: FeedServiceDep
) -> Paged[ActivityOut]:
    return activity_page(await service.user_activity(profile.id, username, *page))


@router.post("/users/{user_id}/follow")
async def follow(user_id: UUID, profile: ProfileDep, service: FollowServiceDep) -> FollowOut:
    """Active right away for public profiles, pending until accepted for private ones."""
    return FollowOut(status=await service.follow(profile.id, user_id))


@router.delete("/users/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow(user_id: UUID, profile: ProfileDep, service: FollowServiceDep) -> None:
    await service.unfollow(profile.id, user_id)


@router.get("/users/{user_id}/followers")
async def followers(
    user_id: UUID, profile: ProfileDep, page: PageDep, service: FollowServiceDep
) -> Paged[ConnectionOut]:
    return _connections(await service.followers(profile.id, user_id, *page))


@router.get("/users/{user_id}/following")
async def following(
    user_id: UUID, profile: ProfileDep, page: PageDep, service: FollowServiceDep
) -> Paged[ConnectionOut]:
    return _connections(await service.following(profile.id, user_id, *page))


@router.post("/users/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def block(user_id: UUID, profile: ProfileDep, service: ModerationServiceDep) -> None:
    await service.block(profile.id, user_id)


@router.delete("/users/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def unblock(user_id: UUID, profile: ProfileDep, service: ModerationServiceDep) -> None:
    await service.unblock(profile.id, user_id)


@router.post("/users/{user_id}/report", status_code=status.HTTP_204_NO_CONTENT)
async def report(user_id: UUID, body: ReportIn, profile: ProfileDep, service: ModerationServiceDep) -> None:
    """Saved for manual review (reports table in Supabase)."""
    await service.report(profile.id, user_id, body.reason, body.details)
