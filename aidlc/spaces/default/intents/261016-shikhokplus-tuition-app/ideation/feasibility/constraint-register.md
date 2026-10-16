# Constraint Register — ShikhokPlus

**Stage**: feasibility (1.3)
**Phase**: Ideation
**Date**: 2026-10-17

Constraints bind design. Each row is something later stages may not contradict
without an explicit, recorded decision to change it.

---

## Technical constraints

| ID | Constraint | Origin | Binds |
|---|---|---|---|
| TC-1 | `compileSdk` and `targetSdk` must be 36 (Android 16). Play requires API 36+ for all new app submissions, already in force. | [play-target-sdk] | Android build config |
| TC-2 | Package namespace is `com.shikkhokplus.app`. Permanent once published. | [intent: Q3] | Android module, Play Console |
| TC-3 | No device or advertising identifier may be transmitted anywhere: AAID, SIM serial, build serial, BSSID, MAC, SSID, IMEI, IMSI. | [intent: Q17] | Every SDK choice, analytics, crash reporting |
| TC-4 | The device phone number must never be read via `TelephonyManager`. Numbers are always typed by the user. | [play-families] [intent: Q17] | Auth UI, onboarding |
| TC-5 | No SMS read permission. OTP autofill via SMS Retriever API only. | [desc §11] | Auth implementation |
| TC-6 | No ads SDK. | [intent: Q17] | Dependency set |
| TC-7 | Money is fixed-point decimal, BDT only: `NUMERIC(12,2)` server-side, `BigDecimal` in Kotlin, never float or double, serialized as a JSON string. | [Q8] | Schema, API contract, client models |
| TC-8 | All writes require connectivity. Cached reads only; no local write queue in V1. | [intent: Q6] [intent: Q18] | Android data layer, UX error states |
| TC-9 | Every rule lives server-side. The Android app holds no business logic; it renders what the server computes. | [desc §12a] | Both surfaces |
| TC-10 | `Batch` ownership is indirected through an `Owner` entity from day one, so organisation-owned batches need no `Batch` migration later. | [desc §12b] | Schema |
| TC-11 | Role is computed per request from owned batches and enrollments. No role field on the account, and no cached role. | [desc §3] [desc §12c] | Auth, every endpoint |
| TC-12 | Fee-cycle generation is idempotent by database constraint — unique on `(enrollment_id, period)` — not by application-level guard. | [desc §12d] | Schema, scheduled job |
| TC-13 | Nothing a student or guardian writes is visible to any teacher. Enforced structurally: separate tables, row-level security, distinct response schemas. | [desc §4] [desc §12f] | Schema, API, authorization |
| TC-14 | A platform administrator may see subscriber information only — teacher name, plan, payment status — never student or guardian data. | [intent: Q20] | Future admin surface |
| TC-15 | Bangla and English from the start. No hardcoded strings; Bangla text must not break layouts. | [desc §11] | Every Android screen |
| TC-16 | Android App Bundle output, signing config, release and debug flavours, R8 rules that survive minification. | [desc §11] | Build config |
| TC-17 | Small APK and low-end-device performance are design constraints, not aspirations. | [desc §11] | Dependency choices, image handling |
| TC-18 | Correct back-stack behaviour and accessibility basics. Play's pre-launch report checks both. | [desc §11] | Navigation, every screen |
| TC-19 | Two account-deletion paths: in-app, plus an externally accessible route usable without reinstalling the app. | [play-deletion] [desc §11] | Backend, Android, web |
| TC-20 | Mandatory tests on money paths: fee-cycle arithmetic, carry-forward, partial approval, waiver. | [desc §13.6] | Test suite, CI |

---

## Organisational constraints

| ID | Constraint | Origin | Binds |
|---|---|---|---|
| OC-1 | Solo build. The agent writes most code; the user reviews. | [Q1] | Delivery pace, review load |
| OC-2 | Backend must favour Python or Node/TS — the user's strong languages. No Kotlin backend. | [Q2] | Stack choice |
| OC-3 | Android choices must be conventional and well-documented. No declared Android experience, so review depth is limited there. | [Q2] | Android architecture |
| OC-4 | Infrastructure under USD 50/month. | [Q3] | Hosting, database, all managed services |
| OC-5 | Closed testing with pilot teachers in about 1 month. | [Q4] | Scope sequencing |
| OC-6 | Structural concerns are raised as they arise; naming and conventions are not. | [Q12] | How the agent reports |
| OC-7 | No organisational blockers; availability is not constrained. | [Q10] | — |

---

## Regulatory and compliance constraints

| ID | Constraint | Origin | Binds |
|---|---|---|---|
| RC-1 | Play target audience is mixed, including children. Families policy applies in full. | [intent: Q17] | Play Console declarations, SDK set |
| RC-2 | COPPA compliance (US children's privacy). | [play-families] [intent: Q17] | Data handling, retention, disclosure |
| RC-3 | GDPR-K compliance (EU children's data). | [play-families] [intent: Q17] | Data handling, subject rights |
| RC-4 | Data Safety form content must declare exactly what personal data is collected (phone numbers, children's names, attendance, marks), why, whether shared, and how deleted. | [desc §11] [play-deletion] | Release deliverable |
| RC-5 | Privacy policy must be drafted, including any data retained post-deletion for security, fraud or regulatory reasons. | [desc §11] [play-deletion] | Release deliverable |
| RC-6 | Only certified ads SDKs may be used in Families apps — moot here, since no ads SDK is used at all. | [play-families] | Dependency set |
| RC-7 | No general Bangladeshi data-residency statute applies; no residency constraint imposed. Nearest region chosen for latency. | [Q7] | Hosting region |
| RC-8 | Children's data at rest must be encrypted. This disqualifies hosting tiers without storage encryption. | [RC-1] [aws-lightsail] | Database tier choice |

---

## Constraints deliberately *not* imposed

Recording these matters as much as the constraints themselves, because each was
considered and rejected.

| Not a constraint | Why |
|---|---|
| Data residency in Bangladesh | No statute requires it; the user imposed none. [Q7] |
| PCI-DSS scope | No payment gateway in V1; money moves out-of-band and the app records claims only. [desc §9] |
| High availability / multi-AZ | Not justified at 100 teachers inside a USD 50 budget. Single-AZ with backups is the accepted posture. [Q3] [Q9] |
| Offline write capability | Explicitly excluded by the user. [intent: Q18] |
| Subscription state in V1 | Deferred, but must be absorbable later. [intent: Q20] |
| Multi-device session management | Out of V1. [intent: Q12] |

---

## Assumptions & Open Questions

- RC-2 and RC-3 are asserted from the Families policy's own text, which requires
  COPPA and GDPR compliance for apps whose audience includes children. Whether
  ShikhokPlus has actual US or EU users is unknown and arguably irrelevant, since
  Play imposes the obligation through its policy rather than through
  jurisdiction. Not independently legally reviewed. [assumption]
- TC-7's `NUMERIC(12,2)` precision allows values up to 10^10 taka, far beyond any
  realistic tuition fee. Chosen for headroom rather than from a stated
  requirement. [assumption]
- TC-1's API 36 requirement was verified against Google's official
  documentation on 2026-10-17. Play requirements change annually, so this needs
  rechecking at release. [assumption]
- RC-8 is inferred: the Families policy requires protecting children's privacy
  and complying with applicable law, and encryption at rest is the standard
  control. No policy text names encryption at rest explicitly. [assumption]
- No SMS gateway vendor is selected, so no vendor-specific constraint (sender-ID
  registration, minimum commitment, masked-sender rules) is yet recorded.
  [assumption]

## Sources

- [desc] Initial description, including §3, §4, §9, §11, §12 and §13.6.
- [Q1]–[Q12] Confirmed answers in `feasibility-questions.md`.
- [intent: Q3], [intent: Q6], [intent: Q12], [intent: Q17], [intent: Q18],
  [intent: Q20] — confirmed answers carried from `ideation/intent-capture/`.
- [play-target-sdk] https://developer.android.com/google/play/requirements/target-sdk
  — retrieved 2026-10-17.
- [play-families] https://support.google.com/googleplay/android-developer/answer/9893335
  — retrieved 2026-10-17.
- [play-deletion] https://support.google.com/googleplay/android-developer/answer/13327111
  — retrieved 2026-10-17.
- [aws-lightsail] https://aws.amazon.com/lightsail/pricing/ — retrieved
  2026-10-17.
