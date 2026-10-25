# The Bangla layout check

**Decided 2026-10-22.** The obligation is affirmed —
*"ALWAYS externalize user-facing strings with Bangla and English present from
the start, and verify that longer Bangla text does not break the layout"*
[TC-15, D-43] — and until today it had **no verifier at all**. Both string
bundles are complete at 53 entries each, which the build checks; nothing
checked the layout.

`team.md` names two acceptable verifiers: Compose screenshot tests at the
longest Bangla string, or an explicit per-screen manual check. **The manual
check is the one chosen**, on 2026-10-22.

## What makes this honest rather than a wish

A manual check depends on someone doing it, which is the failure mode this
project's practices usually design against. Three things are done here to
narrow that gap, and it is worth being plain that they narrow it rather than
close it:

1. **The table below is the artifact.** A screen with no row is a visible
   gap in a committed file, not a thing someone forgot. A unit is not
   complete while a screen it ships has no row.
2. **The check names the exact string to test with**, so "I looked at it"
   becomes "I rendered the longest Bangla string in this screen's longest
   field". Those are different claims.
3. **A failing row stays in the table with its finding.** Rows are not
   deleted when they fail; they are marked and fixed, so the table records
   what broke as well as what passed.

What this does not do: catch a regression. A screen that passed in D1 and
breaks in D4 is found only if someone re-checks it. That is the real cost of
choosing the manual option, and it is accepted deliberately rather than
hidden. If it bites, the escalation is the screenshot-test option, which the
practice already permits without re-deciding anything.

## How to run the check

For each screen, on a device or emulator in Bangla locale:

1. Set the device language to **বাংলা (বাংলাদেশ)**.
2. Open the screen with **real data at its longest realistic values** — a
   full Bangla name, a full batch name, a four-digit fee with the `৳` prefix.
3. Look for the four failure shapes:
   - **Truncation** — text cut with an ellipsis where the English fits.
   - **Overflow** — text escaping its container or overlapping a neighbour.
   - **Wrapping** — a label that was one line in English becoming three and
     pushing the layout.
   - **Clipping of Bangla glyph marks** — conjuncts and the ি / ী / ু vowel
     signs extend above and below the Latin line box, and a container sized
     to Latin metrics clips them. This is the Bangla-specific one and the
     easiest to miss, because the text is readable at a glance and wrong on
     inspection.
4. Record the row.

## Longest-string reference

The longest entries in `values-bn/strings.xml` at the time of each check.
Re-derive rather than trusting this list once strings change:

```
python3 - <<'EOF'
import re, pathlib
p = pathlib.Path("android/src/main/res/values-bn/strings.xml")
rows = re.findall(r'<string name="([^"]+)">(.*?)</string>', p.read_text(), re.S)
for name, text in sorted(rows, key=lambda r: -len(r[1]))[:10]:
    print(f"{len(text):4d}  {name}")
EOF
```

## The table

**Status values**: `PASS`, `FAIL (<what broke>)`, `FIXED (<what was done>)`.
A screen may appear more than once — a later unit re-checking it adds a row
rather than editing the old one.

| Unit | Screen | Artboard | Checked on | Longest string used | Status |
|---|---|---|---|---|---|
| — | Auth: phone entry | `O2` | *not yet checked* | | |
| — | Auth: OTP entry | `O3` | *not yet checked* | | |
| — | Batch list | `T6` | *not yet checked* | | |
| — | Roster | `T7` | *not yet checked* | | |
| D1 | Signup | `O1` | *not yet checked* | `signup_already_added_notice` (88) | |
| D1 | Invitations | `O4` | *not yet checked* | `invitations_empty_body` (104) | |
| D1 | Decline sheet — student | `O4` | *not yet checked* | `decline_student_body` (106) | |
| D1 | Decline sheet — guardian | `O4` | *not yet checked* | `decline_guardian_body` (125) | |
| D1 | Profile (edit half) | `O5` | *not yet checked* | `profile_teacher_name_note` (105) | |
| D2 | Batch list (with the count) | `T6` | *not yet checked* | `roster_accepted_count` (33) | |
| D2 | Roster (per-link states, declined mark) | `T7` | *not yet checked* | `roster_declined_mark` (31) | |
| D2 | Add student | `T8` | *not yet checked* | `student_add_guardian_hint` (61) | |
| D2 | Create batch | — | *not yet checked* | `batch_create_created` (18) | |
| D2 | Remove seat (confirm + two refusals) | — | *not yet checked* | `roster_remove_claimed_remedy` (145) | |
| D2 | Guardian child home | `G1` | *not yet checked* | `guardian_empty_body` (96) | |
| D3 | Fee history (student and guardian) | `G3` | *not yet checked* | `fees_empty` (25) | |
| D3 | Batch fees (what each student owes) | `T5`, `S2` | *not yet checked* | `batch_fees_empty` (31) | |
| D3 | Payment form | `S3` | *not yet checked* | `payment_ask_teacher` (93) | |
| D3 | Claim outcomes (incl. the correction notice) | `T4`, `G3` | *not yet checked* | `fees_claim_corrected` (34) | |
| D4 | Session list (today's and past classes) | `T1` | *not yet checked* | `sessions_empty` (32) | |
| D4 | Session detail with the roster (attendance marking) | `T2` | *not yet checked* | `attendance_queued` (74) | |
| D4 | **Conflict resolution (two rosters side by side)** | `T2` | *not yet checked* | `attendance_version_conflict` (122) | |
| D4 | Exam list | `T3` | *not yet checked* | `exam_entered_count` (43) | |
| D4 | Mark entry | `T3` | *not yet checked* | `mark_entry_locked` (40) | |
| D4 | Marksheet (student and guardian) | `G4` | *not yet checked* | `marksheet_no_comparison` (45) | |
| D4 | Guardian progress over time | `G4` | *not yet checked* | `progress_title` (14) | |
| D5 | **Teacher overview (earnings, trend, next exam)** | `T6` | *not yet checked* | `dues_nobody_owes` (86) / `overview_earnings_label` (16) | |
| D5 | Cross-batch dues list | `T5` | *not yet checked* | `dues_nobody_owes` (86) | |

**D4's seven rows are open, and nothing automated discharges them.**
The obligation is a check on a device in Bangla locale [team: Testing
Posture], there is still no screenshot harness in this project, and
code generation cannot perform one. Stated plainly because a manual
verifier described without that sentence reads, to the next person, as
a verifier [project.md, learned 2026-10-23]. BR7.5 makes a screen with
no row an incomplete unit; these rows exist so the gap is a visible
line in a committed file.

**D5's two rows are open on the same terms**, and the same sentence
applies to them: nothing automated discharges either. D5 added no
screenshot harness, because the human closed that choice on 2026-10-23
in favour of the manual per-screen check, and a correctness test does
not discharge a layout obligation [project.md].

**The teacher overview is D5's first row to check**, and the reason is
density rather than length. `overview_earnings_label` is only 16
characters, but it sits *directly above a money amount rendered in
Bangla numerals* — and that pairing is the densest short string in the
product. Bangla conjuncts and the ি / ী / ু vowel signs extend above
and below the Latin line box, so a headline-sized figure under a label
in a container sized to Latin metrics is exactly the clipping case the
check exists to find. It is also the screen a teacher opens most.

The lengths were **computed from `values-bn/strings.xml` after this
unit's strings landed**, by running the snippet above rather than
estimating. **Both bundles stand at 245 entries**, of which D5 added 10
to each — counted on 2026-10-25 with
`grep -c "<string " android/src/main/res/values{,-bn}/strings.xml`, and
equal on both sides, which is the property that matters. (An earlier
revision of this sentence said 223; that figure predated D4's strings
reaching the working tree and was never recounted. Where a document
states a number, the number is a claim [project.md].)

**The conflict-resolution screen is the first row to check, and by some
distance.** Three things compound on it, and no other screen in the
product carries all three:

- `attendance_version_conflict` at **122 characters is the third-longest
  string in the whole bundle**, behind only
  `roster_remove_claimed_remedy` (145) and `decline_guardian_body`
  (125). It is a two-clause sentence and it sits *above* the comparison
  rather than replacing it, so unlike those two it does not have the
  panel to itself.
- The screen then renders **two labelled columns of names side by side**
  on a phone — the densest Bangla text this unit ships [BR7.5]. Each
  cell is a weighted half of a `Row`, so a long Bangla name wraps inside
  its own half rather than clipping; what the check must confirm is that
  the wrap is *readable*, not merely that nothing is cut.
- The two column headings (`conflict_mine_heading`,
  `conflict_theirs_heading`) must stay visually parallel. If one wraps
  to two lines and the other does not, the columns stop reading as a
  comparison, which is the one thing this screen exists to communicate.

The whole screen scrolls vertically, so the failure to look for is
**wrapping and glyph clipping rather than being pushed below the fold**.

**A second D4 row carries a check the others do not: the queued
notice.** `attendance_queued` (74) and the four `queue_state_*` strings
are the only copy in the product that has to make an unsent write read
as *unsent*. BR3.1's whole guarantee is that a queued roster never
renders as confirmed, and in Bangla the risk is specific: if
`queue_state_queued` ("এই ফোনে আছে, এখনও পাঠানো হয়নি") is truncated at
the comma, what remains reads as "it is on this phone" — which a teacher
would reasonably take as saved. **A checker must confirm these four
strings are not truncated**, and that `queue_state_failed` and
`queue_state_conflicted` remain visibly different sentences rather than
both collapsing to an ellipsis [AC3.1.10]. Truncation here is not a
cosmetic fault; it is the silent-queue failure arriving through the
layout.

**One thing a well-meaning checker must not "fix" on the marksheet
rows.** `marksheet_rank` and `exam_entered_count` reorder their two
placeholders relative to the English (`%2$s জনের মধ্যে %1$s তম`,
`%2$s-এর মধ্যে %1$s জনের`), the same shape as D3's two amount strings.
Reversing them would read as the wrong rank or the wrong count, not as
a layout fault, and nothing automated would catch it. Marks render
through `Numerals.marks` and counts through `Numerals.count`, so
**Latin digits inside Bangla text is the intended result** here exactly
as it is for money.

**D3's four rows are open for the same reason the eleven above are, and
two of them carry a check the others do not.**

The lengths were **computed from `values-bn/strings.xml` at the time of
writing**, not taken from the reference list below and not estimated.
This project's memory records a stage whose table asserted figures were
measured when they were not, so the method is stated rather than
implied.

**The payment form is the row to check first.** `payment_ask_teacher`
at 93 characters is the copy shown *instead of* the destination step
where a teacher set no collection number [NFR14.34], so it lands in the
space a number and a channel list would otherwise occupy — the most
variable vertical space on any D3 screen. A checker should confirm it
does not push the amount field below the fold on a small device.

**Two D3 rows need a check nothing else in this table has needed: the
digits inside them must stay Latin.** Every amount on these screens is
rendered through `Numerals.money`, and the server's `Money.format`
agrees [BR6.6] — so `৳1,25,400` is the intended result in Bangla, with
Bengali text around Latin digits and a Bengali taka sign. Three specific
things to confirm, each of which a well-meaning fix would break:

- `fees_outstanding_of_charged` renders **two** amounts in one sentence
  (`%2$s-এর মধ্যে %1$s বাকি`), with the placeholders in the opposite
  order to the English. A reversed pair would read as the wrong figure
  owed, not as a layout fault, and nothing automated would catch it.
- `claim_claimed_amount` likewise reorders its two placeholders
  (`%2$s-এ %1$s`), putting the channel before the amount.
- Lakh grouping (`1,25,400`, not `125,400`) must survive, because
  Western grouping reads as a different magnitude to a Bangladeshi
  reader.

**A checker who "corrects" any of those three is breaking the rule
rather than the layout**, which is the same warning the accepted-count
row below carries.

**Nothing automated discharges these four rows.** The obligation is a
check on a device in Bangla locale [team: Testing Posture], there is
still no screenshot harness in the project, and code generation cannot
perform one. Stated plainly because a manual verifier described without
that sentence reads, to the next person, as a verifier [project.md,
learned 2026-10-23].

**D2's six rows are open for the same reason D1's five are**, and they
are added here with the exact string each check must use so the gap is a
visible line in a committed file rather than an omission.

**Two of D2's rows deserve naming before anyone runs them.**

`roster_remove_claimed_remedy` at **145 characters is now the longest
string in the whole bundle**, displacing `decline_guardian_body` (125).
Re-derived at the time of writing rather than taken from the reference
list. It is a three-clause sentence sitting in a refusal panel beside a
title and two buttons, which is where wrapping and glyph-clipping
failures are most likely. **It is the first D2 row to check.**

The batch-list and roster rows carry a failure mode the other rows do
not: **`roster_accepted_count` is the one count in the product with no
locale helper between the server and the screen** [NFR3.3]. Money goes
through `Numerals.money`, marks through `Numerals.marks`; this string
formats two bare integers through `Numerals.count`, which renders them
Latin by the project's own numeral rule. What the check must confirm is
that "9 of 12 accepted" reads correctly in Bangla with **Latin digits
inside Bangla text**, which is the intended and slightly unusual
result — and that the sentence does not wrap badly when both numbers
reach three digits. A checker who "fixes" this by converting the digits
would be breaking the rule, not the layout.

**D1's five rows are open, and that is the accurate record.** The
obligation this table exists to carry is a check **on a device in Bangla
locale** [team: Testing Posture], and code generation cannot perform one:
nothing automated discharges it, which is the sentence this project
requires to be written rather than implied [project.md, learned
2026-10-23]. The rows are added now, with the exact string each check must
use, so the gap is a visible line in a committed file rather than an
omission — which is what the table was created to make impossible.

**D1's strings are now the four longest in the whole bundle**, re-derived
at the time of writing rather than taken from the reference list below.
`decline_guardian_body` at 125 characters is the longest string in the
app, and it sits in a bottom sheet beside a title and two buttons — the
tightest vertical space in the product. That is where the wrapping and
glyph-clipping failures are most likely, and it is the first row to check.

The five rows are a D1 obligation that is **not discharged**; see the
Gaps section of this unit's `code-summary.md`.

The four rows above are the screens that **already shipped** without this
check existing. They are listed as outstanding rather than assumed good:
three Android Bolts merged before the obligation had a verifier, so nothing
establishes that they pass. Checking them is part of D1, alongside the
screens D1 adds.

### Screens still to come

Added to the table by the unit that ships them. From the approved plan:

- **D1** — `O1` create account, in all five states; the pending-seat list
- **D2** — `T7` roster with pending state, `T8` add student, create batch,
  remove student, `G1` guardian child home
- **D3** — `T5` dues, `S2` batch fees, `T4` verify, `S3` submit, `G3` history
- **D4** — *added to the table above.* The plan named four screens
  (`T1` today, `T2` record a class, `T3` mark entry, marksheet); the
  unit ships **seven**, because the conflict-resolution screen, the
  exam list and guardian progress are each their own screen rather than
  states of another. BR7.5 enumerates all seven by name and a screen
  with no row means an incomplete unit, so the table carries seven rows
  rather than the four forecast here.
- **D5** — *added to the table above.* The plan forecast "insights" as
  one screen; the unit ships **two**, because the cross-batch dues list
  and the teacher overview are different screens with different refresh
  patterns rather than two states of one [functional-spec § 7a].
- **D6** — deletion confirmation and its copy
