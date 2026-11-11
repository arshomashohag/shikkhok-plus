# Improvement sprint plan (2026-11-11)

Delivery manager's consolidation of the four specialist reviews in this
folder: `product-owner.md` (PO-*), `security.md` (SEC-*), `ux.md` (UX-*) and
`architecture.md` (ARC-*). This file records what this sprint builds, what it
defers and why, and which decisions belong to the product owner rather than
to the team.

## Baseline before any change

| Gate | Result |
|---|---|
| Web (`cd web && npm run check`) | green |
| Android unit tests (`./gradlew :android:testDebugUnitTest`) | green |
| Backend (`make test`, real PostgreSQL 16 via testcontainers) | recorded in the QA report |

## How items were selected

An item made the sprint when all four held:

1. It has file:line evidence that a second reader confirmed against the code.
2. It needs no product or privacy decision that has not yet been made.
3. One developer can finish it with tests in one working session.
4. It can run in parallel with the other streams without editing the same
   hand-written files. Generated files (`openapi.json`,
   `web/src/api/schema.d.ts`, `web/src/i18n/generated/*`) are regenerated
   after the merge, never merged by hand.

## Sprint backlog: five parallel streams

| Stream | Owner role | Items | Surfaces |
|---|---|---|---|
| S1 Security hardening | developer + security | SEC-3 (hide SQL parameters, map `DataError` to 400, bound `total_marks`), SEC-1 (password failures get their own alerting-only global scope), SEC-4 (the already-added lookup gets its own allowance), SEC-6 (the deletion verify step counts toward the network-wide ceilings), SEC-7 (app-side security headers on the deletion HTML page), ARC-7 (fail at startup on a malformed JWT key set) | backend |
| S2 Schema integrity | developer + architect | ARC-1: reconcile the SQLAlchemy models with the migrations so that `alembic check` passes at head, and add that check to `make check` | backend, CI |
| S3 Class-change notifications | developer + product | PO-1: families get an inbox item when a class is cancelled or rescheduled. PO-10: the unread count matches what the client can show | backend, web, Android |
| S4 Web parity | developer + product | PO-5: web marksheet-visibility toggle. PO-6: the web sign-up "already added" notice | web |
| S5 Attendance and destructive-action UX | developer + designer | UX-1: the web attendance row keeps Bangla names readable at 320 px. UX-8/9/10: every destructive action asks for confirmation, and a sheet with unsaved input asks before it closes. UX-2: the Android attendance switch announces whose attendance it is | web, Android |

QA runs the full gate (`make check`: lint, typecheck, backend suite with
both coverage floors, Android tests and quality, web, site, infra functions)
on the merged result. An independent code review covers the merged diff
before anything is pushed.

## Deferred, with reasons

| Item | Why not now |
|---|---|
| SEC-2 re-authentication on `DELETE /v1/me` | Correct and wanted. It changes the request body on both clients, plus a prompt on each, so it is its own slice. **Next sprint, first.** |
| SEC-5 increment-first ceilings and scrypt semaphore | Concurrency rework of the auth hot path. Needs a load test. |
| SEC-8 refresh token in an HttpOnly cookie | Changes the auth transport for the PWA. Already listed as follow-up work in `web/README.md`. |
| SEC-9, SEC-10, SEC-11 | Infrastructure changes that need a `terraform plan` against the real account, which this environment cannot reach. |
| ARC-2 transaction-ownership rule | L effort, touches 116 call sites. Needs its own design first. |
| ARC-3 dead `verify_claim`/`reject_claim` | Money-module test migration. Do it test-first in a dedicated change. |
| ARC-4 Bangla layout verifier | Needs a screenshot-harness choice (Roborazzi or Paparazzi). The choice belongs to the team. |
| ARC-5, ARC-6 pagination and N+1 | API contract change for list endpoints. Both clients must follow. |
| PO-2 share sheet, PO-4 CSV export, PO-12 data download | **Product and privacy decision needed:** each moves child-identifying data out of the app. The privacy policy and Data Safety form must declare it first. |
| PO-3 receipts | M effort. Ready once the receipt format is agreed. |
| PO-7 automatic reminders, PO-8 absence alerts | **Product decision needed:** they reverse recorded decisions ("a reminder is sent by a person"; no per-kind muting). |
| PO-9, PO-11 | L or M, and lower value before launch. |
| UX-6/7/11 shared form field, UX-12 to UX-15 navigation and focus, UX-3 to UX-5, UX-24 | Valid. Next UX slice, after S5 lands the shared confirm pattern. |

## Decisions for the product owner

1. PO-2, PO-4, PO-12: allow teachers to export or share dues data, and
   update the privacy policy and Data Safety form to match?
2. PO-7: allow opt-in automatic due reminders per batch, off by default?
3. PO-8: allow a teacher-owned per-batch switch for same-day absence alerts?
4. ARC-4: Roborazzi or Paparazzi for the Bangla screenshot verifier, or a
   recorded per-screen manual check?
