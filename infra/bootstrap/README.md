# Bootstrap

**Run this once, from your laptop. Everything after it runs in GitHub
Actions.**

## Why this exists at all

Terraform in CI needs remote state and AWS credentials. Both have to
exist before Terraform can run — and Terraform is what creates them.
That circle has to be broken somewhere, and this is the smallest place
to break it: three resources that never change.

| Resource | Why |
|---|---|
| S3 state bucket | Versioned, encrypted, all public access blocked |
| GitHub OIDC provider | So Actions can get a token without a stored key |
| IAM role `shikkhokplus-github-actions` | What that token assumes |

Its own state stays **local**, and that is fine: it describes three
resources that never change. If it is lost, `terraform import` on three
known names rebuilds it — cheaper than securing a second bucket to hold
the state of the first.

## No long-lived AWS keys, anywhere

An access key in GitHub secrets never expires, cannot be rotated
without a human remembering to, and is usable by anyone who can edit a
workflow file. OIDC issues a **one-hour token per run**, scoped to this
repository.

The security boundary is one string — the `sub` condition in the trust
policy. The OIDC provider trusts *GitHub*, not your repo, so without
that condition **any repository on GitHub could assume this role**. It
is scoped to:

```
repo:arshomashohag/shikkhok-plus:ref:refs/heads/main
repo:arshomashohag/shikkhok-plus:environment:*
```

A pull request from a fork carries `pull_request` in its subject and
matches neither. That is what stops a drive-by PR applying
infrastructure.

## The IAM scope, stated honestly

The role gets **service-level** permissions (`lightsail:*`,
`cloudfront:*`, `acm:*`, `route53:*`, `rds:*`), not per-action
least-privilege. That is a trade, not an oversight.

Enumerating every action Terraform needs across five services produces
a policy that breaks on the next provider upgrade and gets widened
under deadline pressure — which ends at the `*` it was meant to avoid,
having cost a day first.

What makes it defensible: the role is assumable **only** from this
repository, on main or through an environment with manual approval, and
it holds **no IAM write permissions at all**. It cannot grant itself
anything.

## Running it

```bash
cd infra/bootstrap
terraform init
terraform plan        # read it
terraform apply
```

Then do what the `next_steps` output says:

```
GitHub → Settings → Secrets and variables → Actions

Variables:
  AWS_ROLE_ARN          (from the output)
  TF_STATE_BUCKET       (from the output)
  TF_DOMAIN_NAME        your domain, e.g. shikkhokplus.com
  TF_SSH_KEY_PAIR_NAME  the Lightsail key pair name
  TF_ENVIRONMENT        staging

Secrets:
  TF_OPERATOR_IP_CIDR   your IP as a /32, for SSH
```

> `TF_OPERATOR_IP_CIDR` is a **secret** rather than a variable because
> it is your home or office address. Everything else is a variable:
> variables are readable in logs, secrets are masked, and marking
> something secret that appears in plan output anyway only produces
> `***` where a reviewer needed to see a value.

Then move the main module's state to S3:

```bash
cd ..
terraform init -migrate-state \
  -backend-config="bucket=$(terraform -chdir=bootstrap output -raw state_bucket)"
```

## Environments to create

Both in Settings → Environments:

| Environment | Reviewers | Why |
|---|---|---|
| `terraform-plan` | none | A plan that needed approval would mean nobody sees the diff until after someone approves it |
| `terraform-apply` | **you, required** | This is the gate. Without a required reviewer, dispatching apply runs it immediately and the manual step is a button rather than a decision |

**The approval requirement is the whole point of the apply job.** A
Terraform run can replace the Lightsail instance, and in Phase 1 that
destroys the containerised Postgres with it — a database whose only
backup is `pg_dump`.

## After this

You never run Terraform locally again. Infrastructure changes go:

1. Edit `infra/**` on a branch, open a PR
2. The plan appears as a PR comment
3. Merge
4. Actions → terraform → Run workflow → **apply** → approve

## A note on pinned action versions

The workflow pins `configure-aws-credentials@v4`, `setup-terraform@v3`,
`github-script@v7` and `upload-artifact@v4`. Each of those has a newer
major available, and each pinned tag was verified to still exist.

They are left where they are deliberately: bumping four majors at once
risks input changes that cannot be tested without running against your
real account. Bump them one at a time, watching a plan run after each.
