# Security Test Instructions — Unique usernames

This intent changes authentication (a new sign-in key, two public lookups, a
rename and hold model, contact replacement and removal) and adds a private
field on a children's-data app. The security requirements are NFR1
(anti-enumeration), NFR2 (rate limits), NFR3 (privacy boundary), FR9 (username
private to its owner) and the unit security NFRs. This file lists each security
check, the command that runs it, and which checks run only in CI or only
against a deployed host.

## 1. Authentication and anti-enumeration (automated, backend)

| Target | What it asserts | Check |
|---|---|---|
| NFR1, FR4.3, U1 NFR1.1 | unknown username, password-less account and wrong password return the identical full response (`auth.password.wrong`), with one statement and one scrypt each | `tests/auth/test_username_sign_in.py` |
| U1 NFR1.4, NFR1.5, NFR1.7, FR2.4 | sign-up draft response is the same whether or not the contact has an account; `account.username.unavailable` never reveals held vs taken | `tests/accounts/test_verify_first_signup.py`, `test_username_claims.py` |
| U2 NFR1.1–1.4, FR6.7 | the already-added lookup by email discloses only "a teacher recorded this", never a name | `tests/accounts/test_lookup.py`, `tests/batches/test_roster_states.py` |
| NFR2, FR3.2, FR4.4, U1 NFR2.1–2.12, U2 NFR2.1–2.5 | every ceiling driven to its limit and one past: availability (per /64, per /48, global alert), username sign-in failures (per username, cross-network rule), rename claims, verify-time replacements, contact changes per day | `tests/auth/test_username_sign_in.py`, `tests/accounts/test_username_claims.py`, `tests/accounts/test_ceilings.py`, `tests/accounts/test_contact_change.py` |
| U1 NFR3.2, NFR3.4, U2 NFR3.4, FR9.3 | no sentinel username, phone, email or code in any log record, audit row or error body | `tests/accounts/test_username_sentinels.py`, `tests/accounts/test_contact_sentinels.py` |
| U1 NFR3.3, FR7.4 | a deleted account's hold stores only an HMAC digest and expiry | `tests/accounts/test_usernames.py`, `tests/governance/test_deletion_paths.py` |
| U1 NFR3.5 | both availability lookups are `POST` with a body, so no username reaches a URL | `tests/contract/test_privacy_schema.py` |
| FR10.1 | forgot-password and both deletion paths refuse a username | `tests/accounts/test_verify_first_signup.py`, `tests/governance/test_deletion_paths.py` |

All run in B1 (`CI=true make PY=.venv/bin/python lint typecheck test`).

## 2. Privacy boundary (automated, backend)

| Target | Check |
|---|---|
| NFR3, FR9.1, FR9.2 | `tests/contract/test_privacy_schema.py` walks every non-owner response in the generated OpenAPI schema; `tests/contract/test_admin_contract.py` holds the admin forbidden-field list; a test fails if `account.username` exists without being in both |
| NFR3 precondition | `tests/conftest.py` meta-check: `current_user` is `shikkhok_app`, not a superuser, `row_security` on and the policy present, before the privacy suite runs. **The privacy suite's pass counts only if this held** and the JUnit report shows no skipped test (B2) |
| FR3.3 | `tests/contract/test_route_lenses.py`: the new public route is in `PUBLIC_ROUTES` and the count is asserted |

## 3. Client security checks (automated)

| Surface | Target | Check | Command |
|---|---|---|---|
| Android | U3 NFR3.2–3.5 | masked `toString` (`IdentifierToStringTest`), no logging API (`NoLoggingTest`, detekt `ForbiddenImport` on `android.util.Log` and Ktor logging), nothing secret saved (`NoSavedSecretsTest`), username only where allowed (`UsernameDeclarationScanTest`) | B3 |
| Android | forbidden identifiers at commit time | Android Lint with `HardwareIds` fatal (`android/lint.xml`) | B3 (`lintDebug`) |
| Web | U4 NFR3.2–3.7 | `noIdentifierLeaks.test.tsx` (no identifier in storage, title, route state, console, IndexedDB), `lintConfig.test.ts` (`no-console` is an error on every shipped file), `usernameKeyScan.test.ts` | B4 |
| Web | U4 NFR3.17 | `scripts/check-bundles.mjs`: the admin and main bundles are separate | B4 |

## 4. Static analysis (SAST)

| Tool | Scope | Command |
|---|---|---|
| Ruff `S` rules (bandit) and the rest of the named rule sets | `app`, `tests` | B1 (`make lint`) |
| mypy, strict islands on `app.money`, `app.schemas` | `app` | B1 (`make typecheck`) |
| detekt, Android Lint | `android/` | B3 |
| ESLint `--max-warnings 0`, `tsc` | `web/` | B4 |

## 5. Secrets and dependency CVEs

| Check | Where it runs | Blocking? | Run locally in this stage? |
|---|---|---|---|
| Gitleaks, full history, with the "history is deep enough" precondition step | CI `backend` job | yes | **No.** The binary is not installed here and downloading it was refused by this environment's permission policy. CI is the arbiter |
| Lockfile install with `--require-hashes` | CI `backend` job | yes | Not separately: the local `.venv` was installed from it earlier. `requirements.txt` and `pyproject.toml` are unchanged in this intent |
| "Lockfile is current" (pip-compile against the committed lock) | CI `backend` job | yes | Not run: neither input changed in this intent, so its result equals `main`'s |
| `pip-audit --requirement requirements.txt --desc --strict` | CI `backend` job, annotating | no (blocks at release gate) | **Yes**: `make audit` equivalent, see test-results.md |
| `npm audit --omit=dev --audit-level=low` and `npm audit --audit-level=high` | CI `web` job, annotating | no | **Yes**, see test-results.md |
| `osv-scanner` on the Gradle lockfiles | CI `android-unit` job, annotating | no (blocks in `release-android.yml`) | **No**: not installed; download refused. CI is the arbiter. No Gradle lockfile changed in this intent |

## 6. Dynamic testing (DAST)

The OWASP ZAP API scan lives in `.github/workflows/security-scan.yml`, triggered
by `workflow_dispatch` against a deployed environment, driven from the committed
`openapi.json`; High or above blocks promotion. It cannot run in this stage
(no deployed host). It belongs to `deployment-execution` and the release
checklist. The new routes (`/v1/accounts/username-availability`,
`/v1/me/username-availability`, `/v1/me/username`, `/v1/me/contact/remove`)
are in `openapi.json`, so the scan will import them.

## 7. What no automated test covers

- Timing equality of the three sign-in refusals (U1 NFR1.2): manual staging
  medians, `deployment-execution`.
- Whether a real screen reader announces the availability hint (U4): not
  verified and not claimed.
- `MainActivity` root wiring of the username gate (U3): review only.

## Sources

- `inception/requirements-analysis/requirements.md` FR3, FR4, FR7, FR9, FR10,
  NFR1–NFR3.
- Unit `nfr-requirements/security-requirements.md` for U1–U4.
- `.github/workflows/check.yml`, `.github/workflows/security-scan.yml`,
  `Makefile` (`lint`, `audit`), `tests/conftest.py`.
- `aidlc/spaces/default/memory/team.md` § Deployment (two-speed CVE model).

## Assumptions & Open Questions

- **Assumption**: the annotating CVE steps are reproduced locally where the
  tool is present; their findings, if any, are recorded but do not block, as
  the affirmed two-speed model requires.
- **Open**: Gitleaks and osv-scanner were not run locally; their verdict comes
  from CI on the pull request.
