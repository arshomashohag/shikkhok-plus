# Business Rules — D1 `signing-up-and-joining`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> Rule IDs are **unit-scoped**, as in every prior unit of this project: `BR1.1`
> here is D1's first authorization rule and is a different rule from `BR1.1` in
> `identity-and-access`. Group meanings are kept stable across units — group 1
> authorization, group 2 abuse control, group 3 privacy, group 4 signup, group
> 5 acceptance, group 6 erasure, group 7 what the new columns change in code
> that already exists — so a reader moving between units reads the same axis
> under the same number.

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — FR1.7, FR1.9,
  FR1.16, FR1.17
- [upstream] `inception/user-stories/stories.md` — US1.10–US1.16, and US1.5
  from the prior record
- [upstream] `inception/units-generation/unit-of-work.md` — D1's scope
- [prior] `inception/domain-design/decisions.md` — ADR-009 through ADR-014

---

```yaml
rules:

  # ---- Group 1: authorization. The reason this unit exists. ----

  - id: BR1.1
    statement: >
      A student or guardian lens is granted for a seat only when the link
      naming this account carries decision `accepted`.
    category: authorization
    applies_to: Enrollment, lens resolution
    trigger: Every authenticated request that resolves a lens.
    logic: >
      IF a link on this enrollment names this account
      AND that link's decision is `accepted`
      AND that link's erasure marker is not set
      THEN grant the matching lens for this seat
      ELSE grant nothing for this seat.
    violation_behaviour: >
      No lens. The request proceeds with whatever other lenses the account
      legitimately holds, or is refused if it holds none for the route.
    source: FR1.9a
    notes: >
      This is the rule the whole re-cut exists to install. Before it, naming
      an account on a link WAS the grant, so a mistyped digit handed a
      stranger a guardian lens. It is enforced inside the granting query
      rather than above it [ADR-014], because a check above a query is a check
      a future query can bypass.

  - id: BR1.2
    statement: >
      The lens-summary counts behind the lens picker count only `accepted`
      links, by the same predicate as the grant itself.
    category: authorization
    applies_to: Lens summary, GET /v1/me
    trigger: Rendering the lens picker or any count of a person's seats.
    logic: >
      IF counting a person's student seats or guardian children
      THEN count only links naming this account whose decision is `accepted`.
    violation_behaviour: >
      A count that disagrees with the grant: the picker offers a lens that
      resolves to nothing, or hides one that works.
    source: FR1.4a
    notes: >
      Stated as its own rule rather than folded into BR1.1 because it is a
      SEPARATE statement in a different module, and a change to one alone is
      a silent half-fix [ADR-014]. The summary is what renders the picker;
      the resolver is what grants. Both read the same columns and neither
      reads the other.

  - id: BR1.3
    statement: >
      An invitation lens is granted for a seat when a link on that enrollment
      names this account and its decision is `pending` or `declined`.
    category: authorization
    applies_to: Enrollment, InvitationLens
    trigger: A request on an invitation route.
    logic: >
      IF a link on this enrollment names this account
      AND that link's decision is `pending` OR `declined`
      THEN grant an invitation lens scoped to that one enrollment.
    violation_behaviour: Refused. The person reaches no seat they do not hold.
    source: FR1.9d, FR1.9d.1
    notes: >
      `declined` is included deliberately: BR5.4 makes a decline reversible by
      its holder, which requires the holder to still reach the seat.
      Resolved by its own statement rather than a fourth branch of the
      hot-path query, because an invitation grant is a SET and that query
      returns scalars [ADR-011].

  - id: BR1.4
    statement: >
      An invitation lens grants read of exactly three fields of its seat —
      batch name, subject, fee amount — and no write action.
    category: authorization
    applies_to: InvitationLens, invitation response
    trigger: Reading a pending or declined seat.
    logic: >
      IF rendering a seat through an invitation lens
      THEN return batch name, subject and fee amount only
      AND expose no attendance, no marks, no other enrollment, and no write
      action other than accept and decline on this link.
    violation_behaviour: >
      Any additional field is an unconsented disclosure to a person who has
      not agreed to be in the batch.
    source: FR1.9d
    notes: >
      A response-schema obligation, not a filter: the invitation response
      carries only those fields, so there is nothing to leak.

  - id: BR1.5
    statement: >
      Accepting grants the seat's full history from creation, not from the
      moment of acceptance.
    category: authorization
    applies_to: Enrollment, post-acceptance reads
    trigger: Any read of an accepted seat.
    logic: >
      IF a lens is granted on a seat
      THEN the whole seat is visible, including dues accrued and events
      recorded before the decision changed to `accepted`.
    violation_behaviour: >
      A person sees a partial record of their own enrollment and cannot
      reconcile a balance.
    source: FR1.9g

  # ---- Group 2: abuse control. ----

  - id: BR2.1
    statement: >
      Signup is bounded by its own per-number and per-IP ceilings, separate
      from the OTP path's ceilings.
    category: constraint
    applies_to: Signup
    trigger: Each signup request.
    logic: >
      IF signup requests from one number exceed the per-number ceiling
      OR signup requests from one IP exceed the per-IP ceiling
      THEN refuse further requests.
    violation_behaviour: Refused as a conflict, not as a transient error.
    source: FR1.7d
    notes: >
      Separate from the OTP controls rather than extra conditions on them,
      because signup and OTP have OPPOSITE disclosure properties by design
      and conflating their controls is how one inherits the other's
      assumptions.

  - id: BR2.2
    statement: >
      The OTP endpoint's response remains byte-identical for a known and an
      unknown number after signup exists.
    category: constraint
    applies_to: OTP issue
    trigger: Every OTP request.
    logic: >
      IF an OTP is requested for any number
      THEN the response body, status and timing characteristics do not vary
      with whether an account exists.
    violation_behaviour: >
      The endpoint becomes a number-enumeration oracle, which is the property
      the existing seven OTP controls were built to deny.
    source: FR1.7e
    notes: >
      A regression rule, not a new capability: signup must not weaken what
      `identity-and-access` already built. Asserted byte-for-byte.

  - id: BR2.3
    statement: >
      The already-added lookup names neither a teacher nor a batch.
    category: constraint
    applies_to: Already-added lookup
    trigger: Each lookup call.
    logic: >
      IF a number has a seat a teacher created
      THEN return only that a seat exists, the teacher-typed name to
      pre-fill, and the role to lock
      AND never the teacher's identity nor the batch's name or subject.
    violation_behaviour: >
      The lookup becomes an oracle for who teaches whom, readable by anyone
      who can type a phone number.
    source: FR1.7f
    notes: >
      This lookup deliberately DOES disclose that a seat exists — that is its
      purpose, and it is why BR2.2 is a separate rule rather than one applied
      to both. What is bounded is the WIDTH of the disclosure, not its
      existence.

  # ---- Group 3: privacy. ----

  - id: BR3.1
    statement: >
      Signup's full name is the self-authored name; the teacher-typed display
      name is never changed by it.
    category: policy
    applies_to: Profile.self_name, Enrollment.display_name
    trigger: Signup, and any profile edit.
    logic: >
      IF a person supplies a name at signup or edits their profile
      THEN write Profile.self_name
      AND leave every Enrollment.display_name untouched.
    violation_behaviour: >
      A teacher's roster changes under them from a person's private edit,
      and the two names stop answering different questions.
    source: FR1.12, FR1.17
    notes: >
      No third name exists [ADR-010]. "Which name does a teacher see" stays
      answered by WHICH TABLE the query reads rather than by a filter.

  - id: BR3.2
    statement: >
      The address is personal data on the owner-private profile and is never
      reachable through a teacher lens.
    category: authorization
    applies_to: Profile.address
    trigger: Any read of profile data.
    logic: >
      IF a request carries a teacher lens
      THEN no response schema it can reach contains any Profile field.
    violation_behaviour: >
      A teacher reads a child's home address — the most consequential single
      disclosure available in this product.
    source: FR1.17, TC-13
    notes: >
      Enforced structurally: the address is on `Profile`, which carries the
      row-level-security policy keyed on the session account. The
      schema-wide invariant test covers it without a new per-endpoint test
      [ADR-010].

  - id: BR3.3
    statement: >
      Account and Profile are created in one transaction.
    category: constraint
    applies_to: Signup
    trigger: Account creation.
    logic: >
      IF signup creates an Account
      THEN it creates the matching Profile in the same transaction
      AND a failure in either leaves neither.
    violation_behaviour: >
      An account exists with no Profile row, violating the assumption every
      future reader will make now that Profile is no longer optional.
    source: ADR-010

  # ---- Group 4: signup. ----

  - id: BR4.1
    statement: >
      An Owner row is created at signup if and only if the person chose
      Teacher.
    category: constraint
    applies_to: Signup, Owner
    trigger: Account creation.
    logic: >
      IF the chosen role is Teacher THEN create an Owner row
      ELSE create none.
    violation_behaviour: >
      Either a teacher with no batch list, or a student holding a teacher
      lens.
    source: FR1.7a
    notes: Presence of the row IS the teacher claim; there is no role column.

  - id: BR4.2
    statement: >
      A role claim is not verified.
    category: policy
    applies_to: Signup
    trigger: Role selection.
    logic: >
      IF a person claims a role THEN accept the claim without evidence.
    violation_behaviour: Not applicable; this rule permits rather than forbids.
    source: FR1.7b
    notes: >
      Recorded as a rule because it is a deliberate decision that looks like
      an omission. Claiming Teacher gains nobody anything they could not have
      by creating a batch, and nothing a teacher sees is another person's
      private data.

  - id: BR4.3
    statement: >
      The account is created before the verification code is sent, and the
      submit action names the number the code will go to.
    category: constraint
    applies_to: Signup
    trigger: Signup submission.
    logic: >
      IF signup is submitted
      THEN create the account and profile first
      AND then trigger the existing OTP path
      AND the submit control states the destination number.
    violation_behaviour: >
      A code sent for an account that does not exist, or a person who cannot
      tell which number they are about to be texted.
    source: FR1.7c

  - id: BR4.4
    statement: >
      A number that already has an account cannot sign up again; the person is
      directed to log in.
    category: validation
    applies_to: Signup, Account.phone
    trigger: Signup submission.
    logic: >
      IF an account already exists for this number
      THEN refuse the signup and direct the person to log in.
    violation_behaviour: A duplicate identity for one person.
    source: AC1.12.4
    notes: >
      A uniqueness answer rather than a lookup: Account.phone is unique, so
      the refusal is the constraint reporting itself.

  - id: BR4.5
    statement: >
      On a number a teacher already added, the signup form pre-fills the
      teacher-typed name as correctable and locks the role to the seat's.
    category: validation
    applies_to: Signup form, already-added lookup
    trigger: Rendering the signup form.
    logic: >
      IF the number has a seat a teacher created
      THEN pre-fill the name from the teacher's entry, marked correctable
      AND lock the role to the one the seat carries
      AND state that a teacher has added this number, naming neither.
    violation_behaviour: >
      A person retypes what their teacher recorded, or picks a role that
      contradicts their seat.
    source: FR1.7f

  # ---- Group 5: acceptance. The unit's subject. ----

  - id: BR5.1
    statement: >
      Signing up does not accept a seat. A seat created for a number stays
      `pending` when that number signs up.
    category: policy
    applies_to: Signup, Enrollment decision columns
    trigger: Account creation on a number with existing seats.
    logic: >
      IF an account is created for a number that has seats
      THEN link the account to those seats
      AND leave every decision column unchanged.
    violation_behaviour: >
      The superseded model returns: signing in becomes the act that grants
      the lens, and the unconsented-guardian exposure reopens.
    source: FR1.9a
    notes: >
      The single most important negative in this unit. Stated as a rule
      because the absence of an action is not visible in a diff.

  - id: BR5.2
    statement: >
      A decision is recorded per link and affects only that link's holder.
    category: policy
    applies_to: Enrollment.student_decision, Enrollment.guardian_decision
    trigger: Accept or decline.
    logic: >
      IF a person accepts or declines a seat
      THEN change only the decision column of the link that names them
      AND leave the other link's decision untouched.
    violation_behaviour: >
      One person's choice speaks for another: a guardian's decline removes a
      student's access to their own records, or a student's acceptance
      enrolls a guardian who never agreed.
    source: FR1.9b
    notes: >
      Where the student and guardian are DIFFERENT people, each decision is
      independent and the teacher's roster shows both states separately
      rather than collapsed into one.

  - id: BR5.3
    statement: >
      Where one account holds both links on a seat, one decision moves both
      and the seat appears once.
    category: policy
    applies_to: Enrollment, invitation list
    trigger: Accept or decline on a seat whose links name the same account.
    logic: >
      IF both links on this enrollment name this account
      THEN apply the decision to both columns in one action
      AND list the seat once in that person's invitations, not twice.
    violation_behaviour: >
      A person accepts their own seat twice, or accepts as student and
      remains pending as guardian for themselves.
    source: FR1.16
    notes: >
      Does not contradict BR5.2. BR5.2 makes a decision per link; this rule
      says that when one person holds both links, one ACTION carries both
      decisions. The data stays per-link.

  - id: BR5.4
    statement: >
      A decline is reversible by its holder at any time, and by nobody else.
    category: policy
    applies_to: Enrollment decision columns
    trigger: Accept on a declined link; any teacher action on the seat.
    logic: >
      IF the holder of a declined link accepts it
      THEN the lens becomes available exactly as if accepted first time
      AND IF a teacher takes any action on that seat, including re-adding the
      number to the batch
      THEN the decline is neither cleared nor re-prompted.
    violation_behaviour: >
      Either a mis-tap locks a person out of their own records permanently,
      or a teacher can re-ask until the person gives in.
    source: FR1.9c, FR1.9c.1, FR1.9c.2
    notes: >
      The asymmetry IS the rule: durable against the teacher, reversible by
      me. A declined seat therefore stays listed, with an accept action, for
      its holder.

  - id: BR5.5
    statement: >
      A declined seat does not appear among the person's enrollments.
    category: policy
    applies_to: Enrollment lists
    trigger: Listing a person's seats.
    logic: >
      IF a link's decision is `declined`
      THEN the seat appears in that person's invitations
      AND NOT among their enrollments.
    violation_behaviour: >
      A refused seat reads as a joined one, and declining achieves nothing
      visible.
    source: FR1.9a
    notes: >
      Both halves matter: out of the enrollments (BR1.1 already denies the
      lens) and still in the invitations, because BR5.4 requires the holder
      to be able to reach it.

  # ---- Group 6: erasure interaction. ----

  - id: BR6.1
    statement: >
      Nothing in this unit clears a decision column.
    category: constraint
    applies_to: Enrollment decision columns
    trigger: Any write path in D1.
    logic: >
      IF any D1 operation writes an enrollment
      THEN it may move a decision only by its holder's accept or decline
      AND never reset one to `pending`.
    violation_behaviour: >
      A decline is silently undone, which is the specific harm BR5.4's
      asymmetry exists to prevent.
    source: FR11.1a
    notes: >
      Deletion is D6's. D1 owns only the half of that contract that it could
      otherwise break: the decision survives.

  - id: BR6.2
    statement: >
      An `accepted` decision on a link whose erasure marker is set grants no
      lens.
    category: authorization
    applies_to: Enrollment, lens resolution
    trigger: Lens resolution.
    logic: >
      IF a link's decision is `accepted`
      AND that link's erasure marker is set
      THEN grant no lens, because the account it named no longer exists.
    violation_behaviour: An erased person's seat still resolves.
    source: ADR-009
    notes: >
      The decision column is not an authorization input on its own. The two
      per-link pairs are independent facts and both are read.
  # ---- Group 7: what the new columns change in code that already exists. ----

  - id: BR7.1
    statement: >
      Seat removability is decided by the decision columns, not by whether a
      link names an account.
    category: authorization
    applies_to: Enrollment removal
    trigger: A teacher removes a seat.
    logic: >
      IF no link on this seat carries decision `accepted`
      AND no erasure marker is set
      THEN the seat is removable
      ELSE refuse, with the existing distinct reasons for claimed and erased.
    violation_behaviour: >
      A teacher cannot remove a seat created on a mistyped number once that
      stranger signs up — the exact recovery path this unit exists to protect.
    source: AC2.5.1a
    notes: >
      **This rule exists because D1's migration breaks a merged behaviour, and
      the review caught that the first draft did not say so.** The built
      `remove_enrollment` refuses when `student_account_id IS NOT NULL`, which
      under the superseded model meant "claimed". After D1, signing up links
      the account while the decision stays `pending` [BR5.1], so that test
      starts reporting claimed for a seat nobody has accepted.

      The predicate must therefore change in the SAME unit that changes what
      the column means. D2 owns the roster SCREEN that shows the states
      [AC1.10.7]; D1 owns not leaving a merged write path wrong in the
      meantime.

  - id: BR7.2
    statement: >
      Teacher-facing dormancy is `no link has accepted`, not `no account is
      named`.
    category: calculation
    applies_to: Roster rows
    trigger: Rendering a roster row's state.
    logic: >
      IF no link on this seat carries decision `accepted`
      THEN the seat is not claimed
      ELSE it is claimed by whichever links accepted.
    violation_behaviour: >
      The roster shows a seat as claimed the moment a stranger signs up on a
      mistyped number, which is both false and the opposite of the signal the
      teacher needs to spot the error.
    source: FR1.9h
    notes: >
      The built roster computes `is_dormant = student_account_id is None`.
      D1 makes that computation wrong rather than merely incomplete, so the
      derivation moves here with the columns. D2 renders the per-link detail;
      D1 keeps the single flag truthful in the interim.
```

---

## Rules summary

| ID | Category | In one line |
|---|---|---|
| BR1.1 | authorization | A lens needs `accepted`, checked inside the granting query |
| BR1.2 | authorization | The picker's counts use the same predicate as the grant |
| BR1.3 | authorization | `pending` or `declined` grants an invitation lens for that one seat |
| BR1.4 | authorization | An invitation shows three fields and no write action |
| BR1.5 | authorization | Accepting reveals the seat's whole history, not just what follows |
| BR2.1 | constraint | Signup has its own per-number and per-IP ceilings |
| BR2.2 | constraint | The OTP response stays byte-identical, known number or not |
| BR2.3 | constraint | The lookup names neither teacher nor batch |
| BR3.1 | policy | Signup's name is the private one; the teacher's typed name is untouched |
| BR3.2 | authorization | The address is owner-private and unreachable by a teacher |
| BR3.3 | constraint | Account and Profile are created together or not at all |
| BR4.1 | constraint | `Owner` is created for Teacher and only Teacher |
| BR4.2 | policy | Nothing verifies a role claim |
| BR4.3 | constraint | Account first, then the code, and the button names the number |
| BR4.4 | validation | An existing number is sent to log in |
| BR4.5 | validation | Name pre-filled and correctable, role locked |
| BR5.1 | policy | **Signing up does not accept** |
| BR5.2 | policy | A decision is per link and speaks for nobody else |
| BR5.3 | policy | One person holding both links decides once |
| BR5.4 | policy | A decline is durable against the teacher, reversible by me |
| BR5.5 | policy | A declined seat leaves the enrollments, stays in the invitations |
| BR6.1 | constraint | Nothing here resets a decision to `pending` |
| BR6.2 | authorization | `accepted` plus erased grants nothing |
| BR7.1 | authorization | Removability reads the decision, not the link |
| BR7.2 | calculation | Dormant means nobody accepted, not nobody signed up |

## The three rules this unit would be worthless without

**BR1.1 and BR1.2 together.** Either alone is a half-fix: lenses correct and
picker counts wrong, or the reverse. They live in different modules and must
change together.

**BR5.1.** The absence of an action, which no diff shows. If signing up
quietly accepts, every other rule here is decoration.

## The rules the review added, and why they were missing

**BR7.1 and BR7.2 exist because D1's migration changes what a column already
in use *means*.** `student_account_id` meant "claimed" to every reader written
before acceptance existed. After D1 it means "has an account", and claimed is
a different column.

The first draft of this file named the two queries ADR-014 names and stopped
there, which is the exact failure this project recorded on 2026-10-22:
*adding a column is not adding a behaviour; name the queries that must start
reading it.* Having recorded it, I repeated it. The sweep below is what the
rule asks for, and it belongs in the artifact rather than in a reviewer's
memory.

| Reader | Reads | After D1 | Owner |
|---|---|---|---|
| `_LENS_QUERY` | both link columns | **wrong** — grants on a pending link | BR1.1, D1 |
| `_SUMMARY_QUERY` | both link columns | **wrong** — counts pending seats | BR1.2, D1 |
| `remove_enrollment` | `student_account_id` | **wrong** — blocks removing a mistyped seat the moment that stranger signs up | BR7.1, D1 |
| roster `is_dormant` | `student_account_id` | **wrong** — shows claimed when nobody accepted | BR7.2, D1 |
| `list_guardian_children` | `guardian_account_id` | safe, but only because `GuardianLens` stops being granted (BR1.1). Defended by the lens, not by itself | noted |
| `create_enrollment` | writes both | must state the initial decision, since there is no column default | ADR-013 |
| `privacy.py` field list | names both as never-exposed | unaffected | — |

**`remove_enrollment` is the one that would have shipped as a real defect.**
The others are wrong in ways someone notices; this one silently removes the
recovery path for a mistyped number — the single scenario the unit was created
to handle — and it is a merged, routed write path, not a screen.

## Assumptions & Open Questions

- **Assumed**: the ceilings in BR2.1 take the same shape as the OTP path's
  existing ones. The numbers are Code Generation's to set from the existing
  configuration; the rule fixes that they are separate, not what they are.
- **Open, and D3's**: every money consequence of a decline. BR5.5 removes a
  declined seat from the enrollments; whether a fee cycle stops generating,
  and what happens to dues already accrued, is US1.14 and there is no ledger
  until D3 builds one.
