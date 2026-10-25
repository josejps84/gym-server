import logging
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.auth import AuthUser
from app.domain.activity import Activity, ActivityType
from app.domain.errors import Conflict, Invalid
from app.domain.profile import (
    DISPLAY_NAME_MAX,
    Profile,
    generated_username,
    normalize_bio,
    normalize_display_name,
    normalize_username,
)
from app.domain.social import Relationship
from app.domain.sync import CustomExerciseRecord, RoutineRecord, exercise_ids
from app.domain.visibility import Visibility, can_view, visible_levels
from app.services.access import relationship, visible_profile_by_username
from app.services.ports import AvatarStorage, IdentityAdmin, SignedUpload, UnitOfWork

log = logging.getLogger(__name__)

SEARCH_MIN = 2
SEARCH_LIMIT = 20
AVATAR_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_AVATAR_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")


@dataclass(frozen=True, slots=True)
class ProfilePatch:
    username: str | None = None
    display_name: str | None = None
    bio: str | None = None
    is_private: bool | None = None
    avatar_url: str | None = None
    clear_avatar: bool = False


@dataclass(frozen=True, slots=True)
class MeView:
    profile: Profile
    followers_count: int
    following_count: int
    featured_routine_ids: list[UUID]


@dataclass(frozen=True, slots=True)
class PublicProfileView:
    profile: Profile
    followers_count: int
    following_count: int
    relationship: Relationship
    # False when the profile is private and the viewer is not an accepted follower.
    content_visible: bool
    featured_routines: list[RoutineRecord]
    exercises: list[CustomExerciseRecord]


@dataclass(frozen=True, slots=True)
class AvatarUpload:
    upload: SignedUpload
    avatar_url: str


async def custom_exercises_of(uow: UnitOfWork, routines: list[RoutineRecord]) -> list[CustomExerciseRecord]:
    """The owners' own exercises the routines use, so others can see what each id is."""
    wanted: dict[UUID, UUID] = {}
    for routine in routines:
        for exercise_id in exercise_ids(routine.exercises):
            try:
                wanted[UUID(exercise_id)] = routine.owner_id
            except ValueError:
                continue  # A catalog exercise ("seed-..."): every app already has it.
    found = await uow.exercises.get_many(wanted.keys())
    return [
        exercise
        for exercise in found.values()
        if exercise.deleted_at is None and exercise.owner_id == wanted[exercise.id]
    ]


class ProfileService:
    def __init__(self, uow: UnitOfWork, storage: AvatarStorage) -> None:
        self._uow = uow
        self._storage = storage

    async def ensure(self, user: AuthUser) -> Profile:
        """The caller's profile, created on their first request with a placeholder username."""
        profile = await self._uow.profiles.get(user.id)
        if profile:
            return profile
        for _ in range(5):
            candidate = Profile(
                id=user.id,
                username=generated_username(),
                display_name=" ".join((user.name or "").split())[:DISPLAY_NAME_MAX],
                bio="",
                avatar_url=None,
                is_private=False,
                created_at=datetime.now(UTC),
            )
            if await self._uow.profiles.insert_if_absent(candidate):
                await self._uow.commit()
                return candidate
            # Either the username was taken or a parallel request just created the profile.
            existing = await self._uow.profiles.get(user.id)
            if existing:
                return existing
        raise Conflict("username.generate", "Could not create the profile, try again")

    async def me(self, user_id: UUID) -> MeView:
        profile = await self._uow.profiles.get(user_id)
        assert profile is not None, "current_profile runs first"
        followers, following = await self._uow.profiles.counts(user_id)
        featured = await self._uow.featured.ids_of(user_id)
        return MeView(profile, followers, following, featured)

    async def update_me(self, user_id: UUID, patch: ProfilePatch) -> MeView:
        current = await self._uow.profiles.get(user_id)
        assert current is not None, "current_profile runs first"
        updated = current
        if patch.username is not None:
            updated = replace(updated, username=normalize_username(patch.username))
        if patch.display_name is not None:
            updated = replace(updated, display_name=normalize_display_name(patch.display_name))
        if patch.bio is not None:
            updated = replace(updated, bio=normalize_bio(patch.bio))
        if patch.is_private is not None:
            updated = replace(updated, is_private=patch.is_private)
        if patch.clear_avatar:
            updated = replace(updated, avatar_url=None)
        elif patch.avatar_url is not None:
            self._check_avatar_url(user_id, patch.avatar_url)
            updated = replace(updated, avatar_url=patch.avatar_url)

        await self._uow.profiles.update(updated)
        if current.is_private and not updated.is_private:
            await self._accept_pending_requests(user_id)
        await self._uow.commit()

        if current.avatar_url and current.avatar_url != updated.avatar_url:
            await self._delete_avatar_quietly(user_id, current.avatar_url)
        return await self.me(user_id)

    async def avatar_upload_url(self, user_id: UUID, content_type: str) -> AvatarUpload:
        extension = AVATAR_TYPES.get(content_type)
        if extension is None:
            raise Invalid("avatar.type", "Use a JPEG, PNG or WebP image")
        # A new name each time, so phones never show a cached old photo.
        path = f"{user_id}/{uuid4().hex}.{extension}"
        upload = await self._storage.create_upload_url(path)
        return AvatarUpload(upload, self._storage.public_url(path))

    async def public_profile(self, viewer_id: UUID, username: str) -> PublicProfileView:
        profile = await visible_profile_by_username(self._uow, viewer_id, username)
        rel = await relationship(self._uow, viewer_id, profile.id)
        followers, following = await self._uow.profiles.counts(profile.id)
        levels = visible_levels(is_owner=rel.is_owner, owner_is_private=profile.is_private, is_follower=rel.is_follower)
        featured: list[RoutineRecord] = []
        if levels:
            ids = await self._uow.featured.ids_of(profile.id)
            routines = await self._uow.routines.get_many(ids)
            featured = [
                routine
                for routine_id in ids
                if (routine := routines.get(routine_id))
                and routine.is_shared
                and can_view(
                    routine.visibility,
                    is_owner=rel.is_owner,
                    owner_is_private=profile.is_private,
                    is_follower=rel.is_follower,
                )
            ]
        return PublicProfileView(
            profile=profile,
            followers_count=followers,
            following_count=following,
            relationship=rel,
            content_visible=bool(levels),
            featured_routines=featured,
            exercises=await custom_exercises_of(self._uow, featured),
        )

    async def search(self, viewer_id: UUID, query: str) -> list[Profile]:
        query = query.strip().lstrip("@")
        if len(query) < SEARCH_MIN:
            raise Invalid("search.tooShort", f"Type at least {SEARCH_MIN} characters")
        return await self._uow.profiles.search(query, viewer_id, SEARCH_LIMIT)

    def _check_avatar_url(self, user_id: UUID, url: str) -> None:
        """Only photos uploaded through avatar_upload_url, in the user's own folder."""
        prefix = self._storage.public_url(f"{user_id}/")
        if not (url.startswith(prefix) and _AVATAR_NAME.match(url[len(prefix) :])):
            raise Invalid("avatar.url", "Upload the photo with /me/avatar-upload-url first")

    async def _accept_pending_requests(self, user_id: UUID) -> None:
        """A profile that becomes public accepts everyone who was waiting."""
        now = datetime.now(UTC)
        for follower_id in await self._uow.follows.accept_all_pending(user_id):
            await self._uow.activities.upsert(
                Activity(uuid4(), follower_id, ActivityType.STARTED_FOLLOWING, user_id, Visibility.PUBLIC, now)
            )

    async def _delete_avatar_quietly(self, user_id: UUID, url: str) -> None:
        prefix = self._storage.public_url(f"{user_id}/")
        if not url.startswith(prefix):
            return
        try:
            await self._storage.delete([f"{user_id}/{url[len(prefix) :]}"])
        except Exception:
            log.warning("Could not delete the old avatar of %s", user_id, exc_info=True)


class AccountService:
    def __init__(self, uow: UnitOfWork, storage: AvatarStorage, identity: IdentityAdmin) -> None:
        self._uow = uow
        self._storage = storage
        self._identity = identity

    async def delete_account(self, user_id: UUID) -> None:
        """Deletes everything: our data first, then photos and login, so a failed call can be retried."""
        await self._uow.profiles.delete(user_id)  # Every table cascades from profiles.
        await self._uow.commit()
        paths = await self._storage.list_paths(str(user_id))
        if paths:
            await self._storage.delete(paths)
        await self._identity.delete_user(user_id)
