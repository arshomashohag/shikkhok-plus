# Security Requirements — `identity-and-access` (U3)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**
**Depth**: Comprehensive

> **The first real attack surface.** U1 had no I/O and U2 no routes. U3 has
> three public endpoints, a phone number belonging to someone adjacent to a
> child, and a gateway that spends money on every call.
>
> The seven OTP abuse controls are specified as business rules [BR2.1–BR2.7]
> and not repeated here. This document covers what those rules do **not**
> reach: the secrets, the storage, the transport, and the two assets most
> likely to be defended against the wrong threat.

## Sources

- [stage] `nfr-requirements-questions.md` — Q1 (latency), Q2 (availability),
  Q3 (the SMS budget), Q4 (observability), Q5 (security), Q6 (scaling)
- [upstream] `construction/identity-and-access/functional-design/rules.md`
  — BR1.1–BR6.3
- [upstream] `construction/identity-and-access/functional-design/functional-spec.md`
- [upstream] `inception/contract-design/contract-summary.md` — §B.3, §C, §C.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR12, NFR13, NFR14
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1, US1.2, US1.5, US1.8, US1.9
- [team] `## Deployment` → secrets and scanning, `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. Threat model

### T1 — A leaked database yields live codes and live sessions

**NFR9.5, NFR9.6**

The asset is the `OtpRequest` and `RefreshToken` tables. The attacker has a
copy of the database — from a backup, a misconfigured restore, or the
Phase 1 reality that production access happens by `psql` against a live
instance holding children's data.

**NFR9.5 — the OTP is stored as an HMAC under a server-held key.**
Measured on this machine rather than assumed:

| Scheme | Cost per issue | Offline exhaustion of the 10⁶ space |
|---|---|---|
| SHA-256 | ~0.1 µs | **0.07 seconds** |
| bcrypt cost 8 | 15 ms | 4 hours |
| bcrypt cost 10 | 58 ms | 16 hours |
| **HMAC-SHA256 + key** | **~1 µs** | **impossible without the key** |

> **This requirement changed when it was measured, and the first version
> read as more security-conscious.** "Use a real password hash" is the
> instinct, and it is right about the threat: a 6-digit code has only 10⁶
> possibilities, so a leaked table under a bare digest falls in under a
> tenth of a second, and BR2.3's attempt ceiling does nothing about it —
> that defends the *online* path only.
>
> But bcrypt is designed for secrets drawn from a large space, where
> slowing each guess is the only lever. Against a 10⁶ space it buys hours,
> at 15–60 ms of CPU **per OTP issue** on a 2 GB instance. HMAC under a key
> held outside the database **defeats the attack outright** rather than
> delaying it, at a thousandth of the cost. Recorded because the wrong
> answer is the one that survives review.

**NFR9.6 — refresh tokens are stored hashed**, asserted by reading the
column. A leaked table must not yield usable sessions.

---

### T2 — A secret reaches a repository, an image, or a log

**NFR9.1, NFR9.2, NFR9.7**

Three named secrets enter the system here: the gateway credentials, the JWT
signing key, and the database URL.

**NFR9.1 — no secret in the repository or the image.** Environment
variables in Phase 1, SSM `SecureString` in Phase 2. Gitleaks blocks every
push, with no severity threshold and no exceptions — it is binary,
near-zero false positive, and always actionable by whoever just pushed.

**NFR9.2 — `error_message` from the gateway is never logged.** Verified
against the live endpoint: the error body **echoes the API key back in
plaintext** (`"user id not found in this <key> key"`). Only `response_code`
is logged. This is a live credential-leak path into the logs, not a
hypothetical one.

**NFR9.7 — the gateway request body is never logged at any level**,
because that call carries the phone number **and the OTP together**. Each
send logs `(purpose, outcome, correlation_id)` and nothing else [BR6.2].

---

### T3 — The OTP or the phone number crosses the network in cleartext

**NFR9.3**

**The scheme is enforced in code, not configuration.** Verified against the
live endpoint: plain HTTP serves the same BulkSMSBD API with **no redirect
and no HSTS**, so a misconfigured `http://` ships the phone number and the
OTP in cleartext and **succeeds silently** — nothing fails, warns or logs.

The adapter asserts `urlparse(base_url).scheme == "https"` at construction
and raises otherwise. No TLS-verification toggle is exposed, and a test
asserts the resolved URL starts with `https://`.

> Under RC-1/RC-2/RC-3 this is a privacy failure on children's-adjacent
> data, which is why it is a mechanism rather than a review item. `team.md`:
> *where a rule is important, it is mechanical.*

---

### T4 — A teacher reaches what a student or guardian wrote

**NFR14.1, NFR14.2, NFR14.3**

**NFR14.1 — separate tables by writer** [BR3.1]. `Profile` is written only
by its owner; the teacher-typed `display_name` lives on `Enrollment`. Which
name a teacher sees is answered by **which table the query reads**, not by
a filter someone remembers to apply.

**NFR14.2 — row-level security on `Profile`** [BR3.2], keyed on the
session's account id.

**NFR14.3 — the suite connects as a restricted non-superuser role, and a
meta-test asserts that before the privacy suite runs** [BR3.3].

> **Without NFR14.3 the other two certify nothing.** PostgreSQL documents
> that superusers and table owners bypass RLS entirely, and the default
> testcontainers connection is `postgres` — a superuser. A privacy suite
> run as superuser passes identically whether the policy is correct,
> broken, or absent. This is a `project.md` NEVER rule, and it is the one
> that makes the strongest obligation in the project mean something.

---

### T5 — A stolen refresh token outlives its theft

**NFR13.1, NFR13.2**

**NFR13.1 — presenting a rotated-out token invalidates the whole family**
[BR4.1], emits `REFRESH_REUSE_DETECTED`, and returns 401.

> **Reuse detection degrades silently into non-rotating tokens, because the
> happy path is identical either way.** Only a replayed token reveals the
> difference — which is the stolen-token case the mechanism exists for.
> Invalidating only the presented token leaves the thief's working, which
> inverts the control.

**NFR13.2 — a 15-minute-expired access token is refused**, enforced
server-side. The access token carries **no role and no lens claim**: a lens
baked into a 15-minute token is a cached role by another name, and would
survive an ownership change for up to fifteen minutes.

---

### T6 — An attacker spends the project's money

**NFR7.1–NFR7.4**

This is the one threat where the attacker's gain is the project's direct
loss, and the budget is USD 50/month total.

**NFR7.1 — a global daily SMS ceiling**, configured rather than hardcoded,
checked before every send.

**NFR7.2 — per-number and per-IP-prefix sub-ceilings, checked BEFORE the
global one** [BR2.5]. Narrowest first, and a scope's counter increments
only when that scope's check passes.

> **The order is the control, and an earlier draft had it backwards.**
> Global-first lets one attacker consume the global daily counter before
> their own per-number limit trips — stopped eventually, but only after
> spending every legitimate teacher's allowance for the day. Caught at
> review; recorded because the broken order still *looks* like defence in
> depth.

**NFR7.3 — every outcome consumes budget**, including `UNKNOWN` and
`BUDGET_REFUSED`. An `UNKNOWN` may have cost money, and counting only
`SENT` lets a flapping gateway spend without bound.

**NFR7.4 — a ceiling breach alerts**, verified in staging before the auth
slice reaches production.

---

### T7 — The existence oracle

**NFR12.1, NFR12.2**

**NFR12.1 — issue responses for a known and an unknown number are
byte-identical** [BR2.7].

**NFR12.2 — both branches perform the same work**, including the database
write: the unknown branch performs an equivalent INSERT and **rolls it
back**.

> **The write is the larger asymmetry and an earlier version missed it.**
> A transactional write means lock acquisition and a WAL flush — a far
> louder timing signal than a hash computation. A test asserting only
> hashing symmetry would guard the quiet channel while leaving the loud one
> open, and the accompanying "honest limitation" note would make that read
> as closed. Caught at review.
>
> **What remains**: equivalent work is not constant time. A patient
> attacker with a very large sample could still find residual variance.
> Closing that needs a fixed response deadline, which is implementable but
> would become a latency floor on every OTP request — disproportionate
> here, and stated rather than left as an implied guarantee.

---

### T8 — The audit log leaks what it audits

**NFR8.1, NFR8.2**

**NFR8.1 — an append-only auth audit log** holding OTP issued, verify
failed, verify succeeded, refresh rotated, refresh reuse detected.

**NFR8.2 — it holds no OTP, no token, no phone number and no child name.**
The correlation id ties a row to a request without carrying its contents.

> With zero audit logging this project cannot answer *"was this child's
> data accessed improperly"* — the question both COPPA and GDPR-K assume is
> answerable and which a parent complaint will ask. But an audit log that
> carries the thing it audits is a common and self-defeating mistake, so
> both halves are requirements.

---

## B. What this Unit does not defend against

Recorded so the gaps are deliberate rather than discovered.

| Not defended | Why |
|---|---|
| An attacker with the HMAC key **and** the database | Defence in depth stops here; the key is one of three named secrets with an exercised rotation runbook |
| Timing analysis with a very large sample | NFR12.2 closes the dominant asymmetry; constant-time would need a fixed response deadline and a latency floor on every request |
| SIM swap | The phone number is the identity by design [D-35]. No second factor exists at this scale |
| A compromised production host | At this budget there is no admin surface and no host isolation; the controls are the named-role access log and the append-only audit |
| Denial of service | One instance, no WAF, no CDN. The SMS ceilings bound the *cost*, not the availability |

---

## C. Verification

| ID | Verified by | Fails when |
|---|---|---|
| NFR7.1–7.2 | Counter tests at a test-configured threshold, narrowest-first | A refused request consumes a wider budget |
| NFR7.3 | Outcome-accounting test | An `UNKNOWN` does not consume budget |
| NFR7.4 | Staging alert verification | The breach is silent |
| NFR8.1–8.2 | Audit-row content assertion | Any forbidden value appears |
| NFR9.1 | Gitleaks, blocking every push | A secret reaches a commit |
| NFR9.2, NFR9.7 | Log-content assertion over the adapter | `error_message` or a request body is logged |
| NFR9.3 | Construction-time assertion + a URL test | A non-https scheme constructs |
| NFR9.5 | The stored value differs from the transmitted one, and is not reproducible without the key | A bare digest, or a plaintext column |
| NFR9.6, NFR13.2 | Column read; a 15-minute-expired token refused | A usable token in the table |
| NFR12.1 | Byte comparison of both responses | Any observable difference |
| NFR12.2 | Statement-level assertion over both branches | One branch skips the write |
| NFR13.1 | Five-transition state machine | Family invalidation missing |
| NFR14.1–14.2 | Adversarial probes under a teacher lens | Any profile field reachable |
| NFR14.3 | **Meta-test, runs first** | `current_user` is a superuser, or RLS is off |

---

## Assumptions & Open Questions

**One, and it is a value rather than a decision.** [assumption] The global
daily SMS ceiling's *number* derives from BulkSMSBD's per-SMS rate against
the USD 50/month budget — commercial information this stage does not hold.
The requirement is that the ceiling exists, is configured rather than
hardcoded, and is derived from the budget. Tests exercise the mechanism at
a test-configured threshold, so the value does not block this Unit.
