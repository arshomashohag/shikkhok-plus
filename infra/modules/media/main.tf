# The public hub's photos: one private bucket, and one role that may touch
# nothing else.
#
# The flow, with the prefix each step uses:
#
#   owner's browser --presigned POST--> quarantine/{media_id}     (1 day)
#   sanitiser Lambda (Task 3, lambda.tf) --> staged/{media_id}/   (30 days)
#   API on complete --pinned copy--> archive/{media_id}/  (frozen, never expire)
#   API on approval --copy archive/--> public/{public_key}/
#   site distribution /m/{public_key}/{w}.webp --OAC--> public/  (never expire)
#
# **The bytes never touch the API.** The browser posts straight to the
# bucket with a form the API signed (10 minutes, 1 B to 8 MB, the exact key
# quarantine/{id} and Content-Type). Nothing a person uploads is ever served:
# the Lambda re-encodes it into staged/, an administrator approves the
# re-encoded variants, and only their copies in public/ are readable by
# CloudFront.
#
# **How the API reaches S3 without the instance role** [H3 deviation 1].
# The container still cannot reach IMDS (hop limit 1, modules/app). The
# host's cron job assumes the role below every 15 minutes and writes its
# one-hour credentials into a file mounted read-only into the container.
# A compromised container therefore holds, for at most an hour, the right
# to read and write photos in four prefixes of one bucket -- not the
# instance role, not any other bucket, not any other prefix.
#
# **Cost**: priced as `media` in ../../main.tf's cost model.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  # Built rather than read from bucket_regional_domain_name: the provider
  # has returned the legacy global name (<bucket>.s3.amazonaws.com) for
  # us-east-1 buckets, which names no region and is not the endpoint the
  # SDK signs for. This is the one host the web and admin pages' CSP admit,
  # so it is spelled out once, here, in the regional form.
  regional_domain = "${aws_s3_bucket.media.id}.s3.${data.aws_region.current.name}.amazonaws.com"
}

# ---------------------------------------------------------------------
# The bucket
# ---------------------------------------------------------------------

# In the app's runtime region [R5], beside the Lambda that reads it and the
# host that signs for it. Account-suffixed, as the config, web, site and
# admin buckets are: S3 names are global, and the infrastructure role may
# create only `shikkhokplus-<env>-media-*` (infra/bootstrap/main.tf).
resource "aws_s3_bucket" "media" {
  bucket = "${var.name_prefix}-media-${data.aws_caller_identity.current.account_id}"

  tags = { Role = "hub-media" }
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket = aws_s3_bucket.media.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ACLs off: every object belongs to the bucket owner whoever wrote it, so
# no upload can carry an ACL that grants anything.
resource "aws_s3_bucket_ownership_controls" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# SSE-S3, as the site bucket: OAC reads it with no key policy. Children's
# data at rest is encrypted [RC-8]; a photo of a classroom is treated as
# such whatever it shows.
resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# **No versioning, deliberately.** A withdrawn, rejected or held photo is
# deleted, and with versioning on its bytes would survive as a noncurrent
# version that nothing in the application knows to remove.

# Unsubmitted uploads expire after a day and unreviewed variants after
# thirty, so an abandoned upload leaves nothing behind. The two published
# prefixes have no rule: approved copies live until the application deletes
# them (withdrawal, takedown, account deletion).
resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    id     = "expire-quarantine"
    status = "Enabled"

    filter {
      prefix = "quarantine/"
    }

    expiration {
      days = 1
    }
  }

  rule {
    id     = "expire-staged"
    status = "Enabled"

    filter {
      prefix = "staged/"
    }

    expiration {
      days = 30
    }
  }
}

# The browser's upload is the only cross-origin call: a multipart form POST
# from the web app, whose Content-Type is CORS-safelisted, so no request
# header needs allowing and none is. Every other origin, and every other
# method, gets no CORS answer at all. The presigned GETs the editor and the
# admin preview use are <img> loads, which need no CORS.
resource "aws_s3_bucket_cors_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  cors_rule {
    allowed_methods = ["POST"]
    allowed_origins = [var.web_app_origin]
    max_age_seconds = 600
  }
}

resource "aws_s3_bucket_policy" "media" {
  bucket = aws_s3_bucket.media.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Approved photos only, only the site distribution. No ListBucket,
        # so a missing key answers 403 rather than 404.
        Sid       = "CloudFrontReadsPublicPhotos"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = ["s3:GetObject"]
        Resource  = ["${aws_s3_bucket.media.arn}/public/*"]
        Condition = {
          StringEquals = { "AWS:SourceArn" = var.site_distribution_arn }
        }
      },
      {
        # TLS only [OPS-4], as every bucket here.
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.media.arn, "${aws_s3_bucket.media.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.media]
}

# ---------------------------------------------------------------------
# The media role
# ---------------------------------------------------------------------

# What the API container's credentials can do, and all of it. Under this
# environment's workload boundary, which caps it at this bucket's objects.
resource "aws_iam_role" "media" {
  name = "${var.name_prefix}-media"
  path = "/shikkhokplus/"

  permissions_boundary = var.permissions_boundary_arn

  # Assumed from the instance role's own session, which is role chaining:
  # AWS caps a chained session at one hour whatever this says, and the
  # host asks for exactly that.
  max_session_duration = 3600

  # Trusted by exactly one principal: the primary app host's instance role.
  # Not the rehearsal host, not the account root.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = ["sts:AssumeRole"]
      Principal = { AWS = var.instance_role_arn }
    }]
  })
}

resource "aws_iam_role_policy" "media" {
  name = "media-bucket"
  role = aws_iam_role.media.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Never called directly: the API signs a POST policy with it, and
        # the policy is only as wide as the signer.
        Sid      = "SignUploads"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.media.arn}/quarantine/*"]
      },
      {
        # The Lambda's result.json and the variants, for completion and for
        # the presigned previews; archive/ for a restore.
        Sid    = "ReadResults"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "${aws_s3_bucket.media.arn}/staged/*",
          "${aws_s3_bucket.media.arn}/archive/*",
        ]
      },
      {
        # Completion freezes the variants it read: staged/ -> archive/
        # [I1]. A copy is a GetObject on the source (granted above) and a
        # PutObject on the destination -- and only a copy from staged/: a
        # PutObject carrying no such x-amz-copy-source is refused. AWS
        # documents the condition value as "bucket/key", which botocore
        # sends; the "/bucket/key" spelling the header also allows is
        # admitted too.
        Sid      = "FreezeToArchive"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.media.arn}/archive/*"]
        Condition = {
          StringLike = {
            "s3:x-amz-copy-source" = [
              "${aws_s3_bucket.media.bucket}/staged/*",
              "/${aws_s3_bucket.media.bucket}/staged/*",
            ]
          }
        }
      },
      {
        # Approval and a restore publish the frozen variants: archive/ ->
        # public/, the only prefix CloudFront serves. Only a copy, and only
        # from archive/: a compromised container can neither put its own
        # bytes there nor copy unfrozen staged/ bytes there.
        Sid      = "PublishFromArchive"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.media.arn}/public/*"]
        Condition = {
          StringLike = {
            "s3:x-amz-copy-source" = [
              "${aws_s3_bucket.media.bucket}/archive/*",
              "/${aws_s3_bucket.media.bucket}/archive/*",
            ]
          }
        }
      },
      {
        # Withdrawal, rejection, takedown and account deletion.
        Sid    = "DeleteObjects"
        Effect = "Allow"
        Action = ["s3:DeleteObject"]
        Resource = [
          "${aws_s3_bucket.media.arn}/quarantine/*",
          "${aws_s3_bucket.media.arn}/staged/*",
          "${aws_s3_bucket.media.arn}/public/*",
          "${aws_s3_bucket.media.arn}/archive/*",
        ]
      },
      {
        # Deleting a prefix lists it first. A listing with no prefix, or
        # any other, is refused.
        Sid      = "ListOwnPrefixes"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = ["${aws_s3_bucket.media.arn}"]
        Condition = {
          StringLike = {
            "s3:prefix" = ["quarantine/*", "staged/*", "public/*", "archive/*"]
          }
        }
      },
    ]
  })
}
