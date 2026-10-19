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
resources that never change. Securing a second bucket to hold the
state of the first is a regress with no end.

**If that state is lost, recovery is one flag** — see "Recovering lost
state" below. The three resources still exist in AWS; only the record
of them is gone.

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

The role gets **service-level** permissions (`ec2:*`, `cloudfront:*`,
`acm:*`, `route53:*`, `rds:*`, `ssm:*`), not per-action
least-privilege. That is a trade, not an oversight: enumerating every
action across six services produces a policy that breaks on the next
provider upgrade and gets widened under deadline pressure — ending at
the `*` it was meant to avoid, a day later.

**It also holds real IAM write permissions**, and an earlier version
of this document claimed it did not. SSM needs an instance profile,
which means creating a role and attaching a policy. There is no way
around that, and pretending otherwise would only mean the apply fails.

What bounds it: the IAM actions are restricted **by path** to
`/shikkhokplus/*`, so the CI role cannot touch an unrelated role and
**cannot modify itself** — it lives at the IAM root path. And the role
is assumable only from this repository, on main or through an
environment with manual approval.

## Running it

```bash
# Confirm you are pointed at the right account FIRST.
aws sts get-caller-identity --query Account --output text

cd infra/bootstrap
terraform init
terraform plan        # read it
terraform apply
```

Set `expected_account_id` in a `terraform.tfvars` once you know the
number. Running this against the wrong account creates an OIDC
provider and a role somewhere unintended, and the first symptom is a
CI run failing to assume a role that exists — in a different account.
The precondition makes that mistake impossible rather than merely
unlikely.

The state bucket name defaults to
`shikkhokplus-tfstate-<your-account-id>`. S3 names are globally unique
across **every** AWS account, so an unsuffixed name is very likely
taken by a stranger — and `BucketAlreadyExists` reads like a bug here
rather than a namespace collision.

Then do what the `next_steps` output says:

```
GitHub → Settings → Secrets and variables → Actions

Variables:
  AWS_ROLE_ARN      (from the output)
  TF_STATE_BUCKET   (from the output)
  TF_DOMAIN_NAME    your domain, e.g. shikkhokplus.com
  TF_ENVIRONMENT    staging
```

**No secrets at all.** There is no SSH key and no operator IP, because
there is no SSH — Session Manager replaced both. Everything the
workflow needs is a variable, and variables are readable in logs,
which is correct for values that appear in plan output anyway.

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
Terraform run can replace the app instance, and in Phase 1 that
destroys the containerised Postgres with it — a database whose only
backup is `pg_dump`.

## After this

You never run Terraform locally again. Infrastructure changes go:

1. Edit `infra/**` on a branch, open a PR
2. The plan appears as a PR comment
3. Merge
4. Actions → terraform → Run workflow → **apply** → approve

## Recovering lost state

If `infra/bootstrap/terraform.tfstate` is deleted, the three resources
still exist in AWS. Terraform no longer knows that, so the next apply
tries to create them and fails with `EntityAlreadyExists` and
`BucketAlreadyOwnedByYou` — errors that read like a bug in this module.

The recovery is built in as `import` blocks rather than written here as
commands, because a documented command is one nobody can find under
pressure and a block is one `terraform plan` checks:

```bash
terraform init
terraform plan -var recover_existing=true
```

**The plan must say `3 to import, 0 to add, 0 to change, 0 to
destroy`.** Anything to add or destroy means the names in `import.tf`
do not match what is actually in the account — stop and read them
rather than applying.

```bash
terraform apply -var recover_existing=true
```

Then leave `recover_existing` at false. Nothing in AWS changes; only
the state file is rebuilt.

## A note on pinned action versions

The workflow pins `configure-aws-credentials@v4`, `setup-terraform@v3`,
`github-script@v7` and `upload-artifact@v4`. Each of those has a newer
major available, and each pinned tag was verified to still exist.

They are left where they are deliberately: bumping four majors at once
risks input changes that cannot be tested without running against your
real account. Bump them one at a time, watching a plan run after each.
