# NFR Requirements Questions — `batches-and-enrollment` (U4)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **Answered from the artifacts rather than asked**, per the standing
> instruction to decide and proceed. Each answer names what it was
> decided from, so a wrong one is correctable rather than mysterious.

## Sources

- [upstream] `functional-design/` — all three artifacts
- [upstream] `inception/requirements-analysis/requirements.md`
- [upstream] `construction/identity-and-access/nfr-requirements/`
- [team] `## Testing Posture`, `## Deployment`
- [project] `## Forbidden` / `## Mandated`

---

## Q1. Does the roster read need a latency target?

**No — a query-count assertion instead** [NFR6.11, NFR6.12].

U3 settled the principle: a count is stable across machines and a
duration is not, and a flaky performance assertion gets deleted the
third time CI fails on it, taking the real check with it. What U4 adds
is the **fixture size**: a query-count test written against a one-row
roster passes against an N+1 implementation.

## Q2. Is pagination required?

**No.** 100 teachers and a few thousand students [NFR6] puts the
largest plausible roster at tens of rows. Pagination now is a contract
that an unpaginated client would later have to be taught.

## Q3. What does a second worker change for enrollment?

**One partial unique constraint** [NFR10.8, NFR10.9]. The same teacher
double-submitting is the realistic case, and an application-level
check fails under concurrency — the lesson U3 learned with per-process
counters.

The constraint must be **partial**, excluding NULL student accounts:
several dormant seats in one batch are normal early in its life, and a
plain unique constraint would refuse the second.

## Q4. Does the migration need anything B3's did not?

**Yes, and this is the answer I am least comfortable leaving implicit**
[NFR6.16, NFR6.18]. B3 created tables from zero against an empty
database. U4 **renames columns on tables that may already hold rows**.

Two consequences: renames must preserve data rather than
drop-and-recreate, and a test must migrate **from the B3 head
revision** as well as from zero. CI migrates from zero every run, so a
rename that works on an empty table passes forever while the
production path is never exercised.

## Q5. Should enrollment changes be audited?

**No in V1, and the limitation is recorded** [NFR8.13]. Per-row access
logging is disproportionate at this budget. The question COPPA and
GDPR-K assume answerable is about *access to a child's data*, which
the auth log covers at the session boundary.

**But this answer should not be inherited.** A teacher editing a
display name leaves no record of who or when, which is acceptable
because the teacher authored that field. It would not be acceptable
for attendance or marks, and U5 and U6 should reach their own
conclusion.

## Q6. Does U4 need new alerting?

**No** [NFR8.11], stated as a requirement rather than an omission. No
U4 operation costs money, loses data irrecoverably, or indicates an
attack. U3's six alerts each earned their place; a seventh for
"enrollment failed" would dilute them, and the correct signal for a
broken write is the request's own error response.

## Q7. Is the money `TypeDecorator` a dependency or a deliverable?

**A deliverable of this Unit** [A.6, BR3.2]. A review found the rule
naming it as the enforcing mechanism while nothing implemented it —
`app/money/` has no SQLAlchemy type. B1 correctly never built one,
having no tables to map.

The honest split: the schema assertion is the enforcement that exists
and works regardless of how a column was created; the decorator
catches a `Float` reaching the ORM at author time. **Neither alone is
sufficient**, and a badly-named money column created by raw SQL is
caught by neither.

---

## Assumptions & Open Questions

**None.** [assumption] Every question above was answerable from the
functional design, the upstream requirements or an existing team
practice. None needed evidence nobody has yet, which is the test for
whether a question should be escalated rather than decided.
