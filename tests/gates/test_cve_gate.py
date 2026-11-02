"""The production release gate's CVE decision [OPS-19].

The affirmed model is two-speed: dependency CVEs annotate on every push
and BLOCK at the release gate, where each Critical and High is fixed or
carries a dated, unexpired entry in ``.security-exceptions.md``, and an
expired entry fails the gate. Until 2026-11-02 the release gate did not
read CVE results at all, so the blocking half did not exist.

The decision is pure, so it is tested here without the network: the
severity lookup is injected. Each case is the acceptance criterion
stated in the exceptions file, not a description of the code.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import sys
from collections.abc import Callable
from types import ModuleType

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TODAY = dt.date(2026, 11, 2)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "cve_gate", ROOT / "deploy" / "cve_gate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cve_gate"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()

REPORT = {
    "dependencies": [
        {"name": "fastapi", "version": "0.162.0", "vulns": []},
        {
            "name": "starlette",
            "version": "1.10.0",
            "vulns": [{"id": "PYSEC-2026-1", "aliases": ["GHSA-aaaa-bbbb-cccc"]}],
        },
    ]
}


def _entry(advisory: str, expires: str) -> str:
    return (
        f"### {advisory} — starlette 1.10.0\n\n"
        "- **Severity**: High\n"
        f"- **Expires**: {expires}\n"
        "- **Accepted by**: someone\n"
    )


def _severity(value: str) -> Callable[[str], str]:
    return lambda _advisory: value


def test_the_committed_file_parses_and_its_template_is_not_an_entry() -> None:
    text = (ROOT / ".security-exceptions.md").read_text()

    assert "GHSA-xxxx-xxxx-xxxx" in text, "the template moved; re-check this test"
    assert gate.parse_exceptions(text) == []


def test_a_high_finding_without_an_exception_blocks() -> None:
    findings = gate.parse_audit(REPORT)

    problems = gate.decide(findings, [], TODAY, _severity("HIGH"))

    assert len(problems) == 1
    assert "starlette" in problems[0]


def test_a_critical_finding_with_an_unexpired_exception_by_alias_passes() -> None:
    exceptions = gate.parse_exceptions(_entry("GHSA-aaaa-bbbb-cccc", "2026-11-30"))

    problems = gate.decide(
        gate.parse_audit(REPORT), exceptions, TODAY, _severity("CRITICAL")
    )

    assert problems == []


def test_an_exception_is_valid_through_its_expiry_day() -> None:
    exceptions = gate.parse_exceptions(_entry("PYSEC-2026-1", TODAY.isoformat()))

    assert (
        gate.decide(gate.parse_audit(REPORT), exceptions, TODAY, _severity("HIGH"))
        == []
    )


@pytest.mark.parametrize("severity", ["MODERATE", "LOW"])
def test_below_high_does_not_block(severity: str) -> None:
    assert gate.decide(gate.parse_audit(REPORT), [], TODAY, _severity(severity)) == []


def test_an_unknown_severity_blocks_as_high() -> None:
    # An OSV outage must not become a silent pass.
    problems = gate.decide(gate.parse_audit(REPORT), [], TODAY, _severity("UNKNOWN"))

    assert len(problems) == 1


def test_an_expired_exception_fails_the_gate_on_its_own() -> None:
    exceptions = gate.parse_exceptions(_entry("CVE-2025-0001", "2026-11-01"))

    problems = gate.decide([], exceptions, TODAY, _severity("LOW"))

    assert problems == ["exception for CVE-2025-0001 expired on 2026-11-01"]


def test_an_entry_without_an_expiry_is_refused() -> None:
    with pytest.raises(ValueError, match="Expires"):
        gate.parse_exceptions("### GHSA-aaaa-bbbb-cccc — x 1\n\n- **Severity**: High\n")


def test_the_highest_severity_among_aliases_wins() -> None:
    finding = gate.parse_audit(REPORT)[0]
    by_id = {"PYSEC-2026-1": "MODERATE", "GHSA-aaaa-bbbb-cccc": "CRITICAL"}

    assert gate.severity_of(finding, by_id.__getitem__) == "CRITICAL"
