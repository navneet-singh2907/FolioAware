"""System runtime values isolated behind small capabilities."""

from datetime import UTC, datetime
from uuid import uuid4


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UUID4Provider:
    def new(self) -> str:
        return str(uuid4())
