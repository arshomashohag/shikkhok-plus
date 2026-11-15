# NFR Requirements Questions — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`. These are the only questions that need
judgement. Everything else is already decided by the requirements (NFR1 to
NFR9), the approved functional design, team.md and project.md, or the code as
built, and goes straight into the artifacts. The person said: "don't wait for
my approval. Go with your recommendations." So each answer is the recommended
option, listed as A, and the agent made the choice.

## Question 1: What happens when the database aborts a U2 transaction with a deadlock, a serialization failure or a lock timeout?

Context: review-02 R-08 and R-10 show that the lock order in the functional
design leaves out account rows and foreign-key key-share locks, and that
PostgreSQL aborts a deadlocked transaction with SQLSTATE `40P01`. The design
does not say how that abort is classified. Today `app/request_scope.py` renders
any `OperationalError` (deadlock, serialization failure, lock timeout) as
`TransientError` with `retryable: true`. Nothing in the backend retries a
transaction on the server side. team.md's error-handling rule calls a
serialization failure "a bounded transaction retry".

A. Remove the cycle with one documented lock order (advisory keys first, then rows in a fixed table order, then the account row last; see reliability-requirements NFR4.2). As a backstop, keep the existing classification: `40P01`, `40001` and `55P03` roll the whole transaction back and come back as `TransientError`, `retryable: true`. The retry is the client's explicit retry prompt (TC-8), so a person decides each retry and the retries are bounded. Add no server-side automatic retry. Each interleaving that review-02 named gets a two-connection test.
B. The same lock order, plus a server-side retry wrapper on U2's write transactions (at most 2 retries with jittered backoff)
C. Run U2's write transactions at SERIALIZABLE and rely on a server-side retry instead of a lock order
D. A server-side retry only, with the lock order left as the functional design stated it
X. Other (please specify)

[Answer]: A

## Question 2: How does an erased account's seat stay unlinkable, given that the shipped deletion never sets the relink-blocked markers?

Context: review-02 R-09 found that `delete_account` deletes the account row
and depends on `ON DELETE SET NULL`. Nothing in `app/` sets
`student_relink_blocked_at` or `guardian_relink_blocked_at`; only tests do. So
an erased person's seat ends up with an empty link that still records their
phone. The phone matcher relinks it today, and U2's email matcher would relink
it too. The functional design's RelinkBlocked state and rules BR2.4, BR3.6 and
BR4.3 all assume the marker gets set.

A. U2 changes `delete_account`. Inside the deletion's own transaction, and in the lock order of NFR4.2, it takes the account key and the account's contact keys, locks every seat linked to the account in ascending id order, sets the matching role's marker, and only then deletes the account row. It also deletes the `contact_replace` code rows the account requested. Both deletion routes are covered by tests written first.
B. A `BEFORE DELETE` trigger on `account` that sets the markers on referencing seats
C. Leave erasure to a later unit, drop the erasure claims from BR2.4 and BR3.6 and the state machine, and accept the relink risk with a named owner
D. Keep a table of keyed digests of erased contacts and have the matcher consult it
X. Other (please specify)

[Answer]: A

## Question 3: What discharges the latency targets?

Context: project.md forbids discharging a performance obligation with a
correctness test, and requires the artifact to say so plainly when the verifier
is manual. The public lookup's per-IP ceiling (30 per hour) also stops anyone
from load-testing it at volume from one host. The repository has no load tool.
`httpx` is already a pinned dependency.

A. Two automated CI checks that prove the mechanism but not the number. The first asserts that every matcher and lookup statement can use its partial index (plan inspected with sequential scans disabled). The second asserts that the matcher issues a constant number of statements whatever the row count. The numbers themselves come from one timed, manual run on staging, using a small `httpx` script within the ceilings, and the results are recorded in the Bolt's PR. Nothing automated discharges the latency figures, and the artifact says so.
B. A timing assertion in CI against the testcontainers database
C. Add a load-testing tool (Locust or k6) and a scheduled staging run
D. State no latency target for this unit
X. Other (please specify)

[Answer]: A

## Question 4: Does the contact matcher get its own branch-coverage gate?

Context: team.md measures the authorization layer by branch coverage because
line coverage hides untested branches. The matcher decides who receives a
child's seat invitation, branching on the contact's kind and on the student
and guardian links. The backend's floor is 80% line, and the money module
alone carries a 100% branch gate in `make test`.

A. The matcher module (the file that holds `match_contact` and its kind dispatch) carries a 100% branch gate. It is added to `make test` as a second `coverage report --include` pass, in the same way as the money module.
B. Report the matcher's branch coverage without a gate
C. Only the backend's 80% line floor
X. Other (please specify)

[Answer]: A

## Question 5: After review-01 R-03, does U2 retry `40001` and `40P01` on the server, as team.md's error-handling rule says?

Context: [Q1] A chose no server-side retry. Review `reviews/review-01.md` R-03
found that this contradicts team.md: "a serialization failure is a bounded
transaction retry", affirmed and unchanged. Deletion also runs legacy
statements that U2 does not order, so some deadlock pairs can only be
absorbed, not prevented. The orchestrator decided under the person's
instruction "Go with your recommendations". This answer supersedes [Q1]'s
no-retry clause. [Q1]'s lock order stands.

A. Yes, a bounded retry. `40001` and `40P01` re-run the whole unit of work: at most 2 retries, with jittered backoff of 10–50 ms and then 50–150 ms. This applies only to U2's write paths and `delete_account`, each of which sends nothing before its commit. After the last attempt the request fails as `TransientError`, `retryable: true`. `55P03` is not retried
B. No server-side retry, recorded as a named exception to team.md, with its reason and owner
C. Retry `40001` only, not `40P01`
D. Retry every `OperationalError`, `55P03` included
X. Other (please specify)

[Answer]: A
