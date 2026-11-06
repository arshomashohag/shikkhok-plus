"""A simulated clock for the services the seeder drives.

**Why a shim rather than a parameter.** Most services take ``today`` or
``now``, but several read the clock themselves -- ``create_batch``,
``record_mark``, ``approve_submission``, ``post_announcement`` -- and a
three-month history written at the real moment would put every
``created_at``, ``submitted_at`` and ``verified_at`` on one afternoon.
Changing those signatures to seed test data would widen production
code for a tool; patching the clock they read keeps the tool's reach
inside the tool.

**What is patched, exactly.** Every loaded ``app.*`` module reads the
clock as ``dt.datetime.now(tz=dt.UTC)`` through its own ``dt`` alias of
the standard ``datetime`` module (asserted by
``tests/seed/test_clock.py``). For the duration of
:func:`simulated_clock` each such alias is pointed at a copy of the
module whose ``datetime`` class answers ``now`` from the simulation.
Nothing outside ``app`` is touched -- not SQLAlchemy, not psycopg, not
the standard library, and not ``app.seed`` itself, which builds moments
rather than reading the clock -- and every alias is restored on exit,
including when the body raises.

``isinstance(value, dt.datetime)`` keeps working for values the
database returns, which are real ``datetime`` instances: the shim's
metaclass answers the check against the real class.
"""

from __future__ import annotations

import datetime as dt
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from typing import ClassVar

__all__ = ["SimulatedClock", "simulated_clock"]


class SimulatedClock:
    """The moment the simulation is at. Set it before each action.

    :ivar moment: The current simulated instant, timezone-aware
    """

    def __init__(self, moment: dt.datetime) -> None:
        """Start the clock at a moment.

        :param moment: A timezone-aware instant
        :raises ValueError: The moment is naive
        """
        self.moment = moment
        self.set(moment)  # validates

    def set(self, moment: dt.datetime) -> None:
        """Move the clock to a moment, which must not be naive.

        :param moment: A timezone-aware instant
        :return: None
        :raises ValueError: The moment is naive
        """
        if moment.tzinfo is None:
            raise ValueError("the simulated clock needs a timezone-aware moment")
        self.moment = moment


class _RealDatetimeCheck(type):
    """Answer ``isinstance`` against the real ``datetime`` class.

    Without this, a value loaded from the database -- a real
    ``datetime`` -- would fail ``isinstance(value, dt.datetime)`` inside
    a patched module, and code branching on that check would silently
    take the wrong branch.
    """

    def __instancecheck__(cls, instance: object) -> bool:
        """Delegate to the real class.

        :param instance: The value being checked
        :return: Whether it is a real ``datetime``
        """
        return isinstance(instance, _REAL_DATETIME)

    def __subclasscheck__(cls, subclass: type) -> bool:
        """Delegate to the real class.

        :param subclass: The class being checked
        :return: Whether it derives from the real ``datetime``
        """
        return issubclass(subclass, _REAL_DATETIME)


_REAL_DATETIME = dt.datetime


def _clock_datetime(clock: SimulatedClock) -> type[dt.datetime]:
    """Build a ``datetime`` subclass whose ``now`` reads ``clock``.

    :param clock: The simulation's clock
    :return: The class to install as ``datetime`` in the shim module
    """

    class ClockDatetime(dt.datetime, metaclass=_RealDatetimeCheck):
        """``datetime``, with ``now`` and ``utcnow`` from the simulation."""

        source: ClassVar[SimulatedClock] = clock

        # The override returns a REAL datetime, not this subclass, by
        # design: values the services store must be ordinary datetimes.
        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> dt.datetime:  # type: ignore[override]
            """Return the simulated moment, in ``tz`` or naive local.

            :param tz: The zone to express it in, or None
            :return: The simulated moment
            """
            if tz is None:
                return cls.source.moment.astimezone().replace(tzinfo=None)
            return cls.source.moment.astimezone(tz)

        @classmethod
        def utcnow(cls) -> dt.datetime:  # type: ignore[override]
            """Return the simulated moment as naive UTC.

            :return: The simulated moment
            """
            return cls.source.moment.astimezone(dt.UTC).replace(tzinfo=None)

    return ClockDatetime


@contextmanager
def simulated_clock(clock: SimulatedClock) -> Iterator[SimulatedClock]:
    """Point every loaded ``app`` module's ``dt`` alias at the clock.

    Import the services you drive BEFORE entering: a module first
    imported inside the block keeps the real clock. The seeder imports
    every service at module level, which is what makes that true.

    :param clock: The simulation's clock
    :return: A context manager yielding the same clock
    """
    shim = types.ModuleType("datetime")
    shim.__dict__.update(dt.__dict__)
    shim.datetime = _clock_datetime(clock)  # type: ignore[attr-defined]

    patched: list[types.ModuleType] = []
    for name, module in list(sys.modules.items()):
        if module is None or not (name == "app" or name.startswith("app.")):
            continue
        # The seeder's own modules build moments rather than read the
        # clock, and keeping them unpatched keeps that distinction.
        if name == "app.seed" or name.startswith("app.seed."):
            continue
        if getattr(module, "dt", None) is dt:
            module.dt = shim  # type: ignore[attr-defined]
            patched.append(module)
    try:
        yield clock
    finally:
        for module in patched:
            module.dt = dt  # type: ignore[attr-defined]
