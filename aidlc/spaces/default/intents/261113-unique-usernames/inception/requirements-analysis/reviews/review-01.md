## Review

**Verdict:** READY
**Reviewer:** aidlc-product-lead-agent
**Date:** 2026-11-13T10:43:34Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261113-unique-usernames/inception/requirements-analysis/requirements.md > FR8.2, FR8.3, NFR2 | Replacing or removing a phone or email needs only the password, yet it moves the account's recovery channel on a children's-data app. Nothing says whether the old contact is notified or whether other signed-in devices are signed out, and NFR2 puts no ceiling on contact changes. | State the security side effects of a contact change (notice to the old contact, effect on other sessions) and add a rate ceiling for replace and remove with a test, or record explicitly that none is wanted and why. | New |
| R-02 | Major | aidlc/spaces/default/intents/261113-unique-usernames/inception/requirements-analysis/requirements.md > FR6.5, FR6.6, FR8.3, A1 | A seat stays linked after its contact is removed, and a seat already linked is never re-linked. The requirements are silent on a teacher later editing or clearing the recorded phone or email on an already-linked seat, and on a recycled number that a new account then verifies. | Add a requirement and a Given/When/Then for a teacher changing the recorded contact on a linked seat, and for a freed contact verified by a second account, so Domain Design is not left to guess who keeps access. | New |
| R-03 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/requirements-analysis/requirements.md > FR6.4, FR6.2 | Centre invites by email need a nullable email column beside `owner_member.invited_phone`, which is NOT NULL today (`app/db/models.py:978`). Uniqueness of guardian email and of centre-invited email is not stated, while student email is (FR6.2). | Name the existing NOT NULL constraint as a migration constraint and state the uniqueness rule for guardian and centre email, or declare none. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/requirements-analysis/requirements.md > FR3.1, FR4.4, NFR1 | The availability lookup makes every username's existence public, and the "held" answer also reveals a recent rename or deletion. The per-username failure ceiling then lets anyone lock a known username out of sign-in for an hour; phone and email keys were never public, so this is new exposure. | Record that this trade-off is accepted, or key the failure counter per username plus network so a stranger cannot lock out the owner. | New |
| R-05 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/requirements-analysis/requirements.md > FR3, FR1.4, FR2.4, FR5.3, FR7.5, FR11, NFR8 | Several requirements have no pass/fail criterion QA could run. These are the held, reserved and invalid lookup answers, whitespace trimming, identical draft response for a known or unknown contact, an old client without a username, rename and other devices, and the client screens. NFR8 says "normal load" without defining it. | Add one Given/When/Then for each, and replace "normal load" with a stated request rate or drop the p95 figure. | New |
| R-06 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/requirements-analysis/requirements.md > FR5.1 | `username_required` is defined for "every authenticated response" but does not say it is false for platform administrators and other principals who have no username, which is out of scope. | State that the flag is false for any account that cannot choose a username. | New |

### Summary

The requirements are specific, traceable and mostly testable, and they correct the request's "dormant account" premise against the code in the open. Two security gaps remain around contact replacement and linked seats; neither blocks engineering, but both should be settled before Domain Design.
