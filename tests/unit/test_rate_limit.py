import pytest

from folioaware.security import FixedWindowRateLimiter, PublicRequestGuard


class FakeMonotonicClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_per_client_limit_returns_retry_after_and_resets() -> None:
    clock = FakeMonotonicClock()
    limiter = FixedWindowRateLimiter(
        per_client_limit=2,
        global_limit=10,
        window_seconds=60,
        max_clients=100,
        clock=clock,
    )

    assert limiter.admit("client-a").admitted
    assert limiter.admit("client-a").admitted
    rejected = limiter.admit("client-a")

    assert rejected.reason == "rate_limited"
    assert rejected.retry_after_seconds == 60
    assert limiter.admit("client-b").admitted

    clock.advance(59.1)
    assert limiter.admit("client-a").retry_after_seconds == 1
    clock.advance(0.9)
    assert limiter.admit("client-a").admitted


def test_global_limit_applies_across_client_keys() -> None:
    limiter = FixedWindowRateLimiter(
        per_client_limit=2,
        global_limit=3,
        window_seconds=60,
        max_clients=100,
    )

    assert limiter.admit("client-a").admitted
    assert limiter.admit("client-b").admitted
    assert limiter.admit("client-c").admitted
    assert limiter.admit("client-d").reason == "rate_limited"


def test_global_rejection_does_not_create_or_evict_client_buckets() -> None:
    limiter = FixedWindowRateLimiter(
        per_client_limit=1,
        global_limit=1,
        window_seconds=60,
        max_clients=2,
    )

    assert limiter.admit("client-a").admitted
    assert limiter.tracked_client_count == 1

    rejected = limiter.admit("client-b")

    assert rejected.reason == "rate_limited"
    assert limiter.tracked_client_count == 1


def test_client_state_is_bounded_with_least_recently_used_eviction() -> None:
    limiter = FixedWindowRateLimiter(
        per_client_limit=2,
        global_limit=10,
        window_seconds=60,
        max_clients=2,
    )

    limiter.admit("client-a")
    limiter.admit("client-b")
    limiter.admit("client-c")

    assert limiter.tracked_client_count == 2
    assert limiter.admit("client-a").admitted


def test_concurrency_capacity_releases_for_the_next_request() -> None:
    guard = PublicRequestGuard(
        per_client_limit=10,
        global_limit=20,
        window_seconds=60,
        max_clients=100,
        max_concurrent=1,
    )

    assert guard.admit("client-a").admitted
    rejected = guard.admit("client-b")

    assert rejected.reason == "capacity_exceeded"
    assert rejected.retry_after_seconds == 1
    guard.release()
    assert guard.admit("client-c").admitted
    guard.release()


@pytest.mark.parametrize(
    ("per_client", "global_limit", "window", "clients"),
    (
        (0, 10, 60, 100),
        (1, 0, 60, 100),
        (1, 10, 0, 100),
        (1, 10, 60, 0),
        (5, 4, 60, 100),
    ),
)
def test_invalid_limiter_configuration_is_rejected(
    per_client: int, global_limit: int, window: int, clients: int
) -> None:
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(
            per_client_limit=per_client,
            global_limit=global_limit,
            window_seconds=window,
            max_clients=clients,
        )


def test_invalid_concurrency_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="concurrent"):
        PublicRequestGuard(
            per_client_limit=1,
            global_limit=1,
            window_seconds=60,
            max_clients=100,
            max_concurrent=0,
        )
