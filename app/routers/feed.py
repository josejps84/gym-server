from fastapi import APIRouter

from app.dependencies import FeedServiceDep, PageDep, ProfileDep
from app.domain.pagination import Page
from app.routers.schemas import ActivityOut, Paged, ProfileCard, SharedRoutineOut, WorkoutOut
from app.services.feed import ActivityView

router = APIRouter(tags=["feed"])


def activity_out(view: ActivityView) -> ActivityOut:
    out = ActivityOut(
        id=view.activity.id,
        type=view.activity.type,
        created_at=view.activity.created_at,
        actor=ProfileCard.of(view.actor),
    )
    if view.session:
        out.workout = WorkoutOut(
            session_id=view.session.id,
            name=view.session.name,
            routine_id=view.session.routine_id,
            started_at=view.session.started_at,
            ended_at=view.session.ended_at,
            summary=view.session.summary,
        )
    if view.routine:
        out.routine = SharedRoutineOut(
            id=view.routine.id, name=view.routine.name, exercise_count=len(view.routine.exercises)
        )
    if view.user:
        out.user = ProfileCard.of(view.user)
    return out


def activity_page(page: Page[ActivityView]) -> Paged[ActivityOut]:
    return Paged(items=[activity_out(v) for v in page.items], next_cursor=page.next_cursor)


@router.get("/feed")
async def feed(profile: ProfileDep, page: PageDep, service: FeedServiceDep) -> Paged[ActivityOut]:
    """Activity of the people I follow, newest first, 20 per page."""
    return activity_page(await service.feed(profile.id, *page))
