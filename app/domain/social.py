from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.domain.profile import Profile
from app.domain.visibility import FollowStatus

REPORT_DETAILS_MAX = 1000


@dataclass(frozen=True, slots=True)
class Follow:
    follower_id: UUID
    followee_id: UUID
    status: FollowStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Connection:
    """A user in someone's followers / following / requests list, and since when."""

    profile: Profile
    since: datetime


@dataclass(frozen=True, slots=True)
class Relationship:
    """How the viewer relates to the owner of a profile."""

    is_owner: bool
    # The viewer's follow of the owner, if any.
    following: FollowStatus | None
    followed_by: bool

    @property
    def is_follower(self) -> bool:
        return self.following == FollowStatus.ACTIVE


class ReportReason(StrEnum):
    SPAM = "spam"
    HARASSMENT = "harassment"
    INAPPROPRIATE = "inappropriate"
    IMPERSONATION = "impersonation"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Report:
    id: UUID
    reporter_id: UUID
    target_user_id: UUID
    reason: ReportReason
    details: str
    created_at: datetime
