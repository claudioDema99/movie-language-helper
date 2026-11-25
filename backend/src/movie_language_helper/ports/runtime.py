"""Deterministic time and opaque-ID ports."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Supply aware UTC time."""

    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    """Supply opaque, non-sequential capability identifiers."""

    def new(self) -> str: ...
