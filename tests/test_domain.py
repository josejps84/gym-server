from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.domain.errors import Invalid
from app.domain.pagination import Cursor, page_of
from app.domain.profile import (
    generated_username,
    normalize_bio,
    normalize_display_name,
    normalize_username,
    provider_photo_url,
)
from app.domain.sync import TutorialEntry, exercise_ids, merge_tutorials, remap_exercises, should_replace
from app.domain.visibility import FollowStatus, Visibility, can_view, follow_status_for, visible_levels
from app.rate_limit import RateLimiter


class TestUsername:
    def test_is_lowercased_and_trimmed(self) -> None:
        assert normalize_username("  Jose.Pi_84 ") == "jose.pi_84"

    @pytest.mark.parametrize("raw", ["ab", "x" * 31, "jose pi", ".jose", "jose.", "jo..se", "josé", "jose-pi"])
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(Invalid):
            normalize_username(raw)

    def test_generated_is_valid(self) -> None:
        assert normalize_username(generated_username()).startswith("user")


def test_display_name_collapses_spaces_and_bio_has_a_limit() -> None:
    assert normalize_display_name("  José   Piñeros ") == "José Piñeros"
    with pytest.raises(Invalid):
        normalize_bio("x" * 161)


class TestVisibility:
    def test_owner_sees_everything(self) -> None:
        assert visible_levels(is_owner=True, owner_is_private=True, is_follower=False) == set(Visibility)

    def test_stranger_sees_public_items_of_public_profiles_only(self) -> None:
        assert visible_levels(is_owner=False, owner_is_private=False, is_follower=False) == {Visibility.PUBLIC}
        assert visible_levels(is_owner=False, owner_is_private=True, is_follower=False) == set()

    def test_follower_sees_followers_and_public_items(self) -> None:
        for private in (True, False):
            levels = visible_levels(is_owner=False, owner_is_private=private, is_follower=True)
            assert levels == {Visibility.FOLLOWERS, Visibility.PUBLIC}

    def test_private_items_stay_private(self) -> None:
        assert not can_view(Visibility.PRIVATE, is_owner=False, owner_is_private=False, is_follower=True)

    def test_private_profiles_need_approval(self) -> None:
        assert follow_status_for(target_is_private=True) == FollowStatus.PENDING
        assert follow_status_for(target_is_private=False) == FollowStatus.ACTIVE


class TestCursor:
    def test_round_trip(self) -> None:
        cursor = Cursor(datetime(2026, 10, 25, 12, 30, 1, 123456, tzinfo=UTC), uuid4())
        assert Cursor.decode(cursor.encode()) == cursor

    @pytest.mark.parametrize("token", ["", "nope", "bm9wZQ"])
    def test_rejects_garbage(self, token: str) -> None:
        with pytest.raises(Invalid):
            Cursor.decode(token)

    def test_page_of_uses_the_extra_row_only_to_know_there_is_more(self) -> None:
        now = datetime.now(UTC)
        items = [(now - timedelta(minutes=i), uuid4()) for i in range(3)]
        page = page_of(items, 2, lambda item: Cursor(*item))
        assert page.items == items[:2]
        assert page.next_cursor == Cursor(*items[1]).encode()
        assert page_of(items, 3, lambda item: Cursor(*item)).next_cursor is None


class TestSync:
    def test_last_writer_wins_and_resending_is_a_no_op(self) -> None:
        t = datetime(2026, 10, 1, tzinfo=UTC)
        assert should_replace(None, t)
        assert should_replace(t, t + timedelta(seconds=1))
        assert not should_replace(t, t)
        assert not should_replace(t, t - timedelta(seconds=1))

    def test_exercise_ids_and_remap(self) -> None:
        exercises: list[dict[str, Any]] = [
            {"exerciseId": "a", "targetSets": 3},
            {"exerciseId": "b"},
            {"exerciseId": "a"},
        ]
        assert exercise_ids(exercises) == ["a", "b"]
        remapped = remap_exercises(exercises, {"a": "z"})
        assert [e["exerciseId"] for e in remapped] == ["z", "b", "z"]
        assert remapped[0]["targetSets"] == 3
        assert exercises[0]["exerciseId"] == "a"


def test_rate_limiter_counts_per_key_and_minute() -> None:
    now = [0.0]
    limiter = RateLimiter(2, clock=lambda: now[0])
    assert limiter.hit("a") is None
    assert limiter.hit("a") is None
    assert limiter.hit("a") == pytest.approx(60)
    assert limiter.hit("b") is None
    now[0] = 61
    assert limiter.hit("a") is None


def test_rate_limiter_off_with_zero() -> None:
    limiter = RateLimiter(0)
    assert all(limiter.hit("a") is None for _ in range(1000))


def test_provider_photo_url_only_trusts_google_and_asks_for_512_px() -> None:
    assert (
        provider_photo_url("https://lh3.googleusercontent.com/a/x=s96-c")
        == "https://lh3.googleusercontent.com/a/x=s512-c"
    )
    assert provider_photo_url("https://lh3.googleusercontent.com/a/x") == "https://lh3.googleusercontent.com/a/x"
    for raw in [
        None,
        "",
        "http://lh3.googleusercontent.com/a",
        "https://evil.example/a",
        "https://lh3.googleusercontent.com:8443/a",
    ]:
        assert provider_photo_url(raw) is None


def test_tutorials_merge_entry_by_entry_and_the_latest_change_wins() -> None:
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    later = t0 + timedelta(minutes=5)
    stored = {"logSets": TutorialEntry(True, t0), "rest": TutorialEntry(True, later)}
    incoming = {
        "logSets": TutorialEntry(False, later),  # replayed on another device
        "rest": TutorialEntry(False, t0),  # older than what is stored
        "history": TutorialEntry(True, t0),  # new
    }
    assert merge_tutorials(stored, incoming) == {
        "logSets": TutorialEntry(False, later),
        "rest": TutorialEntry(True, later),
        "history": TutorialEntry(True, t0),
    }
    # The same version again changes nothing.
    assert merge_tutorials(stored, stored) == stored
