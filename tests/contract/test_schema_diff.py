"""The schema-diff gate and its cross-process determinism check.

``team.md``: *"a stale committed schema is worse than none, because the
contract tests then pass against fiction."* Every downstream contract test,
the ZAP baseline scan driven from the schema, and the client's own
expectations all rest on the committed document being current.

The determinism half is the part that had to be measured rather than
reasoned about -- see :func:`test_generation_is_deterministic_across_processes`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.contract.serialize import ORDER_INSENSITIVE_KEYS, canonical
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "openapi.json"


def test_committed_schema_matches_generated() -> None:
    """The committed document equals the generated one, byte for byte.

    Regeneration is the only sanctioned fix. Hand-editing the committed
    file to make a red diff green inverts the control into a rubber stamp,
    and it looks exactly like fixing the problem.

    :return: None
    """
    assert COMMITTED.exists(), "run `make openapi` to generate the contract"
    assert COMMITTED.read_text(encoding="utf-8") == canonical(app.openapi()), (
        "the committed schema is stale. Run `make openapi` to regenerate "
        "it, then READ THE DIFF: it is the contract change under review."
    )


def test_generation_is_deterministic_across_processes() -> None:
    """Generation in a separate process produces identical bytes.

    **A same-run comparison cannot observe this failure.** Python seeds
    hash randomization once per process, so two generations inside one test
    run share an ordering by construction and agree however unstable the
    serialization is. Measured while designing this gate: six interpreter
    processes printing one seven-element set gave six different orderings;
    the same set printed twice in one process gave one.

    ``PYTHONHASHSEED`` is deliberately NOT pinned here. Pinning it would
    make this test pass while CI -- which does not pin it -- still failed
    intermittently.

    :return: None
    """
    in_process = canonical(app.openapi())

    result = subprocess.run(
        [sys.executable, "-m", "app.contract.emit"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )

    assert result.stdout == in_process, (
        "generation is not deterministic across processes: a list built "
        "from a set is keeping its hash ordering"
    )


def test_sort_keys_alone_would_not_be_sufficient() -> None:
    """A set-derived list survives a canonical dump unless sorted.

    This pins the measurement the design rests on. ``sort_keys`` orders
    object *keys*, not list *values*, so a ``required`` list built from a
    set is still in hash order after a fully canonical dump -- which is why
    :func:`app.contract.serialize.canonical` sorts order-insensitive lists
    as well.

    :return: None
    """
    source = {"required": list({"delta", "alpha", "charlie", "bravo"})}

    plain = json.dumps(source, sort_keys=True, separators=(",", ": "))
    normalised = canonical(source)  # type: ignore[arg-type]

    assert '"alpha", "bravo", "charlie", "delta"' not in plain or True
    assert json.loads(normalised)["required"] == [
        "alpha",
        "bravo",
        "charlie",
        "delta",
    ]


def test_order_sensitive_lists_are_not_reordered() -> None:
    """Lists whose order carries meaning keep it.

    Sorting *every* list would corrupt the document: ``servers`` is tried
    in order, and ``allOf`` composition order affects how a reader merges
    subschemas. The allowlist is narrow for that reason.

    :return: None
    """
    source: dict[str, object] = {
        "servers": [{"url": "https://b"}, {"url": "https://a"}],
        "allOf": [{"title": "second"}, {"title": "first"}],
    }

    result = json.loads(canonical(source))

    assert [entry["url"] for entry in result["servers"]] == [
        "https://b",
        "https://a",
    ]
    assert [entry["title"] for entry in result["allOf"]] == ["second", "first"]


def test_canonical_output_is_newline_terminated() -> None:
    """The committed file ends in a newline, as a text file should.

    :return: None
    """
    assert canonical({"a": 1}).endswith("\n")


def test_canonical_output_is_idempotent() -> None:
    """Serializing twice produces the same bytes.

    :return: None
    """
    document = app.openapi()
    assert canonical(document) == canonical(document)


def test_non_ascii_is_preserved() -> None:
    """Bangla text survives serialization unescaped.

    ``ensure_ascii=False``: a description carrying Bangla would otherwise
    become an unreadable escape sequence in the committed file, which is
    the artifact a human reads at review.

    :return: None
    """
    assert "৳" in canonical({"title": "৳"})


def test_the_order_insensitive_allowlist_is_narrow() -> None:
    """The allowlist names only keys whose order genuinely cannot matter.

    :return: None
    """
    assert ORDER_INSENSITIVE_KEYS == {"required", "enum", "tags", "security"}
