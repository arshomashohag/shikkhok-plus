# Legal documents

`PRIVACY.md` is the privacy policy the Play Store listing links to.

## The policy is generated from the schema, not written beside it

**This heading is now true.** It was written before any generator
existed: the text underneath was hand-authored *against* the schema and
verified by a five-row table of manual checks — careful work, and not
what the heading claimed. `scripts/generate_privacy_policy.py` is what
makes the sentence a fact.

`team.md` requires the text to follow each table's written disposition
rather than being authored independently, because *a privacy policy that
contradicts the implementation is worse than a vague one*.

### How it works

The generator writes **between markers** in `PRIVACY.md`:

```
<!-- BEGIN GENERATED: governance manifest -->
<!-- END GENERATED: governance manifest -->
```

Everything outside them is human prose and stays editable — the contact
address, the reasoning a parent reads, the plain-language summary.
Inside them is what can silently stop matching the code: which data is
deleted, which is kept, and for how long.

```
python3 -m scripts.generate_privacy_policy          # regenerate
python3 -m scripts.generate_privacy_policy --check  # the gate's form
```

`make check` compares the committed region against a fresh render and
**fails on drift**, the same shape as the OpenAPI schema-diff gate and
for the same reason. **Regeneration is the only sanctioned fix.**
Hand-editing the file to turn a red check green inverts the control into
a rubber stamp, and it looks exactly like fixing the problem.

The compared region ends with a digest over the whole manifest —
disposition, retention class **and basis** for every table. Without it a
changed `basis` would alter nothing on the page and pass the gate, which
is how the first version of this generator behaved, on precisely the
field that matters most: the generator publishes the manifest's stated
reasoning, so a basis that disagrees with its own disposition produces a
policy that is mechanically consistent and substantively wrong.

### What this does NOT cover

Nothing mechanically prevents a factual claim being written in the prose
**outside** the markers, where the comparison does not reach. The rival
hand-written table that used to sit in this file has been removed to
shrink that surface, and the `PRIVACY.md` retention table with it — but
the obligation remains partly manual and is recorded as such rather than
rounded up.

These claims are outside the generated region and were checked by hand:

| Claim | Verified against |
|---|---|
| One-time code expires in 5 minutes | `CODE_LIFETIME` in `app/auth/otp.py` |
| Session tokens last 30 days | `REFRESH_TOKEN_LIFETIME` in `app/auth/tokens.py` |
| Codes and tokens stored as hashes | `app/auth/hashing.py` |
| Internet is the only granted permission | the merged release manifest |
| No device or advertising identifiers | the release DEX scan |

## NOT YET TRUE: account deletion

**The policy describes two deletion paths. Neither is implemented.**

`project.md` makes both release-blocking:

> ALWAYS provide both account-deletion paths — in-app, and an
> externally accessible route usable without reinstalling the app —
> as release-blocking V1 deliverables [TC-19] [RC-4] [RC-5]

Current state:

- No deletion endpoint exists in `app/api/`
- No Settings screen exists in the Android app
- No externally reachable deletion page exists

This is recorded here rather than softened in the policy, because the
policy has to describe what the finished product does and the gap is
a build obligation, not a drafting one.

**Do not submit the Data Safety form or publish to a public track
until both paths exist and are tested.** Play requires a working
deletion route for any app that collects personal data, and a policy
promising one that does not answer is worse than no policy — it is a
false statement to a regulator about children's data.

Internal testing is fine meanwhile; the policy is accurate about
everything else.

## The disposition decided for this policy

**The table that used to sit here has been removed, and its removal is
the point.** It was a second per-table disposition list, maintained by
hand beside `app/governance/dispositions.py` — and the two had already
disagreed: this file said `account` was "hard delete" while the manifest
said `ANONYMIZE_IN_PLACE` and `PRIVACY.md` promised the phone number was
"deleted permanently". Three documents, three answers, nothing failing.
A rival source is how that happens, so there is now one source.

**`app/governance/dispositions.py` is it.** Every disposition, retention
class and stated reason lives there, the policy is generated from it,
and the drift gate keeps the two in step.

Two decisions worth recording here, because they are history rather than
current state and the manifest carries only the latter:

- The open question `team.md` flagged — what happens to a teacher's
  record of a child who deletes their account — was first decided on
  2026-10-20 as **anonymise in place**.
- On **2026-10-25** the human reversed the `account` entry to **hard
  delete**, choosing the published policy's promise over the manifest.
  The hazard the old basis named — a released number being reused by a
  different person while enrollments still referenced the account — is
  real and is closed by the constraint rather than by the disposition:
  migration `0007` makes the three `account` references `SET NULL`, so a
  new account taking the same number inherits nothing from the old one.

**The deletion implementation must match the manifest**, and
`project.md` already requires a test per path asserting exactly that.

## Hosting the link

Play needs a public URL. The raw GitHub link works:

```
https://raw.githubusercontent.com/arshomashohag/shikkhok-plus/main/docs/legal/PRIVACY.md
```

Raw Markdown renders as plain text, which Play accepts but reads
poorly on a phone. Better options, in order of effort:

1. **GitHub Pages** — enable it for this repository and the file
   renders as a styled page at a stable URL.
2. The repository's own file view, which renders Markdown but shows
   GitHub's chrome around it.

Whichever you choose, the branch must be public and the URL must stay
reachable: Play rechecks it, and a dead privacy-policy link is grounds
for removal.
