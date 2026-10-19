# Domain Design — Questions

**Stage**: domain-design (2.6)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — ~90 FR, ~19 NFR
- [upstream] `inception/user-stories/stories.md` — 45 stories
- [upstream] `inception/refined-mockups/` — the design system and 21 screens
- [architecture] `ideation/feasibility/architecture-proposal.md` §8a-f
- [team], [project] the affirmed practices and 32 permanent rules

---

## How this stage was answered

The user delegated the remaining Inception decisions ("decide the best possible
options... so that I do not need to check"), so the six questions this stage
owned went to a dispatched architect with the full upstream context, and its
decisions were applied. Each is recorded as an ADR in `decisions.md` with its
reasoning, consequences and rejected alternatives.

The six were not component-boundary questions in the usual sense — all six are
structural decisions deferred by earlier stages, and the component catalogue was
drawn around what they imply rather than the reverse.

## Q1. The teacher-vs-teacher privacy boundary

[Answer]: A teacher's lens is scoped to the batches their Owner owns, enforced
as one invariant: every teacher-lens query is rooted at `owner_id`, and no
teacher-facing response schema carries an account id. FR2.19 is the general
rule, not a special case. See ADR-001.

## Q2. The FeeCycle redesign

[Answer]: Append-only ledger entries with a derived balance, plus a thin
`FeeCycle` row carrying only the idempotency constraint and the period identity.
Six entry kinds, amounts always non-negative with the sign in the kind, credit
held at the enrollment rather than the cycle. The team's recorded Hypothesis
invariant is incomplete and is corrected in the ADR. See ADR-002.

## Q3. Deletion dispositions per table

[Answer]: A teacher's deletion removes their identity and ends their sign-in; it
deletes no student record. The Owner moves to a terminal `deleted` state making
batches permanently read-only. Full disposition table per entity, with
`PaymentClaim` anonymized rather than deleted and `Enrollment.guardian_phone`
retained as teacher-authored. See ADR-003.

## Q4. Academic-record retention

[Answer]: Per data class — auth ephemera 7 days, refresh tokens 30 days past
expiry, auth audit 13 months, academic records 3 years, financial records 6
years, dormant enrollments with no activity 18 months. See ADR-004.

## Q5. Subscription absorb mechanism

[Answer]: Three accommodations, none of them subscription logic: the Owner
carries the anchor columns, the teacher lens carries one entitlement value
always full in V1, and the client renders an unknown error code as a generic
localized message. See ADR-005.

## Q6. Concurrent edits

[Answer]: Split the rule. Interactive writes keep last-write-wins per field.
Queued writes use optimistic concurrency and are **refused and reported** on
conflict, never merged and never silently applied. Requires FR11.4 amended and
NFR5.1 extended with a fourth queue state. See ADR-006.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Ten components: Identity, Ownership, Enrollment, Teaching, Money, Fees,
  Payments, Notifications, Authorization, Governance. Twenty-four entities, each
  owned by exactly one component. The dependency graph is acyclic and its edges
  are symmetric.
- Three components own no entity — Money (a type with enforced boundaries),
  Authorization (the rule every other component is scoped by) and Governance
  (the manifests that keep the privacy policy from drifting from the code).
- The teacher-vs-teacher boundary is a keying rule rather than a filter: teacher
  reads are keyed on enrollment, never on an account.
- The fee ledger is append-only with every quantity derived, so a seventh
  quantity would be a new kind value rather than a migration.
- A teacher deleting their account cannot delete their students' records.
- Retention is three years for academic records and six for financial.
- Queued writes refuse on conflict rather than overwriting silently.
- Two decomposition choices were made with alternatives recorded: Fees and
  Payments stay separate because the writer difference is the privacy boundary,
  and Teaching stays as one component because splitting would duplicate the
  concurrency rule.

[Answer]: Looks correct
