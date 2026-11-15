# Observability Requirements — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1 (kind: service). IDs inherit the
inception NFR whose control is being observed. The constraint over all of
them is security NFR3.4: no username, login value or key in any log line,
audit row, counter row or error.

What exists and is reused: plain-text structured logs to stdout through
`StructuredFormatter` (`app/logging_setup.py`), with `STRUCTURED_FIELDS`
already carrying `purpose`, `outcome`, `correlation_id`, `event`, `scope`,
`error_class` and `sqlstate`; `fire_ceiling_alert` (a `CRITICAL` line) for
the members of `_ALERTING_SCOPES`; the append-only `auth_audit_log`; the
retention purge's heartbeat alert; and `run_with_retry`'s one line per
re-run. Container stdout goes to the app's CloudWatch log group, and a metric
filter on `"CRITICAL:"` raises the host alarm
(`infra/modules/app/monitoring.tf` 30-49). That filter matches any
`CRITICAL` line whatever its scope, so "alert" below means a `CRITICAL` line.
(The `app/logging_setup.py` docstring still says nothing ships the logs. That
is out of date, and U1 does not rely on it.) U1 adds **no new structured
field**, so `STRUCTURED_FIELDS` is unchanged.

## Requirements

| ID | Requirement | Verifier |
|---|---|---|
| NFR2.10 | `un_lk_global_hr` joins `_ALERTING_SCOPES`. Its limit comes from `SHIKKHOKPLUS_GLOBAL_HOURLY_USERNAME_LOOKUPS` (default 1000; a value, not a decision, set at deployment like the built `SHIKKHOKPLUS_GLOBAL_HOURLY_LOOKUPS`). It alerts once, on the request that fills the hour, and refuses nothing. The line reads `sms ceiling breached [scope='un_lk_global_hr']`, which is the built message text. No other new scope alerts: per-account, per-network and per-username scopes fire in ordinary use, which trains the operator to ignore the channel (the `fire_ceiling_alert` docstring). | Test: the 1000th count logs exactly one `CRITICAL` record with `scope='un_lk_global_hr'`, the 1001st logs none, and both are served. A test that `_ALERTING_SCOPES` holds no other `un_` member |
| NFR2.11 | **Targeted guessing is visible without alerting.** The request whose failure fills `un_fail_hour` for a username, that is the 20th failure in the window, logs one `WARNING` line: message `username failure ceiling filled`, `event='un_fail_hour_filled'`, `scope='un_fail_hour'`, `correlation_id`. There is no username and no counter value in it. Later refusals in that window log nothing new. Broad guessing across many names is already covered by the built `pwf_global_hour` alert at 300, which username failures also count. | Test: 20 failures from different /64s give exactly one such record. A sentinel check (security NFR3.4) on that record |
| NFR2.12 | Every refusal by a new scope is identifiable to the operator by its scope name, never by its subject. `CeilingBreach.scope` is set, as built, and any log line written at a refusal carries `scope`. | Covered by security NFR2.6's parametrized test, extended to assert `breach.scope` |
| NFR3.10 | **Audit events.** `USERNAME_SET` (account created with a username, or the first choice) and `USERNAME_CHANGED` (an ordinary rename, a reclaim or a case-only change) are written to `auth_audit_log` in the same transaction as the change, with the account id and the correlation id only (BR2.8, FR9.3). A no-op (identical text) writes no row (BR6.7). The existing sign-in events (`PASSWORD_SIGN_IN_FAILED`, `PASSWORD_SIGN_IN_SUCCEEDED`, `PASSWORD_CEILING_BREACHED`) are written for username sign-ins exactly as for phone and email, with the account id null when none was found. | Tests per workflow asserting the exact rows written, and none on a no-op or a refusal. Security NFR3.4's sentinel test over the rows |
| NFR4.8 | Database re-runs are visible. A rename or first choice re-run by `run_with_retry` logs its existing one line per re-run (`event='db_retry'`, `sqlstate`, `purpose='attempt_<n>'`, `outcome`). A rename unit that exhausts its retries is distinguishable in the log from an ordinary refusal. | NFR4.3's forced-deadlock tests assert the records |
| NFR7.4 | The migration runs as the deploy's own logged step (`deploy.yml`), and its duration is read from that log (reliability NFR7.2). | The staging deploy log. **Manual reading; nothing automated checks it.** |

## SLIs and SLOs

U1 defines one service-level indicator and no new SLO with an error budget.
The backend has none yet, and a closed-testing audience gives too few
requests for a 30-day percentage to mean anything.

- **SLI:** availability-lookup latency, measured as the p95 of the manual
  staging run (performance NFR8.1, target 300 ms). It is recorded per Bolt
  in the PR. It is not computed continuously, because nothing collects
  request durations. **Nothing automated measures it.**
- Health: unchanged. The `/health` endpoint already reports database
  connectivity and the applied migration revision, and the revision is what
  shows the U1 migration applied.

## Dashboards

None. Apart from the one `CRITICAL:` metric filter there is no metrics
store, and a dashboard for one unit's counters would add cost against the USD
50 ceiling (project.md) for nothing the alarm does not already surface.

## Assumptions & Open Questions

- Checked, not assumed: `un_lk_global_hr`'s alert reaches the operator with no
  infrastructure change, because the metric filter matches every `CRITICAL:`
  line (`infra/modules/app/monitoring.tf` 37).
- Open questions: None.

## Sources

- Requirements NFR2, NFR3 and FR9.3: `inception/requirements-analysis/requirements.md`.
- Functional design: `rules.md` BR2.8, BR4.4, BR4.6, BR6.7, BR8.4;
  `functional-spec.md` § 7.
- Code read: `app/logging_setup.py`, `app/auth/ceilings.py`
  (`_ALERTING_SCOPES` 409-419, `fire_ceiling_alert` 577-590), `app/db/retry.py`,
  `Dockerfile`, `infra/modules/app/monitoring.tf`.
- Rules: team.md Deployment (secrets leak through logs; the audit log),
  phases/operation.md (every component has a health metric).
