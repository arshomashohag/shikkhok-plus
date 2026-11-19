"""No server path links a join request to a seat [H5 Task 4].

A request is something a guardian typed; a seat is something an owner
recorded, through the roster, after the guardian has an invitation to
accept (Review Focus 5). The mechanical form of keeping the two apart is
that ``app/hub/enquiries/**`` imports nothing that writes or decides a
seat, a fee, a mark or a guardian link: not the student roster, not the
fee and marks modules, not the guardian views, and not the invitation and
decision modules that turn a seat into a lens.

Imports are judged as absolute names, so ``from app import students`` and
a relative import are seen for what they reach, and a literal dynamic
import counts like a static one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.gates.test_import_gates import ROOT, _hub_public_imports

ENQUIRIES: Final = ROOT / "app" / "hub" / "enquiries"

#: What a join-request module may never import, nor any submodule of it.
FORBIDDEN: Final[tuple[str, ...]] = (
    "app.students",
    "app.fees",
    "app.marks",
    "app.guardians",
    "app.authz.invitations",
    "app.accounts.decisions",
)


def _offenders(sources: list[Path], package: str = "app.hub.enquiries") -> list[str]:
    """List every forbidden import in these files.

    :param sources: The files to parse
    :param package: The package relative imports resolve against
    :return: One description per offending import
    """
    found: list[str] = []
    for source in sources:
        for name in sorted(_hub_public_imports(source, package)):
            if any(name == f or name.startswith(f"{f}.") for f in FORBIDDEN):
                found.append(f"{source.name} imports {name}")
    return found


def test_enquiries_package_imports_nothing_private() -> None:
    """The real package is clean, and the walk covers every module of it."""
    sources = sorted(ENQUIRIES.rglob("*.py"))
    names = {source.name for source in sources}
    assert {"owner.py", "sending.py", "forget.py", "target.py"} <= names, names
    assert _offenders(sources) == []


def test_enquiries_import_gate_fires(tmp_path: Path) -> None:
    """Each forbidden name, however it is spelled, is refused."""
    probe = tmp_path / "probe.py.txt"
    probe.write_text(
        "from app.students.service import create_student\n"
        "from app import fees\n"
        "import app.marks.service\n"
        "from app.guardians import views\n"
        "from app.authz import invitations\n"
        "from app.accounts.decisions import accept_seat\n"
        "from app.authz.lenses import TeacherLens\n"
        "from app.studentsish import nothing\n"
        "def later():\n"
        "    import importlib\n"
        "    importlib.import_module('app.fees.generation')\n",
        encoding="utf-8",
    )

    assert _offenders([probe]) == [
        "probe.py.txt imports app.accounts.decisions.accept_seat",
        "probe.py.txt imports app.authz.invitations",
        "probe.py.txt imports app.fees",
        "probe.py.txt imports app.fees.generation",
        "probe.py.txt imports app.guardians.views",
        "probe.py.txt imports app.marks.service",
        "probe.py.txt imports app.students.service.create_student",
    ]
