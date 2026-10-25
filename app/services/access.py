from uuid import UUID

from app.domain.errors import NotFound
from app.domain.profile import Profile
from app.domain.social import Relationship
from app.domain.visibility import FollowStatus
from app.services.ports import UnitOfWork


async def visible_profile(uow: UnitOfWork, viewer_id: UUID, user_id: UUID) -> Profile:
    """The profile, unless it doesn't exist or a block hides it (both look the same to the viewer)."""
    profile = await uow.profiles.get(user_id)
    return await _unless_blocked(uow, viewer_id, profile)


async def visible_profile_by_username(uow: UnitOfWork, viewer_id: UUID, username: str) -> Profile:
    profile = await uow.profiles.get_by_username(username.lower())
    return await _unless_blocked(uow, viewer_id, profile)


async def _unless_blocked(uow: UnitOfWork, viewer_id: UUID, profile: Profile | None) -> Profile:
    if profile is None or (profile.id != viewer_id and await uow.blocks.between(viewer_id, profile.id)):
        raise NotFound("user.notFound", "User not found")
    return profile


async def relationship(uow: UnitOfWork, viewer_id: UUID, owner_id: UUID) -> Relationship:
    if viewer_id == owner_id:
        return Relationship(is_owner=True, following=None, followed_by=False)
    mine = await uow.follows.get(viewer_id, owner_id)
    theirs = await uow.follows.get(owner_id, viewer_id)
    return Relationship(
        is_owner=False,
        following=mine.status if mine else None,
        followed_by=theirs is not None and theirs.status == FollowStatus.ACTIVE,
    )
