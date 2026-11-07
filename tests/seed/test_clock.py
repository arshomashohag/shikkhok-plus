"""The simulated clock reaches exactly the modules it claims to.

The seeder's whole history rests on one premise: that every ``app``
module reads the clock as ``dt.datetime.now`` through an alias of the
standard ``datetime`` module. A module that wrote ``from datetime import
datetime`` would read the real clock inside a simulated run, stamping a
three-month-old payment with this afternoon -- silently. So the premise
is asserted over the source rather than trusted.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

import app.local_time
from app.seed import clock as clock_module
from app.seed.clock import SimulatedClock, simulated_clock

APP = Path(__file__).resolve().parents[2] / "app"

MOMENT = dt.datetime(2026, 8, 3, 18, 30, tzinfo=dt.UTC)


def _offending_imports(path: Path) -> list[str]:
    """List the datetime imports in a file other than ``import datetime as dt``.

    :param path: A Python source file
    :return: One description per offending import
    """
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            found.append(f"{path}:{node.lineno} from datetime import ...")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "datetime" and alias.asname != "dt":
                    found.append(
                        f"{path}:{node.lineno} import datetime as {alias.asname}"
                    )
    return found


def test_every_app_module_reads_the_clock_through_a_dt_alias() -> None:
    offending = [
        line for path in sorted(APP.rglob("*.py")) for line in _offending_imports(path)
    ]
    assert offending == [], (
        "the seeder's simulated clock patches `dt` aliases only; these modules "
        "would read the real clock inside a seed run:\n" + "\n".join(offending)
    )


def test_inside_the_block_app_modules_read_the_simulated_moment() -> None:
    clock = SimulatedClock(MOMENT)
    with simulated_clock(clock):
        assert app.local_time.bangladesh_today() == dt.date(2026, 8, 4)
        clock.set(MOMENT + dt.timedelta(days=30))
        assert app.local_time.bangladesh_now() == (
            MOMENT + dt.timedelta(days=30)
        ).astimezone(app.local_time.DHAKA)


def test_outside_the_block_the_real_clock_is_back() -> None:
    with simulated_clock(SimulatedClock(MOMENT)):
        pass
    assert app.local_time.dt is dt
    assert app.local_time.bangladesh_now().year >= 2026
    assert abs(
        app.local_time.bangladesh_now() - dt.datetime.now(tz=dt.UTC)
    ) < dt.timedelta(minutes=1)


def test_the_real_clock_is_restored_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError), simulated_clock(SimulatedClock(MOMENT)):
        raise RuntimeError("boom")
    assert app.local_time.dt is dt


def test_a_real_datetime_still_passes_isinstance_inside_the_block() -> None:
    real = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    with simulated_clock(SimulatedClock(MOMENT)):
        assert isinstance(real, app.local_time.dt.datetime)
        assert issubclass(dt.datetime, app.local_time.dt.datetime)


def test_the_seeder_itself_and_the_standard_library_are_not_patched() -> None:
    with simulated_clock(SimulatedClock(MOMENT)):
        assert clock_module.dt is dt
        assert dt.datetime.now(tz=dt.UTC) > MOMENT + dt.timedelta(days=30)


def test_a_naive_moment_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SimulatedClock(dt.datetime(2026, 8, 3, 18, 30))  # noqa: DTZ001
