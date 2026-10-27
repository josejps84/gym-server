from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.activities import SqlActivityRepository, SqlReactionRepository
from app.repositories.social import (
    SqlBlockRepository,
    SqlFollowRepository,
    SqlProfileRepository,
    SqlReportRepository,
)
from app.repositories.sync import (
    SqlExerciseRepository,
    SqlFeaturedRoutineRepository,
    SqlRoutineRepository,
    SqlSessionRepository,
    SqlTutorialRepository,
)
from app.services.ports import (
    ActivityRepository,
    BlockRepository,
    ExerciseRepository,
    FeaturedRoutineRepository,
    FollowRepository,
    ProfileRepository,
    ReactionRepository,
    ReportRepository,
    RoutineRepository,
    SessionRepository,
    TutorialRepository,
)


class SqlUnitOfWork:
    """All repositories of one request share its transaction; nothing is saved until commit()."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.profiles: ProfileRepository = SqlProfileRepository(session)
        self.follows: FollowRepository = SqlFollowRepository(session)
        self.blocks: BlockRepository = SqlBlockRepository(session)
        self.reports: ReportRepository = SqlReportRepository(session)
        self.routines: RoutineRepository = SqlRoutineRepository(session)
        self.sessions: SessionRepository = SqlSessionRepository(session)
        self.exercises: ExerciseRepository = SqlExerciseRepository(session)
        self.featured: FeaturedRoutineRepository = SqlFeaturedRoutineRepository(session)
        self.activities: ActivityRepository = SqlActivityRepository(session)
        self.reactions: ReactionRepository = SqlReactionRepository(session)
        self.tutorials: TutorialRepository = SqlTutorialRepository(session)

    async def commit(self) -> None:
        await self._session.commit()
