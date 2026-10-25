from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.domain.visibility import Visibility


class ActivityType(StrEnum):
    WORKOUT_COMPLETED = "workout_completed"
    ROUTINE_SHARED = "routine_shared"
    STARTED_FOLLOWING = "started_following"


@dataclass(frozen=True, slots=True)
class Activity:
    id: UUID
    user_id: UUID
    type: ActivityType
    # Session id, routine id or followed user id, depending on the type.
    ref_id: UUID
    visibility: Visibility
    created_at: datetime
