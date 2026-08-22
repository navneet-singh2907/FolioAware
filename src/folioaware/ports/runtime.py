"""Small runtime nondeterminism capabilities."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdentifierProvider(Protocol):
    def new(self) -> str: ...
