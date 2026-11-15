# Functional Design Questions — U3 android-identity

Unit `android-identity` (U3, kind `ui`). These are the five corners the
requirements, the contracts and the built backend leave open for the Android
client. Everything else is settled by FR1–FR11, C1, C2 and the two backend
functional designs, and is written into `functional-spec.md` directly.

The person instructed: "don't wait for my approval. Go with your
recommendations." Every answer below is the recommended option, A.

## Q1. How the live username availability check behaves while typing

FR3.1 asks for a live check, FR3.2 puts it behind tight ceilings (30 per /64
per hour, shared with sign-up replacements), FR11.3 forbids a client hint that
refuses what the server accepts, and NFR8 targets 300 ms at p95.

A. No client copy of the FR1 rules at all. The trimmed text is sent to the
   lookup 500 ms after the last keystroke, only when non-empty; at most one
   request is in flight; an answer is applied only if it is for the text still
   in the field (latest wins); answers are remembered per text for the life of
   the screen so retyping a name asks nothing new. A refused or failed lookup
   says "could not check" and never blocks submission.
B. Mirror the FR1 rules on the client to skip lookups for names that are
   certainly invalid, and call the lookup only for names that pass.
C. Check only when the field loses focus.
D. Check only on submit; no live check.
E. Check on every keystroke with no debounce.
X. Other (please specify)

[Answer]: A

## Q2. Where the choose-username screen sits and how it cannot be dismissed

FR5.2: shown after sign-in, before anything else, not dismissible except by
choosing a name or signing out. `MainActivity.AppRoot` already resolves
`GET /v1/me` behind a loader before building the graph, and returns the lens
picker the same way.

A. A full-screen gate returned by `AppRoot` after the account read and before
   the lens picker and the navigation graph, exactly as the lens picker is:
   not a back-stack entry, no back arrow, and the graph (home, More, the
   password prompt, the two-step offer) is not composed while it shows. Its
   only exits are a successful choice and "Sign out". System Back leaves the
   app as on any root screen; reopening shows the gate again because the flag
   is read from the server on every resolve.
B. A navigation destination pushed on top of home, with a BackHandler that
   swallows Back.
C. A modal dialog over the home screen.
D. A persistent banner like the set-password prompt.
E. A step inside the sign-in screen, before `SignedIn` is published.
X. Other (please specify)

[Answer]: A

## Q3. How Settings presents the contacts and the rule about the last one

FR8.2 / FR8.4: replace or remove after the password, refused for the last
contact. FR11.3: the client does not decide whether a contact may be removed.
Today More shows "Add phone number" or "Add email" only when one is missing.

A. One "Phone and email" row in More's account section opens a Contacts
   screen listing both kinds. A present contact shows its value with Replace
   and Remove; an absent one shows Add (the existing add flow). Remove is
   offered for every present contact, the last one included, and the server's
   `account.contact.last_one` explains a refusal. Replace and Remove ask for
   the current password inline; an account the server says has no password
   sees an informational note with a link to set one, and its actions stay
   enabled so the server's refusal is what decides.
B. Separate More rows per contact, each opening its own screen.
C. As A, but hide Remove when only one contact remains.
D. As A, but disable Replace and Remove when `has_password` is false.
E. Keep only Add in More; put Replace and Remove behind the deletion screen.
X. Other (please specify)

[Answer]: A

## Q4. Whether sign-up calls the already-added lookup for an email

U2 built `GET /v1/accounts/already-added?email=` (FR6.7). The Android sign-up
calls it for a phone only (`HttpSignupRepository.lookup(phone)`), so a person
a teacher recorded by email gets no locked role. FR11.1 does not list this
explicitly; FR6.7 is otherwise unreachable from Android.

A. Include it in U3: when the email field is left holding a well-formed
   address, the same lookup runs with `email`, with the phone lookup's exact
   behaviour (once per value, role locked on a seat, nothing named).
B. Leave it out of U3; record it as a gap for a later unit.
C. Run it on submit only.
D. Run it for an email only when the person chose the Student or Guardian role.
E. Remove the phone lookup too, for symmetry.
X. Other (please specify)

[Answer]: A

## Q5. The client email shape check is stricter than the server's

Computed against the code, not asserted: the server accepts an address when
it fully matches `[^@\s]+@[^@\s]+\.[^@\s]+` (`app/accounts/identifier.py:50`).
The client's `emailIsWellFormed` (`core/model/Identifier.kt:70`) also refuses
a domain that starts or ends with a dot. So `a@b.c.` and `a@.b.c` are accepted
by the server and refused by the client, which FR11.3 forbids. U3 adds two
more email fields that would inherit it (student form, centre invite).

A. Align `emailIsWellFormed` to the server's pattern in this unit, keep it the
   one shared client check for every email field, and pin the two corner
   cases in a test so the two sides cannot drift again silently.
B. Leave the existing check as it is.
C. Drop client email checks everywhere and rely on the server's
   `email.invalid`.
D. Make the client check advisory (shown, but never blocking submission).
E. Make the server stricter to match the client.
X. Other (please specify)

[Answer]: A
