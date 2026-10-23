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
- **D4** — `T1` today, `T2` record a class, `T3` mark entry, marksheet
- **D5** — insights
- **D6** — deletion confirmation and its copy
