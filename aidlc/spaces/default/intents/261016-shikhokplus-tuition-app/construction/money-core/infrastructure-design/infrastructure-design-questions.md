# Infrastructure Design Questions — money-core (U1)

**Stage**: infrastructure-design (3.4)
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`
**Phase**: Construction
**Depth**: Comprehensive

> U1 provisions **nothing**: no compute, no database, no network, no DNS, no
> queue, no cache. The stage's per-kind applicability reflects that — a
> `library` Unit produces `cicd-pipeline.md` and `traceability.json` only, and
> no infrastructure specification or monitoring design. What B1 genuinely
> builds is **the pipeline every later Bolt inherits**, so that is what these
> questions are about.

---

## Q1 — Is this Unit's pipeline B1's pipeline, or the project's?

B1 is the first Bolt. Whatever it establishes becomes the default.

[Answer]: **The project's**, and that is the honest framing. `team.md`
sequences the toolchain explicitly: Ruff with its named rule sets, mypy on the
money module, pytest with testcontainers, secrets scanning as a pre-commit
hook *and* a CI job, and the dependency lockfiles all arrive at skeleton time
— which is B1. Later Bolts add their own jobs (the Android build at B4, the
database-backed integration suite at B3) but none re-establishes the
foundation.

So this document specifies the whole backend pipeline skeleton with B1's own
steps filled in, and marks the slots later Bolts extend. Writing it as "U1's
private pipeline" would describe something that does not exist and would make
B2 reinvent it.

---

## Q2 — One entrypoint or two, given `team.md` requires the same gate locally and in CI?

[Answer]: **One**, non-negotiably. A single `make check` target that runs the
identical sequence locally and in CI. `team.md` gives the reason in terms that
matter for a solo build: a gate reproducible only by pushing is a gate that
gets bypassed, and once bypassed it is decoration.

The practical consequence worth stating: **the blocking suite must run with no
secret**. That is already required — the SMS gateway is stubbed in tests — and
it means B1's pipeline has no credential dependency at all, so a fresh clone
can run the full gate immediately.

---

## Q3 — What is the CI minute budget, and does B1 fit it?

`team.md` requires the per-month minute budget to be stated and monitored, and
the backend path to stay under about ten minutes.

[Answer]: B1's full gate is **well under one minute of compute** — roughly 35
seconds by the step estimates in the security design, dominated by the
property test. It fits with enormous headroom, and that headroom is the point:
B1 sets the pattern, and the constraint binds later Bolts whose suites include
a real PostgreSQL container and an Android build.

The budget is stated here as a project figure rather than a U1 figure, since a
per-Unit minute budget would be meaningless. GitHub Actions' free tier for a
private repository is 2,000 minutes per month; the monitoring obligation is
that this figure is checked rather than assumed, and the Android job is split
from the backend job so a Kotlin build never gates a backend change.

---

## Q4 — Does B1 need a deployment pipeline at all?

[Answer]: **No, and saying so explicitly matters.** A library is not deployed.
It has no image, no artifact registry entry, no environment promotion and no
rollback unit — it ships inside whatever image contains it, first built at B3.

What B1 *does* establish for later deployment is narrower and worth naming:
the lockfiles that make a build reproducible, and the commit-SHA tagging
convention that makes a deployed artifact identifiable. Both are deployment
prerequisites created here; neither is a deployment.

---

## Q5 — Branch protection and the merge gate for a solo developer

`team.md`: trunk-based, squash-merge per Bolt, one reviewer who is also the
only author.

[Answer]: Branch protection **on**, requiring the CI check to pass, with no
required-approvals rule — a required approval from the sole author is
theatre, and `team.md` already records that pull requests here are a record
rather than a negotiation.

The rule that does carry weight is the **post-merge run on `main`**. With
squash-merge and one reviewer it is the only thing that catches a stale-base
merge: a PR green against an older `main` can break on merge, and nobody
notices if only PRs are checked.

---

## Q6 — Where does the secrets scan run, and does it block?

[Answer]: **Both pre-commit and CI, blocking absolutely in both, with no
severity threshold.** The duplication is deliberate rather than redundant: the
hook gives immediate feedback and can be bypassed with `--no-verify`, so the
CI job is what makes it a gate rather than a courtesy.

`team.md` separates this from dependency CVEs on purpose — secrets and
lockfile failures are binary, near-zero false positive and always actionable
by whoever just pushed, while CVEs need triage and so annotate per-push and
block at the release gate instead. B1 establishes both channels even though
its own dependency surface is nearly empty, because later Bolts inherit them.

---

## Q7 — Caching: worth it at this size?

[Answer]: **Yes for dependencies, no for anything else.** The dependency cache
keyed on the lockfile hash is the one that pays — it saves most of the install
time on every run and invalidates exactly when it should. Test-result caching
and incremental-lint caching are not worth their complexity at B1's scale and
introduce a class of bug (a stale cache masking a real failure) that is
precisely what this Unit's whole control set exists to avoid.

---

## Assumptions & Open Questions

**OQ-B1-1 remains open** and is unchanged by this stage: the Bangla money
rendering. It affects what the locale-completeness check asserts, not how the
pipeline runs.

**Carried from NFR Design (NFR9.32)**: the two schema assertions need adding
to B2's and B3's definitions of done. That is a cross-Bolt obligation this
stage records but cannot execute.

---

## Consolidated Summary Confirmation

B1's pipeline is the **project's** backend pipeline skeleton, not a private
one — `team.md` sequences the whole toolchain at skeleton time, so writing it
as U1-only would make B2 reinvent it. One `make check` entrypoint runs
identically locally and in CI, with no secret required, because a gate
reproducible only by pushing gets bypassed. B1's full gate runs in well under
a minute against a 2,000-minute monthly budget, with the Android job split off
so it never gates a backend change. **No deployment pipeline**: a library is
not deployed, though B1 does establish the lockfiles and commit-SHA tagging
that later deployment needs. Branch protection requires the CI check but no
approval, since a required approval from the sole author is theatre — and the
post-merge run on `main` is what actually catches a stale-base merge. Secrets
scanning blocks in both pre-commit and CI, the CI job being what makes it a
gate rather than a courtesy. Dependency caching only; no test-result caching,
because a stale cache masking a real failure is the exact defect class this
Unit exists to prevent.

Does this all look correct?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions
