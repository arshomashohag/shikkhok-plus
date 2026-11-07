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


# ---------------------------------------------------------------------------
# The other two report shapes [C-32]: osv-scanner for the Gradle
# lockfiles, ECR's scan for the image's operating-system packages.
# ---------------------------------------------------------------------------

OSV_REPORT = {
    "results": [
        {
            "source": {"path": "android/gradle.lockfile", "type": "lockfile"},
            "packages": [
                {
                    "package": {"name": "com.squareup.okio:okio", "version": "3.0.0"},
                    "vulnerabilities": [
                        {
                            "id": "GHSA-dddd-eeee-ffff",
                            "aliases": ["CVE-2026-0001"],
                            "database_specific": {"severity": "HIGH"},
                        }
                    ],
                },
                {
                    "package": {"name": "androidx.core:core", "version": "1.0.0"},
                    "vulnerabilities": [
                        {
                            "id": "GHSA-gggg-hhhh-iiii",
                            "database_specific": {"severity": "LOW"},
                        }
                    ],
                },
            ],
        }
    ]
}

ECR_REPORT = {
    "imageScanStatus": {"status": "COMPLETE"},
    "imageScanFindings": {
        "findings": [
            {
                "name": "CVE-2026-1111",
                "severity": "CRITICAL",
                "attributes": [
                    {"key": "package_name", "value": "openssl"},
                    {"key": "package_version", "value": "3.0.15-1"},
                ],
            },
            {"name": "CVE-2026-2222", "severity": "UNDEFINED", "attributes": []},
        ]
    },
}


def _no_lookup(advisory: str) -> str:
    raise AssertionError(f"looked up {advisory} although the scanner rated it")


def test_osv_scanner_findings_use_the_stated_severity() -> None:
    findings = gate.parse_report(OSV_REPORT)
    problems = gate.decide(findings, [], TODAY, _no_lookup)

    assert len(findings) == 2
    assert len(problems) == 1
    assert "okio" in problems[0]
    assert "HIGH" in problems[0]


def test_an_osv_scanner_finding_is_excepted_by_its_alias() -> None:
    exceptions = gate.parse_exceptions(_entry("CVE-2026-0001", "2026-12-01"))

    findings = gate.parse_report(OSV_REPORT)

    assert gate.decide(findings, exceptions, TODAY, _no_lookup) == []


def test_ecr_findings_block_on_critical_and_not_on_undefined() -> None:
    findings = gate.parse_report(ECR_REPORT)
    problems = gate.decide(findings, [], TODAY, _no_lookup)

    assert len(problems) == 1
    assert "openssl" in problems[0]
    assert "CRITICAL" in problems[0]


def test_enhanced_scanning_findings_are_read_too() -> None:
    # A registry on Inspector leaves `findings` empty; reading only that
    # list would pass every image.
    report = {
        "imageScanStatus": {"status": "COMPLETE"},
        "imageScanFindings": {
            "enhancedFindings": [
                {
                    "severity": "HIGH",
                    "packageVulnerabilityDetails": {
                        "vulnerabilityId": "CVE-2026-3333",
                        "vulnerablePackages": [{"name": "zlib", "version": "1.2"}],
                    },
                }
            ]
        },
    }

    problems = gate.decide(gate.parse_report(report), [], TODAY, _no_lookup)

    assert len(problems) == 1
    assert "zlib" in problems[0]


def test_an_incomplete_ecr_scan_is_refused_rather_than_read_as_clean() -> None:
    report = {**ECR_REPORT, "imageScanStatus": {"status": "IN_PROGRESS"}}

    with pytest.raises(ValueError, match="IN_PROGRESS"):
        gate.parse_report(report)


def test_an_unrecognised_report_is_refused_rather_than_read_as_empty() -> None:
    with pytest.raises(ValueError, match="unrecognised"):
        gate.parse_report({"vulnerabilities": []})
