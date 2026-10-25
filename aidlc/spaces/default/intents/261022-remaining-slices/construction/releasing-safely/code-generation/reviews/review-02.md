## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T11:10:07Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | `app/governance/dispositions.py` entries for `rate_limit_counter` (and `job_heartbeat`), rendered into `docs/legal/PRIVACY.md` under "Deleted outright when you delete your account" | `rate_limit_counter` and `job_heartbeat` are declared `Disposition.HARD_DELETE` in the manifest — whose own docstring defines the enum as "what deletion does to a table's rows" — but `app/governance/deletion.py`'s `HARD_DELETE_SCOPES` scopes both as `Scope.NOT_PERSONAL`, and the code comment there states explicitly that `rate_limit_counter` is deliberately never touched by a deletion so the abuse ceilings it protects cannot be reset by the deletion route; `test_the_counters_are_not_cleared_by_a_deletion` proves this directly. The manifest's own disposition field is therefore false for these two tables, and that falsehood is not cosmetic: `scripts/generate_privacy_policy.py` reads `Disposition.HARD_DELETE` to choose the published heading, so the generated, regulator-facing `docs/legal/PRIVACY.md` currently states under "Deleted outright when you delete your account" that "Counters that limit sign-in attempts" (rate_limit_counter) are removed when the user deletes their account — the opposite of what the code does and of what the dedicated judgement-call note in `code-summary.md` §4 says is intentional. Nothing in the test suite catches this: `test_every_hard_delete_table_has_a_scoping_decision` and its sibling only assert that a `HARD_DELETE` table has *some* entry in `HARD_DELETE_SCOPES` and that every entry's table is still `HARD_DELETE` — neither asserts that a `NOT_PERSONAL`-scoped table cannot simultaneously be labelled `HARD_DELETE`, which is the exact combination that produces this contradiction. This is precisely the class of document-vs-code drift NFR14.101/BR2.3 were built to close, on a point D6's own digest mechanism does not reach because the manifest is internally self-contradictory rather than merely stale. | Either add a disposition value that means "not personal, outside account scope" (distinct from `HARD_DELETE`) and use it for `rate_limit_counter` and `job_heartbeat`, or add a test asserting that every `Scope.NOT_PERSONAL` table's disposition is never `HARD_DELETE`/`ANONYMIZE_IN_PLACE`/`RETAIN_WITH_BASIS` in a way that implies account-deletion reachability — whichever is chosen, regenerate `docs/legal/PRIVACY.md` and move these two rows out of "Deleted outright when you delete your account" into language that accurately states they persist independent of account deletion and expire only on their own window. | Resolved (reviewer) |
| R-02 | Major | `app/governance/deletion.py` `delete_account`, around the "account not found" branch (lines ~300-316) | The function's docstring and `code-summary.md` both describe "one transaction, committed once at the end," and the teacher-with-batches refusal is correctly checked before any destructive statement runs — that part is sound. But the "account not found" path (`account_id is None`) issues the phone-scoped deletes and then calls `session.commit()` at line 315, a **second, earlier** commit point distinct from the final one at line 342. This is not the refusal-safety hazard the dispatch brief asked to check (that one is fine — the refusal raises before any DELETE executes), but it does mean the function has two commit points rather than one, which the docstring's "everything happens in ONE transaction" does not disclose. In practice this is benign only because the unknown-number path deletes nothing account-scoped (there is no account to touch), so there is no partial-destruction hazard today — but the next person reading "one transaction, committed once at the end" and adding a step to the unknown-number branch would be working from a false premise. | Either make the docstring's "one transaction" claim scope-accurate (e.g., "the known-account path is one transaction; the unknown-number path commits its phone-scoped deletes and returns early"), or restructure so there is genuinely one commit point regardless of branch. | Resolved (reviewer) |
| R-03 | Major | `app/governance/dispositions.py` `DISPOSITIONS["rate_limit_counter"].basis` and `DISPOSITIONS["job_heartbeat"].basis` | Both basis strings are about the table's nature ("the longest window is a day", "names no person... falls outside the privacy boundary entirely") and say nothing about disposition at all — they read equally well under any disposition value. Given the Critical finding above, these basis strings were never actually scrutinized against the chosen `HARD_DELETE` value the way `account`'s basis was (per `code-summary.md` §2.6 and the dedicated regression test): nothing forced a human or a test to ask "does this basis describe what HARD_DELETE claims happens?" for these two rows, because the generator's digest only proves the basis hasn't silently drifted from whatever it was written against — not that it was ever checked against the disposition value next to it. | When the disposition value for these two tables is corrected (see the Critical finding), rewrite the basis to state plainly that the table is outside the account-deletion path entirely, matching the code's actual behavior rather than only its storage lifetime. | Resolved (reviewer) |
| R-04 | Minor | `scripts/generate_privacy_policy.py` `render()`, the `NOT_PERSONAL` section's explanatory paragraph | The sentence "where it says there is no time limit, the record is a single running total that is overwritten rather than accumulated" is literally false for `job_heartbeat`: `JobHeartbeat.job_name` is the primary key and `stamp_heartbeat` upserts per job name via `on_conflict_do_update(index_elements=[JobHeartbeat.job_name])`, so the table holds one row *per scheduled job* (today: fee generation, session generation, and this unit's new retention-purge job — three, not one), each overwritten in place on its own schedule. The surrounding claim that matters to a regulator — "it never grows with the people using the service" — is true regardless of row count, since the table grows with the number of scheduled jobs, not with users, so this does not misstate anything privacy-relevant. But it is the same category of defect this unit has now caught twice in its own generated prose: an unverified factual detail in a sentence a regulator reads, this time about the generator's own description of its output rather than about the manifest. | Reword to something like "the record is one line per scheduled job, overwritten on each run rather than appended to, so it never grows with the people using the service" — accurate to the actual mechanism and keeps the claim that matters intact. | New |

> R-01 Reviewer note: Confirmed fixed. `Disposition.NOT_PERSONAL` was added with a docstring that states the previous `rate_limit_counter`/`job_heartbeat` contradiction explicitly as the reason the value exists. Both tables are now declared `NOT_PERSONAL` with bases rewritten to lead with what the disposition does (not what the table is) [addresses the third finding too]. `docs/legal/PRIVACY.md`'s generated region now places both rows under a dedicated "Not about you, and not changed when you delete your account" heading, out of "Deleted outright when you delete your account". `python3 -m scripts.generate_privacy_policy --check` passes against the committed file (verified directly). The missing cross-check now exists as `test_not_personal_scoping_and_not_personal_disposition_agree`, asserted in both directions, and I independently reproduced the mutation the fix agent reported: reverting `rate_limit_counter` to `Disposition.HARD_DELETE` in-process makes `scoped_not_personal - declared_not_personal == {"rate_limit_counter"}`, which the test would catch. `tests/governance/` runs 63 passed, matching the reported count.

> R-02 Reviewer note: Confirmed fixed. `delete_account`'s docstring now reads "there are two commit points, not one" and explains precisely why the early-return branch's commit is safe (only phone-scoped deletes precede it) and explicitly warns a future reader not to generalize from it. The module docstring also states this up front. Accurate to the code as read.

> R-03 Reviewer note: Confirmed fixed, subsumed by R-01's fix. Both `basis` strings now lead with "A deletion request does nothing to these rows" / "because they are not about a person" before describing the table's nature — exactly the ordering the finding asked for, and `dispositions.py`'s own comment on the `rate_limit_counter` entry explicitly names why the old basis (table-nature-only) could sit unchallenged above a wrong disposition while the new one cannot.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `python3 -m pytest tests/governance/ -q` (re-run independently) | 63 passed | Matches the fix agent's reported count exactly; no regression introduced by the fix. |
| `python3 -m scripts.generate_privacy_policy --check` (re-run independently) | `docs/legal/PRIVACY.md is current.`, exit 0 | The committed policy matches the generator's current output; the two rows are confirmed out of the "Deleted outright" table and under the new heading by direct inspection of the rendered markers region. |
| In-process mutation of `DISPOSITIONS["rate_limit_counter"]` back to `Disposition.HARD_DELETE` (independent reproduction, not the fix agent's own report) | `scoped_not_personal - declared_not_personal == {"rate_limit_counter"}` | Confirms the new cross-check test would fail exactly as claimed; the gate is live, not merely present. |
| Adversarial construction of three escape shapes for the manifest cross-check (table `HARD_DELETE` + scope `NOT_PERSONAL`; table scope `NOT_PERSONAL` + disposition something else; table disposition `NOT_PERSONAL` + absent from `HARD_DELETE_SCOPES`) | All three are vacuous under the two original membership tests alone, and all three are caught by `test_not_personal_scoping_and_not_personal_disposition_agree`'s bidirectional set-difference | The loop closure claim holds: the `Scope.NOT_PERSONAL` subtraction in `test_no_scoping_decision_names_a_table_that_is_not_hard_delete` is not an open escape hatch, because the new cross-check independently constrains every table admitted through it. Deleting the entries instead (the rejected alternative) would indeed have discarded the abuse-ceiling-reset reasoning the dispatch brief was right to want kept. |
| Direct enumeration of all 25 manifest entries against `HARD_DELETE_SCOPES` | `scoped_not_personal == declared_not_personal == {job_heartbeat, rate_limit_counter}`; no undeclared and no phantom tables in either direction | Confirms the "no third table carries the same contradiction" claim across the full manifest, not merely by walking the diff. |

### Summary

The Critical finding from iteration 1 is genuinely closed: the chosen remedy (a fourth `Disposition` value plus a bidirectional cross-check test) is the structurally correct fix rather than a wording patch, it closes the escape path I tried to construct against it in three different shapes, and the generated privacy policy now states the true thing about both tables under a heading built to block both wrong readings a regulator could take from it. Both Major findings are fixed as described, with the transaction docstring now accurately scoped. One new Minor surfaced on independent adversarial reading of the new generator prose — a non-privacy-relevant but still false factual detail about `job_heartbeat` being "a single" row rather than one per job — which does not block this verdict but is worth a one-line fix given this unit's own stated lesson about unverified generated prose.

---

## Resolution - 2026-10-25

**READY. All three iteration-1 findings Fixed and re-verified independently
by both the reviewer and the orchestrator; the one new Minor is fixed.**

| Finding | Closed by |
|---|---|
| **R-01 (Critical)** - the manifest declared `rate_limit_counter` and `job_heartbeat` `HARD_DELETE` while the code deliberately never deletes them, so the generated policy told users their sign-in counters were deleted with their account | A fourth `Disposition` value, `NOT_PERSONAL` [human, 2026-10-25]. The enum had no value meaning "deletion does nothing to these rows because they are not about a person", which is **why the manifest was forced into a false label**. Both entries re-declared, both `basis` strings rewritten, the rows moved out of the deletion tables into their own section, and - the real remedy - a bidirectional cross-check pinning `Scope.NOT_PERSONAL` to `Disposition.NOT_PERSONAL` |
| **R-02 (Major)** - `delete_account`'s docstring claimed one transaction against two commit points | Docstring corrected to "two commit points, not one", naming the early-return branch and why it is safe, with an explicit warning against generalising from it. The code was not restructured: the prose was what was wrong |
| **R-03 (Major)** - the two `basis` strings described table *nature*, so nothing forced a basis-vs-disposition check | Subsumed by R-01: both now lead with what the disposition does before giving the table's nature as its argument |
| **R-04 (Minor, new)** - "a single running total" is untrue of `job_heartbeat` | Reworded to **"one line per scheduled job, overwritten on each run rather than appended to"**. Regenerated; the drift gate accepts it (181 governance + contract tests green) |

**Why R-01 escaped every existing gate, which is the part worth keeping.**
The completeness tests compare **membership only** - every `HARD_DELETE`
table has *an* entry, no entry names a non-`HARD_DELETE` table - so both
passed over a table whose disposition its own scoping contradicted. And the
sha256 digest could not help either: **a digest proves the document matches
the manifest, and here the manifest itself was wrong.** Two sources of truth,
never compared.

**`Scope.NOT_PERSONAL` already existed, with a correct docstring.** The truth
was written down in one of the two files the whole time; the defect was
purely that the other disagreed and nothing checked. That is `team.md`'s
**"where a rule is important, it is mechanical"** not applied to the one pair
of manifests that most needed it - the reasoning was never missing, only
unenforced.

**The one judgement call, and it was challenged rather than accepted.**
Moving the tables out of `HARD_DELETE` broke
`test_no_scoping_decision_names_a_table_that_is_not_hard_delete`, which was
widened by subtracting **only** `Scope.NOT_PERSONAL` entries. The reviewer
constructed **three distinct escape shapes** against that loop
(`HARD_DELETE` + `NOT_PERSONAL` scope; `NOT_PERSONAL` scope + other
disposition; `NOT_PERSONAL` disposition + absent from scopes) and confirmed
all three are vacuous under the old membership tests and **all three are
caught** by the new cross-check. Closed, not patched for the one case found.

### Verified independently by the orchestrator, not taken on report

- The two rows are out of the "Deleted outright" table, under a heading that
  denies deletion **and** denies personhood in one line.
- Both assertion directions present.
- **1425 passed, 0 skipped, 0 failed** (baseline 1424; +1 for the new test),
  counted from raw progress output rather than a summary line.
- **Mutation-proved**: flipping `rate_limit_counter` back to `HARD_DELETE`
  fails with *"these tables are scoped NOT_PERSONAL but carry another
  disposition: ['rate_limit_counter']"* - the mutation reproduces the
  original defect exactly and the new test names it. Restored clean.
- `job_heartbeat` is keyed on `job_name` and upserted with
  `on_conflict_do_update`, so it is one row per job - **three** today, since
  D6's purge added its own.

### The lesson this unit learned twice

**Both false statements in the generated policy were caught only by a
deliberate re-read as a regulator, never by a test.** The first said
`LIFE_OF_ACCOUNT` rows are deleted with the account when they survive it; the
second said the heartbeat is "a single running total" when it is one row per
job. In each case the surrounding claim was true, which is exactly why the
false half survived a careful read. **A generated document is not true
because it is generated** - and the generator's prose *about itself* is the
part no gate covers.
