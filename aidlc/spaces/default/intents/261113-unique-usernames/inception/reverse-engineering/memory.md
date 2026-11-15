<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-11-13T00:00:00Z — the CR's premise of dormant teacher-created accounts is false against the code: teachers record numbers on student/enrollment/owner_member, accounts are created only at verify-first signup, and "claiming" is link_phone_seats at creation and phone-add; the Account docstring and an otp.verify comment are stale. Requirements must restate the claim constraint as seat linking, not account takeover.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-11-13T00:00:00Z — username cannot live on profile (FORCE RLS blocks pre-auth lookup), so it sits on account outside RLS and only the response-schema gate protects it; the privacy-gate auto-enrolment covers Profile columns only and must be extended. Decide in domain design.
- 2026-11-13T00:00:00Z — a held (cooling-off) username after hard delete retains an identifier; needs a disposition and retention class.
