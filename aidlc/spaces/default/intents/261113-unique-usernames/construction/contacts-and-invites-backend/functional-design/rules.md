# Business Rules — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2. Source of truth for this unit's
decision logic. `test_first: true` marks a rule that meets the team's
test-first predicate (team.md, Testing Posture): the correct output is knowable
from the requirement before the code exists, and a wrong answer is an
authorization error. Those tests are written first. The other rules are
test-after, written from the rule, not from the implementation.

Groups: BR1 recording emails; BR2 link target on a teacher or centre save;
BR3 ContactMatching; BR4 the already-added lookup; BR5 contact changes on an
account.

```yaml
rules:
  # ---------------------------------------------------------------- BR1
  - id: BR1.1
    statement: A teacher-recorded or centre-invited email is stored in one canonical form.
    category: validation
    applies_to: [Student.student_email, Student.guardian_email, OwnerMember.invited_email, already-added lookup email]
    trigger: A student create or edit, a centre invitation, or an already-added lookup carries an email
    logic: >
      IF an email is given THEN trim it, lowercase it, and accept it only when
      it is at most 254 characters with one @, no whitespace and a dot in the
      domain (the existing canonical email rule); an empty or whitespace-only
      value is treated as absent on create and as "clear it" on edit only when
      sent as null.
    violation: Refused with email.invalid (ValidationError, 400); nothing is written and the form keeps what was typed.
    source: [FR6.1, FR6.4, FR6.7]
    test_first: false

  - id: BR1.2
    statement: A student email is unique among one teacher's students.
    category: constraint
    applies_to: [Student.student_email]
    trigger: A student create or an edit that sets student_email
    logic: >
      IF another student of the same owner, archived or not, already has this
      student_email THEN the save is refused (subject to BR1.7's identification
      rule on create). A database uniqueness rule on (owner, student_email)
      where present is the backstop; a concurrent duplicate that reaches it is
      mapped to the same refusal, never a server error.
    violation: Refused with student.email.taken (ConflictError, 409, code STUDENT_EMAIL_TAKEN).
    source: [FR6.2]
    test_first: false

  - id: BR1.3
    statement: A guardian email is not unique.
    category: constraint
    applies_to: [Student.guardian_email, Enrollment.guardian_email]
    trigger: A student create or edit that sets guardian_email
    logic: IF the same guardian_email is recorded on several students THEN all are accepted, exactly as guardian_phone is.
    violation: None (no refusal exists for this case).
    source: [FR6.2]
    test_first: false

  - id: BR1.4
    statement: Teacher-recorded emails are teacher-written data under their own names, never the account's email.
    category: authorization
    applies_to: [StudentCreateRequest, StudentUpdateRequest, StudentResponse, MemberResponse]
    trigger: Any response that carries a recorded email
    logic: >
      IF a response carries a teacher-recorded email THEN it is named
      student_email or guardian_email (invited_email for a centre) and is
      returned only on the owning teacher's (or centre manager's) responses;
      it is never read from or written to Account.email, and no student,
      guardian, membership or administrator response carries it.
    violation: A schema carrying it elsewhere fails the existing schema-wide privacy gate in CI.
    source: [FR6.3]
    test_first: false

  - id: BR1.5
    statement: Every seat carries the student's current emails, written in the same transaction as the student.
    category: constraint
    applies_to: [Enrollment.student_email, Enrollment.guardian_email]
    trigger: A student create, edit, revive, or a new seat
    logic: >
      IF a student's emails are set or changed THEN every seat of that student
      receives the same values in the same transaction; a new seat copies them
      at creation, as it copies the phones.
    violation: Not reachable through the API; a divergence is a defect caught by the roster tests.
    source: [FR6.1]
    test_first: false

  - id: BR1.6
    statement: A guardian recorded only by email is pending, not absent.
    category: calculation
    applies_to: [roster guardian state per seat, student guardian_state]
    trigger: Any read that reports a guardian link's state
    logic: >
      IF guardian_phone, guardian_email and guardian_account_id are all absent
      THEN the guardian state is absent ELSE it is the guardian decision. Both
      existing predicates (the roster's per-seat guardian state and the
      student list's has-guardian test) read guardian_email; adding the column
      without changing them would report every email-only guardian as absent.
    violation: Wrong state shown to the teacher and a wrong count of outstanding decisions.
    source: [FR6.1]
    test_first: false

  - id: BR1.7
    statement: On create, the phone identifies an existing student first; the email must agree.
    category: validation
    applies_to: [student create path]
    trigger: A student create that carries a student_phone, a student_email or both
    logic: >
      IF a student_phone is given THEN the existing phone rule identifies the
      student (active: refused; archived: revived). THEN IF a student_email is
      given and belongs to a different student of this owner, the create is
      refused. IF no student_phone is given and the student_email belongs to
      an active student THEN refused; IF it belongs to an archived student
      THEN that student is revived with the typed name and guardian contacts,
      as the phone path does. (Question 6.)
    violation: Refused with student.phone_taken or student.email.taken (409).
    source: [FR6.2]
    test_first: false

  - id: BR1.8
    statement: A centre invites by phone, by email, or both, and a live contact is invited once per centre.
    category: validation
    applies_to: [OwnerMember, MemberInviteRequest]
    trigger: A centre manager invites a member
    logic: >
      IF neither phone nor email is given THEN refused. IF a live (unrevoked)
      invitation of this centre already has the phone, or already has the
      email THEN refused. A concurrent duplicate that reaches either database
      uniqueness rule is mapped to the same refusal.
    violation: Missing both is a request validation error (422); a duplicate is centre.member.already_invited (409).
    source: [FR6.4]
    test_first: false

  - id: BR1.9
    statement: A member response carries the invited phone as optional and the invited email.
    category: constraint
    applies_to: [MemberResponse]
    trigger: Listing or creating centre members
    logic: >
      IF an invitation has no phone THEN phone is null; a legacy stored empty
      phone is also presented as null; invited_email is returned when present.
      New manager rows written at centre creation store no phone when the
      creating account has none, and store its email. (Question 3.)
    violation: Not applicable; covered by the response tests.
    source: [FR6.4]
    test_first: false

  - id: BR1.10
    statement: Email recording enters through the student routes and the centre member route only.
    category: policy
    applies_to: [batch add-seat route, staff console invite]
    trigger: A seat added through the batch roster route, or a teacher invited from the staff console
    logic: >
      IF a seat is added through the batch add-seat route THEN no email is
      accepted there (C2 does not extend it); its student gains emails through
      the student edit route. IF the staff console invites a teacher THEN it
      stays phone-only (admin routes do not change). Both still write through
      the one invitation writer and the one seat writer, so every rule above
      applies to what they write.
    violation: Not applicable.
    source: [FR6.1, FR6.4]
    test_first: false

  - id: BR1.11
    statement: The batch roster row shows the recorded emails beside the recorded phones.
    category: constraint
    applies_to: [RosterRow (app/batches/service.py), RosterRowResponse (app/schemas/batches.py), its mapper (app/api/batches.py)]
    trigger: Any roster read or a seat just created through the roster
    logic: >
      IF a seat records guardian_email or student_email THEN the roster row
      and its response carry them as guardian_email and student_email (null
      when not recorded), beside guardian_phone, so a guardian recorded only
      by email shows as pending with a contact rather than with none. These
      are teacher-written fields on a teacher-lens response (BR1.4).
    violation: Not applicable; covered by the roster response tests and the privacy gate.
    source: [FR6.1, FR6.3]
    test_first: false

  # ---------------------------------------------------------------- BR2
  - id: BR2.1
    statement: "The one precedence rule: when a link records a phone, only that phone's account may take it; the email is used only when the link records no phone."
    category: authorization
    applies_to: [Enrollment student link, Enrollment guardian link, OwnerMember link]
    trigger: Every path that writes a link (teacher save, centre invite, ContactMatching)
    logic: >
      The link target of a record's link is: IF the link is relink-blocked
      THEN none; ELSE IF the link records a phone THEN the account holding
      that phone, or none; ELSE IF it records an email THEN the account holding
      that email, or none; ELSE none. A save is never refused because the
      phone and the email belong to different accounts, so the teacher learns
      nothing about who holds which contact.
    violation: A link to the wrong account is an authorization error (a stranger receives a seat invitation that can become a lens).
    source: [FR6.5, FR6.6]
    test_first: true

  - id: BR2.2
    statement: A save links a record's link to its target at once, and states the decision.
    category: policy
    applies_to: [seat creation, student revive, centre invitation]
    trigger: A seat or an invitation is written
    logic: >
      IF the BR2.1 target exists THEN the link is set to it; the seat decision
      is pending unless the same account already accepted another seat of this
      student (existing carried-decision rule); an invitation is pending. IF no
      target exists THEN the link stays empty until ContactMatching links it.
    violation: Not applicable.
    source: [FR6.5]
    test_first: false

  - id: BR2.3
    statement: Changing a recorded contact relinks that link and resets it to pending.
    category: authorization
    applies_to: [student edit]
    trigger: A teacher changes student_phone or student_email (student link), or guardian_phone or guardian_email (guardian link), to a different value, including clearing it
    logic: >
      IF a contact of a link changes THEN on the student and every seat the
      new value is written, the link is set to the BR2.1 target computed from
      the link's contacts after the change (possibly none), and the link's
      decision becomes pending. This is the existing phone rule, extended to
      email unchanged; it applies whether or not the change alters the target.
    violation: A link left on the old account after its contact changed would keep a person attached to a record the teacher re-addressed.
    source: [FR6.6]
    test_first: true

  - id: BR2.4
    statement: A recorded contact cannot change on a link that was accepted or erased.
    category: authorization
    applies_to: [student edit]
    trigger: A teacher changes any contact of a link
    logic: >
      IF on any seat of the student that link is accepted THEN refused; ELSE
      IF on any seat that link is relink-blocked THEN refused. Checked before
      anything is written, and only after the student's seat rows are locked
      (BR2.6), so the decision read is the decision in force when the write
      happens. The name can always change.
    violation: Refused with student.number_accepted (STUDENT_NUMBER_ACCEPTED) or student.number_erased (STUDENT_NUMBER_ERASED), both 409, the existing keys now also covering email.
    source: [FR6.6]
    test_first: true

  - id: BR2.5
    statement: A save never gives one account two student links in one batch.
    category: constraint
    applies_to: [seat creation, student edit]
    trigger: A seat is created, or a student edit relinks the student link
    logic: >
      IF the BR2.1 student target already holds the student link of another
      seat in the same batch, OR another seat in that batch records the same
      student phone or the same student email THEN the save is refused.
      (Question 4.)
    violation: Refused with enrollment.student_already_in_batch (409), never a database error.
    source: [FR6.5]
    test_first: false

  - id: BR2.6
    statement: A teacher's contact edit and a holder's accept, decline or erasure on the same seats serialise on the seat rows.
    category: authorization
    applies_to: [student edit, seat creation, seat accept and decline, account erasure, ContactMatching]
    trigger: A teacher edits a student's contacts, or creates a seat for a student, while a holder decides, an account is erased, or a match runs
    logic: >
      The edit and the seat-creation paths lock every existing seat row of
      the student for update, in ascending seat id order, before the BR2.4
      check and before reading sibling decisions and blocked markers, and
      hold the lock to their commit. The accept and decline write, the
      erasure write and every match statement change seat rows only through
      an update whose condition names the link's current state (the holder's
      account for accept and decline; an empty link for matching), which
      takes the same row lock and re-evaluates its condition against the
      committed row once the edit releases it. THEREFORE: IF the accept
      commits first THEN the edit sees accepted and is refused (BR2.4); IF the
      edit commits first THEN the accept finds the link no longer names the
      holder and changes nothing, and the holder sees the seat leave their
      invitations. No order lets an accepted decision be reset or re-pointed.
    violation: Without the lock, an accepted link's contact could change and its decision be reset to pending under concurrency.
    source: [FR6.6]
    test_first: true

  - id: BR2.7
    statement: A save that resolves a link target and a match for the same contact serialise on that contact.
    category: constraint
    applies_to: [seat creation, student create and edit, centre invitation, match_contact]
    trigger: A save resolving a target from a contact, or match_contact for a contact
    logic: >
      Both paths take a transaction-scoped advisory lock keyed on a hash of
      "contact:" plus the contact's kind and canonical value, held to commit.
      A save takes one lock per distinct contact it resolves, in ascending key
      order, before resolving targets and before the seat row locks of BR2.6;
      match_contact takes the lock for its one contact before its first
      statement. THEREFORE a seat or invitation saved while a match for its
      contact runs either sees the matched account at save time (match
      committed first) or is seen by the match (save committed first); none
      is left unlinked by the race.
    violation: Without it, a record saved during the match window stays unlinked until that contact is verified again, which may be never.
    source: [FR6.5]
    test_first: false

  # ---------------------------------------------------------------- BR3
  - id: BR3.1
    statement: ContactMatching runs once per newly verified contact, at three moments, inside the caller's transaction.
    category: policy
    applies_to: [ContactMatching]
    trigger: An account is created (the contact it was created with); a phone is added or replaces another; an email is added or replaces another
    logic: >
      IF a contact has just become an account's verified contact THEN the
      matcher is called with the account id and that contact, in the same
      transaction as the write that made it the account's, and asks
      StudentRoster and then CentreMembership to link their records. Its
      signature is match_contact(session, account_id, contact). The callers
      are the account-creation write and the contact add or replace write;
      U2 owns both call lines (C3).
    violation: A missed moment leaves an invitation unreachable; covered by one test per moment.
    source: [FR2.5, FR6, FR6.5]
    test_first: false

  - id: BR3.2
    statement: A phone links every unlinked, unblocked link that records that phone.
    category: authorization
    applies_to: [StudentRoster link statements, CentreMembership link statement]
    trigger: match_contact with a phone
    logic: >
      FOR each seat link (student, guardian) and each invitation: IF its
      recorded phone equals the contact AND it has no account AND it is not
      relink-blocked (seats) or revoked (invitations) THEN set its account to
      this account.
    violation: See BR3.4 to BR3.6 for what must never happen.
    source: [FR6.5]
    test_first: true

  - id: BR3.3
    statement: An email links only links that record no phone.
    category: authorization
    applies_to: [StudentRoster link statements, CentreMembership link statement]
    trigger: match_contact with an email
    logic: >
      FOR each seat link and each invitation: IF its recorded email equals the
      contact AND its recorded phone is absent AND it has no account AND it is
      not relink-blocked or revoked THEN set its account to this account. A
      link that records a phone is never linked by an email, now or later.
    violation: An email linking a phone-recorded link hands a seat to someone the teacher addressed by a different contact.
    source: [FR6.5, FR6.6]
    test_first: true

  - id: BR3.4
    statement: Matching sets links and never decisions.
    category: authorization
    applies_to: [ContactMatching, every link statement]
    trigger: Any link written by matching
    logic: >
      IF matching links a seat or an invitation THEN its decision columns are
      left exactly as they were (pending for every never-answered link);
      nothing in matching writes accepted or declined.
    violation: Writing accepted would grant a lens without the holder's decision.
    source: [FR2.5, FR6.6]
    test_first: true

  - id: BR3.5
    statement: A link that already has an account is never relinked by matching.
    category: authorization
    applies_to: [ContactMatching]
    trigger: A contact is verified by an account while records carrying it are linked to another account (recycled or removed contact)
    logic: IF a link already names an account THEN matching leaves it, whatever the contact.
    violation: Relinking would move a child's seat to whoever verifies a contact next.
    source: [FR6.6, FR8.3]
    test_first: true

  - id: BR3.6
    statement: Matching never links a relink-blocked seat link or a revoked invitation.
    category: authorization
    applies_to: [ContactMatching]
    trigger: match_contact
    logic: IF a seat link is relink-blocked, or an invitation is revoked, THEN it is not linked.
    violation: Linking would reattach records a person erased.
    source: [FR6.6]
    test_first: true

  - id: BR3.7
    statement: Matching skips a seat whose student link would give the account a second seat in one batch.
    category: constraint
    applies_to: [student link statements]
    trigger: match_contact finds a student link to set in a batch where this account already holds a student link, or where two candidate seats are in one batch
    logic: >
      IF setting the student link would make this account the student of two
      seats in one batch THEN that seat is left unlinked and the match
      continues; the guardian link has no such rule. Nothing fails.
      (Question 4.)
    violation: Without the rule the database uniqueness rule fails the whole sign-up or contact add.
    source: [FR6.5]
    test_first: false

  - id: BR3.8
    statement: Matching is idempotent.
    category: constraint
    applies_to: [ContactMatching]
    trigger: match_contact runs twice for the same account and contact
    logic: IF it runs again THEN it changes nothing, because every statement only fills an empty link.
    violation: Not applicable.
    source: [FR6.5]
    test_first: false

  - id: BR3.9
    statement: The phone-only call sites are replaced by the matcher, and only U2 edits them.
    category: policy
    applies_to: [account creation write, contact attach write, link_phone_seats, link_memberships, already_added]
    trigger: U2's change
    logic: >
      The "if phone: link_phone_seats" line in account creation, the
      "if phone: link_phone_seats" line in the contact attach write, the
      phone-only link_memberships signature, and the phone-only seat link
      statements are replaced by match_contact and contact-generic owner
      statements. link_phone_seats is removed once neither caller uses it.
      U1 adds only its username argument to account creation and does not
      edit these lines (C3).
    violation: Two units editing the same lines; the second to merge rebases.
    source: [FR2.5, FR6.5]
    test_first: false

  # ---------------------------------------------------------------- BR4
  - id: BR4.1
    statement: The already-added lookup takes exactly one of a phone or an email.
    category: validation
    applies_to: [GET /v1/accounts/already-added]
    trigger: A lookup request
    logic: IF neither or both are given THEN refused before any ceiling is counted or anything is read.
    violation: Request validation error (422).
    source: [FR6.7]
    test_first: false

  - id: BR4.2
    statement: The lookup discloses only that a seat exists and its role.
    category: authorization
    applies_to: [AlreadyAddedResponse]
    trigger: A lookup by phone or by email
    logic: >
      The answer is exactly: whether a teacher recorded the contact on a seat,
      and the role of the matched link (student preferred over guardian).
      Never whether an account exists for the contact, never a name, teacher,
      batch, enrollment id or fee; display_name stays empty when a seat
      exists, as today. For the email form, "a teacher recorded the contact"
      is decided only from what a teacher typed (BR4.3), never from any
      account's email, so the answer is identical whether or not an account
      holds the address. Centre invitations are not consulted by either form,
      because the response's role lock has no centre value.
    violation: Any wider answer turns a public route into an account or child oracle.
    source: [FR6.7]
    test_first: true

  - id: BR4.3
    statement: An email lookup reports only seats a teacher recorded with that email and no phone.
    category: authorization
    applies_to: [already-added lookup by email]
    trigger: A lookup by email
    logic: >
      A seat link matches IF it records this email AND records no phone for
      that link AND it is not relink-blocked, whether or not it is already
      linked. There is no account half: an email held by an account that is
      linked to a seat, but recorded on no seat, answers already_added false.
      The phone form keeps its existing matching exactly as today, account
      half included (out of this unit's scope).
    violation: Reporting a phone-recorded seat would promise a link BR3.3 never makes; an account half would make a true answer mean "an account holds this email", an account-existence oracle on a guessable identifier.
    source: [FR6.7]
    test_first: true

  - id: BR4.4
    statement: Both lookup kinds share the existing lookup ceilings and refuse with 429.
    category: policy
    applies_to: [already-added lookup]
    trigger: Every lookup, before anything is read
    logic: >
      The existing lookup cascade is consumed first, for every contact whether
      recorded or not: per contact per day (lk_number_day, keyed on the
      contact's rate_key, so an email counts as 'e:' plus its hash), per
      network per hour (lk_ip_hour), per coarse network per hour
      (lk_ip48_hour), and the global hourly alert (lk_global_hour, alert-only).
      IF a scope refuses THEN the answer is HTTP 429 auth.lookup.too_many,
      retryable false, with no retry-after hint, for both phone and email.
      (Question 2.)
    violation: Refused as stated; the refusal does not depend on whether a seat exists.
    source: [FR6.7]
    test_first: false

  # ---------------------------------------------------------------- BR5
  - id: BR5.1
    statement: Adding a missing contact is unchanged, and it matches.
    category: policy
    applies_to: [POST /v1/me/contact, POST /v1/me/contact/verify]
    trigger: The account has no contact of the kind sent
    logic: >
      IF the account has no contact of this kind THEN the request sends a
      code with no password (as today) and the verify, after the code is
      spent and the destination is found free, stores it and calls
      match_contact for it (now for email too, not only phone). A destination
      held by another account is refused only after the code, as today.
    violation: Existing refusals (code refused, account.contact.taken).
    source: [FR8, FR8.1]
    test_first: false

  - id: BR5.2
    statement: Replacing or removing a contact needs the account's password.
    category: authorization
    applies_to: [replacement request, removal]
    trigger: A replacement is requested (the account holds a contact of that kind) or a removal is requested
    logic: >
      IF the account has no password THEN refused with
      account.contact.password_required (the person sets one first). ELSE IF
      no password is sent THEN refused with account.contact.password_required.
      ELSE the password is checked under the existing per-account password
      failure ceilings (the 'acct:' key change_password uses); a wrong one is
      recorded and refused. Checked before any state is read that could
      differ by outcome.
    violation: account.contact.password_required (400) or auth.password.current_wrong (400); at the password ceiling, auth.password.too_many_attempts (409).
    source: [FR8, FR8.2]
    test_first: true

  - id: BR5.3
    statement: A replacement can be completed only by the account that confirmed its password for it.
    category: authorization
    applies_to: [replacement verify]
    trigger: A verify for a kind the account already holds
    logic: >
      IF the account already holds a contact of this kind THEN the verify is
      a replacement. The requester binding is part of row selection, not a
      check after it: the verify selects, and locks, the latest unexpired
      contact_replace code for that destination whose requesting account is
      this account. Another account's codes for the same destination are
      never selected, so they can neither shadow this account's code nor be
      spent, attempted or killed by this account's verify; a wrong code is
      recorded as an attempt only against the row this account selected. IF
      no such row exists THEN the code is refused with no attempt recorded
      against any code (the per-network verify-failure ceilings still count
      it, as today). IF the account does not hold that kind THEN only an add
      code (purpose contact) is selected. (Question 1.)
    violation: Code refused (existing auth.otp refusal), counted as a verify failure under the existing per-network ceilings.
    source: [FR8.2]
    test_first: true

  - id: BR5.4
    statement: A replacement verifies the new contact first, then removes the old, in one transaction.
    category: constraint
    applies_to: [replacement]
    trigger: A replacement verify with an accepted code
    logic: >
      IF the new destination equals the current one THEN the request was
      already refused at the request step (account.contact.already_set). IF
      the new destination is held by another account THEN refused after the
      code (account.contact.taken). ELSE in one transaction, with the account
      row locked: the change ceiling is consumed, the contact column takes the
      new value (the old is gone), match_contact runs for the new value,
      pending sign-up drafts for the new value are discarded, CONTACT_REPLACED
      is audited, and it commits. Any failure leaves the old contact in place.
    violation: As stated; never a state with both or neither.
    source: [FR8.2]
    test_first: false

  - id: BR5.5
    statement: The last verified contact cannot be removed.
    category: authorization
    applies_to: [removal]
    trigger: A removal of the only contact the account holds
    logic: >
      IF after the removal the account would hold no phone and no email THEN
      refused, with the account row locked so two concurrent removals cannot
      both pass. The database CHECK ck_account_has_identifier stays the
      backstop; a violation reaching it maps to the same refusal.
    violation: Refused with account.contact.last_one (409); the contact stays.
    source: [FR8.4]
    test_first: true

  - id: BR5.6
    statement: At most 5 contact changes per account per day.
    category: policy
    applies_to: [replacement, removal]
    trigger: A replacement request, a replacement verify, a removal
    logic: >
      The replacement request only reads the contact_chg_day count for the
      account (no increment) and refuses at the limit before a code is sent.
      A completed replacement or removal consumes one through a
      non-committing consume: the same upsert-and-compare the ceiling module
      uses, but without the commit the existing cascade consume performs
      after each scope (app/auth/ceilings.py, `_consume`), and without a
      separate committed release on breach. It runs inside the change's own
      transaction while the account row lock is held. GUARANTEE: the
      counter increment, the spent code (replacement) and the contact write
      commit together in the change's single commit, or all roll back
      together; the account row lock is held from its acquisition to that
      commit; a breach raises and the change's transaction is rolled back,
      so nothing is counted and the code stays unspent. The existing
      committing cascade is unchanged for every other scope. Adding a
      missing contact does not count. (Question 5.)
    violation: Refused with account.contact.change_limit (409).
    source: [FR8.2]
    test_first: false

  - id: BR5.7
    statement: Removing or replacing a contact never unlinks anything.
    category: authorization
    applies_to: [removal, replacement]
    trigger: A contact leaves an account
    logic: >
      IF a contact leaves the account THEN every seat link and invitation
      already linked to the account stays linked with its decision unchanged,
      so the account's lenses are the same before and after.
    violation: Unlinking would silently withdraw a child's records from the person the teacher meant.
    source: [FR8.3]
    test_first: true

  - id: BR5.8
    statement: A removed or replaced contact is free for another account.
    category: policy
    applies_to: [Account.phone, Account.email]
    trigger: A contact leaves an account
    logic: >
      IF a contact leaves an account THEN no record of it remains on the
      account, and another account may add and verify it. When one does,
      matching links only still-unlinked records (BR3.5).
    violation: Not applicable.
    source: [FR8.3]
    test_first: false

  - id: BR5.9
    statement: A best-effort notice goes to the removed contact after commit.
    category: policy
    applies_to: [RemovedContactNotice]
    trigger: A replacement or removal has committed
    logic: >
      After commit, one notice is sent to the contact that left: by email
      through the email gateway, or as one SMS segment counted against the
      existing daily SMS send budget. It is sent once, never retried; a
      failure or a refused budget is logged with the correlation id and the
      channel only, and never surfaced to the person. The text carries no
      username, no new contact, no account id and no code.
    violation: Not applicable (best-effort by design, the stated exception to "silent failures are not acceptable", as FCM).
    source: [FR8.2]
    test_first: false

  - id: BR5.10
    statement: A contact change signs no device out.
    category: policy
    applies_to: [replacement, removal]
    trigger: A replacement or removal commits
    logic: IF a contact changes THEN no token family is revoked and every signed-in device keeps working; each reads the new contacts on its next GET /v1/me.
    violation: Not applicable.
    source: [FR8.2]
    test_first: false

  - id: BR5.11
    statement: Contact changes are audited by account id only.
    category: policy
    applies_to: [AuthAuditEvent]
    trigger: A replacement or removal commits
    logic: >
      IF a contact is replaced THEN CONTACT_REPLACED; IF removed THEN
      CONTACT_REMOVED; each row carries the account id and correlation id and
      never the phone, email, kind of value, code or username. No log line
      carries a contact or a username.
    violation: A contact in a log or audit row is a privacy defect.
    source: [FR8.2]
    test_first: false

  - id: BR5.12
    statement: Removing a kind the account does not hold changes nothing.
    category: policy
    applies_to: [removal]
    trigger: A removal of a kind the account has no value for
    logic: >
      IF the account holds no contact of that kind (after the password check)
      THEN the answer is the current account, nothing is counted, audited or
      sent.
    violation: Not applicable.
    source: [FR8.2]
    test_first: false

  - id: BR5.13
    statement: A contact on the platform-administrator allowlist cannot be removed or replaced.
    category: authorization
    applies_to: [replacement request, replacement verify, removal]
    trigger: The contact that would leave the account is on the administrator allowlist
    logic: >
      Administrator status is computed per call from an account's current
      phone and email against the deploy-time allowlist, so a freed
      allowlisted contact would make whichever account verifies it next an
      administrator (BR5.8). THEREFORE IF the contact that would leave the
      account (the current value of the kind being replaced, or the kind
      being removed) is on the allowlist THEN the request is refused, after
      the password check, at the replacement request, again at the
      replacement verify (the allowlist may have changed in between), and at
      removal. Membership is read exactly as administrator status reads it
      (the same allowlist function, canonical comparison). To change such
      a contact, the allowlist entry is first changed at deploy time.
      Administrator behaviour itself is unchanged.
    violation: Refused with account.contact.admin_locked (ConflictError, 409); the contact stays.
    source: [FR8.3]
    test_first: true
```

## Rules summary

| ID | Rule | Category | Test-first | Source |
|---|---|---|---|---|
| BR1.1 | Recorded and looked-up emails are canonical (trimmed, lowercased, valid) | validation | no | FR6.1, FR6.4, FR6.7 |
| BR1.2 | Student email unique per teacher, archived included | constraint | no | FR6.2 |
| BR1.3 | Guardian email not unique | constraint | no | FR6.2 |
| BR1.4 | Recorded emails are teacher-written, under distinct names | authorization | no | FR6.3 |
| BR1.5 | Seats carry the student's emails, same transaction | constraint | no | FR6.1 |
| BR1.6 | Email-only guardian is pending, not absent (two predicates) | calculation | no | FR6.1 |
| BR1.7 | Phone identifies a student first; the email must agree | validation | no | FR6.2 |
| BR1.8 | Centre invites by phone, email or both; one live invitation per contact | validation | no | FR6.4 |
| BR1.9 | Member response phone optional, invited_email added, legacy "" read as null | constraint | no | FR6.4 |
| BR1.10 | Batch add-seat route and staff console stay without email | policy | no | FR6.1, FR6.4 |
| BR1.11 | Roster row shows recorded student and guardian emails | constraint | no | FR6.1, FR6.3 |
| BR2.1 | The one precedence rule (phone owns the link; email only without phone) | authorization | yes | FR6.5, FR6.6 |
| BR2.2 | A save links to the target at once and states the decision | policy | no | FR6.5 |
| BR2.3 | Changing a recorded contact relinks and resets to pending | authorization | yes | FR6.6 |
| BR2.4 | No contact change on an accepted or erased link | authorization | yes | FR6.6 |
| BR2.5 | A save never makes one account a student twice in a batch | constraint | no | FR6.5 |
| BR2.6 | Teacher edit and holder accept/decline/erase/match serialise on locked seat rows | authorization | yes | FR6.6 |
| BR2.7 | Save and match for one contact serialise on a contact advisory lock | constraint | no | FR6.5 |
| BR3.1 | Matcher runs per verified contact at three moments, in the caller's transaction | policy | no | FR2.5, FR6, FR6.5 |
| BR3.2 | A phone links unlinked, unblocked links recording it | authorization | yes | FR6.5 |
| BR3.3 | An email links only links that record no phone | authorization | yes | FR6.5, FR6.6 |
| BR3.4 | Matching never writes a decision | authorization | yes | FR2.5, FR6.6 |
| BR3.5 | A linked link is never relinked | authorization | yes | FR6.6, FR8.3 |
| BR3.6 | Blocked seat links and revoked invitations are never linked | authorization | yes | FR6.6 |
| BR3.7 | Matching skips a second student link in one batch | constraint | no | FR6.5 |
| BR3.8 | Matching is idempotent | constraint | no | FR6.5 |
| BR3.9 | Phone-only call sites replaced by the matcher; U2 owns those lines | policy | no | FR2.5, FR6.5 |
| BR4.1 | Lookup takes exactly one of phone or email | validation | no | FR6.7 |
| BR4.2 | Lookup discloses only seat existence and role | authorization | yes | FR6.7 |
| BR4.3 | Email lookup: only seats recording the email and no phone; no account half | authorization | yes | FR6.7 |
| BR4.4 | Shared lookup ceilings, 429 `auth.lookup.too_many` for both kinds | policy | no | FR6.7 |
| BR5.1 | Adding a missing contact unchanged, and it matches (email too) | policy | no | FR8, FR8.1 |
| BR5.2 | Replace and remove need the password | authorization | yes | FR8, FR8.2 |
| BR5.3 | Replacement code selected by requester; others' codes never touched | authorization | yes | FR8.2 |
| BR5.4 | Replacement: new verified, old removed, one transaction | constraint | no | FR8.2 |
| BR5.5 | Last contact cannot be removed | authorization | yes | FR8.4 |
| BR5.6 | At most 5 completed changes per day; non-committing consume in the change's transaction | policy | no | FR8.2 |
| BR5.7 | A contact leaving never unlinks anything | authorization | yes | FR8.3 |
| BR5.8 | A removed contact is free for another account | policy | no | FR8.3 |
| BR5.9 | Best-effort notice to the removed contact, after commit | policy | no | FR8.2 |
| BR5.10 | No device is signed out | policy | no | FR8.2 |
| BR5.11 | Contact changes audited by account id only | policy | no | FR8.2 |
| BR5.12 | Removing an absent kind changes nothing | policy | no | FR8.2 |
| BR5.13 | An allowlisted administrator contact cannot be removed or replaced | authorization | yes | FR8.3 |
