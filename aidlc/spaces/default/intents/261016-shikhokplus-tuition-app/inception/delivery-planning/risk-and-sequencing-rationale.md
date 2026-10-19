# Risk and Sequencing Rationale

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive

> Why the Bolts sit in the order they do, what each early one buys, and where
> the schedule is most likely wrong.

## Sources

- [upstream] the Bolt plan and the Units Generation DAG
- [upstream] `inception/contract-design/contract-summary.md` open questions
- [human] the stated top risk: the privacy boundary

---

## B. Should a formal WSJF-style scoring model be used?

**No. Recommending against it, and recommending the rationale artifact say so explicitly rather than silently omitting it.**

The reasoning:

- **The DAG leaves almost no freedom to score.** Of eleven positions, seven are forced or near-forced: B1, B2, B3 are a strict chain; B5 is forced after B3; B7 is forced after B6; B10 is forced after B7 and B9; B11 is terminal. Genuine freedom exists in exactly two places — where U10 goes, and the internal order of {U5, U6, U7}. Producing eleven WSJF scores to decide two orderings is numbers dressing up a decision the geometry already made, which is precisely the failure mode the delivery knowledge base warns about.
- **WSJF's denominator does not discriminate here.** Job size across the three contested Units is L, L and M — a one-step spread on a four-step scale. WSJF rewards small-and-valuable; with sizes that flat, the ordering collapses onto the numerator, which is just risk-first by another name.
- **WSJF's value term is undefined for this project.** Every V1 capability is Must Have and the minimum viable scope equals full V1 scope [scope: Q1]. Cost of delay is therefore identical across all eleven Bolts: nothing ships until everything ships. A scoring model whose value axis is constant for every item is not a model.
- **The one real decision was settled by a hard constraint, not a trade-off.** U10's placement turned on the Macrobenchmark harness being a prerequisite of U5. No score would have surfaced that; reading the artifacts did.

**What I recommend instead, and what the artifact should carry:** the named heuristic (walking-skeleton-first, then risk-first) plus the two explicit justifications above for the only two free choices. That is auditable, falsifiable, and honest about where judgement was actually exercised. If the human wants a scored comparison for the {U5, U6, U7} ordering specifically, I can produce one — but I would be reverse-engineering weights to reach the answer the critical path already gives.

---

## E. Risk and sequencing rationale

### Top risks, ranked

1. **Privacy-boundary failure** (human's stated chief worry) — a student's or guardian's private write reaching a teacher, RLS not actually in force, or a cross-teacher leak through an account enrolled with several teachers. Likelihood: medium. Impact: **critical** — it is a children's-data breach under RC-1/RC-2/RC-3 in a product whose Play declaration is mixed-audience-including-children, and it is the vulnerability class a scanner cannot find because finding it requires knowing the intended policy.
2. **Money arithmetic defect** — likelihood medium (the identity was wrong twice already, per the recorded learnings), impact high. The fee model is *already known to be in revision* [D-18], so the arithmetic will be disturbed after it is written.
3. **Android surface quality** [OC-3] — the thinnest-reviewed part of the product, reviewed by someone learning the platform. Likelihood medium-high, impact medium. Mitigated mechanically rather than by more review.
4. **Play release blocked late** — 12-tester/14-day window, account type unresolved, four release-blocking V1 deliverables all living in the terminal Bolt. Likelihood medium, impact high (no release).
5. **SMS gateway unselected at skeleton time** — likelihood high (it is unselected today and B3 is the third Bolt), impact medium-high (blocks the skeleton's verification as written).
6. **Schedule** — every capability is Must Have, so nothing absorbs variance.

### What each early Bolt buys

- **B1** buys the money invariant under randomized test before any caller exists, which is the only point at which 100% branch coverage is reachable, and the only point at which the fee-model revision is cheap.
- **B2** buys both mechanical privacy gates — the route-enumeration test and the schema-wide no-profile-field assertion — *before the first route exists*. This is the highest-leverage position in the whole sequence: a privacy gate installed after routes exist is a gate shaped around what already passes.
- **B3** buys the computed lens, row-level security in force under a restricted non-superuser role, and the seven OTP abuse controls, all demonstrated end-to-end on real hardware against a real host. It also buys the governance manifest's *mechanism*, so the disposition obligation is enforced from the third Bolt rather than the eleventh.
- **B4** buys the forbidden-identifier enforcement before six Bolts' worth of dependencies arrive, the Macrobenchmark harness B8 needs, and the start of the Play clock.
- **B5** buys the first genuinely multi-party privacy test — two teachers, one shared account — and settles OQ-7.
- **B6** buys the fee arithmetic pinned by tests before the known revision lands, and the concurrency-tested idempotency constraint.

### Addressing the stated privacy worry directly

**What the sequence proves early:**

- **By end of B2** (second Bolt): that a route without a lens cannot merge, and that a teacher-lens response schema cannot carry a profile field — both enforced in CI, both demonstrated against deliberately introduced violations. These are schema-level and route-level invariants, so they cover endpoints that do not exist yet, including the ones added in B10 after everyone has stopped thinking about privacy. This is the single most important early privacy win and it is available at Bolt 2 precisely because U2 was carved out as its own Unit.
- **By end of B3** (the skeleton, human-checkpointed): that row-level security is genuinely in force — asserted by a meta-test that `current_user` is not a superuser and `row_security` is on, running *before* the privacy suite, so the suite cannot pass vacuously. That the owner-private `profile` is under RLS. That the lens is computed per request with no role field and no cache. That a cross-teacher request returns a **403 byte-identical** to the response for an id that does not exist, so the response is not an enumeration oracle. *(Status amended 2026-10-18 at B2 Functional Design per BR1.4/BR4.3: this said "404 and not 403". The property that matters is indistinguishability, not which status; the normative schema fixes 403, and a uniform status carrying distinct `code` values would still be an oracle.)*
- **By end of B5**: that two teachers sharing one student account cannot see each other's data, and that every teacher-facing read is keyed on `enrollment_id` rather than an account id — the keying rule ADR-001 makes the whole boundary rest on.
- **By end of B7**: the IDOR shapes that matter for money — teacher A requesting teacher B's batch, a guardian requesting a non-child's enrollment, a student requesting a fee cycle not their own.

**What remains unproven until late, stated plainly:**

- **Deletion actually removing what the policy says it removes** is unproven until **B11**, the final Bolt, running in autonomous mode. This is the gap I am most uncomfortable with, and it is why I recommend re-gating B11 as a human checkpoint (section A). `team.md` is explicit that deletion features are the ones most reliably shipped broken, because nobody tests the absence of data — and the sequence as the DAG permits it puts that test last.
- **The purge honouring retention clocks** is likewise B11-only, and its failure mode is silent: children's data simply persisting past its stated retention, which no user notices and no test outside B11 covers.
- **The schema-iterating completeness test** is only *fully* meaningful at B11, when the last table exists. The per-Bolt obligation makes it meaningful *incrementally* from B3, which is the mitigation, but incremental meaningfulness is not the same as the final assertion.
- **The AC9.4.2 back-stack case** — Back must never land in another lens's or another child's data — is a standing per-Unit obligation rather than a Bolt, which means it is verified per screen rather than globally. A screen-count-complete assertion does not exist in this plan. Flagging: if the human wants one, it belongs in B11's DoD and would be a scope addition.

### The three named open items

- **The fee model is already known to be in revision [D-18].** This is why B6 sits first among the parallel set and why `team.md`'s test-first predicate is at its strongest there. The suite that pins the arithmetic is what makes the revision a safe change rather than a frightening one. The residual exposure: if the revision lands *after* B7 has built on the current arithmetic, the blast radius includes payment verification and carry-forward, not just fee generation. B6-then-B7 adjacency is deliberate — it keeps the two money Bolts together so a revision touches a contiguous region of history.
- **FR8.3's collection-rate definition is open to correction**, and AC8.3.4's credit rule postdates it. B10 is position 10, the maximum deferral the DAG allows. My recommendation stands: if still open at B10, omit the field rather than ship provisional arithmetic, because `/v1/` is additive and a wrong number in an installed client cannot be withdrawn.
- **Two deletion-related open questions remain** — OQ-1 (`PaymentClaim.transaction_id` surviving the claimant's deletion) and OQ-5 (the external deletion route's web surface against Play's expectations). Both block B11, which is release-blocking. Neither is a workflow decision; both are human judgements. The useful observation is that **both are cheap to close now and expensive to close at B11**: OQ-1 changes a response schema that B7 ships (so closing it before B7 avoids a revisit), and OQ-5 is confirmable by reading Play's current requirements the moment Play Console access exists at B4.

### Deviation from topological order — declared

The chosen sequence respects every DAG edge. One deviation from the *obvious* topological reading is declared explicitly: **U10 is lifted from its natural late position to position 4**, which the DAG permits (U10 depends only on U3) and which the units artifact flagged as the useful hidden opportunity. Justification is in section A and rests primarily on the undeclared Macrobenchmark-harness dependency from U5 to U10.

---

## F. Schedule shape

### Is 11 Bolts at the stated complexities consistent with 8–12 weeks?

**Marginally, at the optimistic end, and only under assumptions worth naming.** My honest read is that 8 weeks is unlikely and 12 weeks is achievable-but-tight, with meaningful probability of overrun. I am giving a range with assumptions rather than a point estimate, per the brief's own reservation that 8–12 weeks is judgement and not measured velocity.

The complexity inventory: 1 × XL, 4 × L, 4 × M, 1 × S, plus U11 at L. Against a solo build with one human reviewer in the loop for seven of eleven Bolts.

**A sizing sketch, explicitly illustrative rather than estimated** — calibrating against nothing, because no velocity exists yet on this codebase:

| Band | Bolts | Illustrative span |
|---|---|---|
| S | B2 | ~2–4 days |
| M | B1, B4, B9, B10 | ~4–7 days each |
| L | B5, B6, B7, B8, B11 | ~1–2 weeks each |
| XL | B3 | ~2–3 weeks |

That totals roughly **10–17 weeks** of build, which straddles and mostly exceeds the 8–12 week range. I am not presenting that as an estimate — it is arithmetic over guesses, and the guesses are the whole content. What it does usefully say is that **the brief's range is on the optimistic side of a straightforward sum, not the pessimistic side**, and anyone planning against 8 weeks is planning against the best case of a range that was already described as judgement.

### Where the estimate is most likely wrong

Ranked by expected magnitude of error:

1. **B3 is the dominant uncertainty and the most likely underestimate.** It is XL, it is first, it is the walking skeleton, and `team.md` concedes it is "deliberately larger than a minimal connectivity proof." It carries seven adversarial abuse-control tests, datastore-backed counters, a two-tier ceiling with a defined degradation path, JWT `kid` with key rotation, a full refresh-token state machine with reuse detection, RLS with a restricted-role meta-test, the first Alembic migration against real Postgres, the entire skeleton-time toolchain, *and* an Android surface in a framework with no declared experience — plus the governance-manifest mechanism I added. It is also the Bolt with the least calibration behind it, because nothing has been built yet. If one Bolt doubles, it is this one.
2. **The Android learning curve is unpriced across every screen-bearing Bolt.** [OC-3] states no declared Kotlin or Android experience. Every one of B3, B5, B8, B9, B10 carries Compose work, and the first of them pays an onboarding cost that no complexity letter reflects. The M and L letters describe scope, not unfamiliarity.
3. **Review latency is not in the arithmetic at all.** Seven of eleven Bolts are human checkpoints, the reviewer is one person who also holds every other role, and `team.md` acknowledges review depth on the Android surface is shallow. Wall-clock elapsed time exceeds build time by however long each checkpoint waits, and that term is entirely unmodelled.
4. **The teacher analytics dashboard was explicitly excluded from the 8–12 week range** by the brief's own second reservation, on the grounds that it was a Must Have specifying nothing. Requirements Analysis has since defined it (FR8.1–FR8.3) and it now lives in **B10**. So the range excludes work that is now in the plan. That is a known, named gap in the original estimate's coverage, not a new risk.
5. **The three external dependencies with unknown lead times** — SMS vendor, Play account type and verification, and the OQ-1/OQ-5 decisions — are all currently open and none has a committed date. The Play 12-tester/14-day window is a hard 14 days that cannot overlap with itself, and it cannot start before B4 uploads. Placing B4 at position 4 is the mitigation; it does not remove the dependency.
6. **Nothing absorbs variance.** Every capability is Must Have and minimum viable scope equals full V1 scope, so there is no descope lever. A slip moves the date one-for-one. This was recorded as an accepted risk at Ideation and remains the structural reason the range cannot be defended as tight.

### Recommended framing

**Build: 10–16 weeks, with B3 the dominant variance term.** Plus Play's 14-day closed-testing window, which can run concurrently with later Bolts *only if* B4 lands on schedule at position 4 and the account type permits — and the account type is currently unknown.

Named assumptions behind that range:
- The SMS vendor is selected before B3 starts (otherwise B3's verification is deferred and the skeleton checkpoint is provisional).
- The Play account exists and is verified before B4 completes.
- Review turnaround on each of the seven gated checkpoints is days, not weeks.
- The fee-model revision [D-18] lands before or during B6, not after B7.
- No forbidden-identifier finding at B4 requires removing an already-integrated SDK.

**What would firm this up at essentially zero cost:** B1 and B2 together are small, low-risk, and almost entirely backend. Completing them yields the first real velocity data point on this codebase, this reviewer and this toolchain — and re-estimating B3 onward from that point will be worth more than any amount of further reasoning now. I recommend the schedule be re-stated after B2 rather than defended before B1.

---

## Flagged for the human — not decided by me

1. **Re-gating B11 as a human checkpoint**, notwithstanding the settled gated-through-U8 decision. B11 holds both deletion paths and four release-blocking Play deliverables, and deletion is the surface `team.md` says is most reliably shipped broken. This is an amendment to a settled decision and is yours.
2. **The SMS vendor and the skeleton checkpoint.** Without a vendor, B3 cannot satisfy the Construction Verification Command as `team.md` words it ("an SMS arrives through the real gateway"). Either start vendor selection now as a B1/B2-parallel activity, or accept a provisionally-verified skeleton with a recorded obligation to re-verify before B4's first upload. I recommend the former but will not choose it for you.
3. **The Play account type**, which determines whether the 12-tester/14-day requirement applies and whether the fallback is a materially longer organisation-account verification path. Worth resolving before Construction starts.
4. **The AC9.4.2 back-stack privacy case has no screen-count-complete verifier** in this plan — it is a per-Unit obligation, verified per screen. If you want a global assertion, it is a scope addition to B11.
5. **The 15 MB download-size ratchet can fail a feature Bolt** once B4 establishes it at position 4. That is the intended behaviour, but no budget is allocated for the remediation when it happens.
