# Functional Design Questions — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`. Only questions that need judgement are asked
here. Everything the requirements, ADR-004 to ADR-006, ADR-009, contracts C2
and C3, and the accepted review points already settle is carried into the
artifacts without a question. The person directed: "don't wait for my approval.
Go with your recommendations." Each answer below is the recommended option,
listed as A, and was left to the agent.

## Question 1: How is the password confirmed when a replacement is requested bound to the verify that completes it?

Context: C2 puts the password on `POST /v1/me/contact` (the request that sends
the code) and leaves `POST /v1/me/contact/verify` unchanged. Codes are stored
per destination, not per account (`otp_request` has no account column). Without
a binding, a person who controls a session on account B but not B's password,
and who also controls the new destination, can obtain a replacement code by
requesting it from another account whose password they know, then spend it on
B's session. That is exactly the takeover ADR-006 exists to stop.

A. A replacement code has its own purpose (`contact_replace`) and records the account that requested it, after its password was confirmed. Verify treats a request as a replacement when the account already holds a contact of that kind, and accepts only the latest `contact_replace` code for that destination whose recorded account is the verifying account. One nullable account column is added to the code-request record (an addition to C3's `u2_adds`)
B. A separate purpose only, with no account binding (leaves the cross-account gap open)
C. Ask for the password again on verify (changes the C2 verify request)
D. A separate short-lived "replacement grant" record, created at request time and consumed at verify
X. Other (please specify)

[Answer]: A

## Question 2: What does the already-added lookup answer when a lookup ceiling refuses it?

Context: review point R-06 settles that the email path answers HTTP 429
`auth.lookup.too_many`. Today the phone path refuses through `CeilingBreach`, a
`ConflictError` (409) with `signup.temporarily_unavailable`. One route answering
two different refusals depending on which parameter was sent is avoidable.

A. Both the phone and the email paths answer HTTP 429 `auth.lookup.too_many`, `retryable: false`, with no retry-after hint; the same refusal U1's availability lookup uses
B. The email path answers 429 `auth.lookup.too_many`; the phone path keeps its 409 `signup.temporarily_unavailable`
C. Both keep the existing 409 `signup.temporarily_unavailable` (contradicts the accepted review point)
X. Other (please specify)

[Answer]: A

## Question 3: What happens to centre manager rows that store an empty string as the invited phone?

Context: `create_centre` writes `invited_phone = phone or ""` for the manager
row, so a centre created by an email-only account has `""` today. Once
`invited_phone` is nullable with an at-least-one CHECK and `MemberResponse.phone`
is nullable, `""` is a second spelling of "no phone".

A. New rows write no phone (null) and the creating account's email as `invited_email`; existing `""` rows are left as stored (they are already linked and accepted, and `""` never equals a canonical number); every response presents `""` as null, so clients see one spelling
B. The U2 migration also rewrites `""` to null and fills `invited_email` from the linked account, leaving a row whose account is gone as `""`
C. Keep writing `""` for new manager rows
X. Other (please specify)

[Answer]: A

## Question 4: What happens when linking would give one account two student links in the same batch?

Context: `uq_enrollment_batch_student` allows one student link per account per
batch. With email, a teacher can record the same child twice in one batch, once
by phone and once by email (two student records). When one account holds both,
the second link would violate the index, which today would fail the whole
sign-up or contact-add transaction.

A. Matching skips that seat (it stays unlinked, nothing fails, and the teacher still sees it waiting); a teacher save or edit that would create the second link is refused with the existing `enrollment.student_already_in_batch`
B. Fail the match, so the sign-up or contact add fails
C. Link it and unlink the other seat
X. Other (please specify)

[Answer]: A

## Question 5: What counts against the 5-per-day contact-change ceiling, and when?

A. A completed replacement and a completed removal each count one, consumed in the transaction that makes the change (so a failed or abandoned change costs nothing); the replacement request step only checks the ceiling, so a person at the limit is refused before a code is sent; adding a missing contact does not count (it is bounded by there being at most one of each kind and by the existing send ceilings)
B. Count at the request step, whether or not the change completes
C. Count adds as well as replacements and removals
X. Other (please specify)

[Answer]: A

## Question 6: How is a new student identified when the phone and the email typed point at existing students?

Context: today a typed student phone that belongs to an archived student
revives that student, and one that belongs to an active student is refused (or
reused on the add-to-batch path). With a second unique contact, the two can
disagree.

A. The phone identifies first, as today. The email must then be unused among this teacher's students or belong to the same student, otherwise `student.email.taken`. With no phone, the email identifies by the same rules the phone follows (active: refuse; archived: revive)
B. Refuse whenever either contact matches an archived student
C. Email identifies first
X. Other (please specify)

[Answer]: A
