# Unit / Story Map

**Stage**: units-generation (2.7)
**Phase**: Inception
**Depth**: Comprehensive

> Which Unit implements which story. Order *within* a Unit is noted; order
> *between* Units is Delivery Planning's (2.9) decision, not stated here.

## Sources

- [upstream] `inception/user-stories/stories.md` — 45 stories
- [upstream] `inception/units-generation/unit-of-work.md`
- [upstream] `inception/units-generation/unit-of-work-dependency.md`

---

## Story to Unit

| Story | Unit ID | Directory | Note |
|---|---|---|---|
| US1.1 | U3 | `u3-identity-and-access` | OTP issue and verify, the skeleton auth path |
| US1.2 | U3 | `u3-identity-and-access` | Lens resolution per request, no stored role |
| US1.3 | U4 | `u4-batches-and-enrollment` | Teacher adds a student; dormant account resolution |
| US1.4 | U3 | `u3-identity-and-access` | An account owning no batches is never offered a teacher lens |
| US1.5 | U3 | `u3-identity-and-access` | Owner-private profile under row-level security |
| US1.6 | U11 | `u11-privacy-and-governance` | In-app deletion path — moved out of U3 deliberately, see note |
| US1.7 | U11 | `u11-privacy-and-governance` | Externally accessible deletion route — same reason |
| US1.8 | U3 | `u3-identity-and-access` | Refresh-token rotation with reuse detection |
| US1.9 | U3 | `u3-identity-and-access` | Lens switching without re-authentication |
| US2.1 | U4 | `u4-batches-and-enrollment` | Batch creation with subjects and schedule |
| US2.2 | U4 | `u4-batches-and-enrollment` | Add student to batch |
| US2.3 | U4 | `u4-batches-and-enrollment` | Attach an existing account to a new enrollment |
| US2.4 | U4 | `u4-batches-and-enrollment` | Per-enrollment fee override — the anchor U7 charges against |
| US2.5 | U4 | `u4-batches-and-enrollment` | Edit and remove an enrollment |
| US2.6 | U4 | `u4-batches-and-enrollment` | Teacher-typed display name and guardian number |
| US2.7 | U4 | `u4-batches-and-enrollment` | Student and guardian batch lists |
| US2.8 | U4 | `u4-batches-and-enrollment` | Guardian child selection and hide-batch preference |
| US3.0 | U5 | `u5-sessions-and-attendance` | Session instances from weekly recurrence |
| US3.1 | U5 | `u5-sessions-and-attendance` | Atomic roster write, mid-class path |
| US3.2 | U5 | `u5-sessions-and-attendance` | Topic log |
| US3.3 | U5 | `u5-sessions-and-attendance` | Reschedule and cancel |
| US3.4 | U5 | `u5-sessions-and-attendance` | Attendance visible to student and guardian |
| US3.5 | U5 | `u5-sessions-and-attendance` | Announcements per batch |
| US4.1 | U6 | `u6-exams-and-marksheets` | Exam creation per batch and subject |
| US4.2 | U6 | `u6-exams-and-marksheets` | Marksheet visibility toggle |
| US4.3 | U6 | `u6-exams-and-marksheets` | Mark entry with four result states |
| US4.4 | U6 | `u6-exams-and-marksheets` | Batch-scoped marksheet and guardian progress view |
| US5.1 | U7 | `u7-fee-cycles-and-ledger` | Fee-cycle generation, idempotent by constraint |
| US5.2 | U7 | `u7-fee-cycles-and-ledger` | Carry-forward and the ledger quantities (arithmetic in U1) |
| US5.3 | U7 | `u7-fee-cycles-and-ledger` | Server-computed fee status |
| US5.4 | U7 | `u7-fee-cycles-and-ledger` | Student and guardian fee views |
| US6.1 | U8 | `u8-payment-claims-and-verification` | Payment claim submission, identical in both lenses |
| US6.2 | U8 | `u8-payment-claims-and-verification` | Pending-verification list |
| US6.3 | U8 | `u8-payment-claims-and-verification` | Approve, approve-less, reject; carry-forward or waive |
| US6.4 | U8 | `u8-payment-claims-and-verification` | Payment history views |
| US7.1 | U9 | `u9-teacher-insights` | Cross-batch dues, driven by outstanding balance |
| US8.1 | U9 | `u9-teacher-insights` | Monthly earnings |
| US8.2 | U9 | `u9-teacher-insights` | Earnings trend |
| US8.3 | U9 | `u9-teacher-insights` | Collection rate — inherits an open arithmetic definition |
| US8.4 | U9 | `u9-teacher-insights` | Next upcoming exam — needs U6 only, not the money path |
| US9.1 | U7 | `u7-fee-cycles-and-ledger` | Fee-due reminder and the FCM adapter; marks trigger in U6 |

## Stories that span units

Four stories are cross-cutting by nature. Each is assigned, not deferred — the
assignment names which Unit owns the mechanism and which Units carry the
obligation.

| Story | Units | How it splits |
|---|---|---|
| US9.2 | U2, U5, and every write-bearing Unit | The error taxonomy and the server-supplied `retryable` envelope field are U2 — `retryable` is not a per-feature choice. The queued three-state case is U5. Preserving typed input on a failed write is a standing obligation on every Unit that writes. |
| US9.3 | U3, then every screen-bearing Unit | Server-side collation and Latin-numeral rendering are established in U3. Both bundles present, no hardcoded strings, and the longest-Bangla-string layout check are standing per-Unit obligations. |
| US9.4 | U11, and every screen-bearing Unit | AC9.4.3's deletion-confirmation copy is U11, because it must agree with the disposition manifest. No colour-only status and correct back-stack behaviour are per-Unit obligations — AC9.4.2 is a privacy case, not a navigation nicety. |
| US10.1 | U2, U3, and every route-adding Unit | U2 owns the schema-wide no-profile-field invariant and the route-enumeration harness, so they cover routes added later. U3 owns lens resolution and the RLS context. Each feature Unit owns the IDOR probes against its own routes. |

### Three placements worth stating

- **US1.6 and US1.7 move out of the auth Unit into U11.** A deletion path built
  before the disposition manifest exists would delete by ad-hoc logic and then
  need rewriting against the manifest. The manifest is the specification; the
  endpoints are its execution.
- **US9.2's error-taxonomy half sits in U2** because `retryable` is a
  server-supplied envelope field. The client is forbidden business logic
  [TC-9], so it does not infer retryability from a status code — it is told.
- **US10.1 is deliberately distributed.** The schema-wide and route-wide
  guarantees are U2's precisely so they cover endpoints added later; the
  per-route IDOR probes belong to whoever adds the route.

---

## Per-unit view

### U1 `money-core`

**Direct stories**: *(cross-cutting and obligations only)*

**Implementation order within the Unit**: The type, its rounding mode and both chokepoints, then the import-boundary checks, then the property test. Buildable with no database present.

### U2 `api-contract`

**Direct stories**: *(cross-cutting and obligations only)*

**Implementation order within the Unit**: The error envelope and taxonomy first (every later Unit raises into it), then the schema and its diff gate, then the route-enumeration harness and the schema-wide privacy assertion.

### U3 `identity-and-access`

**Direct stories**: US1.1, US1.2, US1.4, US1.5, US1.8, US1.9

**Implementation order within the Unit**: Migration and schema, then OTP issue/verify with the abuse controls, then tokens and `kid`, then lens resolution with the RLS context, then the Compose screen that proves it end to end.

### U4 `batches-and-enrollment`

**Direct stories**: US1.3, US2.1, US2.2, US2.3, US2.4, US2.5, US2.6, US2.7, US2.8

**Implementation order within the Unit**: Owner indirection, then Batch and its children, then enrollment with dormant-account resolution, then the read surfaces and the Room cache pattern.

### U5 `sessions-and-attendance`

**Direct stories**: US3.0, US3.1, US3.2, US3.3, US3.4, US3.5

**Implementation order within the Unit**: Session generation, then the atomic roster write with optimistic concurrency, then the queue and its four states, then the conflict screen, then announcements.

### U6 `exams-and-marksheets`

**Direct stories**: US4.1, US4.2, US4.3, US4.4

**Implementation order within the Unit**: Exam, then mark entry with the four result states and correction history, then the marksheet and its visibility toggle.

### U7 `fee-cycles-and-ledger`

**Direct stories**: US5.1, US5.2, US5.3, US5.4, US9.1

**Implementation order within the Unit**: Ledger entries and the generation constraint, then periods and the clamp, then credit and two-sided carry-forward, then the scheduled job, then the views. Money tests are a completion condition, not a follow-up.

### U8 `payment-claims-and-verification`

**Direct stories**: US6.1, US6.2, US6.3, US6.4

**Implementation order within the Unit**: Claim submission, then the verification decisions, then the ledger writes they produce, then history.

### U9 `teacher-insights`

**Direct stories**: US7.1, US8.1, US8.2, US8.3, US8.4

**Implementation order within the Unit**: Dues first (it shares the ledger-reading and Owner-scoping code the analytics views reuse), then earnings, trend, collection rate, then next exam.

### U10 `release-packaging`

**Direct stories**: *(cross-cutting and obligations only)*

**Implementation order within the Unit**: Signing and flavours, then R8 and the minified build, then the manifest allowlist and DEX scan against that build, then size and benchmark gates, then SBOM.

### U11 `privacy-and-governance`

**Direct stories**: US1.6, US1.7

**Implementation order within the Unit**: The two manifests as data, then the schema-iterating test, then the purge, then both deletion paths, then the generated policy and form text.

---

## Coverage verification

- **45 of 45 stories assigned.** 41 to a single Unit, 4 cross-cutting with an
  explicit split.
- **Every Unit carries rows.** U1, U2, U10 and U11 carry no direct feature
  story by design — they own types, contracts, packaging and governance — and
  each appears in the cross-cutting table or the obligations list.
- **Every target is a declared Unit** in `unit-of-work.md`.
