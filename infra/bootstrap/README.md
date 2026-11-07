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
repo:arshomashohag@*/shikkhok-plus@*:environment:staging-infra
repo:arshomashohag@*/shikkhok-plus@*:environment:production-infra
```

There is deliberately **no `ref:refs/heads/main`** subject any more: it
let any workflow on main assume this role without passing an
environment's required reviewer [OPS-2]. No workflow used it.

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

## The deploy roles: one per environment

`deploy.yml`'s plan and release jobs and `security-scan.yml` run in the
`staging` or `production` GitHub environment and assume a **deploy
role**, never the infrastructure role. There is one deploy role per
environment (`deploy_role.tf`), and each:

- trusts exactly `…:environment:<env>` — a staging-approved run cannot
  assume the production role;
- can push only to `shikkhokplus-<env>-backend`, read and write only its
  own `image-tag` and `runtime-env` parameters and read its own
  `api-url`, roll only `shikkhokplus-<env>-*` groups, and snapshot only
  `shikkhokplus-<env>-db` (pruning only its own `-predeploy-*`
  snapshots);
- reads **no Terraform state** and **no database credential**.

Until 2026-11-02 a single role trusted both environments, used
`shikkhokplus-*` wildcards and could read both state files — so a
staging approval could change production and read its database master
password [OPS-3].

**Which ARN goes where.** After `terraform apply`, read
`terraform output deploy_role_arns` and set each value as the
`AWS_DEPLOY_ROLE_ARN` variable **of that environment only**
(Settings → Environments → *env* → Environment variables):

| GitHub environment | `AWS_DEPLOY_ROLE_ARN` | Role name |
|---|---|---|
| `staging` | `deploy_role_arns["staging"]` | `shikkhokplus-github-deploy` (unchanged — the `moved` block keeps the existing role, so the staging variable already holds this ARN) |
| `production` | `deploy_role_arns["production"]` | `shikkhokplus-github-deploy-production` (new) |

Putting the wrong ARN into an environment fails at role assumption
rather than granting anything.

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

The role gets **service-level** permissions for the services whose
Terraform action set is wide and moves with the provider (`ec2:*`,
`cloudfront:*`, `acm:*`, `route53:*`, `rds:*`, `ecr:*`,
`autoscaling:*`), not per-action least-privilege. That is a trade, not
an oversight: enumerating every action across them produces a policy
that breaks on the next provider upgrade and gets widened under
deadline pressure.

Where the actions Terraform uses are known and few, they are listed:
SSM is **parameter management under `/shikkhokplus/` only** (`ssm:*`
included `SendCommand`, a shell on any instance); logs, SNS and
CloudWatch alarms are scoped to `shikkhokplus` names; and Route53
record changes are **denied for any name not containing
`shikkhokplus`**, so the role cannot repoint another project's record
in the shared apex zone.

Lambda is **`lambda:*` on `shikkhokplus-<env>-*` function names
only**, per environment, for the staging seeder (`modules/seeder`), and
`iam:PassRole` names two services, EC2 and Lambda -- still only for that
environment's roles under `/shikkhokplus/`, which all carry that
environment's boundary. Each boundary includes Lambda's VPC
network-interface actions; the CI role holds `ec2:*` already, so no
role it creates can reach further than it does. The plan role reads
that environment's functions and image metadata, for the deploy's
seeder-eligibility check.

**It also holds real IAM write permissions**, and an earlier version
of this document claimed it did not. SSM needs an instance profile,
which means creating a role and attaching a policy. There is no way
around that, and pretending otherwise would only mean the apply fails.

What bounds it [OPS-2]:

- **One infrastructure role per environment** [C-09]. Each trusts only
  its own `<env>-infra` environment, reads and writes only `<env>/` in
  the state bucket, and is explicitly denied the other environment's
  database, repository, group and every resource tagged with the other
  environment's name. CloudFront distributions and hosted zones carry
  generated ids and no tag condition, so those stay account-wide; a
  separate production account is the fix for that remainder.
- **A permissions boundary per environment on every role it creates.**
  Bootstrap creates `shikkhokplus-workload-boundary-<env>` (path
  `/shikkhokplus/`), a ceiling listing only what that environment's app
  host does -- its own parameters, repository, buckets and logs [C-08].
  `CreateRole`, `PutRolePolicy` and `PutRolePermissionsBoundary` are
  allowed only with `iam:PermissionsBoundary` equal to the role's own
  environment's boundary, and `DeleteRolePermissionsBoundary` is
  denied.
- **No managed policy may be attached.** The only one it could attach,
  `AmazonSSMManagedInstanceCore`, grants `ssm:GetParameter` on `*`; the
  host now carries the agent's actions inline instead.
- **`PassRole` only to EC2** (`iam:PassedToService`), for its own
  environment's roles.
- The IAM actions are restricted **by path and name** to
  `/shikkhokplus/shikkhokplus-<env>-*`, so the CI role cannot touch an
  unrelated role and **cannot modify itself**, nor the boundary: it
  lives at the IAM root path and has no policy-level write action.
- **A read-only plan role per environment** [C-11], assumable from the
  `<env>` deploy environment, renders the plan the `<env>-infra`
  reviewer reads before approving, and stores the plan file the apply
  then applies.

**Order of applies.** The main module now sets `permissions_boundary`
on the instance role, and the CI role can only create or extend a role
that carries it -- so **apply this bootstrap first**, then let the next
deploy apply the main module. Applied the other way round, the main
module's first apply fails at `PutRolePermissionsBoundary` with
AccessDenied and changes nothing.

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

Repository variables:
  TF_STATE_BUCKET   state_bucket (from the output)
  APEX_DOMAIN       the PARENT zone, e.g. nirmatabd.com

Per-environment variables (staging, production):
  AWS_DEPLOY_ROLE_ARN   deploy_role_arns[<env>] -- see the table above
  AWS_PLAN_ROLE_ARN     plan_role_arns[<env>]

Per-environment variables (staging-infra, production-infra):
  AWS_ROLE_ARN          infra_role_arns[<env>]
```

**Delete any repository-level `AWS_ROLE_ARN`.** A repository variable
is what an environment falls back to, so production-infra would
silently receive the staging role -- and then fail at role assumption,
because that role trusts only staging-infra.

**Order of applies for C-08/C-09.** Apply this bootstrap first: it
creates the per-environment boundaries and roles and KEEPS the retired
single boundary, which roles still carry. Then deploy each environment
once, which moves its instance role onto its own boundary and drops the
managed SSM policy. Then remove `aws_iam_policy.workload_boundary` from
main.tf and apply the bootstrap again.

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

| Environment | Reviewers | Role it can assume |
|---|---|---|
| `staging` | none | the staging deploy role and the staging plan role |
| `staging-infra` | none | the staging infrastructure role |
| `production` | **you, required** | the production deploy role and the production plan role |
| `production-infra` | **you, required** | the production infrastructure role |

**Restrict `production` and `production-infra` to the `main` branch**
(Settings -> Environments -> Deployment branches and tags). deploy.yml
also refuses a production commit that is not on `main`, but the
environment's own branch policy is what stops a modified workflow on
another branch from reaching the role at all.

**`production-infra`'s required reviewer is the gate on production
infrastructure**, and since 2026-11-02 there is no way around it: the
infrastructure role no longer trusts `ref:refs/heads/main`, which let
any workflow running on main assume it with no environment and
therefore no approval [OPS-2].

## After this

You never run Terraform locally again. Infrastructure changes go:

1. Edit `infra/**` on a branch, open a PR, merge
2. Actions -> deploy -> Run workflow, choosing the environment
3. The `plan` job prints the Terraform plan to its summary
4. For production, read it, then approve `production-infra`; that job
   applies exactly the saved plan file and nothing else [C-11]

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
