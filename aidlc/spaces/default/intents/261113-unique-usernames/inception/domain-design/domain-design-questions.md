# Domain Design Questions — Unique usernames

These are the design decisions the approved requirements leave to this stage,
including the six findings accepted at the Requirements Analysis gate
(R-01 to R-06), which are design-level and are settled here rather than left
open.

## Question 1: How is case-insensitive uniqueness stored? (OQ2)

A. Two columns on `account`: `username` as typed, and `username_key` (lowercase) with a plain UNIQUE constraint and a CHECK that it equals `lower(username)` — the same canonical-column approach `account.email` already uses
B. One `username` column with a unique index on `lower(username)`
C. A `citext` column
X. Other (please specify)

[Answer]: A

## Question 2: What does a username hold store? (OQ1)

A. A keyed digest (HMAC under the existing server-held key) of the lowercase username, the expiry, and the account id while the account exists; never the username text
B. A plain SHA-256 of the lowercase username
C. The username text, purged at expiry
X. Other (please specify)

[Answer]: A

## Question 3: A teacher records both a phone and an email for one person, and they belong to two different accounts. Which account is linked? (R-02)

A. The phone's account; the email is used only when no account holds the phone. No refusal, so the form reveals nothing about who holds what
B. Refuse the save, saying the two contacts belong to different people
C. Link neither until the teacher resolves it
X. Other (please specify)

[Answer]: A

## Question 4: What happens when a person removes or replaces a phone or email? (R-01)

A. Password confirmation first; a short notice sent after commit to the removed contact (best-effort, not retried); other devices stay signed in; at most 5 contact changes per account per day
B. As A, and every other device is signed out
C. No notice and no ceiling
X. Other (please specify)

[Answer]: A

## Question 5: How are failed username sign-ins counted, so a stranger cannot lock the owner out? (R-04)

A. Per username and network prefix (10 per hour), plus a looser per-username ceiling across all networks (30 per hour); the public availability lookup answers "taken" for a held name, so it does not reveal renames or deletions
B. Per username only (10 per hour), as phone and email are today
X. Other (please specify)

[Answer]: A

## Question 6: Where does matching an account to recorded seats and invitations live? (FR6.5)

A. One matcher that takes a verified phone or email and calls the roster and centre components' own link statements; called at sign-up and at every contact add
B. Keep separate phone and email linking functions in each module
X. Other (please specify)

[Answer]: A
