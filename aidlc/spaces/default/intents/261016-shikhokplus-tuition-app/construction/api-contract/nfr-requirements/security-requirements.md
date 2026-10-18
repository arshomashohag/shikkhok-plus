# Security Requirements — `api-contract` (U2)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Depth**: Comprehensive

> **The asset under protection here is not data — it is a set of guarantees.**
> U2 holds no rows, authenticates nobody and authorizes nothing. What it owns
> is four CI gates and an error contract that later Units cannot violate
> without failing a build. A security document listing authentication controls
> would be boilerplate; this one treats the gates themselves as the control,
> and asks the only question worth asking about a control: **can it be
> satisfied without being true?**
>
> That question has unusual force in B2, because **every schema assertion this
> Unit ships iterates an empty set**. There are no routes, no money endpoints
> and no response schemas yet. Four green checks that have never examined
> anything is the realistic failure mode, and it is worse than having no
> checks, because it manufactures documented confidence.

## Sources

- [stage] `nfr-requirements-questions.md` — Q1 (which NFRs bind), Q2 (the
  asset), Q3 (the diff gate and its one bypass), Q4 (the handler's single
  runtime requirement), Q5 (coverage)
- [upstream] `construction/api-contract/functional-design/rules.md` — BR1.1–BR4.4
- [upstream] `construction/api-contract/functional-design/functional-spec.md`
- [upstream] `inception/requirements-analysis/requirements.md` — NFR3, NFR9,
  NFR13, NFR14, NFR16, NFR17
- [upstream] `inception/contract-design/contract-summary.md` — §B.2–B.5, §E.2
- [upstream] `inception/domain-design/decisions.md` — ADR-001
- [team] `## Testing Posture`, `## Code Style` → error handling, authorization
- [project] `## Forbidden` / `## Mandated`

---

## Part A — Threat model for a Unit that ships gates rather than behaviour

### T1 — A gate passes because it has nothing to examine

**NFR14.1, NFR9.1, NFR17.1**

The money assertion, the privacy assertion, the `*_display` pairing rule and
the route-enumeration harness all iterate collections that are **empty in B2**.
Each returns green. Nothing is wrong, and nothing has been checked.

This is the single most likely way this Unit ships broken, and it is invisible
by construction: a passing test and a vacuous test are the same colour.

**NFR14.1** — Each of the four gates ships with a **committed fixture that
violates it**, asserted to be caught [BR4.1]. The fixtures are:

| Gate | Fixture |
|---|---|
| Money schema assertion | A property declaring an inline money-shaped string instead of `$ref`-ing the `Money` component |
| `*_display` pairing | A `<x>_display` field with no sibling `<x>` |
| Privacy assertion | A teacher-lens response schema declaring an owner-private profile field, and a second declaring `student_account_id` |
| Route enumeration | A route whose dependency returns no `Lens` subtype and is not allowlisted |

**NFR14.2** — Each fixture test asserts **which violation was reported**, not
merely that the gate refused. A fixture that fails for a cheaper reason — a
malformed document, a missing key — certifies nothing about the rule it was
written for, and it does so while looking exactly like a working test.

**NFR17.1** — A fixture that stops failing is itself a build failure. This
inverts the usual reading: the fixtures are the only part of U2 whose *failure*
is the passing condition.

> Why this is T1 rather than a testing note: the privacy assertion is the
> API-level half of NFR14, which is a COPPA/GDPR-K boundary over children's
> data. A vacuous privacy gate is not a quality problem, it is a compliance
> claim with nothing behind it.

---

### T2 — The committed schema drifts from the generated one

**NFR16.1, NFR16.2, NFR16.3**

`team.md` is explicit: *"a stale committed schema is worse than none, because
the contract tests then pass against fiction."* Every downstream contract test,
the ZAP baseline scan driven from the schema, and the client's own expectations
all rest on the committed document being current.

**NFR16.1** — The committed OpenAPI 3.1 document must equal the generated one.
CI fails on any difference [BR2.1].

**NFR16.2** — The comparison runs **in CI, not only locally**. `team.md`'s "one
command, local and in CI" rule applies: a gate reproducible only by pushing
gets bypassed, and one that runs only locally gets skipped.

**NFR16.3** — Serialization must be **deterministic** — stable key ordering,
stable formatting. This is a security requirement rather than an ergonomic one:
a byte comparison with unstable output produces false failures, and a gate that
cries wolf is disabled by whoever is holding the pager.

> **The one bypass, stated plainly because no check closes it.** An implementer
> can regenerate the schema and commit it without reading the diff. That is not
> a technical hole; it is why the diff exists in a pull request where the one
> reviewer sees it [OC-1]. Recording it is better than implying the gate is
> stronger than it is.
>
> **The likely misuse is different and worse**: hand-editing the committed file
> to make the diff pass. The committed document is an *output*. Editing it
> inverts the control into a rubber stamp, and it looks like fixing the gate.
> **NFR16.4** — the regeneration command is the only sanctioned way to update
> the committed document, and this is stated in the repository beside it.

---

### T3 — A refusal becomes an existence oracle

**NFR14.3, NFR14.4**

Teacher A probes resource ids. Any observable difference between "exists but
not yours" and "does not exist" enumerates teacher B's batches — the IDOR shape
`team.md` names as the vulnerability class a scanner cannot find, because
finding it requires knowing the intended policy.

**NFR14.3** — The two cases return a **byte-identical** response: same status
(403), same `code`, same `retryable`, same `message_key`, same `details`, same
headers [BR1.4]. No code in the registry distinguishes them [BR1.5].

**NFR14.4** — Both branches perform the **same lookup work**; neither returns
before the other's query has run [BR1.4]. Asserted **structurally** — the
queries each branch executes — never as a wall-clock bound, because a
millisecond assertion is flaky and gets deleted the third time CI fails on it.
This mirrors the OTP issue path's control exactly.

> **U2 cannot discharge NFR14.4 and does not claim to.** It owns no lookup
> code. BR4.4 names **U3** as the owner: it owns lens resolution, it is the
> first Unit with a lookup that can fail either way, and it is the walking
> skeleton, so the obligation lands where the human checkpoint reads the
> privacy claim rather than several Bolts later.

---

### T4 — An endpoint ships with no authorization and nothing notices

**NFR14.5, NFR14.6, NFR14.7**

The failure mode is not a *wrong* lens, it is a **forgotten** one — and a
dependency nobody added produces an endpoint that works perfectly and
authorizes nothing. Review cannot reliably catch an absence.

**NFR14.5** — Every route resolves a lens, checked against the **real
application object at test collection time**, so a new unlensed endpoint
reddens CI on the commit that adds it [BR3.1].

**NFR14.6** — Two fixed allowlists, not one open-ended list [BR3.1]:

```
PUBLIC_ROUTES                      # exactly five
  POST /v1/auth/otp                # OTP issue
  POST /v1/auth/verify             # OTP verify
  GET  /health                     # liveness + applied migration revision
  GET  /account-deletion           # external deletion form   [TC-19, U11]
  POST /account-deletion           # external deletion submit [TC-19, U11]

LENS_EXEMPT_AUTHENTICATED          # exactly one
  POST /v1/auth/refresh            # authenticates by refresh token, no lens
```

Stating the counts is the control: a sixth entry is a diff against a number,
not a line in a growing list. Note that the external deletion route is **two**
routes — the form and its submission — and both are unversioned, since that
surface is reached by a browser with no app installed and is not `/v1/` app
surface.

> The separation matters for a specific reason. With one combined allowlist,
> the implementer who first hits a failing refresh route takes the cheapest
> green edit and adds it to `PUBLIC_ROUTES` — after which nothing records that
> the route must stay authenticated.

**NFR14.7** — Lens detection resolves the dependency's **return annotation**
via `typing.get_type_hints` against its own module, never by matching a
function name [BR3.2]. A union counts only when every member qualifies;
`Annotated` and generic aliases are unwrapped. A resolution failure **fails the
build naming the route** and is never swallowed.

> The real damage is not the false negative. It is the implementer who hits the
> `TypeError`, wraps the call in `except TypeError: return True`, and makes the
> entire check pass universally while authorizing nothing. The project's own
> lint configuration selects `UP`, which encourages `from __future__ import
> annotations` — so string annotations are the expected shape here, not an edge
> case.

---

### T5 — A teacher-facing response carries a field it must not

**NFR14.8, NFR14.9**

Two distinct leaks through one mechanism. Owner-private profile fields are what
a student or guardian writes about themselves, which no teacher may ever see
[TC-13, D-5]. Account ids are a **global** key; an enrollment id is scoped to
one owner, so a teacher-facing response carrying `student_account_id` hands
teacher A a stable handle on a student also enrolled with teacher B [ADR-001].

**NFR14.8** — The assertion iterates the **generated schema** rather than
naming endpoints, and carries **both** field sets on one iteration [BR2.4]. Per
endpoint, it would cover the endpoints someone remembered; iteration covers the
one added in B9 after everyone stopped thinking about it.

**NFR14.9** — **Schemathesis never counts as privacy coverage** [BR4.2], and
this is recorded in writing because the distinction is easy to lose and
expensive to lose. A response wrongly carrying profile fields is perfectly
*conformant*: it matches its own declaration. Schemathesis is kept for what it
is good at — unexpected 500s, type and required-field drift, auth present on
every route.

---

### T6 — A money value crosses the boundary as something other than a string

**NFR9.1, NFR9.2**

A JSON number is an IEEE 754 double in most parsers, so emitting one converts
the value to a float on the client, where none of U1's controls reach. The
defect U1's import boundary **cannot** see is a money value typed as a
free-form string in the schema.

**NFR9.1** — Every money-carrying property **`$ref`s the shared `Money`
schema component**, which carries the pattern `^[0-9]+\.[0-9]{2}$` [BR2.2]. The
assertion is that no property declares an inline money-shaped type instead of
referencing the component.

> The predicate matters. An earlier draft said "every property *carrying
> money*", which is not decidable from a generated document: selecting by the
> pattern checks the pattern on properties chosen for having it, and the defect
> this gate exists to catch is precisely what a pattern-based selector cannot
> see. `$ref` to the single declared component is decidable, and it inverts the
> question from "does this match" to "does this reference the one definition".

**NFR9.2** — A `<x>_display` field never appears without its canonical `<x>`
sibling [BR2.3]. The display string is **not** pattern-matched — it is
presentation, and its content is fixed by the rendering specification closed at
OQ-B1-1 (Western digits, 2,2,3 grouping, `৳` prefix). The pairing is structural
and holds regardless of that content.

---

### T7 — The error handler becomes a failure mode of its own

**NFR17.2, NFR17.3**

The handler is U2's only runtime code, and it sits on **every error path in the
system**. If it can fail, it turns a handled 403 into an unhandled 500 at
exactly the moment the system is already degraded.

**NFR17.2** — The handler performs **no I/O**: no database call, no network
call, no file read. Its cost is bounded by construction rather than by a
latency number nobody could defend, and U2 has no endpoint on which to measure
one.

**NFR17.3** — The handler is **total over the taxonomy**: five classes in, a
response out, with no branch that can fall through. BR1.1 closing the hierarchy
at five is what makes totality checkable rather than hoped for.

Its own `except Exception` is one of exactly **two sanctioned sites** in the
backend, the other being the scheduled fee-generation job's top level.

---

### T8 — An error response leaks, or cannot be shown to a Bangla-speaking user

**NFR3.1, NFR13.1**

**NFR3.1** — **No English `message` is ever emitted**, at any level. The
envelope carries `message_key` naming a client string resource, and declares
`additionalProperties: false` so a `message` field fails schema validation and
the diff gate [BR1.3]. A server-authored English string cannot be localized by
the client; in a Bangla-first UI that guarantees untranslated English error text
in front of a teacher, which would make NFR3 unreachable no matter what the
Android Bolts did.

**NFR13.1** — `retryable: false` on a 401 is reconciled with refresh-then-replay
in writing [BR1.6]. `retryable` answers *"may the client repeat this request
unchanged?"*, which for an expired token is genuinely no. The refresh rule
permits a **different** request followed by one replay, bounded at one, only on
`ACCESS_TOKEN_EXPIRED`, with any second 401 ending the session.

> Both halves of that reconciliation produce a defect when read alone: a client
> treating 401 as retryable builds a refresh loop; one reading `retryable:
> false` literally cannot refresh at all.

**NFR3.2** — No error log carries a phone number, an OTP or a token; every
error log carries the correlation id. Phone numbers are children's-adjacent
personal data [RC-1, RC-2, RC-3], so this is a compliance rule rather than
hygiene. U2 owns the envelope shape that makes this achievable — `details` is
typed per code and never a free-form dump of request state.

---

### T9 — A client-supplied lens hint is trusted

**NFR14.10**

[D-2] permits a lens hint for UI shaping and forbids trusting it for
authorization. The erosion path is a hint that shapes more than navigation.

**NFR14.10** — The hint affects navigation and UI shaping **only**. The server
re-derives the lens from owned batches and enrollments on every request, and
**refuses with 403 `LENS_NOT_AVAILABLE`** when the hinted lens has no data
behind it — never silently falling back [BR1.7]. A missing hint on a
lens-ambiguous route is refused with 400 `LENS_HINT_REQUIRED`. The response is
self-describing and names the lens that produced it, so the client renders from
the response rather than from the hint it sent.

> This resolves a contradiction between two upstream sources. `stories.md`
> AC10.1.6 says the server *ignores* an unsupported hint; `contract-summary`
> §B.4 says it *refuses*. FR1.4 settles it — only lenses that have data are
> offered — so an unsupported hint is a stale client, a bug or a crafted
> request, and silent fallback serves all three under a lens the caller never
> named. The two sources agree on the security-relevant half: the hint grants
> nothing and the lens is always re-derived.

---

## Part B — What this Unit does NOT have, and why that is correct

A `spec` Unit that is never deployed has no availability target, no throughput
figure, no scaling trigger and no alerting threshold. Recording that per NFR is
what distinguishes an analysis from an omission.

| Inception NFR | Status | Why |
|---|---|---|
| NFR1 Android/compile SDK | N/A | No Android surface in this Unit |
| NFR2 Device floor, AAB size | N/A | Ships no code to a device |
| NFR3 Languages | **Partial** | NFR3.1 — `message_key` is what makes localized errors reachable |
| NFR4 Offline reads | N/A | No client, no cache |
| NFR5 Offline writes | N/A | No write path |
| NFR6 Scale ceiling | N/A | No process; nothing scales |
| NFR7 Infrastructure cost | N/A | Adds no running infrastructure |
| NFR8 Data residency | N/A | Stores nothing |
| NFR9 Money representation | **Binds** | NFR9.1, NFR9.2 — the schema-level half |
| NFR10 Children's data at rest | N/A | Persists nothing |
| NFR11 Device identifiers | N/A | No device surface |
| NFR12 OTP abuse controls | N/A | Owned by U3 |
| NFR13 Token lifetimes | **Partial** | NFR13.1 — the 401 reconciliation |
| NFR14 Privacy boundary | **Binds** | NFR14.1–NFR14.10 — U2 owns the third layer |
| NFR15 Accessibility | N/A | Renders nothing |
| NFR16 API versioning | **Binds** | NFR16.1–NFR16.4 — the diff gate is the detection mechanism |
| NFR17 Backend coverage | **Binds** | NFR17.1–NFR17.3 |

**On NFR17 specifically.** The 80% line floor applies to U2's runtime code —
the five exception classes and the handler — which is small enough to reach
100% comfortably. The gates themselves *are* tests, and measuring a test
suite's coverage of itself is meaningless. The meaningful target here is **not
a percentage**: it is T1's four fixtures. NFR17's authorization-layer branch
coverage lands on **U3**, which owns lens resolution; U2 owns the `Lens` types
only, and a type declaration has no branches.

---

## Part C — Verification

| ID | Verified by | Fails when |
|---|---|---|
| NFR9.1 | Fixture: inline money-shaped string | A money property does not `$ref` the `Money` component |
| NFR9.2 | Fixture: orphan `*_display` | A display field has no canonical sibling |
| NFR14.1 | Four committed violation fixtures | A fixture stops failing |
| NFR14.2 | Each fixture asserts the reported violation | A fixture fails for a cheaper reason |
| NFR14.3 | Byte-comparison test over both refusal paths | Any observable difference between the two |
| NFR14.4 | **U3** — structural query-equivalence test | A branch short-circuits (BR4.4) |
| NFR14.5 | Route harness over the real app object | A route resolves no lens |
| NFR14.6 | Allowlist length assertions (5 and 1) | A sixth or second entry appears |
| NFR14.7 | Fixtures: string annotation, mixed union, `Annotated` | Resolution is swallowed or name-matched |
| NFR14.8 | Schema-wide iteration, both field sets | Any teacher-lens schema declares either |
| NFR14.9 | Stated in writing in the artifact | — (a documentation obligation) |
| NFR14.10 | Contract test over hint outcomes | A hint grants, or an unsupported hint falls back |
| NFR16.1–3 | Schema-diff gate in CI | Committed ≠ generated, or output is unstable |
| NFR16.4 | Regeneration command documented beside the file | — (a documentation obligation) |
| NFR17.1 | The fixtures' failure is the pass condition | A fixture passes |
| NFR17.2 | Import-boundary assertion on the handler module | The handler imports an I/O module |
| NFR17.3 | Exhaustiveness over the five classes | A class has no mapping |
| NFR3.1 | `additionalProperties: false` + schema validation | A `message` field appears |
| NFR3.2 | Log-content assertion | A phone number, OTP or token reaches a log |
| NFR13.1 | Stated in writing; contract test on the 401 path | A second 401 does not end the session |

**Two obligations are documentation rather than tests** (NFR14.9, NFR16.4) and
are marked as such rather than dressed up as checks. Both exist because the
failure they prevent is a *misunderstanding* — what Schemathesis proves, and
how the committed schema is updated — and a misunderstanding is corrected by a
sentence in the right place, not by an assertion.

---

## Assumptions & Open Questions

**None.** [assumption] OQ-B1-1 closed on 2026-10-18 with the Bangla money
rendering specification. It fixed the *content* of a `*_display` string and
never the structural pairing rule this Unit asserts (NFR9.2), so no requirement
here changes as a result.
