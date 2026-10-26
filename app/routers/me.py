from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies import (
    AccountServiceDep,
    FollowServiceDep,
    ModerationServiceDep,
    PageDep,
    ProfileDep,
    ProfileServiceDep,
    RoutineServiceDep,
    UserDep,
    current_profile,
)
from app.routers.schemas import (
    AvatarUploadIn,
    AvatarUploadOut,
    ConnectionOut,
    FeaturedRoutinesIn,
    FeaturedRoutinesOut,
    MeOut,
    Paged,
    ProfileCard,
    ProfilePatchIn,
    UserList,
)
from app.services.profiles import MeView, ProfilePatch

router = APIRouter(prefix="/me", tags=["me"])


def _me_out(view: MeView) -> MeOut:
    profile = view.profile
    return MeOut(
        id=profile.id,
        username=profile.username,
        display_name=profile.display_name,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        is_private=profile.is_private,
        created_at=profile.created_at,
        followers_count=view.followers_count,
        following_count=view.following_count,
        featured_routine_ids=view.featured_routine_ids,
    )


@router.get("")
async def get_me(profile: ProfileDep, service: ProfileServiceDep) -> MeOut:
    """My profile; the first call creates it with a placeholder username to change with PATCH."""
    return _me_out(await service.me(profile.id))


@router.patch("")
async def update_me(body: ProfilePatchIn, profile: ProfileDep, service: ProfileServiceDep) -> MeOut:
    patch = ProfilePatch(
        username=body.username,
        display_name=body.display_name,
        bio=body.bio,
        avatar_url=body.avatar_url,
        clear_avatar="avatar_url" in body.model_fields_set and body.avatar_url is None,
    )
    return _me_out(await service.update_me(profile.id, patch))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: UserDep, service: AccountServiceDep) -> None:
    """Deletes the account and all its data, including the login. Safe to retry."""
    await service.delete_account(user.id)


@router.post("/avatar-upload-url", dependencies=[Depends(current_profile)])
async def avatar_upload_url(body: AvatarUploadIn, user: UserDep, service: ProfileServiceDep) -> AvatarUploadOut:
    """Signed URL to upload the photo straight to Supabase Storage (resize it to 512 px first)."""
    result = await service.avatar_upload_url(user.id, body.content_type)
    return AvatarUploadOut(
        upload_url=result.upload.upload_url,
        token=result.upload.token,
        avatar_url=result.avatar_url,
        expires_at=result.upload.expires_at,
    )


@router.post("/avatar/provider-photo", dependencies=[Depends(current_profile)])
async def use_provider_photo(user: UserDep, service: ProfileServiceDep) -> MeOut:
    """Makes the Google account's photo the profile photo (a copy in our storage)."""
    return _me_out(await service.use_provider_photo(user))


@router.put("/featured-routines")
async def set_featured_routines(
    body: FeaturedRoutinesIn, profile: ProfileDep, service: RoutineServiceDep
) -> FeaturedRoutinesOut:
    """The shared routines shown on my profile, in this order."""
    return FeaturedRoutinesOut(routine_ids=await service.set_featured(profile.id, body.routine_ids))


@router.get("/follow-requests")
async def follow_requests(profile: ProfileDep, page: PageDep, service: FollowServiceDep) -> Paged[ConnectionOut]:
    result = await service.requests(profile.id, *page)
    return Paged(items=[ConnectionOut.of_connection(c) for c in result.items], next_cursor=result.next_cursor)


@router.post("/follow-requests/{user_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept_follow_request(user_id: UUID, profile: ProfileDep, service: FollowServiceDep) -> None:
    await service.accept(profile.id, user_id)


@router.delete("/follow-requests/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def decline_follow_request(user_id: UUID, profile: ProfileDep, service: FollowServiceDep) -> None:
    await service.decline(profile.id, user_id)


@router.get("/blocks")
async def blocked_users(profile: ProfileDep, service: ModerationServiceDep) -> UserList:
    return UserList(items=[ProfileCard.of(p) for p in await service.blocked(profile.id)])
