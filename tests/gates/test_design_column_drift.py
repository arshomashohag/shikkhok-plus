"""A design document may not name a column its own entity lacks.

**This gate exists because the same defect recurred four times**, and a
reviewer caught it each time rather than a test. The shape was always
identical: a column was invented or renamed, the finding was fixed
where the reviewer pointed, and the identical reference two rules away
in the same file was left standing.

That is a search problem rather than carelessness. Reading a document
for one defect does not surface its siblings.

**The scope is deliberately narrow.** A first attempt matched every
``snake_case`` identifier in backticks and produced ~85 false
positives — YAML keys, function names, ledger quantities, test names —
and zero real findings. A gate that noisy is deleted on its first red
build, which leaves the project worse off than no gate.

So this checks one thing: when a design document writes
``Entity.column`` or ``entity.column`` for an entity **that document's
own Unit declares**, that column must exist in the declaration. That is
exactly the drift that recurred, and nothing else.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECORD = ROOT / "aidlc/spaces/default/intents/261016-shikhokplus-tuition-app"
CONSTRUCTION = RECORD / "construction"
CATALOGUE = RECORD / "inception/domain-design/components.md"

#: ``Entity.column`` inside backticks: the shape a design document uses
#: when it means "this column of that table".
QUALIFIED = re.compile(r"`([A-Z][A-Za-z]+)\.([a-z][a-z0-9_]*)`")

#: Attribute names that are methods or derived values rather than
#: columns, written in the same shape.
NOT_COLUMNS: frozenset[str] = frozenset(
    {
        "format",
        "allocate",
        "sum",
        "zero",
        "state",
        "path",
        "methods",
        "dependant",
    }
)


def _declared() -> dict[str, set[str]]:
    """Map every declared entity to its columns.

    Reads the upstream catalogue and every Unit's ``entities.md``, so a
    Unit legitimately adding a column declares it once and this follows.

    :return: Entity name to column names
    """
    out: dict[str, set[str]] = {}
    sources = [CATALOGUE, *CONSTRUCTION.rglob("functional-design/entities.md")]
    for path in sources:
        if not path.exists():
            continue
        text = path.read_text()
        for match in re.finditer(
            r"- name:\s*(\w+)\s*\n\s*identifier:[^\n]*\n\s*attributes:\s*\[([^\]]*)\]",
            text,
        ):
            name = match.group(1)
            cols = {a.strip() for a in match.group(2).split(",") if a.strip()}
            out.setdefault(name, set()).update(cols)
    return out


def test_no_design_document_names_a_column_its_entity_lacks() -> None:
    declared = _declared()
    assert declared, "no entity declarations found; the gate would pass vacuously"

    offenders: list[str] = []
    for path in sorted(CONSTRUCTION.rglob("functional-design/*.md")):
        if path.name not in {"rules.md", "functional-spec.md", "entities.md"}:
            continue
        for entity, column in QUALIFIED.findall(path.read_text()):
            if entity not in declared or column in NOT_COLUMNS:
                continue
            if column not in declared[entity]:
                offenders.append(f"{path.relative_to(RECORD)}: {entity}.{column}")

    assert offenders == [], (
        f"design documents name columns their entity does not declare: "
        f"{sorted(set(offenders))}. Declare it in the owning "
        "entities.md, or correct the reference. This gate exists "
        "because that drift recurred four times and a reviewer found "
        "it each time -- fixing the occurrence a review names does not "
        "surface its siblings."
    )
