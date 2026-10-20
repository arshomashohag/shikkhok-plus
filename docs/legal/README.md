# Legal documents

`PRIVACY.md` is the privacy policy the Play Store listing links to.

## The policy is generated from the schema, not written beside it

`team.md` requires the text to follow each table's written
disposition rather than being authored independently, because *a
privacy policy that contradicts the implementation is worse than a
vague one*. Every factual claim in it was checked against the code:

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

The open question `team.md` flagged — what happens to a teacher's
record of a child who deletes their account — was decided on
2026-10-20 as **anonymise in place**:

| Table | Disposition |
|---|---|
| `account` | hard delete |
| `profile` | hard delete |
| `otp_request`, `refresh_token`, `verify_attempt` | hard delete |
| `rate_limit_counter` | expires on its own window |
| `auth_audit_log` | retain 12 months, holds no name or code |
| `enrollment` | anonymise: clear name and contact, keep the row |
| attendance, marks, fee entries | retain, no longer identifying |

The reasoning is in the policy itself, where the user reads it: the
entries are at once the child's personal data and the teacher's
record of a class they ran and were paid for. Erasing them would
rewrite an attendance history and a settled fee ledger.

**The deletion implementation must match this table**, and
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
