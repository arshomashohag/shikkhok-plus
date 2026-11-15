# Health Check Report: Unique usernames

## Status: NOT RUN

Nothing was deployed, by the person's decision ("Record, don't deploy
(Recommended)"). No environment was contacted. This report states what the
health check reports, what it must report after this intent is deployed, and
who checks it.

## What `/health` reports

`GET /health` is defined in `app/api/health.py`. It is unversioned and public.
It is listed in `PUBLIC_ROUTES` as `("GET", "/health")`, and its response
model forbids extra fields:

| Field | Values | Meaning |
|---|---|---|
| `status` | `"ok"` | The process is serving |
| `database` | `"ok"` or `"fail"` | `SELECT version_num FROM alembic_version` succeeded, or raised a `SQLAlchemyError` |
| `migration_revision` | string or `null` | The applied Alembic revision. `null` when the database read failed |

This intent does not change the endpoint.

## Expected values after this intent's staging deploy

```json
{"status": "ok", "database": "ok", "migration_revision": "0038"}
```

- **Expected head revision: `0038`**, which is `0038_usernames` (U1). It
  revises `0037_contacts_and_email_invites` (U2), which revises main's
  `0036_hub_listings`.
- The merged tree has one head. It was computed with the same function the
  smoke uses, `deploy/smoke.py` `migration_head()`, which returned `0038` on
  the working tree on 2026-11-15. That function raises if there is not
  exactly one head. `tests/gates/test_migration_numbering.py` asserts the
  linear zero-padded numbering that `migrate-if-behind` relies on.
- If staging was below `0036`, the same boot also applies main's 0034–0036.
  The expected end value is still `0038`.

## Who checks it, and when

| Check | Mechanism | Automated? | Result |
|---|---|---|---|
| New host answers `/health` through nginx over verified TLS before entering service | `user_data.sh.tftpl` readiness probe, plus the ASG launch lifecycle hook (`deploy/roll.sh`) | yes, at deploy | not yet checked |
| Public URL answers `/health` with `database: ok` at head `0038` | `deploy/smoke.py`, step "Smoke through CloudFront", 18 attempts 10 s apart | yes, at deploy | not yet checked |
| After a rollback (`deployment-log.md` § 6), `/health` shows `database: ok` and **`migration_revision: 0038`**, because the schema is not rolled back while the previous image serves | none: the automatic rollback step re-rolls the host and does not run the smoke again | **no. Nothing automated checks it.** The person reads `/health` by hand after any rollback | not applicable (no rollback) |

`/health` proves liveness, database reachability and schema revision. It does
not prove that any of this intent's routes work. Those are the manual checks
M1–M8 in `smoke-test-results.md`.

## Sources

- `app/api/health.py` (`HealthResponse`, `health`).
- `app/contract/routes.py` (`PUBLIC_ROUTES` includes `("GET", "/health")`).
- `deploy/smoke.py` (`migration_head`, the pass condition in `main`).
- `migrations/versions/0036_hub_listings.py`,
  `0037_contacts_and_email_invites.py` and `0038_usernames.py` (`revision` and
  `down_revision`).
- `.github/workflows/deploy.yml` (steps "Roll the instance", "Smoke through
  CloudFront", "Roll back to the previous release").
- `infra/modules/app/user_data.sh.tftpl` (the readiness probe on
  `https://<origin>/health`).
- `app/db/commands.py` (`migrate-if-behind`) and
  `tests/gates/test_migration_numbering.py`.

## Assumptions & Open Questions

- **Assumption**: the merge of `main` into this branch lands with the chain
  `0036 → 0037 → 0038` as it appears in the working tree now. If the
  renumbering changes, the expected head changes with it. The smoke derives
  its head from the tree, so the smoke stays correct either way; this record
  would need updating.
- **Open**: staging's current `migration_revision` is unknown. It was not
  read, because this stage contacts no environment.
