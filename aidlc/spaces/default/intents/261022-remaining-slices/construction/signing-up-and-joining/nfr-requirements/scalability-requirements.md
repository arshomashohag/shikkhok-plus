# Scalability Requirements — D1 `signing-up-and-joining`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> D1 does not change how large this system may become. It changes **who may
> make it larger**: before this unit, account rows appeared only when someone
> inserted them by hand.

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — NFR20–NFR22
- [prior] NFR6, NFR7 of `261016-shikhokplus-tuition-app`
- [upstream] `construction/signing-up-and-joining/functional-design/rules.md` — BR2.1
- [code] `app/auth/ceilings.py`, read 2026-10-23

---

## Requirements

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR6.20 | D1 does not raise or lower the scale ceiling | 100 teachers, a few thousand students | [NFR6] |
| NFR6.21 | Account-table growth is **bounded by signup's own ceilings** | The per-number and per-IP cascade is the growth control as well as the abuse control | [BR2.1] [FR1.7d] |
| NFR6.22 | The declared 48-hour retention on `rate_limit_counter` gains an enforcing job | The retention **decision** exists in `app/governance/dispositions.py` (`HOURS_48`, `HARD_DELETE`); **no job enforces it**, so rows accumulate indefinitely | [code: `dispositions.py:121`, `models.py:267`] |
| NFR7.5 | D1 adds no infrastructure and no recurring cost | No new service, no new datastore, no new scheduled job | [NFR7] |

**NFR6.21 is the one worth stating plainly.** Growth was previously zero by
construction — a row existed only if a person typed SQL. After D1 the account
table grows at whatever rate the public can reach it, and the only thing
standing between "a tuition app for 100 teachers" and an unbounded table is
the ceiling cascade. That reframes NFR12.3 from an abuse control into a
capacity control, and it is why NFR12.5 (counters in the datastore, not in
process memory) is a scalability requirement as much as a security one: a
per-process counter under several Uvicorn workers limits nothing.

**NFR6.22 is narrower than two earlier drafts of it, and the narrowing is the
useful part.**

The first draft asserted the table is "bounded by window expiry". That was an
assumption, and reading migration `0001` and `app/` showed no purge code
anywhere. The second draft swung the other way and called the whole question
open — purge or accept unbounded growth, the human's choice. The architecture
review found that was also wrong: **the retention decision is already made.**
`app/governance/dispositions.py:121` declares `rate_limit_counter` as
`HARD_DELETE` at `HOURS_48`, with the basis "the longest window is a day, so a
48-hour retention covers every live counter with room to spare."

So the gap is one thing, not two: **a declared retention with nothing
enforcing it.** Rows do accumulate — one per
`(scope_kind, scope_value, window_start)`, kept forever — but not because
nobody decided what should happen to them. Somebody did, in the right place,
with a reason.

The growth is slow and the rows are small, so this is not urgent. What makes
it D1's to name is that the table's row count is driven by **unauthenticated**
traffic, and D1 adds a second cascade writing to it. The closure is a
scheduled job honouring a disposition that already exists — not a decision
anyone still has to make.

---

## Concurrency

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR6.23 | Two signups racing on one number produce **one** account | `Account.phone` is unique; the constraint reports the collision and the second attempt is directed to log in | [BR4.4] |
| NFR6.24 | Two accept actions racing on one link converge on one decision | A decision moves `pending`→`accepted` or `pending`→`declined`; a repeat of the same transition is a no-op rather than an error | [BR5.2] |
| NFR6.25 | The ceiling cascade is correct under concurrent workers | The increment-then-compare is atomic, so two workers racing one window cannot both read a passing count | [code: `ceilings.py`] |

**NFR6.23 relies on a constraint rather than a check.** This project's recorded
practice is that application-level "has this already happened" guards fail
under concurrency and the database constraint is the mechanism. Signup
inherits that shape from the fee-cycle idempotency rule, on the same
reasoning.

**NFR6.24 is a smaller version of the same.** Two taps on accept must not
produce an error the person has to understand. The transition is idempotent in
its target state, which is a property of the state machine rather than a lock.

---

## Capacity planning

| Quantity | Before D1 | After D1 | Bound |
|---|---|---|---|
| `account` rows | Grows only by hand-insert | Grows by public signup | Signup ceilings [NFR6.21] |
| `profile` rows | One per edited account | **One per account**, created at signup | Follows `account` [BR3.3] |
| `enrollment` rows | Grows by teacher action | Unchanged by D1 | [NFR6] |
| `rate_limit_counter` rows | OTP cascade's four scopes | Plus signup's scopes | 48h declared, **unenforced** [NFR6.22] |
| `auth_audit` rows | Five event kinds | Plus signup events | Retention class, **D6** |

**`profile` changes shape, not just size.** It was previously optional and
populated on first edit; after D1 every account has one from creation [BR3.3].
The row count is unchanged in order of magnitude and the *assumption* a reader
may make about it is not — which is why BR3.3 makes the two-row creation one
transaction.

---

## Assumptions & Open Questions

- **Checked twice, wrong twice, and the second miss is the instructive one.**
  This file first assumed the counter table expires its windows; reading
  `app/` showed no purge code. It then called the retention question open,
  having searched for purge *code* and not for a retention *declaration* —
  which exists, in the governance manifest, where this project puts exactly
  that. Both drafts searched for the mechanism and neither searched for the
  decision. NFR6.22 now names the one real gap: a declared disposition with no
  job behind it.
- **Assumed**: a retention class for the new signup audit events follows the
  existing auth-record retention, which the team practice names as the first
  data class to carry a scheduled purge. The purge itself is **D6**'s.
