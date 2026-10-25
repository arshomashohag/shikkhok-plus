# Tech Stack Decisions — D4 `teaching-and-recording`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **D4 makes one genuinely new technology decision, and it is on the device:
> how the offline queue is persisted.** Everything else is reuse. The backend
> adds no library, no service and no infrastructure; the session-generation job
> is a second entry point on the mechanism D3 built.
>
> The device-storage decision is real because **no persistence of any kind
> exists in the Android module today** beyond `TokenStore.kt`. I searched for
> Room, SQLite, DataStore and direct file IO across `android/src/` and
> `gradle/libs.versions.toml`: the only storage in the app is
> `EncryptedSharedPreferences` holding the refresh token. The queue cannot
> reuse something that is not there.

> **`NFRx.y` IDs are GLOBAL across units.** D4's new IDs start above the
> high-water mark each base reached after D3. A bare `NFR1.5`, `NFR2.2` or
> `NFR17.3` below is a **citation**, never an ID defined here.

## Sources

- [upstream] `construction/teaching-and-recording/functional-design/rules.md` —
  BR1.1, BR3.1, BR3.2, BR3.5, BR4.5, BR7.5
- [upstream] `construction/teaching-and-recording/functional-design/entities.md` —
  the six new tables and their constraints
- [prior] `261016-.../inception/requirements-analysis/requirements.md` — NFR1,
  NFR2, NFR5.1, NFR11, NFR16, NFR17
- [upstream] `construction/collecting-fees/nfr-requirements/tech-stack-decisions.md`
  — the scheduler decision D4 inherits
- [codekb] `aidlc/spaces/default/codekb/shikkhok-plus/technology-stack.md`
- [code] `android/build.gradle.kts`, `android/coverage.gradle.kts`,
  `android/detekt.yml`, `android/coverage-floor.txt`,
  `gradle/libs.versions.toml`, `android/src/main/kotlin/.../core/network/TokenStore.kt`,
  `app/fees/commands.py`, `app/db/models.py`, `pyproject.toml` — read 2026-10-24

---

## 1. What D4 reuses unchanged

Nothing in this table is a decision; it is stated so the decision in § 2 is
visible as the only one.

| Layer | Technology | Note |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, psycopg 3 | No new library |
| Database | PostgreSQL 16 | Six new tables, no extension |
| Client | Kotlin 2.0.21, Compose, Ktor 2.3.12, kotlinx-serialization | Seven new screens, no new networking |
| Jobs | The management-command pattern plus `JobHeartbeat` | § 3 |
| Notifications | D3's FCM adapter | Reused, not rebuilt [§ G] |
| Tests | pytest, testcontainers (real PostgreSQL 16), JUnit, Turbine, Robolectric | § 5 |

**NFR16.5** — D4's endpoints stay additive under `/v1/` and an installed client
handles unknown fields rather than failing to parse [NFR16, D-26]. This bites
in D4 for a specific reason: `Mark.result_state` is a **four-value enum a
client switches on**, so adding a fifth value later is a breaking change under
§ B.1.1. **Verifier: the schema-diff gate, plus a client-side test asserting an
unknown enum value does not crash the decoder.**

---

## 2. The decision: how the queue is persisted on the device

### What has to be true

From BR3.2 and NFR5.1, the storage must: persist across process death; hold a
structured payload (a roster of up to 20 entries plus `base_attendance_version`,
`client_mutation_id` and `composed_at`); support a mutable state field per item
across four values; and support ordered retrieval for the sync worker. From
NFR2 it must fit a 15 MB AAB ceiling and a `minSdk` 24, 2 GB-RAM floor. From
the project ALWAYS-rule, any new dependency is checked against the
forbidden-identifier set before it is added.

### The options

| Option | Cost | Fit |
|---|---|---|
| **Room** (`androidx.room`) | A new dependency **plus KSP**, the annotation processor | Purpose-built, conventional, well-documented — the choice `team.md`'s "conventional Google choices" rule points at. **But it re-runs the KSP bet this project already lost.** See below |
| **SQLite directly** (`SQLiteOpenHelper`, in the platform) | No dependency at all | Hand-written SQL and a hand-written mapper for one table. More code than Room, and the code is the error-prone kind |
| **A serialized file** via `kotlinx-serialization`, already in the stack | No dependency at all | One small list, rewritten whole on each change. Already used for every DTO. Loses partial-write durability unless written atomically |
| **DataStore** (`androidx.datastore`) | A new dependency, no annotation processor | Built for preferences. Proto needs protobuf tooling; Preferences cannot hold a structured list without encoding it — which lands back on the file option, plus a dependency |

**On the Room row.** The codekb records that **Retrofit was rejected because
"KSP could not parse eight untouched files on this Kotlin/AGP pairing"**, which
is why Ktor is in the stack at all. Room on the same pairing is that same bet
taken a second time — and if it fails, it fails inside the unit whose entire
purpose is the queue.

### Recommendation

**A serialized file written atomically, using `kotlinx-serialization`, which is
already in the stack** — with Room named as the migration path if the queue
ever outgrows it.

Three properties decide it, and the first is the one that matters most:

1. **It adds no annotation processor.** KSP has already failed once on this
   exact Kotlin/AGP pairing, and that failure is why the project runs Ktor
   rather than Retrofit. Reaching for Room means re-running the experiment that
   already cost the project a networking-library decision — and if it fails, it
   fails inside the unit whose whole purpose is the queue.
2. **The data is tiny and is always read and written whole.** A sync worker
   takes the queue, works through it, and rewrites it. There is no query, no
   join, no index and no partial read. A relational store's entire value
   proposition is unused here, so its cost is unopposed.
3. **It adds nothing to the 15 MB AAB ceiling** [NFR2].

**NFR5.10** — The queue's persistence must be **atomic per write**: the file is
written to a temporary path and renamed over the live one, so a process killed
mid-write leaves the previous complete queue rather than a truncated file.
**Verifier: a test that kills the write part-way and asserts the previous
queue is readable.** This is the one property the serialized-file option does
not get for free, and it is why the option is "written atomically" rather than
simply "a file". Without it the option is strictly worse than Room.

**NFR5.11** — The queue file holds **no device or advertising identifier** and
is checked against the forbidden-identifier set [NFR11, project ALWAYS-rule].
It holds enrollment ids, booleans, a version number and two UUIDs. **Verifier:
the existing DEX scan and manifest allowlist, which are unaffected, plus review
of the serialized shape.**

**NFR5.12** — The queue is **not** encrypted at rest on the device, and this is
stated as a decision rather than left silent. It holds a roster of enrollment
ids and presence booleans for one batch — no name, no phone number, no profile
field, no token. `EncryptedSharedPreferences` is used for the refresh token
because that is a 30-day credential readable via adb on a rooted phone
[codekb]; a queued roster is neither a credential nor readable as identifying
data without the server's enrollment mapping. **Verifier: none — this is a
recorded acceptance.** **Flagged for the human**: if the preference is to
encrypt it anyway, `security-crypto` is already a dependency and the cost is
small.

**This is a recommendation, not a fait accompli.** It is the first device
persistence in the product and the human may reasonably prefer Room for being
the conventional answer, accepting the KSP risk. **The requirements in
`reliability-requirements.md` § 2 hold either way** — NFR5.2 through NFR5.9 are
stated against the queue's behaviour, not against its storage.

---

## 3. The session-generation job

**NFR1.6** — Session generation is a **second management command** on the
mechanism D3 built, not a new scheduling technology: an entry point taking no
required arguments, safe to run at any time, writing a `JobHeartbeat` row under
its own job name on completion [`app/fees/commands.py`, `app/db/models.py:977`].
**Verifier: the command's signature and the heartbeat test.**

**NFR1.7** — Its cron entry is installed by **`user_data.sh.tftpl`** — that is,
by Terraform — and never by hand over SSM. **Verifier: the entry's presence in
the Terraform template, reviewed in the infrastructure diff.**

This constraint is not optional and D3 established why: the ASG refreshes on
every deploy, so the instance is replaced and `user_data` re-runs. **A
hand-added cron entry is wiped by the next routine deploy**, and because
generation self-heals, nothing looks wrong — until a teacher opens the app and
there is no class to mark against. That is the alert's failure mode reached by
the route a reasonable operator would take by default.

**NFR1.8** — The two jobs' freshness is tracked **independently**, under
separate job names [`observability-requirements.md` NFR25.23]. **Verifier: two
distinct heartbeat rows after both have run.** A shared name would let a
healthy fee run mask a session job that has never fired.

---

## 4. Backend: no new library, and two notes

**NFR17.4** — D4 adds no backend dependency. The conditional update of BR3.3 is
ordinary SQLAlchemy; the partial unique index of BR4.5 is ordinary Alembic; the
concurrency tests use the testcontainers and threading pattern already proven
at `tests/auth/test_ceilings.py:283`. **Verifier: the absence of a new entry in
`pyproject.toml`.**

**NFR17.5** — D4's six new lens-scoped readers [BR5.2] land under the
**configured strict island** on `app.authz.*`, which carries `strict = true`
and `disallow_any_explicit = true`. **Verifier: `mypy app`, already in
`make check`.**

A correction worth recording, because I nearly wrote the opposite. `team.md`
reports `app.authz` as a *declared* strict island that `pyproject.toml` never
configured, with the fix assigned to "before D1". **That is stale**: the
override is at `pyproject.toml:222-225`, and D1 additionally added a fourth
island on `app.accounts.*` with its reasoning recorded in the file. There is
nothing outstanding here. I state this only because the practice file still
says there is, and because the project's own recorded rule is that a claim
about how a change fits built code is checked against the code — which is what
turned this entry from a finding into a non-finding.

---

## 5. Test tooling — and a correction to `team.md`

**NFR17.6** — D4's tests use what exists: pytest with testcontainers against
**real PostgreSQL 16** for every concurrency and privacy test, JUnit plus
Turbine for ViewModel state machines, and Robolectric for Compose. **Verifier:
`make check`, the same entry point locally and in CI.**

Real PostgreSQL is not a preference here but a requirement of what is under
test: the partial unique index, `ON CONFLICT DO NOTHING`, the conditional
update's affected-row count and row-level security are the behaviours being
asserted, and SQLite emulates none of them faithfully.

**NFR17.7** — The Kotlin coverage ratchet applies to D4's Kotlin and the floor
moves only upward by deliberate commit [`android/coverage.gradle.kts`,
`android/coverage-floor.txt` = **52.54**]. **Verifier: the ratchet task in
`make check`.**

### The correction

**`team.md`'s Android toolchain table is stale.** It records ktlint, spotless,
detekt, `lint.xml` and the Kotlin coverage report as **absent**, assigned to
"before D1". Verified by direct read at commit `c0f8b9c`, that work **landed**:

| Tool | `team.md` says | Built state, verified |
|---|---|---|
| spotless | absent | **present** — `android/build.gradle.kts:6` |
| detekt | absent | **present** — plugin at line 7, config in `android/detekt.yml` |
| Kotlin coverage + ratchet | absent | **present** — `android/coverage.gradle.kts`, floor 52.54 |
| ktlint | absent | **present as a version and deliberately NOT run over `src/**/*.kt`** |

The ktlint row is the one worth reading rather than skimming, because it is a
**decision recorded in the build file**, not a gap: ktlint reads `[...]` inside
KDoc as a reference link, so the project's 52 traceability tags across 21 of 32
Kotlin files fail its parser. The code compiles; the formatter cannot read it.
Rather than change a convention that ties the code to its requirements on both
surfaces, ktlint runs over the Gradle and XML targets only, and detekt plus
Android Lint plus the DEX scan cover Kotlin.

**For the human: `team.md`'s Code Style section should be reconciled with the
built state at a learnings gate.** D4 does not edit memory. The practical
consequence for this unit is nil — the toolchain D4 needs is present — but a
stale practice file is what the 2026-10-22 reconciliation was itself about.

**NFR17.8** — D4 ships **seven** new screens [BR7.5], each needing a row in
`docs/delivery/bangla-layout-check.md`. There is still **no screenshot
harness** — Paparazzi and Roborazzi are absent, which I verified alongside the
rest of the toolchain — so the Bangla layout verifier for this unit is the
**written per-screen check and nothing automated**. **Verifier: a file check
that the row exists; the layout itself has no automated verifier, and that
sentence is the honest half of the obligation.**

---

## 6. What D4 adds no technology for

- **No metrics backend.** None exists; see `observability-requirements.md`'s
  closing note. The counters are stated as facts to be countable.
- **No new alerting infrastructure.** `log.critical` is the channel.
- **No caching layer.** The client caches for offline reads [NFR4]; the server
  adds none, and request-scoped memoization remains the only permitted form.
- **No background-work framework on the device** (WorkManager). The sync
  trigger is reconnect, and adding a scheduler would be a dependency for one
  trigger. **Flagged as the most likely thing a reader would add**: if
  background sync while the app is closed is wanted, that is a WorkManager
  decision and a scope change, not an implementation detail. Nothing in NFR5 or
  NFR5.1 requires it — they require sync on reconnect.
- **No new infrastructure, and no change to the USD 50/month position** [OC-4].

---

## Assumptions & Open Questions

- **The queue storage decision in § 2 is a recommendation for the human**, as
  D3's scheduler decision was. It is the first device persistence in the
  product and it is reversible — the behavioural requirements hold under any of
  the four options.
- **I searched for an existing device persistence mechanism** across
  `android/src/main/kotlin/`, `gradle/libs.versions.toml` and
  `android/build.gradle.kts`, for Room, SQLite, DataStore, `openFileOutput` and
  `filesDir`, and found **only** `TokenStore.kt`'s `EncryptedSharedPreferences`.
  That absence is what makes this a decision rather than a reuse.
- **The KSP failure is recorded in the codekb rather than re-tested here.** The
  technology-stack file states it as the reason Retrofit was rejected. I did
  not re-run it against Room, so § 2's first property is a recorded risk rather
  than a measured one — and that is exactly why the recommendation avoids the
  bet rather than resolving it.
- **`team.md`'s PU-3.6 Testing Posture bullet is also stale**, independently of
  the toolchain table: it names a Macrobenchmark "assigned to D5" for an
  obligation dropped at Q14.3. Covered in `performance-requirements.md` § 6.
