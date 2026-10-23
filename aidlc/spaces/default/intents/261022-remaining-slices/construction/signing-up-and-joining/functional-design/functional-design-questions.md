# Functional Design — Questions

**Stage**: functional-design (3.1)
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

## How this stage was answered

This unit arrives with unusually little left to decide. Six ADRs written three
days ago settle the schema, the lens type, the migration and the two query
changes; 32 requirements and seven stories settle the behaviour; and the
screens are drawn in `refined-mockups/` down to their states. Asking the human
to re-answer any of that would be asking them to repeat themselves.

What remained were corners that the upstream artifacts leave implied rather
than stated, and which a design must commit to one way or the other. Each is
answered below from an upstream source, and the source is named. Where no
source settles it, the answer says so and records the assumption.

---

## Q1. Does accepting a seat require the acceptor to be the named account?

[Answer]: Yes, and it is the whole point. `InvitationLens` is granted only
when a link on that enrollment names **this** account and its decision is
`pending` or `declined` [ADR-011]. The accept action is reachable only through
that lens, so a person can only ever accept a link that names them. There is
no "accept on behalf of" path.

[ADR-011]

## Q2. Can a teacher's action change a decision?

[Answer]: No, in one direction only. **No teacher action clears or reverses a
decline** [AC1.13.3]. Re-adding a declined number to the same batch does not
re-prompt [AC1.13.4]. But the decline is reversible *by its holder* at any
time [AC1.13.1, AC1.13.2].

The asymmetry is deliberate and is what makes the durability protect the right
person: durable against the teacher, reversible by me.

[AC1.13.1–AC1.13.4]

## Q3. What happens when one person is both student and guardian on a seat?

[Answer]: One accept grants both lenses and the seat appears once, not twice
[AC1.10.5]. The two decision columns are independent, so the design must
*detect* the same-account case rather than inherit the right answer: both
links name the same account, so both columns move together on that one action.

[AC1.10.5] [FR1.16]

## Q4. What does a pending person see of a seat they have not accepted?

[Answer]: Exactly three fields — batch name, subject, fee amount — and nothing
else [AC1.10.1]. No attendance, no marks, no other enrollment, no write action
[AC1.10.2]. This is a response-schema obligation, not a filter: the invitation
response carries only those fields, so there is nothing to leak.

[AC1.10.1] [AC1.10.2] [FR1.9d]

## Q5. Does the already-added lookup reveal who added the number?

[Answer]: No. It names neither teacher nor batch [AC1.12.2, AC1.16.4]. It
returns whether a seat exists, the teacher-typed name to pre-fill, and the
role to lock. That is the criterion that keeps the lookup from becoming an
oracle for who teaches whom.

[AC1.12.2] [AC1.16.4] [FR1.7f]

## Q6. Is the lookup rate-limited, and does it leak existence by timing?

[Answer]: It is bounded by signup's own per-number and per-IP ceilings
[AC1.16.1, AC1.16.2]. It is **not** held to the OTP path's byte-identical
response rule, because it exists precisely to tell the caller something about
the number — that is its purpose, and conflating the two controls is how one
inherits the other's assumptions [Q3 of US1.16].

What it must not do is widen that disclosure beyond "a seat exists for this
number, under this role, with this name". AC1.16.3 keeps `POST /v1/auth/otp`
byte-identical independently.

[AC1.16.1–AC1.16.4] [FR1.7d] [FR1.7e]

## Q7. Is the account created before or after the code is sent?

[Answer]: Before, and the submit action names the number the code will go to
[AC1.11.4]. So signup is a write that then triggers the existing OTP path,
rather than a pending intent completed by verification.

[AC1.11.4] [FR1.7c]

## Q8. What does signing up on an already-added number do to the seat?

[Answer]: Nothing. The seat stays `pending` [AC1.12.3]. Signing up is not
accepting, and this is the single most important negative in the unit: the
superseded model made signing in the act that granted the lens, and this
criterion is what retires it.

[AC1.12.3] [FR1.9a]

## Q9. Does accepting reveal history from before the acceptance?

[Answer]: Yes — the seat's **full history from creation**, including dues
accrued before I accepted [AC1.10.3]. Acceptance grants the lens; the lens is
not time-bounded.

[AC1.10.3] [FR1.9g]

## Q10. Is a role claim verified?

[Answer]: No. Nothing verifies it [AC1.11.5]. A person claiming Teacher gets
an `Owner` row and an empty batch list; the claim costs them nothing and gains
them nothing they could not have by creating a batch.

[AC1.11.5] [FR1.7b]

## Assumptions & Open Questions

- **Assumed**: the signup "full name" populates the existing
  `profile.self_name` rather than adding a third name column [ADR-010]. The
  ADR states this; it is recorded here because a reader may expect signup's
  name to be the one teachers see, and it is not.
- **Assumed**: a declined link whose account is later deleted keeps the
  decline [ADR-009's fourth row, FR11.1a]. D6 owns deletion; D1 owns only that
  the decision column is not cleared by anything.
- **Open, and D3's**: every money consequence of declining. AC1.14.2a asks for
  a ledger reversal and no ledger exists until D3 creates one. D1 owns the
  decision-column transition and nothing more.
