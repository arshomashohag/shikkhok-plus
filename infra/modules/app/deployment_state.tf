# **What the instance needs to know at boot, that Terraform does not
# own.**
#
# The image tag is the deploy workflow's business, not Terraform's: an
# apply must never change which version runs, and a deploy must never
# require an apply. But a REPLACED instance has to learn the tag from
# somewhere, or it boots with Docker installed and no application --
# which is exactly the empty-box failure the ASG exists to avoid.
#
# SSM Parameter Store is the handoff. Terraform creates the parameter
# and then ignores its value forever; the deploy workflow writes it;
# user_data reads it. Standard parameters are free.

resource "aws_ssm_parameter" "image_tag" {
  name = "/shikkhokplus/${var.name_prefix}/image-tag"
  type = "String"

  # A placeholder, not a real tag. The instance treats this exact
  # value as "nothing has been deployed yet" and comes up serving
  # nginx only, rather than failing its boot script on a pull that
  # cannot succeed.
  value = "none"

  description = "Image tag the app host runs. Written by deploy-staging, read at boot."

  lifecycle {
    # **The whole point.** Without this, every apply would reset the
    # tag to "none" and the next instance replacement would silently
    # un-deploy the application.
    ignore_changes = [value]
  }
}

# **The runtime environment, as one SecureString.**
#
# `.env` is written by the deploy and lives on the instance's root
# volume, which a REPLACED instance does not have. Without this a
# self-healing boot knows which image to run and cannot start it: no
# database password, no JWT key, no SMS credentials.
#
# One parameter rather than one per variable, because the file is
# written and read atomically and a half-updated environment is worse
# than a stale one. SecureString so it is KMS-encrypted at rest with
# the account's default key -- team.md names SSM over Secrets Manager
# precisely because it is free and rotation we have not wired up is a
# control that does not earn its place.
resource "aws_ssm_parameter" "runtime_env" {
  name  = "/shikkhokplus/${var.name_prefix}/runtime-env"
  type  = "SecureString"
  value = "SHIKKHOKPLUS_ENVIRONMENT=unset"

  description = "The .env the app host runs with. Written by deploy-staging."

  lifecycle {
    # Same reasoning as the image tag: Terraform creates it and never
    # touches the value again. An apply that reset this would strip
    # the running host's credentials.
    ignore_changes = [value]
  }
}

# **A config bucket of its own, in the app's region.**
#
# The compose file used to be inlined with `file()`, which worked
# until the script plus the compose file crossed EC2's hard 16KB
# user_data limit.
#
# The first fix reused the Terraform state bucket -- and failed, with
# `AuthorizationHeaderMalformed: the region 'us-east-1' is wrong;
# expecting 'ap-south-1'`. That bucket was created by bootstrap,
# whose region default is still Mumbai, and S3 requires a request
# signed for the bucket's own region. Terraform's S3 BACKEND
# discovers that automatically; `aws_s3_object` goes through the
# provider, which does not.
#
# A dedicated bucket removes the coupling rather than relocating it:
# the app's config lives in the app's region, created and destroyed
# with everything else this module owns, and no longer depends on
# where bootstrap happened to run.
resource "aws_s3_bucket" "config" {
  bucket = "${var.name_prefix}-config-${var.account_id}"

  # Account-suffixed because S3 names are globally unique across
  # every AWS account, and an unsuffixed name is very likely taken.
  tags = { Role = "host-config" }
}

resource "aws_s3_bucket_public_access_block" "config" {
  bucket = aws_s3_bucket.config.id

  # All four. The compose file names no secret -- those are in the
  # SecureString -- but a publicly listable bucket advertises the
  # shape of the deployment for nothing.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config" {
  bucket = aws_s3_bucket.config.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "compose" {
  bucket = aws_s3_bucket.config.id
  key    = "docker-compose.yml"
  source = "${path.root}/../deploy/docker-compose.staging.yml"

  # Without this the object is replaced only when the KEY changes, so
  # editing the compose file would upload nothing and a replaced
  # instance would fetch the previous one.
  etag = filemd5("${path.root}/../deploy/docker-compose.staging.yml")

  content_type = "text/yaml"
}
