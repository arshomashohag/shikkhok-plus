# Observability Requirements — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2 (kind: service). The current setup,
as built:

- Logs are plain text from `docker logs`, formatted by
  `app/logging_setup.StructuredFormatter`. It prints the message plus only the
  fields listed in `STRUCTURED_FIELDS`: `purpose`, `outcome`, `provider_code`,
  `correlation_id` and `event`.
- Nothing ships logs anywhere. An alert is a `CRITICAL` log line.
- The append-only `auth_audit_log` records authentication events by account
  id.

U2 adds no metrics system and no log sink (USD 50 ceiling, OC-4). It makes its
own events readable in the channels that exist. IDs inherit the inception NFR
each observation serves.

## Logs

| ID | Requirement | Verifier |
|---|---|---|
| NFR4.8 | **Deadlocks and lock timeouts are visible.** Today `request_scope._database` logs `error_class` for every database failure but `sqlstate` only for a `DataError`, and the formatter prints neither, because neither is in `STRUCTURED_FIELDS`. So a `40P01` that reaches a client shows in the log only as "database failure rendered as an envelope". U2 logs `sqlstate` for `OperationalError` too, read from `error.orig.sqlstate`, and adds `error_class` and `sqlstate` to `STRUCTURED_FIELDS`. `40P01`, `40001` and `55P03` from any route then appear as `sqlstate='40P01'` and so on, with the correlation id. | Formatter test, plus an integration test that forces `40P01` and asserts the captured line carries `error_class='OperationalError' sqlstate='40P01' correlation_id=...` |
| NFR4.9 | **Notice outcomes are logged once per notice**, with `purpose='contact_notice_sms'` or `'contact_notice_email'`, `outcome` from the closed set `sent`, `budget_refused`, `failed`, `unknown` (a gateway timeout, as the SMS rule records it), and the `correlation_id`. There is never a contact, an account id or the template text. These are existing structured fields, so the formatter needs no change for this. | Test per outcome, with a gateway stub |
| NFR4.10 | **Each server-side retry is logged once** (reliability NFR4.3). The line carries `event='db_retry'`, `outcome='retrying'` or `'exhausted'`, `sqlstate` (`40001` or `40P01`), the attempt number in `purpose` (for example `'attempt_2'`), and the `correlation_id`. Nothing else is logged: no statement and no values. | Asserted in NFR4.3's forced-deadlock and exhausted-retry tests |

Defined in security-requirements, and only cross-referenced here:

- NFR2.6: `scope` joins `STRUCTURED_FIELDS`, so a ceiling alert names its
  scope.
- NFR3.4: the sentinel test proves that no U2 log line carries a contact.

Log levels: a refusal under a rule (`last_one`, `change_limit`, `admin_locked`,
`email.taken`) is an expected outcome. It is not logged above `INFO`, and it
does not alert. Only the existing whole-product scopes alert
(`_ALERTING_SCOPES`). U2 adds no alerting scope: `contact_chg_day` is
per-account, and an alert on it would fire on ordinary use and teach the
operator to ignore the channel (the reasoning in `fire_ceiling_alert`).

## Audit

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.9 | Two members join the closed `AuthEvent` set: `CONTACT_REPLACED` (16 characters) and `CONTACT_REMOVED` (15), within `auth_audit_log.event` `String(32)`. They are written by `write_audit` in the change's transaction, with the account id and correlation id only, and they fail open through the existing savepoint. `CONTACT_ADDED` keeps its meaning and is now also written for an email add, which also matches. | Tests: each workflow writes exactly one row of its event, carrying no contact; the event set is shared with U1 under C3's merge-order rule |


NFR3.8 (deletion's own record counts the seat links it blocked) is defined in
security-requirements and is only cross-referenced here.

## SLIs and checks

There is no metrics backend, so each indicator below is read from the
container log or from the database by the operator. That makes each one a
**manual check, not an automated SLO**. It is stated so that nobody mistakes
it for monitoring.

| Indicator | Target | How it is read |
|---|---|---|
| Deadlocks or lock timeouts reaching a client from U2 routes | **0** during the staging rehearsal and the first 7 days after each production deploy of U2 | `docker logs <api> 2>&1 \| grep -E "sqlstate='(40P01\|55P03)'"`, run at the end of the rehearsal and on day 7. Any hit on a U2 route is a defect against reliability NFR4.2 |
| Server-side retries | Information only. A retry between two U2-ordered paths is a defect; one between deletion and a residual legacy pair (reliability NFR4.2) is expected and rare | `grep "event='db_retry'"`, counted by `outcome` |
| Notice delivery | No more than 10% `failed` or `unknown` over any 7-day window once in production | `grep "purpose='contact_notice_"` and count by `outcome` |
| Lookup abuse | `lk_global_hour` alert lines | Already a `CRITICAL` line; NFR2.6 makes it name its scope |
| Contact change volume | Information only | `SELECT event, count(*) FROM auth_audit_log WHERE event IN ('CONTACT_ADDED','CONTACT_REPLACED','CONTACT_REMOVED') AND occurred_at > now() - interval '7 days' GROUP BY event` through the named non-superuser production role (team.md: production access is named and logged) |

Dashboards: none. Tracing: none. Neither exists in the product, and U2's
paths run inside one transaction in one process, so the correlation id joins
a request's log lines and audit rows.

## Assumptions & Open Questions

- [assumption] `error.orig.sqlstate` is populated by psycopg 3 for
  `OperationalError` subclasses. It is the attribute the existing
  `sqlstate_of` already reads for `DataError`. NFR4.8's test confirms it.
- [assumption] The 10% notice-failure threshold is the agent's choice. It is
  a prompt to look at the gateway, not an availability promise.
- Open questions: None.

## Sources

- Code read: `app/logging_setup.py` (`STRUCTURED_FIELDS`),
  `app/request_scope.py` (`_database`, `sqlstate_of`), `app/auth/ceilings.py`
  (`fire_ceiling_alert`, `_ALERTING_SCOPES`), `app/audit/log.py`
  (`AuthEvent`, the savepoint), `app/db/models.py` (`auth_audit_log.event`
  `String(32)`), `app/governance/deletion.py` (`DeletionResult`).
- Functional design: `rules.md` BR5.9 and BR5.11; `functional-spec.md` § 7.
- Requirements NFR2, NFR3 and NFR4: `inception/requirements-analysis/requirements.md`.
- Rules: team.md Deployment (secrets leak through logs; production access),
  Code Style (error handling; FCM-style best effort), OC-4.
