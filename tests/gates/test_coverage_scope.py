"""The coverage floor must measure every package, not a stale list.

**This exists because the omission actually happened.** B2 wrote an
explicit ``--cov`` list; B3 added five packages and did not extend it.
The floor then passed at 95% while measuring **none** of the code B3 had
just written -- not by failing, but by quietly covering less.

That is the characteristic failure of an enumerated gate: a missing
entry is indistinguishable from a passing run. So the enumeration is
asserted against the packages on disk, and the next omission fails.

The explicit list is still worth keeping over ``--cov=app``: it makes
adding a package a reviewable decision, and it is what lets a package be
deliberately excluded with a reason. This test supplies the half that
enumeration lacks.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "app"
MAKEFILE = ROOT / "Makefile"

#: Packages deliberately outside the line-coverage floor, with the
#: reason each one is. A package may be absent from the ``--cov`` list
#: ONLY by appearing here.
DELIBERATELY_EXCLUDED: dict[str, str] = {
    "money": (
        "measured separately at 100% BRANCH coverage in the first "
        "pytest run; including it here would let the weaker 80% line "
        "floor stand in for the stronger target"
    ),
}


def _packages_on_disk() -> set[str]:
    """Find every importable unit under ``app/``: packages AND modules.

    **Both, because the first version of this gate checked only
    packages** -- it globbed ``*/__init__.py`` -- and so said nothing
    about a top-level module. ``app/config.py`` then arrived outside
    the floor and the gate passed, which is the exact failure this gate
    exists to prevent, reproduced inside the gate itself.

    :return: The importable names, without the ``app.`` prefix
    """
    packages = {path.parent.name for path in APP.glob("*/__init__.py")}
    modules = {path.stem for path in APP.glob("*.py") if path.stem != "__init__"}
    return packages | modules


def _packages_in_makefile() -> set[str]:
    """Read the LINE-FLOOR ``--cov`` list out of the Makefile.

    Scoped to the second pytest invocation specifically. The first one
    also carries a ``--cov=app.money``, for the 100% branch target, and
    reading both as one list would report the money module as inside
    the line floor when the whole point is that it is not.

    :return: The package names the 80% line floor measures
    """
    text = MAKEFILE.read_text()
    marker = "--cov-fail-under=80"
    assert marker in text, "the line floor's command changed shape"

    # Everything from the second invocation up to its fail-under flag.
    tail = text[: text.index(marker)]
    command = tail[tail.rindex("pytest tests") :]
    return set(re.findall(r"--cov=app\.(\w+)", command))


def test_every_package_is_measured_or_deliberately_excluded() -> None:
    measured = _packages_in_makefile()
    unmeasured = _packages_on_disk() - measured - set(DELIBERATELY_EXCLUDED)

    assert unmeasured == set(), (
        f"these packages are outside the coverage floor: "
        f"{sorted(unmeasured)}. Add each to the --cov list in the "
        "Makefile, or to DELIBERATELY_EXCLUDED with the reason. A "
        "missing entry does not fail the floor -- it silently narrows "
        "what the floor covers."
    )


def test_the_makefile_names_no_package_that_does_not_exist() -> None:
    # The other direction: a stale entry makes the list look more
    # thorough than it is, and `--cov` on a nonexistent package is
    # silently ignored.
    phantom = _packages_in_makefile() - _packages_on_disk()
    assert phantom == set(), f"--cov names nonexistent packages: {phantom}"


def test_the_money_module_is_not_in_the_line_floor() -> None:
    # It carries 100% BRANCH coverage in the first run. Measuring it
    # under the 80% line floor as well would let the weaker target
    # stand in for the stronger one.
    assert "money" not in _packages_in_makefile()


def test_every_exclusion_states_a_reason() -> None:
    assert all(len(reason.strip()) > 20 for reason in DELIBERATELY_EXCLUDED.values())
