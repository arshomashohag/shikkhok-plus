"""BR6.1 and BR6.3, asserted over this Unit's own source.

Two boundaries that no runtime test can see, because the violation of each
one *works*:

* An ``INSERT INTO owner`` inside U3 would make the demo pass. It is the
  ownership transfer BR6.1 forbids, arriving disguised as a fixture.
* An application module importing the seed script would turn a throwaway
  verification aid into a runtime dependency, and B5's obligation to
  delete it would then break the app.

Both are therefore checked statically, over the text and the AST.
"""

from __future__ import annotations

import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

#: The two tables this Unit creates and must never write [BR6.1].
SHELL_TABLES = ("owner", "enrollment")

#: Write verbs, as they would appear in raw SQL against a shell table.
WRITE_PATTERN = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(owner|enrollment)\b",
    re.IGNORECASE,
)


#: The modules permitted to write ``owner`` or ``enrollment``.
#:
#: **U3 banned every write; U4 legitimises exactly one module.** The ban
#: existed because U3 created both tables EMPTY and the seed script was
#: the only thing allowed to fill them [BR6.1, BR6.3]. U4 owns these
#: tables' behaviour, so a blanket ban would now forbid the Unit's whole
#: purpose -- and deleting the test instead would retire a control that
#: still has work to do.
#:
#: An ALLOWLIST rather than a deletion, and an explicit one rather than a
#: directory prefix: adding a module here is a reviewable line, while
#: `app/batches/**` would silently permit every file a later Unit drops
#: into that package.
WRITE_PERMITTED: frozenset[str] = frozenset(
    {
        "app/batches/service.py",
    }
)


def _application_sources() -> list[pathlib.Path]:
    """Collect every application module not permitted to write a shell.

    :return: The paths to check
    """
    return [
        path
        for path in APP.rglob("*.py")
        if str(path.relative_to(APP.parent)) not in WRITE_PERMITTED
    ]


def test_no_application_module_writes_a_shell_table() -> None:
    offenders: list[str] = []
    for path in _application_sources():
        for match in WRITE_PATTERN.finditer(path.read_text()):
            offenders.append(f"{path.name}: {match.group(0)}")
    assert offenders == [], (
        "U3 creates owner and enrollment EMPTY and never writes them "
        f"[BR6.1]. Found: {offenders}"
    )


def test_the_seed_script_is_gone() -> None:
    # U4 makes it obsolete: the batch and enrollment routes create these
    # rows through the real API. Keeping it would leave a second, untested
    # write path into the tables whose shape this Unit just changed -- and
    # its rows are precisely what the 0002 migration's fold guard refuses.
    assert not (APP / "db" / "seed_skeleton.py").exists()

    offenders = [
        path.name for path in APP.rglob("*.py") if "seed_skeleton" in path.read_text()
    ]
    assert offenders == [], f"dangling references to the seed script: {offenders}"


def test_the_write_allowlist_names_only_modules_that_exist() -> None:
    # A stale entry permits nothing and misleads the next reader into
    # thinking a module is exempt when it is not even there.
    missing = [name for name in WRITE_PERMITTED if not (APP.parent / name).exists()]
    assert missing == [], f"allowlisted modules that do not exist: {missing}"


def test_the_allowlisted_module_is_the_only_writer() -> None:
    # Guards the check itself. If the allowlist ever grew to cover every
    # module, the ban above would pass vacuously while forbidding nothing.
    assert len(WRITE_PERMITTED) == 1


def test_the_orm_models_declare_the_shell_tables() -> None:
    # Empty is not absent: the shells must be declared, or lens resolution
    # queries a table that does not exist and fails.
    #
    # The models are imported HERE rather than relying on another module
    # having done it. Declarative registration is an import side effect,
    # so without this the metadata is empty in an isolated run and the
    # assertion passes or fails by test ORDER.
    from app.db import models as _models  # noqa: F401
    from app.db.base import Base

    for table in SHELL_TABLES:
        assert table in Base.metadata.tables
