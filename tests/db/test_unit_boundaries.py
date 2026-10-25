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

import ast
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

#: The two tables this Unit creates and must never write [BR6.1].
SHELL_TABLES = ("owner", "enrollment")

#: Write verbs in raw SQL. Tolerates a quoted or schema-qualified name,
#: both of which an earlier version of this pattern missed entirely.
WRITE_PATTERN = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
    r"(?:\w+\s*\.\s*)?[\"\']?(owner|enrollment)[\"\']?\b",
    re.IGNORECASE,
)

#: ORM writes, which the raw-SQL pattern cannot see at all.
#:
#: **This half was missing and the gap mattered**: the allowlisted module
#: writes through the ORM, so the only shape the ban actually needs to
#: police was the one shape it could not detect. An ORM write from an
#: unlisted module passed the whole check.
#:
#: Matched on the AST rather than by text, because ``session.add(...)``
#: and ``session.delete(...)`` carry a constructor or a variable and a
#: regex over either reads as a guess.
ORM_WRITE_METHODS = frozenset({"add", "add_all", "delete", "merge"})


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
        # The staging seeder. It writes `owner` because NO ENDPOINT
        # CREATES ONE -- that belongs to the subscription surface, which
        # no Unit has built -- and a teacher lens cannot resolve without
        # it, so a device check is impossible without this row.
        #
        # Deliberately NOT the script B5 deleted. That one wrote rows
        # the application also wrote, making it a second untested write
        # path whose output the 0002 fold guard then refused. This one
        # writes ONLY what the API cannot, and a test below pins that
        # distinction so the exemption cannot quietly widen.
        "app/db/seed_staging.py",
        # D1's two, named individually rather than as
        # `app/accounts/**` -- the package is new, and a prefix would
        # silently permit every file a later Unit drops into it.
        #
        # `app/api/accounts.py` is deliberately NOT here. The handlers
        # pass a lens into the two services below and write nothing
        # themselves, which was verified against this check rather than
        # assumed: listing a module that needs no exemption is how an
        # allowlist stops describing what it permits.
        #
        # `accounts/service.py` creates `owner` for a Teacher signup
        # [BR4.1], which is the second place an owner row can now come
        # from: the seeder writes it because no endpoint did, and this
        # is that endpoint. It also LINKS existing seats, and sets no
        # decision while doing so [BR5.1].
        #
        # `accounts/decisions.py` writes the two decision columns and
        # nothing else. It is the only module that may, which is the
        # point of listing it: a decision belongs to the link that
        # names its holder, so any other writer of those columns would
        # be speaking for somebody else.
        "app/accounts/service.py",
        "app/accounts/decisions.py",
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


def _shell_bound_names(tree: ast.Module) -> set[str]:
    """Collect local names assigned a shell model instance.

    ``session.add(record)`` carries a variable, not a constructor, so
    matching the argument name against the model names finds nothing.
    The binding has to be resolved first: ``record = Enrollment(...)``
    makes ``record`` a shell name for the rest of the module.

    Module-wide rather than per-scope, which over-approximates. That is
    the right direction for a ban: a false positive is a reviewable line,
    a false negative is a silent hole.

    :param tree: The parsed module
    :return: Every local name bound to a shell model instance
    """
    models = {"Owner", "Enrollment"}
    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)):
            continue
        if value.func.id not in models:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _orm_write_offenders(path: pathlib.Path) -> list[str]:
    """Find ORM writes of a shell model in one module.

    Walks the AST for ``<session>.add(...)`` and its siblings, resolving
    a variable argument back to its assignment. A text search cannot do
    this at all: the table name never appears, only the mapped class --
    and often not even that, only a local name.

    :param path: The module to inspect
    :return: One description per offending call
    """
    models = {"Owner", "Enrollment"}
    tree = ast.parse(path.read_text(), filename=str(path))
    bound = _shell_bound_names(tree)
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue

        attribute = node.func.attr
        if attribute not in ORM_WRITE_METHODS | {"insert", "update", "delete"}:
            continue

        for argument in node.args:
            named: str | None = None
            if isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name):
                named = argument.func.id
            elif isinstance(argument, ast.Name):
                named = argument.id
            if named in models or named in bound:
                found.append(f"{path.name}: {attribute}({named})")
    return found


def test_no_application_module_writes_a_shell_table() -> None:
    offenders: list[str] = []
    for path in _application_sources():
        for match in WRITE_PATTERN.finditer(path.read_text()):
            offenders.append(f"{path.name}: {match.group(0)}")
        offenders.extend(_orm_write_offenders(path))
    assert offenders == [], (
        "Only the allowlisted module writes owner and enrollment "
        f"[BR6.1]. Found: {offenders}"
    )


def test_the_ban_detects_an_orm_write_and_not_only_raw_sql() -> None:
    # GUARDS THE CHECK ITSELF. The allowlisted module writes through the
    # ORM, so the one shape this ban actually needs to police is the one
    # a raw-SQL pattern cannot see. Before this, an ORM write from an
    # unlisted module passed the whole check.
    # The ORM writer specifically. WRITE_PERMITTED is a frozenset with
    # no order, and the staging seeder writes raw SQL -- so picking an
    # arbitrary member made this guard pass or fail by iteration order.
    permitted = APP.parent / "app/batches/service.py"
    assert _orm_write_offenders(permitted) != [], (
        "the allowlisted module writes through the ORM, so if this finds "
        "nothing the AST walk is not working and the ban is vacuous"
    )


def test_the_raw_sql_pattern_tolerates_quoting_and_qualification() -> None:
    # Three spellings of the same write. An earlier pattern caught only
    # the first, so a quoted or schema-qualified name evaded it.
    for text in (
        "INSERT INTO enrollment (id) VALUES (1)",
        'INSERT INTO "enrollment" (id) VALUES (1)',
        "INSERT INTO public.enrollment (id) VALUES (1)",
        "DELETE FROM owner WHERE id = 1",
    ):
        assert WRITE_PATTERN.search(text), text


def test_the_seed_script_is_gone() -> None:
    # U4 makes it obsolete: the batch and enrollment routes create these
    # rows through the real API. Keeping it would leave a second, untested
    # write path into the tables whose shape this Unit just changed -- and
    # its rows are precisely what the 0002 migration's fold guard refuses.
    assert not (APP / "db" / "seed_skeleton.py").exists()

    # `seed_staging.py` is exempted by NAME, not by weakening the
    # match. Its docstring names the deleted script in order to explain
    # how it differs, and a substring check read that as a dangling
    # reference -- a false positive whose cheapest "fix" would have been
    # deleting the explanation. Exempting one file keeps the check
    # strict everywhere else.
    offenders = [
        path.name
        for path in APP.rglob("*.py")
        if "seed_skeleton" in path.read_text() and path.name != "seed_staging.py"
    ]
    assert offenders == [], f"dangling references to the seed script: {offenders}"


def test_the_write_allowlist_names_only_modules_that_exist() -> None:
    # A stale entry permits nothing and misleads the next reader into
    # thinking a module is exempt when it is not even there.
    missing = [name for name in WRITE_PERMITTED if not (APP.parent / name).exists()]
    assert missing == [], f"allowlisted modules that do not exist: {missing}"


def test_the_staging_seeder_writes_only_what_no_endpoint_can() -> None:
    # THE DISTINCTION THAT JUSTIFIES ITS EXEMPTION. B5 deleted a seed
    # script because it wrote rows the application also wrote, making it
    # a second untested write path. This one is permitted only while it
    # writes `account` and `owner` -- the two rows no endpoint creates,
    # because there is no public sign-up and no subscription surface.
    #
    # The moment it writes a `batch` or an `enrollment`, it has become
    # the thing B5 deleted and this test says so.
    source = (APP / "db" / "seed_staging.py").read_text()
    forbidden = ("INSERT INTO batch", "INSERT INTO enrollment")

    found = [phrase for phrase in forbidden if phrase in source]
    assert found == [], (
        f"the staging seeder writes {found}, which the API can create "
        "itself. A seeded batch proves the seeding works, not that the "
        "product does -- and it reintroduces the second write path B5 "
        "deleted."
    )


def test_the_write_allowlist_has_not_grown_vacuous() -> None:
    # Guards the check itself. If the allowlist ever grew to cover every
    # module, the ban above would pass vacuously while forbidding nothing.
    #
    # Four as of D1: the batch service, the staging seeder, and the two
    # modules that create an account and record a decision. Moving this
    # number is the reviewable act -- `app/` holds far more modules than
    # four, so the ban still forbids something.
    assert len(WRITE_PERMITTED) == 4, (
        f"WRITE_PERMITTED holds {len(WRITE_PERMITTED)} modules, not 4: "
        f"{sorted(WRITE_PERMITTED)}. Each writes `owner` or "
        "`enrollment`, and each needs a reason that is a property of "
        "the module rather than a convenience."
    )


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
