# Stage diary — nfr-requirements (3.2), D4 `teaching-and-recording`

## What I verified rather than took

- **The ID high-water table.** Recomputed across BOTH records plus the whole
  `aidlc/` and `docs/` trees with a sort over `NFR<base>.<n>`. Every base in
  the brief's table matched the computed maximum. NFR15 has no derived IDs
  anywhere, so it has no mark. The brief's table is correct and was used.
- **`RETENTION` is derived, not a second manifest.** `dispositions.py:279-281`
  is a dict comprehension over `DISPOSITIONS`. The obligation is ONE
  `TableGovernance` entry per table carrying `disposition`, `retention` and
  `basis`. Nineteen entries today. The coordinator's correction was right, and
  the module docstring's "two manifests" prose is what misleads.
- **The Android quality toolchain EXISTS now.** `team.md` says spotless,
  detekt, ktlint and the coverage ratchet are all absent. They are in
  `android/build.gradle.kts` (plugins, lines 6-7), `android/coverage.gradle.kts`
  and `gradle/libs.versions.toml`, with a live floor of 52.54 in
  `android/coverage-floor.txt`. `team.md` is stale on this; the before-D1 work
  landed. I state the built reality and flag the staleness.
- **No device persistence of any kind exists in the Android module.** Searched
  for Room, SQLite, DataStore and file IO: the only storage is `TokenStore.kt`
  using `EncryptedSharedPreferences`. The queue's storage is therefore a real
  new decision, not a reuse. It is the one genuine tech-stack choice in D4.
- **D3's scheduler recommendation and its deploy constraint.** A host-level
  cron entry installed by `user_data.sh.tftpl`, never by hand, because the ASG
  refreshes on every deploy. D4's session generation inherits all of it.
- **§ B.7 and § B.8 read in full**, not summarised. Four named writes carry
  `client_mutation_id`; two are D4's. An unmoved `created_at` is the assertable
  part of a replay. A replay of another account's id is an `AuthorizationError`.

## Decisions

- **No latency requirement for the attendance path.** BR7.4 and Q14.3 answer C.
  `performance-requirements.md` states the absence as its own section rather
  than silently omitting it, because an omission reads as an oversight and the
  next developer fills it.
- **Performance is the thin document and says so.** D4's real risks are
  concurrency and privacy, not speed. I state what it sets no target for rather
  than padding it with invented budgets.
- **Three concurrency mechanisms are kept distinct** — the replay guard, the
  version guard, and the insert-conflict generation uses. Blurring them is how
  the wrong one gets reached for.

## One claim I nearly shipped wrong

I drafted NFR17.5 asserting that `app.authz.*` is still an unconfigured strict
island, taking `team.md` at its word. **It is configured**, at
`pyproject.toml:222-225`, and D1 added a fourth island on `app.accounts.*`
besides. The project's own recorded correction — read the code before asserting
how a change fits it — is what caught this, and the entry now records the
non-finding plus the staleness in `team.md`. Same class of error as the three
the record has already logged.

## Verification at the end

- 114 IDs minted across 14 bases, checked mechanically against every prior use
  in both records: **zero collisions**, every base contiguous from its first
  free number.
- `traceability.json`: 114 `reverse` rows and 4 `coverage` rows, with the
  minted set and the reverse set **exactly equal** in both directions.
- Sensors: `required-sections`, `traceability` and `upstream-coverage` all pass
  with zero findings. `linter` and `type-check` inspect TS/JS snippets and
  these documents contain none. `claim-sources` is not among this stage's
  declared sensors and fails identically on D3's reviewed-and-approved files.
- All table cells under 200 characters; every consumed artifact cited where it
  bears.

## Open for the human

- `project.md`'s NEVER on local write queues contradicts its own cited source,
  NFR5. Flagged by the functional design; repeated here because my security and
  reliability documents both specify the queue.
- `team.md`'s Android toolchain table and its PU-3.6 Testing Posture bullet are
  both stale — the first against the built state, the second against Q14.3.
