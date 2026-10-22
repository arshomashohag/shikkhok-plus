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
