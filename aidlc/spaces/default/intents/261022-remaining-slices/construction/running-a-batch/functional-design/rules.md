# Business Rules — D2 `running-a-batch`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **A `ui` unit with rules, and the distinction is worth stating.** D2's
> `produces_kinds` makes `entities.md` optional because D2 adds no entity.
> It does not make D2 ruleless: the roster has to decide what to mark, what to
> count, and what to show for a seat whose holder refused it, and each of
> those is a rule somebody could implement two ways.
>
> **Every rule here is a presentation or response-shape rule.** The
> authorization rules this unit renders — a lens needs `accepted`,
> removability reads the decision — were built in D1 and are cited, not
> restated. Rule IDs are unit-scoped, as in every unit of this project.

## Sources

- [upstream] this stage's `functional-spec.md` — the workflows these rules sit in
- [upstream] `inception/user-stories/stories.md` — AC1.3.x, AC1.15.x, AC2.5.1
- [upstream] `inception/requirements-analysis/requirements.md` — FR1.9b,
  FR1.9h, FR1.9i
- [prior] `construction/signing-up-and-joining/functional-design/rules.md` —
  D1's BR1.1, BR5.2, BR5.4, BR7.1, BR7.2, which D2 renders
- [code] `app/api/batches.py`, `app/schemas/batches.py`, read 2026-10-23

---

```yaml
rules:

  # ---- Group 1: what the roster marks. ----

  - id: BR1.1
    statement: >
      A declined seat is marked per row; a pending seat is not.
    category: policy
    applies_to: Roster row rendering
    trigger: Rendering the roster.
    logic: >
      IF a link on this seat carries decision `declined`
      THEN mark that row
      ELSE IF the link is `pending`
      THEN do not mark the row, and count it at batch level instead.
    violation_behaviour: >
      Marking pending per row decorates the NORMAL state of a new seat, which
      flags normality as a problem and buries the one row that is actionable.
    source: AC1.3.3a
    notes: >
      The superseded AC1.3.3 gave this reasoning for `dormant` and the
      amendment keeps the reasoning while changing which state is normal.
      Declined is abnormal and usually means a mistyped number; pending means
      nobody has opened the app yet.

  - id: BR1.2
    statement: >
      The accepted count is shown at batch level as `accepted` of `total`.
    category: calculation
    applies_to: Batch summary
    trigger: Rendering a batch.
    logic: >
      IF rendering a batch
      THEN show how many seats have at least one accepted link, out of every
      seat on the batch.
    violation_behaviour: >
      A teacher cannot see the scale of who has joined without reading every
      row.
    source: AC1.3.5a

  - id: BR1.3
    statement: >
      The count is computed by the server and never by the client.
    category: constraint
    applies_to: Batch response
    trigger: Producing a batch summary.
    logic: >
      IF a count of accepted seats is needed
      THEN the response carries it
      AND the client never counts rows to derive it.
    violation_behaviour: >
      The client decides what counts as accepted, which is the layer boundary
      this project holds. It is also wrong the moment the roster paginates:
      a client can only count the rows it holds.
    source: TC-9, D-31
    notes: >
      D2 is where this habit is set for D3's fee status and D5's cross-batch
      dues, both of which are the same shape and more consequential.

  - id: BR1.4
    statement: >
      The denominator counts every seat the teacher created, declined ones
      included.
    category: calculation
    applies_to: Batch summary
    trigger: Computing the count.
    logic: >
      IF counting the total
      THEN include seats whose links are pending, accepted or declined
      AND exclude none of them.
    violation_behaviour: >
      The denominator shrinks silently as people decline, so "9 of 12" becomes
      "9 of 11" with nothing having been removed, and the teacher cannot tell
      the difference between a decline and a removal.
    source: AC1.3.5a
    notes: >
      A declined seat is still a seat the teacher created, and the teacher's
      remedy for it is to correct the number rather than to forget it.

  - id: BR1.5
    statement: >
      Creating a seat sends nothing to the person named, and declining one
      sends nothing to the teacher.
    category: policy
    applies_to: Seat creation, decline
    trigger: A teacher adds a seat; a holder declines one.
    logic: >
      IF a teacher creates a seat
      THEN send no SMS, push or other outbound message to that number for
      this purpose, and let the person discover it when they sign in
      AND IF a holder declines a seat
      THEN send the teacher no notification; the roster mark is where they
      already look.
    violation_behaviour: >
      A stranger on a mistyped number receives an unsolicited message naming
      a child's class, which is the exposure the acceptance model exists to
      close, arriving by a different route.
    source: AC1.3.2a, AC1.15.4
    notes: >
      Recorded as a rule because it is an ABSENCE, and the pressure to add a
      notification is real: "the teacher should know" reads as helpful. It is
      not, for the same reason the decline carries no reason [AC1.15.3] —
      asking a stranger to explain themselves is worse than letting them
      refuse. The roster count and the declined mark are the teacher's
      channel.

  - id: BR1.6
    statement: >
      A seat nobody accepts stays pending indefinitely: no expiry, no
      automatic deactivation, no prompt to clean it up.
    category: policy
    applies_to: Seat lifecycle
    trigger: Time passing with a seat unanswered.
    logic: >
      IF a seat has been pending for any length of time
      THEN leave it pending
      AND do not expire it, deactivate it, or decorate it as stale.
    violation_behaviour: >
      A seat vanishes or changes state without anyone acting, so a teacher's
      roster differs from what they recorded for reasons nobody chose.
    source: AC1.15.1, FR1.9e
    notes: >
      Stated explicitly because an expiry is the obvious thing to add and
      inventing a window now would guess at a problem nobody has reported.
      It also interacts with BR1.4: an expiring seat would shrink the
      denominator the same way excluding declined seats would.

  # ---- Group 2: what the roster shows. ----

  - id: BR2.1
    statement: >
      A seat held by two people shows both link states separately, and the
      seat appears once.
    category: policy
    applies_to: Roster row
    trigger: Rendering a seat with both a student and a guardian link.
    logic: >
      IF a seat carries both links
      THEN render one row carrying both decisions
      AND never collapse them into a single seat state.
    violation_behaviour: >
      A student who accepted and a guardian who declined collapse to one
      value, and either choice is wrong: the student is enrolled and owes a
      fee, the guardian simply does not watch.
    source: AC1.10.7, FR1.9b, FR1.9h
    notes: >
      D1 stored the two columns per link [D1 BR5.2]; this rule is the
      rendering half, and it is the reason the response shape has to widen.

  - id: BR2.2
    statement: >
      A link that does not exist reports `absent`, never `pending`.
    category: validation
    applies_to: Roster row, guardian link
    trigger: Rendering a seat with no guardian recorded.
    logic: >
      IF a seat has neither a teacher-typed guardian number nor a guardian
      account
      THEN report the guardian state as `absent`
      AND do not count it as a decision anybody was asked for
      ELSE report that link's own decision.
    violation_behaviour: >
      The batch count is wrong by exactly the number of guardian-less seats,
      because a decision nobody was asked for is counted as outstanding.
    source: functional-spec section 1
    notes: >
      **The link is the teacher-typed number, not the account id.** Both
      columns are nullable and a seat genuinely can have no guardian, so this
      is a real case rather than a defensive one — but keying absence on
      `guardian_account_id` alone is wrong in the expensive direction. That
      column is filled only at signup, so every guardian a teacher recorded
      who has not yet signed up would read `absent` when they are genuinely
      `pending`: they were asked and have not answered. That inverts this
      rule's own violation, dropping those seats OUT of the outstanding
      figure rather than counting them in.

  - id: BR2.3
    statement: >
      A declined seat shows the bare number, not the teacher-typed name.
    category: policy
    applies_to: Roster row
    trigger: Rendering a declined seat.
    logic: >
      IF a seat's link is declined
      THEN show the number the teacher typed
      AND do not show the display name.
    violation_behaviour: >
      A name is displayed for a person who has said the seat is not theirs.
    source: AC1.3.3a, ADR-012
    notes: >
      The name is RETAINED — it is the teacher's own record of who they meant
      to add, and the commonest cause of a decline is a mistyped number they
      need to correct — and it is not displayed. Retention and display are
      different decisions and the governance manifest records the first.

  - id: BR2.4
    statement: >
      A seat nobody ever accepted is distinguishable on the roster from one
      that was accepted and then erased.
    category: policy
    applies_to: Roster row
    trigger: Rendering a seat whose links name no live account.
    logic: >
      IF no link ever accepted
      THEN show the seat as never accepted
      ELSE IF a link accepted and that account was later erased
      THEN show the seat as erased
      AND never render the two the same way.
    violation_behaviour: >
      A teacher cannot tell a mistyped number from a person who left, and
      the two call for opposite actions: correct the number, or leave the
      record alone.
    source: AC1.3.6a
    notes: >
      The two are already distinguishable in the DATA — the erasure markers
      are a separate axis from the decisions [D1 BR6.2] — and this rule is
      that the roster must not collapse them. It is the display half of the
      same distinction BR3.2 carries for the refusal message, and they must
      agree: a seat the roster shows as erased must refuse removal with
      `ENROLLMENT_ERASED`.

  # ---- Group 3: what the roster permits. ----

  - id: BR3.1
    statement: >
      Removability is read from the server's decision, never inferred from the
      link states the row carries.
    category: authorization
    applies_to: Roster row, removal action
    trigger: Rendering a seat's actions.
    logic: >
      IF deciding whether to offer removal
      THEN read the server's removability decision
      AND never derive it from the displayed link states.
    violation_behaviour: >
      The removability rule moves into the client, which is exactly where D1
      just finished moving it out of for merged code of the same shape.
    source: AC2.5.1a
    notes: >
      It could be derived from the two link states today. Deriving it is the
      trap: the rule lives in `remove_enrollment` and reads the erasure
      markers too [D1 BR7.1], which the row does not carry.

  - id: BR3.2
    statement: >
      The two removal refusals carry distinct codes and distinct remedies.
    category: policy
    applies_to: Removal failure
    trigger: A refused removal.
    logic: >
      IF removal is refused because a link accepted
      THEN say the seat may be marked inactive instead
      ELSE IF refused because the account was erased
      THEN say the seat cannot be reused at all.
    violation_behaviour: >
      One message for both leaves a teacher trying the remedy that cannot
      work.
    source: AC1.3.6a
    notes: >
      The built code already returns `ENROLLMENT_CLAIMED` and
      `ENROLLMENT_ERASED` as different codes for this reason; D2 is where the
      difference becomes visible to a person.

  # ---- Group 4: the guardian's view. ----

  - id: BR4.1
    statement: >
      A guardian reaches children through their own guardian link, never
      through the child.
    category: authorization
    applies_to: Guardian child list
    trigger: Listing a guardian's children.
    logic: >
      IF listing the seats a guardian may see
      THEN find them through this account's guardian links
      AND never by finding the children and then their enrollments.
    violation_behaviour: >
      A guardian recorded by teacher A sees teacher B's batch for the same
      child: two teachers' records merged.
    source: NFR14.15
    notes: >
      Built and unchanged; cited because D2 is the unit that renders it and a
      future convenience query is where it would be undone.

  - id: BR4.2
    statement: >
      Switching children replaces the view rather than stacking it.
    category: constraint
    applies_to: Guardian home navigation
    trigger: Selecting a different child.
    logic: >
      IF a guardian switches child
      THEN replace the current scope
      AND Back must not reach the previous child's data.
    violation_behaviour: >
      Back lands in another scope of the same lens, which is a privacy failure
      wearing navigation's clothes.
    source: AC9.4.2
    notes: >
      The one back-stack obligation in D2 worth testing rather than assuming,
      because it is the only place two scopes of one lens are adjacent.
```

---

## Rules summary

| ID | Category | In one line |
|---|---|---|
| BR1.1 | policy | Declined is marked per row; pending is not |
| BR1.2 | calculation | The batch shows accepted of total |
| BR1.3 | constraint | **The server counts, never the client** |
| BR1.4 | calculation | The denominator includes declined seats |
| BR1.5 | policy | **Nothing is sent** — not to the person added, not to the teacher on a decline |
| BR1.6 | policy | A pending seat stays pending: no expiry, no auto-deactivation |
| BR2.1 | policy | Two holders, two states, one row |
| BR2.2 | validation | A missing link is `absent`, not `pending` |
| BR2.3 | policy | A declined seat shows the number, not the name |
| BR2.4 | policy | Never-accepted is distinguishable from accepted-then-erased |
| BR3.1 | authorization | Removability is the server's decision |
| BR3.2 | policy | Two refusals, two remedies |
| BR4.1 | authorization | Guardians reach children through their own link |
| BR4.2 | constraint | A child switch replaces; Back stays out |

## What D2 does not re-decide

The authorization rules this unit **renders** were built in D1 and are cited
rather than restated: a lens needs `accepted` [D1 BR1.1], a decision is per
link [D1 BR5.2], a decline is reversible by its holder [D1 BR5.4], and
removability and dormancy read the decision columns [D1 BR7.1, BR7.2].

Restating them here would create two places to change one rule, which is the
failure the unit boundary exists to prevent.

## Assumptions & Open Questions

- **Assumed**: BR1.2's "at least one accepted link" is the right definition of
  an accepted seat. A seat whose student accepted is a seat somebody joined,
  whatever the guardian did.
- **Open, and D3's**: what a declined seat shows for its fee. These rules
  govern the roster's acceptance axis; the money axis has no ledger until D3.
