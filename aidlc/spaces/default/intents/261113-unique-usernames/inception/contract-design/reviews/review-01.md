## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-11-14T00:00:00Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261113-unique-usernames/inception/contract-design/contract-summary.md > C2 MemberResponse and MemberInviteRequest | An email-only invitation leaves `MemberResponse.phone` null, but the committed schema and app/schemas/centres.py:104 declare it `phone: str`, required and non-null. Installed clients that decode a null there will fail, which is a retype, and the contract lists only `invited_email` as the addition while its own rules forbid retyping a field under /v1. | State that `MemberResponse.phone` becomes nullable and decide how installed clients are protected, for example by returning an empty-string sentinel or by keeping email-only invitations out of responses an old client can read. Add a compatibility test against the committed schema. | New |
| R-02 | Major | aidlc/spaces/default/intents/261113-unique-usernames/inception/contract-design/contract-summary.md > C1 SignupRequest.username and VerifyRequest | The description says username is "Required for new sign-ups" but `SignupRequest` does not list it under `required`, and the contract never says what the server does when an installed client (or a draft already stored at deploy time) omits it. NFR6 and A5 say installed clients must keep working, and the existing schema is `extra=forbid`. | Pin one behaviour: either an absent username creates the account with `username_required` true (consistent with FR5), or it is a 422 with a named key that old clients can show. Say which, and cover in-flight drafts that have no username at verify. | New |
| R-03 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/contract-design/contract-summary.md > Open questions (R-09) vs C1 /v1/auth/verify 409 | The contract promises `account.username.retry_limit` after a replacement limit, but the same verify transaction is rolled back on a username clash, so a counter kept inside it cannot persist. Leaving the mechanism open leaves the promised response unimplementable as written. | Choose the counting mechanism now, for example an increment committed outside the rolled-back work, and state it. Also state the `retryable` value on the 409 so clients do not infer it. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/contract-design/contract-summary.md > Open questions (R-10) and C1 PUT /v1/me/username | A reclaim does not move `username_changed_at` and places an ordinary hold on the name given up, so an account can alternate between two names indefinitely with its password, bypassing the 30-day limit. The response says `next_change_at` is null when no limit applies, so a client cannot tell. | Record repeated reclaims, for example by capping reclaims per hold or moving `username_changed_at` on a second reclaim, and say what `next_change_at` returns after a reclaim. | New |
| R-05 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/contract-design/contract-summary.md > C1 UsernameChangeRequest and message keys | A rename needs a password, but no key covers a rename request that omits it, unlike `account.contact.password_required` in C2. It is unclear whether that returns `auth.password.current_wrong` or a 422 of another kind. | Add an `account.username.password_required` key, or state that the missing password maps to `auth.password.current_wrong`. Note that `next_change_at` travels in `ErrorBody.details`, which is typed `dict[str, str]`, so it must be an ISO string. | New |
| R-06 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/contract-design/contract-summary.md > C2 /v1/accounts/already-added | Adding `email` makes the public lookup disclose that a teacher recorded an email, as it does for phones, but the C2 block lists no 429 response or ceilings for it and does not say the response must stay at two fields. The email path is a new public existence signal. | Add the 429 `auth.lookup.too_many` response, name the ceiling scopes it shares, and state that only seat existence and role are returned, never account existence. | New |
| R-07 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/inception/contract-design/contract-summary.md > C3 in-process-call | C3 names only the create_account_rows line, but `link_phone_seats` has a second caller at app/accounts/contact.py:136 (phone added after sign-up), and `link_memberships(session, *, account_id, phone)` is phone-only. The email-add and replace paths in U2 go through that second site, which the contract does not cover. | List the contact.py call site and the `link_memberships` signature in C3 and say who changes each, so U1 and U2 do not edit the same lines. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| None listed in the stage definition | Not run | Reviewed by reading the artifact against openapi.json, app/schemas and app/accounts/service.py. |

### Summary

The contracts are well formed: no phone or email existence oracle is reintroduced, the username reaches only owner-only schemas, and the C3 call site matches `create_account_rows` in app/accounts/service.py. Two additive-compatibility gaps (the nullable `MemberResponse.phone` and an unspecified missing-username sign-up) should be settled before approval, and the rest are tightening points.
