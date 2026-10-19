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
| IAM role `shikkhokplus-github-actions` | What the OIDC token assumes |
| Its two inline policies | State access, and the infrastructure scope |

**The GitHub OIDC provider is referenced, not created.** An AWS account
can hold only one provider per URL, and most accounts that have ever
run a GitHub deploy already have it. Owning a shared resource means a
`terraform destroy` here would break every other project trusting it.

Set `create_github_oidc_provider = true` only for an account with
none:

```bash
aws iam list-open-id-connect-providers
```

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

That sharing is not hypothetical. In the account this was first
applied to, the provider already existed and **six unrelated roles
depended on it** — importing it would have put their deploys one
`terraform destroy` away from breaking.

The security boundary is one string — the `sub` condition in the trust
policy. The OIDC provider trusts *GitHub*, not your repo, so without
that condition **any repository on GitHub could assume this role**. It
is scoped to:

```
repo:arshomashohag@*/shikkhok-plus@*:ref:refs/heads/main
repo:arshomashohag@*/shikkhok-plus@*:environment:terraform-plan
repo:arshomashohag@*/shikkhok-plus@*:environment:terraform-apply
```

A pull request from a fork carries `pull_request` in its subject and
matches none of them. That is what stops a drive-by PR applying
infrastructure.

**The environments are named, not wildcarded.** `environment:*` looks
like it means "our environments"; it means any string somebody writes
after `environment:` in a workflow file. Anyone able to push a branch
could add `environment: whatever` and assume this role, going around
the main-branch restriction entirely. Adding an environment is adding
a way into the account, so it takes a change here rather than a
workflow edit.

`deploy-staging.yml` runs in `staging`, which is **not** on that list.
It does not assume this role today. When its SSM delivery step lands
it will need AWS access, and the right answer is a separate deploy
role scoped to SSM and ECR — not widening this one, which carries
`ec2:*`, `rds:*`, `route53:*` and IAM writes. `trust_staging_environment`
exists as the expedient alternative and is off by default.

### Why the `@*` segments are there

This account has **GitHub's OIDC subject customization** enabled, so a
real subject is

```
repo:arshomashohag@20051700/shop-360@1310170125:ref:refs/heads/main
```

with a GitHub-assigned numeric id after the owner *and* after the
repository — not the documented default `repo:<owner>/<repo>:...`.

A trust policy written in the default shape matches **nothing** here
and fails every run at role assumption. That is not a hypothetical: it
is how this role was broken, and it is subtle because the error says
"not authorized to perform sts:AssumeRoleWithWebIdentity", which reads
like a permissions problem rather than a string that cannot match.

Verified against CloudTrail — every successful
`AssumeRoleWithWebIdentity` in this account, across four repositories
and both `ref:` and `environment:` subjects, carries this format.

**The ids are wildcarded rather than pinned** because GitHub assigns
them and a change would silently break the trust policy. The wildcards
do not widen access: the names in front of each `@` are exact, so
`shikkhok-plus@*` does not match `shikkhok-plus-evil@...` — the `@`
must come directly after the name.

If you fork this module into an account **without** that customization,
set `github_subject_has_numeric_ids = false`. To check which you have,
run any workflow that assumes a role and read the subject back:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --max-results 5 --query 'Events[].CloudTrailEvent' --output text
```

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
  APEX_DOMAIN       the PARENT zone, e.g. nirmatabd.com
  TF_ENVIRONMENT    staging
```

**`APEX_DOMAIN` is the parent, not the hostname the API answers on.**
The main module creates its own zone beneath it and delegates it, so
`nirmatabd.com` yields the zone `shikkhokplus.nirmatabd.com` and the
API at `api.shikkhokplus.nirmatabd.com`. The parent zone is looked up
and never modified except for that one NS record — it serves other
projects too, and claiming a name from one of them is exactly what
the dedicated zone avoids.

Change `project_subdomain` if you want a different label under the
apex.

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
