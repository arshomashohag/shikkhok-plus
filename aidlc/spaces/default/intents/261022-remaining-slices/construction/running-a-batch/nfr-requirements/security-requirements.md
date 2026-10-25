# Security Requirements — D2 `running-a-batch`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **D2 opens no new surface.** Every route it uses requires a session and
> resolves a lens, and the abuse controls that matter are D1's and untouched.
> The contrast with D1 is the point: that unit opened an unauthenticated write
> path; this one puts screens over authenticated endpoints.
>
> What D2 does add is **two fields on a teacher-lens response and six screens
> a person navigates between**, so its security requirements are about
> disclosure and navigation rather than about controls.

> **`NFRx.y` IDs are GLOBAL across units.** D2's start above the high-water
> mark each base had reached after D1: **NFR14 from .26, NFR23 from .4**, and
> in the other two files NFR20 from .7, NFR2 from .3, NFR3 from .3.
>
> D2 defines **no NFR12.x**: the abuse-control axis is D1's and is untouched
> here, because D2 adds no unauthenticated route. A draft of this line listed
> a starting point for NFR12 anyway, which would have reserved a number
> against nothing.

## Sources

- [upstream] `construction/running-a-batch/functional-design/rules.md` —
  BR1.5, BR2.1–BR2.4, BR3.1, BR3.2, BR4.1, BR4.2
- [upstream] `construction/running-a-batch/functional-design/functional-spec.md`
- [upstream] `inception/requirements-analysis/requirements.md` — FR1.9b,
  FR1.9h, FR1.9i
- [prior] NFR11, NFR12, NFR14 of `261016-shikhokplus-tuition-app`; D1's
  NFR12.x and NFR14.x
- [code] `app/api/batches.py`, `app/contract/privacy.py`,
  `app/batches/service.py`, read 2026-10-23

---

## Disclosure

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.26 | The two new roster fields carry **decisions, not personal data** | `student_state` and `guardian_state` are enums; neither is a name, a number or an address | [BR2.1] |
| NFR14.27 | No teacher-lens response carries any `Profile` field, the new fields included | The existing schema-wide invariant covers it without a new per-endpoint test | [D1 BR3.2] |
| NFR14.28 | A **declined** row renders the bare number, never the teacher-typed name | The name is retained under the governance basis and is not displayed | [BR2.3] [ADR-012] |
| NFR14.29 | A guardian reaches children **only** through their own guardian link | Never by finding the child and then that child's enrollments | [BR4.1] [NFR14.15] |

**NFR14.28 is the one that needs saying.** The retention decision and the
display decision are different, and the governance manifest records only the
first: `enrollment`'s basis text says the display name is kept **even on a
declined seat**, because it is the teacher's own record of who they meant to
add. Keeping it and showing it are not the same, and a roster that shows it
discloses a name for a person who has said the seat is not theirs.

**NFR14.29 is unchanged and restated because D2 is where it is rendered.**
The alternative — find this guardian's children, then show every enrollment of
those children — merges two teachers' records: a guardian recorded by teacher
A would see teacher B's batch for the same child. The query is already correct;
D2 must not add a convenience path around it.

---

## Navigation as a privacy boundary

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.30 | Switching children **replaces** the view; Back does not reach the previous child | A switch is a selection, not a navigation push | [BR4.2] [AC9.4.2] |

**This is the only place in the product where two scopes of one lens are
adjacent.** A guardian with two children holds one `GuardianLens`; the child
is a path parameter on each request. Back landing on the previous child's
screen would show one child's records in a session scoped to the other — a
privacy failure wearing navigation's clothes, and invisible to every
server-side control because both requests were legitimately authorized.

---

## Authorization, rendered not re-decided

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.31 | Removability is read from the server's decision, never derived client-side | The row carries the decision; the client never computes it from the link states it displays | [BR3.1] |

**Why a client derivation would be wrong rather than merely redundant.**
`remove_enrollment` refuses on **two independent conditions**: no link
accepted, and no erasure marker set. The roster row carries the first and not
the second. A client deriving removability from the two link states would
offer removal for an erased seat — the same silent-regression shape D1's sweep
was written to stop, arriving by a different route.

---

## What D2 does not change

| Control | State |
|---|---|
| Signup and OTP ceilings | D1's, untouched |
| Byte-identical OTP responses | D1's, untouched |
| Row-level security on `profile` | Unchanged |
| The owner-private field set | Unchanged; D2 adds no `Profile` column |
| The audit vocabulary | Unchanged; D2 adds no auth event |
| Unauthenticated surface | **None added** |

---

## Verification

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR23.4 | The count is tested from the criterion **before** the endpoint is written | A wrong count misreports who has agreed, which is the one D2 decision whose wrong answer is not merely cosmetic | [team: Testing Posture] |
| NFR23.5 | The two removal refusals are tested as **distinct outcomes**, not as one failure | Claimed and erased carry different remedies | [BR3.2] |
| NFR23.6 | The Back-after-switch obligation carries a test rather than a review note | [NFR14.30] is unobservable server-side, so a test is the only mechanism | [BR4.2] |

**NFR23.4 is the one exception to D2's test-after cadence.** The affirmed
predicate is test-first when the correct output is knowable from the
requirement **and** a wrong answer is a money or authorization error. The
count is neither, strictly — but it is the number a teacher reads to decide
whether to chase people, and it is the habit D3's fee status and D5's dues
list will copy. Writing it from the criterion first costs nothing and settles
the pattern.

---

## Assumptions & Open Questions

- **Assumed**: the new enums serialize as lowercase strings matching the
  database values, consistent with `status`.
- **Assumed**: `absent` is serialized rather than omitted, so a client reading
  the field always finds a value [BR2.2].
- **Open, and D6's**: nothing in D2. Its Data Safety implications are nil —
  no new collection, no new personal field.
