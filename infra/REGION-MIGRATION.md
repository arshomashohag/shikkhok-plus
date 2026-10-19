# Moving region: destroy first, then switch

**Read this before applying a region change.** It is not a migration;
it is a teardown and a rebuild, and getting the order wrong leaves
resources running that nothing tracks.

## Why the obvious order is wrong

Terraform's AWS provider finds resources by ID within the configured
region. Change `region` and apply, and the provider looks for
`i-0578b785c97b4ec54` in the NEW region, does not find it, and
concludes it was deleted. The plan then reads:

```
Plan: 13 to add, 1 to change, 4 to destroy.
```

Thirteen creates in the new region, and **no destroy for the old
instances, EIPs or VPC** — because the provider can no longer see
them. They keep running. They keep billing. Nothing in state points
at them, so no future apply will ever clean them up.

For this project that is about USD 33/month, invisible.

## The order that works

**1. Destroy ONLY the regional resources, with the old region still
configured.**

A bare `terraform destroy` is WRONG here, and this was verified
against the real state rather than assumed. It plans **37 destroys**,
and among them:

```
# aws_route53_zone.project will be destroyed
# aws_route53_record.delegation will be destroyed
```

The zone and its delegation live in the ROOT module, so they are in
scope even though DNS is not regional. Destroying the zone gives you
a new one with DIFFERENT nameservers, so the delegation has to be
recreated and public propagation starts from zero — on top of the
certificate revalidation you already owe.

Target the regional modules instead:

```bash
cd infra
terraform destroy -var region=ap-south-1 \
  -var apex_domain=nirmatabd.com -var environment=staging \
  -target=module.app -target=module.staging_app -target=module.network \
  -target=module.cdn
```

Read the plan before confirming. `aws_route53_zone.project` and
`aws_route53_record.delegation` must NOT appear in it. If they do,
the -target flags did not take and you are about to delete your DNS.

The CDN module is included because its certificate is regional and
its origin points at an instance that is about to stop existing.
That costs a revalidation either way.

**2. Confirm the old region is actually empty.**

State saying "destroyed" is not the same as AWS having nothing left:

```bash
aws ec2 describe-instances --region ap-south-1 \
  --query 'Reservations[].Instances[?State.Name!=`terminated`].InstanceId'
aws ec2 describe-addresses --region ap-south-1 --query 'Addresses[].PublicIp'
aws ec2 describe-vpcs --region ap-south-1 \
  --query 'Vpcs[?IsDefault==`false`].VpcId'
```

All three must be empty. An unattached Elastic IP bills MORE than an
attached one, so a leftover EIP is the costliest thing to miss.

**3. Then apply with the new region.**

## What survives the move

Verified against a real `terraform plan -destroy`, not assumed:

| Resource | Survives a TARGETED destroy? | Note |
|---|---|---|
| Route53 zone | yes, if you use -target | a bare destroy DELETES it |
| NS delegation | yes, if you use -target | same, and new NS means re-propagation |
| ACM certificate | no | regional; revalidation is 5-30 min |
| CloudFront distribution | no | destroyed with the cdn module; ~15 min to recreate |
| EC2, EIP, VPC, subnets | no | the point of the exercise |
| S3 state bucket | yes | bootstrap module, untouched |
| IAM role and OIDC trust | yes | IAM is global, and in bootstrap |

The instance IAM roles under `/shikkhokplus/` DO get destroyed, since
they belong to the app module. That is fine — they are recreated by
the next apply, and the CI role has path-bounded permission to do so.

## Note on latency

ap-south-1 (Mumbai) was chosen because it is nearest to Bangladesh
[TC-17]. us-east-1 adds roughly 200-250ms round trip for users there.
That was accepted deliberately on 2026-10-19; see the `region`
variable. [TC-17] should be re-measured against the real region
rather than the one the requirement assumed.
