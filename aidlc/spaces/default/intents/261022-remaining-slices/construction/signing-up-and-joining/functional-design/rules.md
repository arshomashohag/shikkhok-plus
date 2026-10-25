# Business Rules — D1 `signing-up-and-joining`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> Rule IDs are **unit-scoped**, as in every prior unit of this project: `BR1.1`
> here is D1's first authorization rule, a different rule from `BR1.1` in
> `identity-and-access`. Group meanings stay stable across units — 1
> authorization, 2 abuse control, 3 privacy, 4 signup, 5 acceptance, 6 erasure,
> 7 what the new columns change in merged code — so a reader moving between
> units reads the same axis under the same number.

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — FR1.7a–f,
  FR1.9a–i, FR1.16, FR1.17, FR11.1a
- [upstream] `inception/user-stories/stories.md` — US1.10–US1.16, and US1.5
  from the prior record
- [upstream] `inception/units-generation/unit-of-work.md` — D1's scope
- [prior] `inception/domain-design/decisions.md` — ADR-009 through ADR-014
- [code] `app/authz/resolve.py`, `app/authz/summary.py`,
  `app/batches/service.py`, `app/contract/privacy.py`, read 2026-10-23

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
      The rule the whole re-cut exists to install. Before it, NAMING an
      account on a link was the grant, so a mistyped digit handed a stranger
      a guardian lens over a child's records. Enforced INSIDE the granting
      query rather than above it [ADR-014], because a check above a query is
      one a future query can bypass.

  - id: BR1.2
    statement: >
      The lens-summary counts behind the lens picker count only `accepted`
      links, by the same predicate as the grant itself.
    category: authorization
    applies_to: Lens summary, GET /v1/me
    trigger: Rendering the lens picker, or any count of a person's seats.
    logic: >
      IF counting a person's student seats or guardian children
      THEN count only links naming this account whose decision is `accepted`.
    violation_behaviour: >
      A count that disagrees with the grant: the picker offers a lens that
      resolves to nothing, or hides one that works.
    source: FR1.4a
    notes: >
      Its own rule rather than a clause of BR1.1 because it lives in a
      SEPARATE statement in a different module, and changing one alone is a
      silent half-fix [ADR-014]. The summary renders the picker; the resolver
      grants. Both read the same columns and neither reads the other.

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
      its holder, which requires the holder to still reach the seat. Resolved
      by its OWN statement rather than a fourth branch of the hot-path query,
      because an invitation grant is a SET and that query returns scalars
      [ADR-011].

  - id: BR1.4
    statement: >
      An invitation lens grants read of exactly three fields of its seat —
      batch name, subject, fee amount — and no write action but accept and
      decline on the link that names the holder.
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
      A response-SCHEMA obligation, not a filter: the invitation response
      carries only those three fields, so there is nothing to leak. All three
      are teacher-authored, so the pending read crosses no privacy boundary.

  - id: BR1.5
    statement: >
      Accepting grants the seat's full history from its creation, not from the
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
      reconcile a balance against what their teacher sees.
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
      IF signup requests for one number exceed the per-number ceiling
      OR signup requests from one IP exceed the per-IP ceiling
      THEN refuse further requests.
    violation_behaviour: >
      Refused as a conflict, not as a transient error — a ceiling breach is
      not retryable [team: Error handling].
    source: FR1.7d
    notes: >
      Separate controls rather than extra conditions on the OTP ones, because
      signup and OTP have OPPOSITE disclosure properties by design, and
      conflating the controls is how one inherits the other's assumptions.

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
      The endpoint becomes a number-enumeration oracle — the property the
      seven existing OTP controls were built to deny.
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
      AND never the teacher's identity, nor the batch's name or subject.
    violation_behaviour: >
      The lookup becomes an oracle for who teaches whom, readable by anyone
      who can type a phone number.
    source: FR1.7f
    notes: >
      This lookup deliberately DOES disclose that a seat exists — that is its
      whole purpose, and it is why BR2.2 is a separate rule rather than one
      applied to both. What is bounded here is the WIDTH of the disclosure,
      not its existence.

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
      A teacher's roster changes under them from a person's private edit, and
      the two names stop answering different questions.
    source: FR1.12, FR1.17
    notes: >
      No third name exists [ADR-010]. "Which name does a teacher see" stays
      answered by WHICH TABLE the query reads, rather than by a filter
      somebody applies.

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
      Enforced structurally rather than per endpoint: the address sits on
      `Profile`, which carries the row-level-security policy keyed on the
      session account, and the schema-wide invariant test already iterates
      every teacher-lens response schema [ADR-010].

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

  - id: BR3.4
    statement: >
      `address` is added to the owner-private field set in the same unit that
      adds the column.
    category: constraint
    applies_to: Profile.address, the teacher-lens schema invariant
    trigger: Adding any column to Profile.
    logic: >
      IF a column is added to Profile
      THEN its field name is added to the owner-private set the schema-wide
      invariant matches on
      AND a test asserts that membership.
    violation_behaviour: >
      The structural gate BR3.2 relies on does not see the new field, so the
      invariant passes while a future teacher-facing schema carrying
      `address` goes unflagged — a child's home address, on the highest-stakes
      disclosure axis in the product.
    source: FR1.17, TC-13
    notes: >
      **BR3.2's mechanism is correct and does not enforce itself.**
      `OWNER_PRIVATE_FIELDS` (`app/contract/privacy.py:56`) is a
      hand-maintained frozenset — currently `{self_name, photo_ref}` — matched
      by FIELD NAME against every teacher-lens response schema. It is not
      derived from `Profile`'s columns, so adding a column does not enrol it.

      This is the same failure as BR7.1 and BR7.2 on a different axis: a
      merged mechanism whose meaning depends on a list nobody updated. The
      sweep in this file was applied faithfully to the two link columns and
      not to this unit's own new Profile column, which the architecture review
      found at iteration 1.

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
      Either a teacher who reaches no batch list, or a student holding a
      teacher lens.
    source: FR1.7a
    notes: >
      The row's presence IS the teacher claim; no role is recorded on the
      account.

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
      Recorded as a rule because it is a deliberate decision that reads as an
      omission. Claiming Teacher gains nobody anything they could not have by
      creating a batch, and nothing a teacher sees is another person's
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
      A uniqueness answer rather than a lookup: `Account.phone` is unique, so
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
      AND state that a teacher has added this number, naming neither teacher
      nor batch.
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
    trigger: Account creation on a number that already has seats.
    logic: >
      IF an account is created for a number that has seats
      THEN link the account to those seats
      AND leave every decision column exactly as it was.
    violation_behaviour: >
      The superseded model returns: signing in becomes the act that grants
      the lens, and the unconsented-guardian exposure reopens.
    source: FR1.9a
    notes: >
      The single most important NEGATIVE in this unit. Stated as a rule
      because the absence of an action is not visible in a diff, and because
      this same step is what makes BR7.1 and BR7.2 necessary.

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
      Where the student and the guardian are DIFFERENT people, each decision
      is independent and the teacher's roster shows both states separately
      rather than collapsed into one seat state.

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
      Does NOT contradict BR5.2. BR5.2 governs the DATA — a decision per
      link; this rule governs the ACTION — one action may carry both
      decisions when one person holds both links. The storage stays per-link.

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
      its holder. The transition is `declined` -> `accepted`, never a reset
      to `pending`, so it does not conflict with BR6.1.

  - id: BR5.5
    statement: >
      A declined seat does not appear among the person's enrollments, and does
      remain among their invitations.
    category: policy
    applies_to: Enrollment lists
    trigger: Listing a person's seats.
    logic: >
      IF a link's decision is `declined`
      THEN the seat appears in that person's invitations
      AND NOT among their enrollments.
    violation_behaviour: >
      A refused seat reads as a joined one, and declining achieves nothing
      visible — or the seat vanishes entirely and BR5.4's reversal is
      unreachable.
    source: FR1.9a
    notes: >
      Both halves matter. Out of the enrollments: BR1.1 already denies the
      lens. Still in the invitations: BR5.4 requires the holder to reach it.

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
      A decline is silently undone — the specific harm BR5.4's asymmetry
      exists to prevent.
    source: FR11.1a
    notes: >
      Deletion is D6's, and FR11.1a is where the obligation lives. D1 owns
      only the half it could otherwise break on its own: the decision
      survives every write D1 makes.

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
      THEN grant no lens, because the account that link named no longer
      exists.
    violation_behaviour: An erased person's seat still resolves a lens.
    source: ADR-009
    notes: >
      The decision column is not an authorization input on its own. The two
      per-link pairs are independent facts and BOTH are read on every grant.

  # ---- Group 7: what the new columns change in merged code. ----

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
      ELSE refuse, keeping the existing distinct reasons for claimed and for
      erased.
    violation_behaviour: >
      A teacher cannot remove a seat created on a mistyped number once that
      stranger signs up — the exact recovery path this unit exists to open.
    source: AC2.5.1a
    notes: >
      **D1's migration breaks a merged, routed write path, and this rule is
      what stops it shipping that way.** `remove_enrollment`
      (defined at `app/batches/service.py:254`; the predicate at line 274)
      refuses when `student_account_id IS NOT
      NULL`, which under the superseded model meant "claimed". After BR5.1,
      signing up links the account while the decision stays `pending`, so
      that check starts reporting claimed for a seat nobody has accepted.

      The predicate must change in the SAME unit that changes what the column
      means. D2 owns the roster SCREEN that shows the per-link states
      [AC1.10.7]; D1 owns not leaving a merged write path wrong in the
      interval between them.

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
      mistyped number — both false, and the opposite of the signal the
      teacher needs to spot the error.
    source: FR1.9h
    notes: >
      The built roster computes `is_dormant = student_account_id is None`
      (`app/batches/service.py:172`). D1 makes that derivation WRONG rather
      than merely incomplete, so it moves here with the columns. D2 renders
      the per-link detail; D1 keeps the single flag truthful meanwhile.
```

---

## Rules summary

| ID | Category | In one line |
|---|---|---|
| BR1.1 | authorization | A lens needs `accepted`, checked inside the granting query |
| BR1.2 | authorization | The picker's counts use the same predicate as the grant |
| BR1.3 | authorization | `pending` or `declined` grants an invitation lens for that one seat |
| BR1.4 | authorization | An invitation shows three fields and no other write action |
| BR1.5 | authorization | Accepting reveals the seat's whole history, not just what follows |
| BR2.1 | constraint | Signup has its own per-number and per-IP ceilings |
| BR2.2 | constraint | The OTP response stays byte-identical, known number or not |
| BR2.3 | constraint | The lookup names neither teacher nor batch |
| BR3.1 | policy | Signup's name is the private one; the teacher's typed name is untouched |
| BR3.2 | authorization | The address is owner-private and unreachable by a teacher |
| BR3.3 | constraint | Account and Profile are created together or not at all |
| BR3.4 | constraint | `address` joins the owner-private field set in the unit that adds it |
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
picker counts wrong, or the reverse. They live in different modules and have to
change together.

**BR5.1.** The absence of an action, which no diff shows. If signing up quietly
accepts, every other rule here is decoration.

## The sweep: every merged reader D1's columns affect

D1's migration changes what `student_account_id` and `guardian_account_id`
*mean* to code written before acceptance existed, and it adds a `Profile`
column that a hand-maintained allowlist does not know about. This project
recorded on 2026-10-22 that **adding a column is not adding a behaviour, and
the queries that must start reading it have to be named.** This is that
naming, from a direct read of `app/` on 2026-10-23 rather than from the two
queries an ADR had already named.

| Reader | File | Reads | After D1 | Owner |
|---|---|---|---|---|
| `_LENS_QUERY` | `app/authz/resolve.py:69,73` | both link columns | **wrong** — grants on a pending link | BR1.1, D1 |
| `_SUMMARY_QUERY` | `app/authz/summary.py:65,69` | both link columns | **wrong** — counts pending seats | BR1.2, D1 |
| `remove_enrollment` | `app/batches/service.py:254`, predicate at 274 | `student_account_id` | **wrong** — blocks removing a mistyped seat the moment that stranger signs up | BR7.1, D1 |
| roster `is_dormant` | `app/batches/service.py:172` | `student_account_id` | **wrong** — shows claimed when nobody accepted | BR7.2, D1 |
| `list_guardian_children` | `app/batches/service.py:179` | `guardian_account_id` | safe, but **only because** `GuardianLens` stops being granted (BR1.1). Defended by the lens, not by itself | noted |
| `add_enrollment` | `app/batches/service.py:438` | writes both | must state the initial decision, since there is no column default | ADR-013 |
| `FORBIDDEN_ACCOUNT_ID_FIELDS` | `app/contract/privacy.py:64` | names both as never-exposed | unaffected — it forbids the columns by name, and D1 changes their meaning, not their exposure | — |
| `OWNER_PRIVATE_FIELDS` | `app/contract/privacy.py:56` | `{self_name, photo_ref}` | **wrong** — a hand-maintained set matched by FIELD NAME, so `address` is absent and BR3.2's structural gate does not see it | BR3.4, D1 |

**`remove_enrollment` is the one that would have shipped as a real defect.**
The others are wrong in ways somebody notices. This one silently closes the
recovery path for a mistyped number — the single scenario the unit was created
to handle — in a merged, routed write path rather than on a screen.

**`list_guardian_children` is worth its row even though it needs no change.**
It is safe only transitively: the lens it requires stops being granted, so it
never runs for an unaccepted seat. A reader who later removes the lens
requirement, or calls it from somewhere else, inherits a query with no
predicate of its own. Recorded so that is a decision rather than a discovery.

**`OWNER_PRIVATE_FIELDS` was the row this sweep missed**, and the architecture
review found it at iteration 1. The first table covered the two link columns
thoroughly and stopped at the columns the unit was *about*, when the sweep's
own question — what merged mechanism depends on a list of names that nobody
updated? — applies identically to `Profile.address`. The same methodology, not
applied to the unit's own second change, on the one axis this product treats
as highest-stakes. BR3.4 closes it.

## Assumptions & Open Questions

- **Assumed**: BR2.1's ceilings take the same shape as the OTP path's existing
  ones. The numbers are Code Generation's to set from the existing
  configuration; the rule fixes that they are *separate*, not what they are.
- **Open, and D3's**: every money consequence of a decline. BR5.5 removes a
  declined seat from the enrollments; whether a fee cycle stops generating,
  and what happens to dues already accrued, is US1.14, and there is no ledger
  table until D3 builds one.
