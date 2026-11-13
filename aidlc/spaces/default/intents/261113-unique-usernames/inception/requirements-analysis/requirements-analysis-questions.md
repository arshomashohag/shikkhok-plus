# Requirements Analysis Questions — Unique usernames

The four product decisions in the change request are settled and are not asked
again here: one sign-in field for username, phone or email; the username
character rules; renameable with a hold on the old name; teachers recording an
email as well as a phone. These questions cover only what the request leaves
open after the code scan.

## Question 1: How long is a released username held before anyone else can take it?

When a person renames, or deletes their account, their old username is held so
nobody can impersonate them by taking it straight away.

A. 30 days
B. 90 days
C. 180 days
D. Never released (a username, once used, is retired forever)
E. Not held at all (free immediately)
X. Other (please specify)

[Answer]: A

## Question 2: How often may a person change their username?

A. At most once every 30 days
B. At most once every 7 days
C. No limit
X. Other (please specify)

[Answer]: A

## Question 3: May a person remove or replace a phone or email they added?

The request says an account must keep at least one verified phone or email.
Today contacts can only be added, never removed or replaced.

A. Yes: remove or replace either, as long as one verified contact remains. Seats and memberships already linked stay linked to the account.
B. Yes, but removing a contact also unlinks any seat that was matched through it and is not yet accepted
C. No: keep contacts add-only, as today
X. Other (please specify)

[Answer]: A

## Question 4: How does sign-up tell the person whether a username is free?

A live check reveals that a username exists (never who holds it). Usernames are owner-private, so nobody can look up whose it is.

A. Live check while typing, through a rate-limited public lookup, and checked again when the account is created
B. No live check: the person learns only when they submit the form (still checked at account creation)
X. Other (please specify)

[Answer]: A

## Question 5: Do coaching-centre invitations to member teachers also accept an email?

Centres invite member teachers by phone today (`owner_member.invited_phone`), the same way teachers record students and guardians.

A. Yes: centres can invite by phone or email, matched the same way as students and guardians
B. No: email invitations are for students and guardians only in this change
X. Other (please specify)

[Answer]: A

## Question 6: Do "forgot password" and account deletion accept a username?

Both send a code to a verified phone or email today, and the person types that phone or email.

A. No: both keep asking for the phone or email the code goes to; only sign-in accepts a username
B. Yes: both accept a username too, and the code goes to the account's verified contact (the response is identical whether or not the username exists)
X. Other (please specify)

[Answer]: A

## Question 7: Are some usernames reserved?

A. Yes: a short reserved list (for example admin, support, help, shikkhokplus, system, root), compared without regard to case
B. No reserved names
X. Other (please specify)

[Answer]: A
