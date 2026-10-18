# Scalability Requirements — `batches-and-enrollment` (U4)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `functional-design/functional-spec.md` — §2.1, §2.2
- [upstream] `functional-design/rules.md` — BR2.2, BR6.1
- [upstream] `inception/requirements-analysis/requirements.md` — NFR6, NFR7
- [team] `## Deployment`, `## Testing Posture`
- [project] `## Mandated`

---

## A. The ceiling, and what it makes affordable

**100 teachers and a few thousand students** [NFR6], on one Lightsail
instance under USD 50/month [NFR7]. That ceiling is what licenses most
of the simplifications below, so it is restated rather than assumed.

| ID | Requirement | Why |
|---|---|---|
| **NFR10.5** | Add-student resolves an existing account by `phone` under its unique index | The lookup runs on every enrollment and the column is already unique [U3] |
| **NFR10.6** | Creating a batch with subjects and slots is **one transaction** | A partial batch — subjects without slots — is a state no screen can render and no later Unit expects |
| **NFR10.7** | `Owner` is created lazily on first batch, not at sign-up | Most accounts are students and guardians who will never own one, so an eager row is a table of mostly-empty records |

---

## B. What a second worker changes, and what it does not

U3 learned this the hard way: a per-process counter passes every naive
test and stops working at two workers. The equivalent question here is
**concurrent enrollment of the same number into the same batch**.

| ID | Requirement | Why |
|---|---|---|
| **NFR10.8** | A unique constraint on `(batch_id, student_account_id)` where the account is non-null | Two teachers clicking add at once is rare; the same teacher double-submitting is not. An application-level check fails under concurrency, which is the lesson U7's idempotency rule already encodes |
| **NFR10.9** | The constraint is **partial**, excluding NULL student accounts | Several dormant seats in one batch are legitimate — a teacher records four numbers before anyone signs in — and a plain unique constraint would forbid the second |

> **NFR10.9 is the half an implementer drops.** A plain
> `UNIQUE (batch_id, student_account_id)` looks correct and refuses
> the second dormant enrollment in a batch, which is the normal state
> early in a batch's life.
>
> **Verified against real PostgreSQL**, all seven cases, rather than
> reasoned about:
>
> | Case | Result |
> |---|---|
> | Second and third dormant seat in one batch | admitted |
> | Same account twice in one batch | **refused** |
> | Same account in two batches of one teacher [AC2.2.3] | admitted |
> | Re-enrolling an **erased** account into the same batch | admitted |
>
> The last is the one worth stating. It is **correct**: the catalogue
> says a teacher may enroll that number again, creating a new
> enrollment with no link to the old. The constraint permits it
> because the erased row's account column is NULL, while the erased
> row itself stays blocked from *automatic* reattachment. A deliberate
> teacher action and a silent re-link are different things, and this
> shape distinguishes them without any extra code.

---

## C. What is deliberately not specified

| Not specified | Why |
|---|---|
| Horizontal scaling | One container on one instance; a second would consume the budget before compute [D-29] |
| Read replicas | A replica would be an authorization bug for the computed lens — stale ownership resolves stale permissions |
| Roster pagination | The largest plausible roster at this ceiling is tens of rows |
| A caching layer | Room is the cache, on the client, and a server-side cache of lens-scoped data is how cross-teacher leakage happens |

---

## Assumptions & Open Questions

**None.** [assumption] NFR10.8's constraint admits the same account in
two **different** batches of one teacher, which AC2.2.3 requires; the
uniqueness is per batch, not per teacher.
