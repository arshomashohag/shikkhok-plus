# Requirement-to-Unit Map — Unique usernames

No user stories were produced for this intent, so every row is keyed by a
functional requirement from `requirements.md`. Each row names the unit that
implements its backend behaviour; client screens for every user-facing
requirement are delivered by U3 (Android) and U4 (web) under FR11.

| ID | Requirement (short) | Unit | Directory | Also touches |
|---|---|---|---|---|
| FR1 | Username rules | U1 | `u1-usernames-backend` | U3, U4 (format hints) |
| FR1.1 | Length and characters | U1 | `u1-usernames-backend` | |
| FR1.2 | Starts with a letter, dot rules | U1 | `u1-usernames-backend` | |
| FR1.3 | Case-insensitive unique | U1 | `u1-usernames-backend` | |
| FR1.4 | Whitespace | U1 | `u1-usernames-backend` | |
| FR1.5 | Reserved names | U1 | `u1-usernames-backend` | |
| FR1.6 | Refusal message keys | U1 | `u1-usernames-backend` | U3, U4 (strings) |
| FR2 | Sign-up with a username | U1 | `u1-usernames-backend` | U3, U4 |
| FR2.1 | Username in the draft | U1 | `u1-usernames-backend` | |
| FR2.2 | Re-check and retry at creation | U1 | `u1-usernames-backend` | |
| FR2.3 | Drafts do not reserve | U1 | `u1-usernames-backend` | |
| FR2.4 | No contact existence oracle | U1 | `u1-usernames-backend` | |
| FR2.5 | Matching at creation | U2 | `u2-contacts-and-invites-backend` | U1 (call site) |
| FR3 | Availability check | U1 | `u1-usernames-backend` | U3, U4 |
| FR3.1 | Lookup answers | U1 | `u1-usernames-backend` | |
| FR3.2 | Lookup ceilings | U1 | `u1-usernames-backend` | |
| FR3.3 | Public-route allowlist | U1 | `u1-usernames-backend` | |
| FR4 | One-field sign-in | U1 | `u1-usernames-backend` | U3, U4 |
| FR4.1 | Server-side classification | U1 | `u1-usernames-backend` | |
| FR4.2 | Phone and email sign-in kept | U1 | `u1-usernames-backend` | |
| FR4.3 | Uniform refusal | U1 | `u1-usernames-backend` | |
| FR4.4 | Failure ceilings | U1 | `u1-usernames-backend` | |
| FR4.5 | Second step unchanged | U1 | `u1-usernames-backend` | |
| FR4.6 | Old request shape accepted | U1 | `u1-usernames-backend` | |
| FR5 | Existing accounts choose a username | U1 | `u1-usernames-backend` | U3, U4 |
| FR5.1 | username_required flag | U1 | `u1-usernames-backend` | |
| FR5.2 | Choose-username screen | U3 | `u3-android-identity` | U4 |
| FR5.3 | Server does not block old clients | U1 | `u1-usernames-backend` | |
| FR5.4 | First choice exempt from limit | U1 | `u1-usernames-backend` | |
| FR6 | Invitations by phone or email | U2 | `u2-contacts-and-invites-backend` | U3, U4 |
| FR6.1 | Teacher records emails | U2 | `u2-contacts-and-invites-backend` | |
| FR6.2 | Student email unique per teacher | U2 | `u2-contacts-and-invites-backend` | |
| FR6.3 | Distinct field names | U2 | `u2-contacts-and-invites-backend` | |
| FR6.4 | Centre invites by email | U2 | `u2-contacts-and-invites-backend` | |
| FR6.5 | Matching at three moments | U2 | `u2-contacts-and-invites-backend` | |
| FR6.6 | Links, never decisions | U2 | `u2-contacts-and-invites-backend` | |
| FR6.7 | Already-added lookup by email | U2 | `u2-contacts-and-invites-backend` | |
| FR7 | Changing the username | U1 | `u1-usernames-backend` | U3, U4 |
| FR7.1 | Rename after password | U1 | `u1-usernames-backend` | |
| FR7.2 | Rename limit | U1 | `u1-usernames-backend` | |
| FR7.3 | 30-day hold and reclaim | U1 | `u1-usernames-backend` | |
| FR7.4 | Digest-only deletion hold | U1 | `u1-usernames-backend` | |
| FR7.5 | Other devices stay signed in | U1 | `u1-usernames-backend` | |
| FR8 | Managing phone and email | U2 | `u2-contacts-and-invites-backend` | U3, U4 |
| FR8.1 | Add a contact | U2 | `u2-contacts-and-invites-backend` | |
| FR8.2 | Replace or remove | U2 | `u2-contacts-and-invites-backend` | |
| FR8.3 | Links survive removal | U2 | `u2-contacts-and-invites-backend` | |
| FR8.4 | Last contact refused; stale prose fixed | U2 | `u2-contacts-and-invites-backend` | U1 (prose) |
| FR9 | Username private | U1 | `u1-usernames-backend` | |
| FR9.1 | No other lens sees it | U1 | `u1-usernames-backend` | |
| FR9.2 | Gate and membership test | U1 | `u1-usernames-backend` | |
| FR9.3 | Never in logs or audit | U1 | `u1-usernames-backend` | U2 (its audit events) |
| FR10 | Deletion and recovery | U1 | `u1-usernames-backend` | |
| FR10.1 | Recovery stays phone or email | U1 | `u1-usernames-backend` | |
| FR10.2 | Deletion hold and disposition | U1 | `u1-usernames-backend` | |
| FR11 | Both clients | U3 | `u3-android-identity` | U4 |
| FR11.1 | Screens | U3 | `u3-android-identity` | U4 |
| FR11.2 | Strings and Bangla layout check | U3 | `u3-android-identity` | U4 |
| FR11.3 | Server decides | U4 | `u4-web-identity` | U3 |

## Cross-cutting rows

- **FR2.5** sits in U2 (the matcher) but is called from U1's Registration at
  the existing call site.
- **FR8.4** has two halves: the last-contact refusal (U2) and the stale prose
  correction (U1, which already edits `app/db/models.py` and `app/auth/otp.py`).
- **FR9.3** is enforced by every unit that adds an audit event.
- **FR11** rows are delivered twice, once per client.

## Implementation order within each unit

- **U1**: migration and Usernames module; AccountDirectory username writes;
  sign-up and the retry; sign-in; availability; `username_required`; rename and
  reclaim; deletion hold; privacy gate and runbook line.
- **U2**: migration; roster and centre email fields; link statements and
  ContactMatching; already-added by email; contact replace and remove.
- **U3, U4**: sign-in and sign-up; choose-username screen; Settings (username,
  contacts); teacher student form and centre invite form.

## Coverage check

Every FR and FR sub-requirement in `requirements.md` (59 IDs) has exactly one
implementing unit above, and every unit has rows: U1 (40), U2 (14), U3 (4), U4
(1, plus every FR11 row as "also touches"); 40 + 14 + 4 + 1 = 59.
