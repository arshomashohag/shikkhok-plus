# Tech Stack Decisions — D5 `knowing-how-it-is-going`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 adds one tool and no libraries.** The one is `bundletool`, in CI only,
> because NFR2's download-size ceiling names a figure that cannot otherwise
> be computed. Everything else this unit needs is built: the fold, the
> `Money` type, the lens, the two privacy gates, the test harness.
>
> That makes this document short, and the short version is the finding:
> **an analytics unit is where a charting library, a reporting framework or
> a caching layer would normally arrive, and none of them does.** § 3 says
> why each was considered and declined, because an absent section reads to
> the next person as a question nobody asked.

> **`NFRx.y` IDs are GLOBAL.** D5's new IDs start above each base's
> high-water mark after D4. A bare `NFR17.5` or `NFR2.9` below is a
> **citation**, never an ID defined here.

## Sources

- [upstream] `.../functional-design/rules.md` — BR4.2, BR4.3
- [upstream] `.../functional-design/functional-spec.md` §§ 6, 7, 7a
- [upstream] this stage's `performance-requirements.md` § 3 — NFR2.12's
  `bundletool` decision and its reasoning
- [prior] `261016-.../inception/requirements-analysis/requirements.md` — NFR2
- [team] `team.md` Code Style — *"conventional, well-documented Google
  choices by default, with project constraints outranking the sample"*; the
  SDK admission note per new third-party dependency
- [code] read 2026-10-25: `pyproject.toml` (the five strict mypy islands),
  `android/build.gradle.kts`, `android/gradle/libs.versions.toml`,
  `.github/workflows/release-android.yml`

---

## 1. The one addition

**NFR2.15** — **`bundletool` is added as a CI-only dependency**, installed in
the release workflow and never shipped in the app. It computes the per-ABI
download size NFR2's ceiling is measured against [performance § 3].

**The SDK admission note `team.md` requires**, written here because the rule
says every new third-party dependency gets one:

| Question | Answer |
|---|---|
| What is it | Google's official command-line tool for Android App Bundles |
| Where does it run | The GitHub Actions release job only |
| Does it ship | **No.** It never enters the APK, the AAB or any build output |
| Forbidden identifiers | **Not applicable** — it is a build-time analyser, not a library linked into the app, so the DEX scan and manifest allowlist are unaffected |
| Conventional? | It is the tool Google documents for exactly this measurement |

**NFR2.16** — Because `bundletool` never ships, the forbidden-identifier set
[TC-3, TC-6, D-37] is **unaffected** and the two built release gates — the
merged-manifest permission allowlist and the minified-release DEX scan —
require no change. **Verifier: those two gates, which already run on the
release build and would fail on a new app-side dependency.** Stated because
"a new dependency" is the trigger for the admission rule, and a reader
checking the rule should see the answer rather than infer it.

---

## 2. What is reused, unchanged

| Need | Built thing | Added |
|---|---|---|
| Money arithmetic | `app/money/` — `derive()`, `Money` | **nothing** [BR4.3] |
| Authorization | `TeacherLens`, the route-enumeration gate | nothing |
| Privacy enforcement | `app/contract/privacy.py` | nothing |
| Query shape | D3's `IN (:seat_ids)` + in-memory fold | nothing |
| Error taxonomy | the closed five-class hierarchy | nothing |
| Test harness | pytest, testcontainers, real PostgreSQL 16 | nothing |
| Android | the existing feature/layer convention | nothing |

**NFR17.9** — D5's new backend modules land under the **existing strict mypy
islands** where they touch authorization, and under the global
`disallow_untyped_defs` otherwise. `pyproject.toml` now configures **five**
strict islands, and D5 adds none — it adds no package that decides an
authorization question, because the lens resolution it uses is `app.authz`'s
already. **Verifier: `mypy app` clean, which is already a `make check` gate.**

---

## 3. What was considered and declined

Each of these is the obvious addition for an analytics unit, which is why
declining them is worth recording rather than leaving silent.

**NFR2.17 — No charting library.** The trend is a monthly series of at most a
dozen points. A chart library is a new Android dependency, a new
forbidden-identifier review, and an APK-size cost measured against a 15 MB
ceiling this very unit is asserting. **The trend renders with the existing
Compose primitives or as a list.** The decision is revisited if a requirement
asks for an interaction a drawn chart provides — zoom, selection, a second
series — and none does. **Verifier: the release-gate size assertion of
NFR2.11, which makes the cost of reversing this visible.**

**NFR2.18 — No caching layer, no materialised rollup.** AC7.1.4 requires
current data on open with no generate step [BR1.4], so a cache would
contradict the requirement rather than optimise it, and a stale figure about
money is worse than a slow one. **Verifier: BR1.4's test — record a receipt
that clears a balance, re-read in the same test, assert the row is gone with
no intervening job.**

**NFR2.19 — No reporting or BI framework.** Two screens with four figures
between them. A framework would be more code than the thing it generates, and
every figure would then be computed somewhere the money module's import
boundary does not reach. **Verifier: the built import-boundary checks, which
would fail on arithmetic outside `app/money/`.**

**NFR2.20 — No background computation of any kind.** No scheduled rollup, no
precomputed table, no job. This follows from BR4.2 and BR1.4 together, and it
is why `observability-requirements.md` has no freshness alert to define.
**Verifier: a file check that D5 adds no cron entry and no
`stamp_heartbeat` call.**

---

## 4. The Android surface

**NFR18.9** — D5's two screens follow the existing
`feature/<name>/{StateMapper,UiState,ViewModel,ui/}` convention with no new
pattern, no new module and no new dependency. **Verifier: review against the
built `feature/roster/` shape, plus the existing detekt and spotless gates.**

**NFR18.10** — Every user-facing string in both bundles, Bangla and English,
and a row per screen in `docs/delivery/bangla-layout-check.md` [BR4.5].
**Verifier: the built `MessageKeyCoverageTest` for any new message key, and
the file check for the rows.** The earnings figure is the string to check
hardest: a money amount in Bangla numerals under a long Bangla label is the
densest short string this unit renders, on the screen a teacher opens most.

---

## Assumptions & Open Questions

- **`bundletool` is pinned by this unit, not deferred to the lockfile
  practice** — corrected 2026-10-25 after review. An earlier draft deferred
  it, which was wrong in a specific way: that practice is assigned "before
  D1" and **has not landed**, so deferring to it leaves an **unpinned tool
  computing the number a release gate blocks on**. A version bump could then
  move the figure, pass or fail the gate for a reason unrelated to the app,
  and nothing would record which version produced the verdict.
  **NFR2.21**: the release workflow installs `bundletool` at a pinned version
  with its checksum verified, in the same step that runs it, and the gate's
  output names the version. **Verifier: the pin is visible in the workflow
  diff; the version in the gate's output is what makes a later disagreement
  traceable.**
- **NFR2.17's decline is the one most likely to be reversed**, because a
  trend is the thing a chart library exists for. The requirement names the
  trigger — a requirement asking for zoom, selection or a second series — so
  the reversal is a decision rather than a drift.
- **NFR17.9 claims five strict islands**, counted from `pyproject.toml` on
  2026-10-25. `team.md` still says three; it is stale and already flagged for
  the human at the learnings gate.
- **No figure in this document was measured.** D5's code does not exist yet.
