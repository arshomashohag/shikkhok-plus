# Security Requirements — D1 `signing-up-and-joining`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> D1 is the unit that opens an unauthenticated write path into a
> children's-data application. Everything below follows from that one fact.
> The authorization half — what a seat grants and when — is designed in
> `functional-design/rules.md`; this file carries the targets and the
> constraints those rules are implemented under.

> **`NFRx.y` IDs are GLOBAL across units, unlike `BRx.y`.** A derived ID
> extends its base NFR on one continuous axis, so `NFR14.23` means one thing
> everywhere and a reader may resolve it in any unit's artifacts. This unit's
> IDs therefore start **above the high-water mark** each base had reached in
> the four merged units: NFR6 from .20, NFR7 from .5, NFR10 from .13, NFR12
> from .3, NFR13 from .4, NFR14 from .22. A bare `NFR6.1` or `NFR12.1` in
> these files is a **citation** of the prior record's rule, not a definition
> here.
>
> The first draft of this file numbered from .1 per base and collided with
> seventeen existing IDs carrying unrelated meanings. That is recorded here
> rather than quietly fixed, because the numbering convention is exactly the
> thing a later unit will copy from this file.

## Sources

- [upstream] `construction/signing-up-and-joining/functional-design/functional-spec.md`
  and `rules.md` — BR1.x, BR2.x, BR3.x
- [upstream] `inception/requirements-analysis/requirements.md` — FR1.7a–f,
  FR1.9a–i, FR1.17, NFR20–NFR23
- [prior] NFR10, NFR11, NFR12, NFR12.1, NFR13, NFR14 of
  `261016-shikhokplus-tuition-app`
- [code] `app/auth/ceilings.py`, `app/audit/log.py`, `app/contract/privacy.py`,
  read 2026-10-23

---

## The change in the threat surface

Before D1 an account could be created only by hand-inserting a database row.
D1 adds `POST /v1/accounts` and an unauthenticated lookup. Three consequences,
and each gets a requirement below:

1. **A new unauthenticated write path** that creates rows and causes an SMS.
2. **A deliberate existence oracle.** The already-added lookup exists to tell
   the caller something about a number [BR2.3], which is the exact property
   the OTP path is built to deny. Two endpoints with opposite disclosure
   properties now sit beside each other.
3. **Two new personal-data columns**, one of them a home address, on a
   product whose users are children.

---

## Requirements

### Authentication and account creation

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR12.3 | Signup carries its own per-number and per-IP ceilings, counted **separately** from the OTP cascade | Distinct `ScopeKind` members and a distinct cascade; a signup refusal never decrements or consumes an OTP allowance, and the reverse | [BR2.1] [FR1.7d] |
| NFR12.4 | Signup's cascade is evaluated **narrowest first**, and a scope that refuses is not counted against wider scopes | The built invariant holds in the new cascade: per-number before per-IP, and a refusal increments nothing wider | [code: `ceilings.py`] |
| NFR12.5 | Signup's counters live in the **datastore**, never in process memory | Phase 1 runs several Uvicorn workers on one host; a per-process counter passes every naive test and silently stops limiting | [code: `ceilings.py`] [NFR7] |
| NFR12.6 | A ceiling breach is a **conflict**, not a transient error | Non-retryable by error class, so the client does not retry into the limit | [BR2.1] [team: Error handling] |
| NFR13.4 | Signup creates the account **before** the code is sent, and issues no session of its own | The existing OTP path remains the only route to an authenticated session; signup grants no token | [BR4.3] [NFR13] |

**Why NFR12.4 is stated at all.** `app/auth/ceilings.py` records that an
earlier design checked the global ceiling first, and that its prose argued
against its own logic: global-first lets one attacker exhaust every
legitimate user's daily allowance before their own per-number limit trips.
The module's docstring says plainly that global-first *still looks like*
defence in depth. A second cascade is exactly where that mistake would be
made again, by someone reading the ordering as incidental.

### Disclosure

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.22 | `POST /v1/auth/otp` stays **byte-identical** for known and unknown numbers after signup exists | Asserted byte-for-byte by the existing adversarial test, re-run as a D1 obligation | [BR2.2] [FR1.7e] |
| NFR14.23 | The already-added lookup discloses **only** that a seat exists, the teacher-typed name, and the role | Never the teacher's identity, never the batch name or subject | [BR2.3] [FR1.7f] |
| NFR14.24 | The invitation response carries **exactly three** fields | Batch name, subject, fee amount; enforced by the response schema, not by a filter | [BR1.4] [FR1.9d] |
| NFR14.25 | No teacher-lens response schema contains any `Profile` field, `address` included | The schema-wide invariant over the generated OpenAPI document, with `address` enrolled in the matched field set | [BR3.2] [BR3.4] |

**NFR14.22 and NFR14.23 are deliberately in tension and must stay separate.**
One endpoint must reveal nothing about whether a number is known; the other
exists to reveal exactly that. Conflating their controls is how one inherits
the other's assumptions — so signup's ceilings are separate (NFR12.3) and the
byte-identical obligation is pinned to the OTP route alone.

**NFR14.25 is the one that needs a mechanism rather than a statement.** The
owner-private field set is matched by *field name* and maintained by hand, so
adding `Profile.address` does not enrol it. BR3.4 carries the membership
obligation; this requirement is what that membership is for.

### Data protection

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR10.13 | `profile.address` and `profile.self_name` are encrypted at rest, inheriting the table's existing protection | No hosting or database tier without storage encryption | [NFR10] [RC-8] [FR1.17] |
| NFR10.14 | The address is reachable only through the row-level-security policy keyed on the session account | Structural, not a query-level filter | [BR3.2] [NFR14] |
| NFR11.1 | Signup transmits no device or advertising identifier, and reads no device phone number | The number is always typed; enforced by the manifest allowlist and the release DEX scan | [NFR11] [TC-3] [TC-4] |

### Audit

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR12.7 | Account creation and signup ceiling breaches are recorded in the append-only authentication audit log | Named members of the **closed** `AuthEvent` vocabulary, never a free-form value | [code: `audit/log.py`] [NFR12] |
| NFR12.8 | No audit row or log line carries a phone number, an OTP, a token, an address or a self-authored name | The row dataclass has no free-form string field but `correlation_id`; a test asserts it | [code: `audit/log.py`] [team: Deployment] |

### Verification

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR23.1 | Every acceptance state transition is written **test-first** | A transition grants or withholds a lens, so a wrong answer is an authorization error and the affirmed predicate holds | [NFR23] [team: Testing Posture] |
| NFR23.2 | The adversarial lens test is written against today's code and must **fail** before the fix | An account named only on `pending` or `declined` links resolves no role lens and reports zero counts | [NFR23] [BR1.1] [BR1.2] |
| NFR23.3 | The authorization layer is measured as **branch** coverage, not line coverage | Lens resolution is pure branching over the link and decision columns; line coverage on it is close to meaningless | [NFR17] [team: Testing Posture] |

**NFR23.2 is the one that is easy to satisfy wrongly.** A test written after
the predicate lands passes immediately and proves nothing about the defect it
names. The obligation is that it fails first, for the stated reason — the
predicate reads the link, not the decision.

**NFR12.7 extends a closed set, and says why.** `AuthEvent`'s docstring states
that the vocabulary is closed because an open one is how a free-form value
re-enters a log specified not to have one. Account creation belongs in that
log on its merits — rate-limited, unauthenticated, and the place an
enumeration attempt would surface — so it is added as a named member under the
same rule, not as a reason to relax the rule.

---

## Threat considerations

| Threat | Mitigation | Requirement |
|---|---|---|
| Number enumeration via the OTP endpoint | Byte-identical responses, unchanged by signup's existence | NFR14.22 |
| Number enumeration via the lookup | Accepted by design, bounded in width and rate | NFR14.23, NFR12.3 |
| Mapping who teaches whom | The lookup names neither teacher nor batch | NFR14.23 |
| Mass account creation to burn the SMS budget | Signup ceilings, plus the OTP path's own global daily ceiling behind them | NFR12.3, NFR12.5 |
| A stranger reaching a child's records via a mistyped number | **The unit's reason to exist**: no lens until acceptance | [BR1.1] [BR1.2] |
| A teacher reading a child's home address | `Profile` row-level security, plus schema-wide invariant with `address` enrolled | NFR14.25, NFR10.14 |
| A role claim used to gain access | Nothing a teacher lens reaches is another person's private data; the claim gains nothing | [BR4.2] |

**The unverified role claim is a deliberate non-threat.** FR1.7b accepts it
without evidence. It is listed here rather than omitted, because an
unverified self-declared role reads as an omission to a security reviewer,
and the reason it is safe is a property of the lens model: a teacher lens
reaches owned batches and their teacher-authored records, never another
person's `Profile`.

---

## Compliance

| Obligation | D1's part | Owner |
|---|---|---|
| Children's data encrypted at rest | The two new columns inherit it | D1 [RC-8] |
| Families target-audience declarations | No new SDK, no new identifier | D1 [RC-1] |
| Data Safety form accuracy | Two new collected fields — address and self-authored name — must appear in the form's declared collection | **D6**, with D1 as the change that makes them collectable |
| Privacy policy disclosure of a declined seat's retained name | The governance basis text is extended; the generated policy must say it | **D6** [ADR-012] |
| Both account-deletion paths | `PUBLIC_ROUTES` already allowlists both; D1 adds neither handler | **D6** [TC-19] |

**D1 creates two release-blocking obligations it does not discharge.** The
address and the self-authored name are new collected personal data on a
Families-track application. The Data Safety form and the privacy policy are
D6's deliverables, and this is the unit that changes what they must say.

---

## Assumptions & Open Questions

- **Assumed**: signup's ceiling values are set from the existing configuration
  in the same shape as the OTP ones. These requirements fix that the counters
  are separate, ordered narrowest-first and datastore-backed; the integers are
  Code Generation's.
- **Assumed**: signup's IP scope derives its prefix exactly as the OTP cascade
  does. Two derivations would make the cascades disagree about what one caller
  is.
- **Open, and D5's**: the OWASP ZAP baseline pass against the staging host,
  driven from the committed OpenAPI schema. D1 adds routes it will cover and
  does not install it.
- **Open, and D6's**: Trivy on the release image, the backend SBOM, and the
  release-gate half of CVE blocking.
