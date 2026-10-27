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
        "measured at 100% BRANCH coverage by its own report; letting "
        "the weaker 80% line floor also cover it would let that floor "
        "stand in for the stronger target. It is MEASURED by the run "
        "and OMITTED from the line report, which is asserted below"
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


def _measured_packages() -> set[str]:
    """Read the ``--cov`` list out of the Makefile's single test run.

    **The suite runs ONCE and is reported twice**, so there is one
    ``--cov`` list covering both floors rather than one list per run.
    It therefore includes ``app.money``, which the line report then
    omits -- see :func:`test_the_money_module_is_omitted_from_the_line_floor`,
    which is now what keeps the weaker floor off the stronger target.

    :return: The package names the run measures
    """
    text = MAKEFILE.read_text()
    marker = "--cov-config=.coveragerc-backend"
    assert marker in text, "the test command changed shape"

    tail = text[: text.index(marker)]
    command = tail[tail.rindex("pytest tests") :]
    return set(re.findall(r"--cov=app\.(\w+)", command))


def _line_floor_omissions() -> str:
    """Read the ``--omit`` the 80% line report is scoped by.

    :return: The omit argument, verbatim
    """
    text = MAKEFILE.read_text()
    match = re.search(r"coverage report --omit='([^']+)'", text)
    assert match is not None, "the line floor's report changed shape"
    return match.group(1)


def test_every_package_is_measured_or_deliberately_excluded() -> None:
    measured = _measured_packages()
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
    phantom = _measured_packages() - _packages_on_disk()
    assert phantom == set(), f"--cov names nonexistent packages: {phantom}"


def test_the_money_module_is_omitted_from_the_line_floor() -> None:
    # **This assertion moved, and the move is the point.** The money
    # module used to be absent from the second run's --cov list; with
    # one run it must be PRESENT there, or it is not measured at all
    # and its own 100% report has no data to read.
    #
    # What keeps the weaker floor off the stronger target is now the
    # line report's --omit. Asserting the old thing against the new
    # command would have passed while checking nothing.
    assert "money" in _measured_packages(), "the run must measure it"
    assert "app/money/*" in _line_floor_omissions(), (
        "the 80% line report must omit app/money, or the weaker floor "
        "stands in for the 100% branch target"
    )


def test_both_floors_are_still_enforced() -> None:
    # A report without --fail-under prints a number and exits zero,
    # which looks identical to a passing gate. Both reports carry one.
    text = MAKEFILE.read_text()
    assert "--fail-under=100" in text, "the money floor stopped failing"
    assert "--fail-under=80" in text, "the line floor stopped failing"


def test_the_suite_runs_exactly_once() -> None:
    # The halving this target exists for. A second `pytest tests` in
    # this recipe would silently restore the duplicate run.
    recipe = MAKEFILE.read_text()
    start = recipe.index("\ntest:")
    end = recipe.index("\ngates:")
    assert recipe[start:end].count("pytest tests") == 1


def test_every_exclusion_states_a_reason() -> None:
    assert all(len(reason.strip()) > 20 for reason in DELIBERATELY_EXCLUDED.values())
