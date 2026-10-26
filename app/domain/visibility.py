from enum import StrEnum


class Visibility(StrEnum):
    PRIVATE = "private"
    FOLLOWERS = "followers"
    PUBLIC = "public"


class FollowStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"


def follow_status_for(target_is_private: bool) -> FollowStatus:
    """Private profiles approve each follower; public ones accept them right away."""
    return FollowStatus.PENDING if target_is_private else FollowStatus.ACTIVE


def visible_levels(*, is_owner: bool, owner_is_private: bool, is_follower: bool) -> frozenset[Visibility]:
    """Which item visibilities a viewer may see on someone's profile.

    A private profile shows nothing but to its accepted followers, whatever each item says.
    """
    if is_owner:
        return frozenset(Visibility)
    if is_follower:
        return frozenset({Visibility.FOLLOWERS, Visibility.PUBLIC})
    if owner_is_private:
        return frozenset()
    return frozenset({Visibility.PUBLIC})


def can_view(visibility: Visibility, *, is_owner: bool, owner_is_private: bool, is_follower: bool) -> bool:
    return visibility in visible_levels(is_owner=is_owner, owner_is_private=owner_is_private, is_follower=is_follower)


def can_view_connections(*, is_owner: bool) -> bool:
    """Only the owner sees who follows them and whom they follow; others see just the counts."""
    return is_owner
