# Project-Level Rules

> Project-specific specialisation and corrections. Loaded after `org.md` and
> `team.md` as strict-additive guidance; contradictions with broader policy
> are rejected. Populated by practices-discovery and the self-learning loop.
>
> Use sparingly: most teams don't need a project layer. Reach for it
> only when this specific project needs stable, durable guidance beyond the
> team practice (for example, package-specific release checks or an additional
> regression suite for a legacy component).

## Way of Working

<!-- Project-specific specialisation. Example: -->
<!-- This monorepo requires package-scoped branch names and a package owner -->
<!-- review in addition to the team's normal merge policy. -->

## Walking Skeleton

<!-- Project-specific specialisation. Example: -->
<!-- The walking skeleton must exercise the legacy service adapter as well -->
<!-- as the new service boundary. -->

## Testing Posture

<!-- Project-specific specialisation. -->

## Guard Policy

<!-- Project-specific. Mode: strict, relaxed, or off. Strict here holds for every intent, whatever one person asks in chat; relaxed or off here applies to every intent whose policy came from its scope, unless the person sets another; changing this line changes it. A section under the retired Change Control heading, written by an earlier release, is still read. -->

## Deployment

<!-- Project-specific specialisation. -->

## Code Style

<!-- Project-specific specialisation. -->

## Tech Stack

<!-- Technology choices locked for this project. -->

## Decided

<!-- Decisions made in earlier stages that should not be re-asked. -->
<!-- Format: DECIDED: [decision] (Stage [slug], [date]) -->

## Scope Overrides

<!-- Custom scope rules for this project. -->

## Forbidden

<!-- Populated by practices-discovery affirmation gate. -->
<!-- Format: NEVER [behavior] (affirmed [date]) -->
<!-- Example: NEVER throw exceptions across service layer boundaries (affirmed 2026-05-17) -->

- NEVER use `float` or `double` for a money value anywhere in the stack, in any language, in storage, in transit or in memory. [TC-7] [D-20] (affirmed 2026-10-16)
- NEVER transmit a device or advertising identifier anywhere: AAID, SIM serial, build serial, BSSID, MAC, SSID, IMEI or IMSI. [TC-3] [D-37] (affirmed 2026-10-16)
- NEVER read the device phone number via `TelephonyManager`; the number is always typed by the user. [TC-4] [D-35] (affirmed 2026-10-16)
- NEVER request SMS read permission; OTP autofill uses the SMS Retriever API only. [TC-5] (affirmed 2026-10-16)
- NEVER add an ads SDK, or an analytics or crash-reporting SDK that transmits a device or advertising identifier. [TC-6] [D-37] (affirmed 2026-10-16)
- NEVER run the privacy-boundary test suite as a database superuser or table owner, because both bypass row-level security and the suite would then pass against a broken or entirely absent policy. [Q9] [pg-rls] [TC-13] (affirmed 2026-10-16)
- NEVER expose anything a student or guardian writes to any teacher. [TC-13] [D-5] (affirmed 2026-10-16)
- NEVER expose student or guardian data to a platform administrator, whose visibility is limited to subscriber information — teacher name, plan and payment status. [TC-14] [D-6] (affirmed 2026-10-16)
- NEVER store or log an OTP in plaintext, and never return a response or timing that reveals whether a phone number exists. [D-33] [architecture §7] (affirmed 2026-10-16)
- NEVER hardcode a credential, API key, token or secret in the repository or in a built image. [construction-phase rules] [D-33] (affirmed 2026-10-16)
- NEVER accept a write without connectivity in V1; there is no local write queue, and a failed write surfaces an explicit retry prompt rather than queueing silently. [TC-8] [D-9] (affirmed 2026-10-16)
- NEVER let the Android client compute a fee balance, an authorization decision or any other business rule. [TC-9] [D-31] (affirmed 2026-10-16)
- NEVER weaken a defined coverage floor or an affirmed quality target to make a build step pass. [org: Testing Posture] (affirmed 2026-10-16)
- NEVER change the package namespace `com.shikkhokplus.app`; it is permanent once published. [TC-2] [D-38] (affirmed 2026-10-16)

- NEVER record an obligation without naming the verifier that discharges it, and never discharge a performance or layout obligation with a correctness test. [TC-15] [TC-17] [D-43] [PU-3.6] (affirmed 2026-10-22)

- NEVER let a comment state a count, a version or a scope that nothing checks; where a comment states a number, the number is a claim and either a test asserts it or the number comes out. [app/contract/routes.py:33-49] (affirmed 2026-10-22)

## Mandated

<!-- Populated by practices-discovery affirmation gate. -->
<!-- Format: ALWAYS [behavior] (affirmed [date]) -->
<!-- Example: ALWAYS use Result<T,E> for fallible operations in service layer (affirmed 2026-05-17) -->

- ALWAYS write tests for the money paths — fee-cycle arithmetic, carry-forward, partial approval and waiver — as a non-negotiable deliverable of the work that implements them, never as a follow-up. [TC-20] [D-23] [PU-5.7] (affirmed 2026-10-16)
- ALWAYS represent money as fixed-point decimal in BDT: `NUMERIC(12,2)` server-side, a decimal-backed value type in Kotlin, and serialized across the API as a JSON string. [TC-7] [D-20] (affirmed 2026-10-16)
- ALWAYS confine money arithmetic to a single module, with the rounding mode declared once in that module, and enforce the boundary with an import-boundary check present from the first commit rather than added after a violation. [D-20] [PU-5.6] [Q9] (affirmed 2026-10-16)
- ALWAYS connect database tests as a restricted non-superuser role, with a meta-test asserting that `current_user` is not a superuser and that row-level security is in force before the privacy suite runs. [Q9] [TC-13] [pg-rls] (affirmed 2026-10-16)
- ALWAYS test fee-cycle generation idempotency with overlapping concurrent generations, never with sequential calls. [Q9] [TC-12] [D-21] (affirmed 2026-10-16)
- ALWAYS enforce fee-cycle generation idempotency with the database unique constraint on `(enrollment_id, period)` and `ON CONFLICT DO NOTHING`, never with an application-level "has this already run" guard. [TC-12] [D-21] (affirmed 2026-10-16)
- ALWAYS provide both account-deletion paths — in-app, and an externally accessible route usable without reinstalling the app — as release-blocking V1 deliverables, with a test per path asserting that deletion removes what the Data Safety form claims it removes and retains only what the privacy policy discloses. [TC-19] [RC-4] [RC-5] (affirmed 2026-10-16)
- ALWAYS keep every business rule server-side; the Android app holds no business logic and renders only what the server computes. [TC-9] [D-31] (affirmed 2026-10-16)
- ALWAYS compute role as a per-request lens from owned batches and enrollments, with no role field on the account and no cached role, and never trust a client-supplied lens hint for authorization. [TC-11] [D-2] (affirmed 2026-10-16)
- ALWAYS enforce the student-and-guardian privacy boundary structurally in all three layers — separate tables by writer, PostgreSQL row-level security on `profile`, and teacher-facing response schemas carrying no profile fields — rather than by filtering in individual queries. [TC-13] [D-5] [D-7] (affirmed 2026-10-16)

- ALWAYS check a new dependency against the forbidden-identifier set before adding it, since removing an SDK after the Families-policy declaration is far more costly than not adding it. [TC-3] [TC-6] [D-37] [RC-1] (affirmed 2026-10-16)
- ALWAYS externalize user-facing strings with Bangla and English present from the start, and verify that longer Bangla text does not break the layout. [TC-15] [D-43] (affirmed 2026-10-16)
- ALWAYS encrypt children's data at rest, which disqualifies any hosting or database tier without storage encryption. [RC-8] [D-29] (affirmed 2026-10-16)
- ALWAYS target `compileSdk` and `targetSdk` 36 (Android 16), and recheck the Play requirement at release. [TC-1] [D-39] (affirmed 2026-10-16)
- ALWAYS raise structural concerns as they arise, and do not raise naming or convention concerns. [OC-6] [D-45] (affirmed 2026-10-16)
- ALWAYS treat the Data Safety form, the privacy policy and the Families target-audience declarations as release-blocking V1 deliverables, not follow-ups. [D-41] [RC-4] [RC-5] (affirmed 2026-10-16)
- ALWAYS prefer conventional, well-documented Android choices over clever ones, because review depth on that surface is limited — while letting project constraints outrank the sample wherever they conflict. [OC-3] [D-27] (affirmed 2026-10-16)
- ALWAYS keep infrastructure spend under USD 50/month. [OC-4] (affirmed 2026-10-16)

- ALWAYS lock dependency resolution on every surface that has a package manager, and make the CI install read the lockfile rather than re-resolve; a CI step may not be labelled as a lockfile or verification check unless it performs one. [team: Deployment] [check.yml:88] (affirmed 2026-10-22)

- ALWAYS pair a mechanical control named in a practice with the deliverable unit that installs it, and treat a unit as incomplete while a control assigned to it is missing. [team: Way of Working] (affirmed 2026-10-22)

- ALWAYS enforce the forbidden-identifier set at commit time as well as at release time, so a forbidden framework reference cannot reach `main` and be found only on the build that was about to ship. [TC-3] [TC-4] [D-35] [D-37] (affirmed 2026-10-22)

- ALWAYS assert that a test suite's precondition held before treating its pass as evidence, so a suite that silently skipped is never read as a suite that passed. [tests/conftest.py] [pg-rls] (affirmed 2026-10-22)

## Corrections

<!-- Project-specific corrections from human feedback. -->
<!-- Format: NEVER/ALWAYS [behavior] (learned [date]) -->
- When a two-way choice is settled by picking the option with no automated verifier, write that sentence in the artifact rather than describing only what the manual check is. Here PU-3.6's latency obligation moved from a Macrobenchmark to a timed manual pilot check, and the honest record is both halves: the named verifier, and the plain statement that nothing automated discharges it. A manual verifier described without that sentence reads, to the next person, as a verifier. (learned 2026-10-23) <!-- cid:261022-remaining-slices:delivery-planning:5fa2cff6686c93ea8090b3ae705d9c720441bc90f75dae09acdaa874b0756011 -->
