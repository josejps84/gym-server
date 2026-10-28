from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthUser, InvalidToken
from app.container import Container
from app.domain.pagination import MAX_PAGE_SIZE, PAGE_SIZE, Cursor
from app.domain.profile import Profile
from app.repositories.unit_of_work import SqlUnitOfWork
from app.services.feed import FeedService
from app.services.ports import UnitOfWork
from app.services.profiles import AccountService, ProfileService
from app.services.routines import RoutineService
from app.services.social import FollowService, ModerationService
from app.services.sync import SyncService
from app.services.workouts import WorkoutService

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def current_user(
    container: ContainerDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    """Sync on purpose: FastAPI runs it in a thread, where fetching the keys can block."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token", {"WWW-Authenticate": "Bearer"})
    try:
        user = container.verifier.verify(credentials.credentials)
    except InvalidToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", {"WWW-Authenticate": "Bearer"}
        ) from None
    retry_after = container.rate_limiter.hit(str(user.id))
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests", {"Retry-After": str(int(retry_after) + 1)}
        )
    return user


UserDep = Annotated[AuthUser, Depends(current_user)]


async def get_uow(container: ContainerDep) -> AsyncIterator[UnitOfWork]:
    """One transaction per request; whatever a service didn't commit is rolled back."""
    async with container.sessions() as session:
        yield SqlUnitOfWork(session)


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


async def current_profile(user: UserDep, uow: UowDep, container: ContainerDep) -> Profile:
    return await ProfileService(uow, container.storage, container.photos).ensure(user)


ProfileDep = Annotated[Profile, Depends(current_profile)]


def page_params(
    cursor: Annotated[str | None, Query(description="nextCursor from the previous page")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = PAGE_SIZE,
) -> tuple[Cursor | None, int]:
    return (Cursor.decode(cursor) if cursor else None, limit)


PageDep = Annotated[tuple[Cursor | None, int], Depends(page_params)]


def profile_service(uow: UowDep, container: ContainerDep) -> ProfileService:
    return ProfileService(uow, container.storage, container.photos)


def account_service(uow: UowDep, container: ContainerDep) -> AccountService:
    return AccountService(uow, container.storage, container.identity)


def follow_service(uow: UowDep) -> FollowService:
    return FollowService(uow)


def moderation_service(uow: UowDep, container: ContainerDep) -> ModerationService:
    return ModerationService(uow, container.mailer, container.settings.reports_email)


def sync_service(uow: UowDep) -> SyncService:
    return SyncService(uow)


def routine_service(uow: UowDep) -> RoutineService:
    return RoutineService(uow)


def feed_service(uow: UowDep) -> FeedService:
    return FeedService(uow)


def workout_service(uow: UowDep) -> WorkoutService:
    return WorkoutService(uow)


ProfileServiceDep = Annotated[ProfileService, Depends(profile_service)]
AccountServiceDep = Annotated[AccountService, Depends(account_service)]
FollowServiceDep = Annotated[FollowService, Depends(follow_service)]
ModerationServiceDep = Annotated[ModerationService, Depends(moderation_service)]
SyncServiceDep = Annotated[SyncService, Depends(sync_service)]
RoutineServiceDep = Annotated[RoutineService, Depends(routine_service)]
FeedServiceDep = Annotated[FeedService, Depends(feed_service)]
WorkoutServiceDep = Annotated[WorkoutService, Depends(workout_service)]
