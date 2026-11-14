# Units Generation Questions — Unique usernames

The walking skeleton does not apply: this plan runs with the skeleton off, and
team.md records that the skeleton was built in B3 and does not recur.

## Question 1: How are the units cut?

A. By deployment target, with the backend split by concern: one backend unit for usernames (sign-up, sign-in, rename, holds, privacy), one backend unit for contacts and email invitations (roster and centre emails, matching, contact replace and remove), one Android unit, one web unit
B. One backend unit and one unit per client (three units)
C. By feature, each a full vertical slice through backend, Android and web (usernames; contacts and invitations)
X. Other (please specify)

[Answer]: A

## Question 2: May independent units be built in parallel?

A. Yes: the two backend units have no dependency between them; the two client units depend only on the backend units
B. No: strictly one after another
X. Other (please specify)

[Answer]: A

## Question 3: How are the units deployed?

A. The two backend units ship in the one existing backend container (a modular monolith), each as its own migration and squash-merged Bolt; Android and web ship on their own release cadence and tolerate a backend that has the change before they do
B. Each unit deployed independently as its own service
X. Other (please specify)

[Answer]: A

## Question 4: How do the units integrate?

A. Through the committed `/v1` OpenAPI contract (pinned in Contract Design) and the shared database schema, which each backend unit extends with its own forward-only migration
B. Through events between the backend units
X. Other (please specify)

[Answer]: A
