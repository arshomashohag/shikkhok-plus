"""The release gate's CVE check: Critical and High block unless excepted.

Usage::

    pip-audit -r requirements.txt --format json -o audit.json || true
    python3 deploy/cve_gate.py audit.json .security-exceptions.md

The report may be any of three shapes, recognised by their top-level
key [C-32]:

* ``dependencies`` -- pip-audit's ``--format json``, for the Python
  lockfile;
* ``results`` -- osv-scanner's ``--format json``, for the Gradle
  lockfiles the Android release ships;
* ``imageScanFindings`` -- ``aws ecr describe-image-scan-findings``,
  for the operating-system packages in the backend image.

This is the BLOCKING half of the two-speed model team.md affirms: every
push annotates dependency CVEs at every severity without blocking
(check.yml), and the production release blocks on each Critical or High
finding unless ``.security-exceptions.md`` carries a dated, unexpired
row for it [OPS-19]. An expired row fails the gate on its own, whether
or not the finding it covered is still present -- an exception nobody
renews is a decision nobody is still making.

**Severity is looked up, not assumed.** pip-audit reports advisory ids
and fix versions but no severity, so each id (and its aliases) is
resolved through the OSV API, preferring the GitHub advisory's
``database_specific.severity``. **A finding whose severity cannot be
established blocks** as if it were High: a lookup that fails open would
turn an OSV outage into a silent pass.

Where the scanner states a severity itself -- an osv-scanner advisory's
``database_specific.severity``, or ECR's ``severity`` -- that is used and
no lookup is made. ECR's ``UNDEFINED`` and ``INFORMATIONAL`` are the
vendor's own rating, not a failed lookup, so they do not block; they are
counted in the summary line.

Standard library only, so it runs on a bare runner.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass

BLOCKING = frozenset({"CRITICAL", "HIGH"})
UNKNOWN = "UNKNOWN"
#: ECR's own "no rating" values: a vendor verdict, not a failed lookup.
VENDOR_UNRATED = frozenset({"UNDEFINED", "INFORMATIONAL"})
OSV_URL = "https://api.osv.dev/v1/vulns/{}"

#: An exception in ``.security-exceptions.md`` is a level-3 heading
#: naming the advisory -- ``### GHSA-xxxx-xxxx-xxxx — <package> <version>``
#: -- followed by a bullet list including ``- **Expires**: YYYY-MM-DD``,
#: the format that file documents. HTML comments (the file's template)
#: are removed before parsing, so the template is never read as a row.
_HEADING = re.compile(r"^###\s+((?:PYSEC|GHSA|CVE|OSV)-[\w-]+)", re.MULTILINE)
_EXPIRES = re.compile(r"\*\*Expires\*\*:\s*(\S+)")


@dataclass(frozen=True)
class Finding:
    """One vulnerability pip-audit reported.

    :ivar package: The distribution name
    :ivar version: The installed version
    :ivar ids: The advisory id and its aliases
    :ivar severity: The severity the scanner itself reported, or None
        when it reported none and the gate must look it up
    """

    package: str
    version: str
    ids: frozenset[str]
    severity: str | None = None


@dataclass(frozen=True)
class Exception_:
    """One dated row of ``.security-exceptions.md``.

    :ivar advisory: The advisory id the row excepts
    :ivar expires: The last day it is valid
    """

    advisory: str
    expires: dt.date


def parse_audit(report: dict[str, object]) -> list[Finding]:
    """Extract findings from pip-audit's JSON report.

    :param report: The decoded ``--format json`` output
    :return: One finding per vulnerability
    """
    findings: list[Finding] = []
    dependencies = report.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise ValueError("pip-audit report has no dependency list")
    for dependency in dependencies:
        for vuln in dependency.get("vulns", []):
            ids = {vuln["id"], *vuln.get("aliases", [])}
            findings.append(
                Finding(dependency["name"], dependency["version"], frozenset(ids))
            )
    return findings


def parse_osv_scanner(report: dict[str, object]) -> list[Finding]:
    """Extract findings from osv-scanner's JSON report.

    :param report: The decoded ``--format json`` output
    :return: One finding per vulnerability per package
    :raises ValueError: The report has no result list
    """
    results = report.get("results")
    if not isinstance(results, list):
        raise ValueError("osv-scanner report has no result list")
    findings: list[Finding] = []
    for result in results:
        for entry in result.get("packages", []):
            package = entry.get("package", {})
            for vuln in entry.get("vulnerabilities", []):
                ids = {vuln["id"], *vuln.get("aliases", [])}
                stated = vuln.get("database_specific", {}).get("severity")
                findings.append(
                    Finding(
                        package.get("name", "?"),
                        package.get("version", "?"),
                        frozenset(ids),
                        str(stated).upper() if stated else None,
                    )
                )
    return findings


def parse_ecr_findings(report: dict[str, object]) -> list[Finding]:
    """Extract findings from ``aws ecr describe-image-scan-findings``.

    :param report: The decoded CLI output
    :return: One finding per reported vulnerability
    :raises ValueError: The scan did not complete, so there is nothing to
        decide on
    """
    status = report.get("imageScanStatus", {})
    if isinstance(status, dict) and status.get("status") not in (None, "COMPLETE"):
        raise ValueError(f"the image scan is {status.get('status')}, not COMPLETE")
    scan = report.get("imageScanFindings")
    if not isinstance(scan, dict):
        raise ValueError("ECR report has no imageScanFindings")
    findings: list[Finding] = []
    # **Enhanced scanning reports elsewhere in the same document.** A
    # registry switched to Inspector leaves `findings` empty and fills
    # `enhancedFindings`; reading only the first would pass every image.
    for item in scan.get("enhancedFindings", []):
        details = item.get("packageVulnerabilityDetails", {})
        packages = details.get("vulnerablePackages") or [{}]
        findings.append(
            Finding(
                packages[0].get("name", "?"),
                packages[0].get("version", "?"),
                frozenset({details.get("vulnerabilityId") or item.get("title", "?")}),
                str(item.get("severity", UNKNOWN)).upper(),
            )
        )
    for item in scan.get("findings", []):
        attributes = {a["key"]: a.get("value", "") for a in item.get("attributes", [])}
        findings.append(
            Finding(
                attributes.get("package_name", "?"),
                attributes.get("package_version", "?"),
                frozenset({item["name"]}),
                str(item.get("severity", UNKNOWN)).upper(),
            )
        )
    return findings


def parse_report(report: dict[str, object]) -> list[Finding]:
    """Extract findings from whichever scanner wrote the report.

    :param report: The decoded JSON report
    :return: The findings
    :raises ValueError: The shape is none the gate knows -- refused,
        because an unrecognised report read as empty would pass
    """
    if "dependencies" in report:
        return parse_audit(report)
    if "results" in report:
        return parse_osv_scanner(report)
    if "imageScanFindings" in report:
        return parse_ecr_findings(report)
    raise ValueError(f"unrecognised report; top-level keys {sorted(report)}")


def parse_exceptions(text: str) -> list[Exception_]:
    """Read the dated exceptions from the file.

    :param text: The file's contents
    :return: One entry per advisory heading
    :raises ValueError: When an entry has no valid Expires date -- an
        exception without an expiry is refused, not treated as permanent
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    headings = list(_HEADING.finditer(text))
    rows: list[Exception_] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        expires = _EXPIRES.search(text, heading.end(), end)
        advisory = heading.group(1)
        if expires is None:
            raise ValueError(f"exception {advisory} has no **Expires** date")
        try:
            rows.append(Exception_(advisory, dt.date.fromisoformat(expires.group(1))))
        except ValueError as exc:
            raise ValueError(
                f"exception {advisory}: expiry {expires.group(1)!r}"
            ) from exc
    return rows


def osv_severity(advisory: str) -> str:
    """Return an advisory's severity from OSV, or UNKNOWN.

    :param advisory: e.g. ``GHSA-xxxx-xxxx-xxxx`` or ``PYSEC-2024-1``
    :return: ``CRITICAL``, ``HIGH``, ``MODERATE``, ``LOW`` or UNKNOWN
    """
    try:
        with urllib.request.urlopen(  # noqa: S310 -- fixed https URL
            OSV_URL.format(advisory), timeout=15
        ) as response:
            record = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return UNKNOWN
    severity = record.get("database_specific", {}).get("severity")
    return str(severity).upper() if severity else UNKNOWN


def severity_of(finding: Finding, lookup: Callable[[str], str]) -> str:
    """Return the highest severity any of a finding's ids reports.

    :param finding: The finding
    :param lookup: Resolves one advisory id to a severity
    :return: A severity, UNKNOWN when no id resolves
    """
    if finding.severity is not None:
        return finding.severity
    order = ["LOW", "MODERATE", "MEDIUM", "HIGH", "CRITICAL"]
    known = [s for s in (lookup(i) for i in sorted(finding.ids)) if s in order]
    return max(known, key=order.index) if known else UNKNOWN


def decide(
    findings: Iterable[Finding],
    exceptions: Iterable[Exception_],
    today: dt.date,
    lookup: Callable[[str], str],
) -> list[str]:
    """Return every reason the release must not proceed.

    :param findings: What pip-audit reported
    :param exceptions: The dated rows
    :param today: The date the gate runs
    :param lookup: Resolves an advisory id to a severity
    :return: Empty when the release may proceed
    """
    exceptions = list(exceptions)
    problems = [
        f"exception for {row.advisory} expired on {row.expires.isoformat()}"
        for row in exceptions
        if row.expires < today
    ]
    valid = {row.advisory for row in exceptions if row.expires >= today}
    for finding in findings:
        severity = severity_of(finding, lookup)
        if severity not in BLOCKING and severity != UNKNOWN:
            continue
        if finding.ids & valid:
            continue
        problems.append(
            f"{finding.package} {finding.version}: {', '.join(sorted(finding.ids))}"
            f" is {severity} with no unexpired exception"
        )
    return problems


def main(argv: list[str]) -> int:
    """Run the gate.

    :param argv: ``[report.json, exceptions.md]``
    :return: The process exit code
    """
    report = json.loads(pathlib.Path(argv[0]).read_text())
    exceptions = parse_exceptions(pathlib.Path(argv[1]).read_text())
    findings = parse_report(report)
    problems = decide(
        findings, exceptions, dt.datetime.now(dt.UTC).date(), osv_severity
    )
    unrated = sum(1 for f in findings if f.severity in VENDOR_UNRATED)
    print(
        f"{len(findings)} finding(s), {len(exceptions)} exception row(s), "
        f"{unrated} rated UNDEFINED or INFORMATIONAL by the scanner."
    )
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        print(
            "Fix each finding, or add a dated entry to .security-exceptions.md "
            "(format documented in that file)."
        )
        return 1
    print("No Critical or High finding without an unexpired exception.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
