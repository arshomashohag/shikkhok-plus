# Scalability Requirements — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1 (kind: service). The inception list
has no scalability NFR of its own. Growth and concurrency are what keep NFR8's
responsiveness true as data accumulates, so they are carried as NFR8.5
onwards. Targets are sized for Phase 1 (closed testing on one Lightsail host)
and stay valid in Phase 2 (one container, RDS `db.t4g.micro`), team.md
Deployment.

## Load projection

The product is unreleased. Its users are the closed-testing audience, and
"hardly anyone" uses it today (contract-summary, 2026-11-14 direction). U1's
load is bounded by its own ceilings more than by its users. Per /64 and hour:
at most 30 typing lookups, 30 claims, 20 replacements and 20 failed username
sign-ins. Product-wide, the typing lookups alert at 1,000 an hour.

## Requirements

| ID | Requirement | Verifier |
|---|---|---|
| NFR8.5 | **`username_hold` stays bounded by accounts.** A rename or reclaim releases one name for 30 days. One ordinary rename and one exempt reclaim are allowed per 30-day window, so one account has at most **2 live holds** of its own at any instant. Each deletion adds one hold for nobody, for 30 days. So live rows ≤ 2 × accounts + deletions in the last 30 days. Expired rows waiting for the daily purge are at most one day's worth on top. One row per digest (BR7.3). | A test that runs a reclaim cycle (rename, reclaim, then a refused third) and asserts at most 2 live holds for the account; NFR4.7's purge test |
| NFR8.6 | **Counter rows stay bounded and short-lived.** A failed username sign-in writes up to four Family D rows: one per key and window, upserted, so repeats add no rows. Across names, one /64 can create at most 20 `un_fail_net_hour` rows an hour, because `un_fail_ip_hour` caps its failures at 20. Every new scope's rows are deleted by the existing retention purge after the counter table's 48-hour window (`rate_limit_counter` disposition). No new purge job is added. | The existing purge test, extended with one row of each new kind that is older than 48 hours |
| NFR8.7 | **No new global lock or hot row beyond what is built.** Advisory keys are per username key and per account, never global (U2 NFR8.11's rule, extended to the `username:` namespace). The one shared row per hour is `un_lk_global_hr`'s `global` counter, upserted atomically, the same shape as the built `lk_global_hour`. Two workers contend on it exactly as they do on the built scope. | Code check in review: no `lock_keys` call with a constant key; the existing atomic-upsert test pattern applied to the new global scope (two concurrent increments give a count of 2) |
| NFR8.8 | **Lookups stay constant-time as accounts grow.** Every username read is a single index probe (NFR8.2), so availability, claim and sign-in cost does not grow with the number of accounts or holds. | NFR8.2's plan test and NFR8.3's seeded statement-count test |

## Scaling triggers

None are introduced. The existing ones stand: a move to Phase 2 hosting is a
deployment decision (team.md). If `un_lk_global_hr` alerts in ordinary use,
not under attack, the lookup ceilings are re-sized in a later change. They are
not raised silently, because NFR2 fixes them as no looser than the
already-added lookup.

## Assumptions & Open Questions

- Open questions: None.

## Sources

- Requirements NFR2 and NFR8: `inception/requirements-analysis/requirements.md`.
- Functional design: `functional-spec.md` § 3.2 and W10; `rules.md` BR6.2,
  BR6.4, BR7.3, BR7.6.
- U2's scalability requirements, NFR8.11 (advisory keys never global).
- Code read: `app/auth/ceilings.py` (`_UPSERT`, `_window_start`),
  `app/governance/commands.py` (`WINDOWS`, `_CLASS_AGE`).
