# The Android App Link fingerprint, one SSM parameter per environment.
#
# `deploy.yml` builds `/.well-known/assetlinks.json` for the web-app host
# from `/shikkhokplus/shikkhokplus-<env>/android-cert-sha256` and fails
# the web deploy while it is missing (web/README.md). Bootstrap owns it
# because it is set once, by a person, from the Play Console, and the
# deploy role that reads it is defined here too (deploy_role.tf).
#
# The value is not a secret: Android fetches it from a public URL to
# verify the link. One value serves both environments, because staging
# and production ship the same package (`com.shikkhokplus.app`) signed by
# the same Play app-signing key.
#
# **us-east-1, not var.region**: the deploy workflow reads every runtime
# parameter in its AWS_REGION, us-east-1, while bootstrap's own resources
# live in ap-south-1.

provider "aws" {
  alias  = "deploy_region"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = "shikkhokplus"
      ManagedBy = "terraform-bootstrap"
    }
  }
}

resource "aws_ssm_parameter" "android_cert_sha256" {
  provider = aws.deploy_region
  for_each = var.android_cert_sha256 == null ? toset([]) : local.environments

  name        = "/shikkhokplus/shikkhokplus-${each.key}/android-cert-sha256"
  description = "SHA-256 certificate fingerprint(s) for the Android App Link (assetlinks.json)"
  type        = "String"
  value       = upper(replace(var.android_cert_sha256, " ", ""))
}
