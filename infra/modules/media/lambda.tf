# The image sanitiser: the one place an uploaded photo's bytes are decoded.
#
# S3 invokes it for every object created under quarantine/. It reads the
# upload, checks its signature is the type its presigned POST declared,
# decodes it under a 40-megapixel cap, and writes WebP variants and a
# result.json to staged/{media_id}/ -- or a result.json saying
# "unreadable" -- then deletes the upload (lambdas/image_sanitiser). Only
# decoded pixels are written, never an original byte [R6].
#
# **Untrusted image decoding never runs on the API host.** A decoder fed
# hostile bytes is the classic way in; here it runs in a function that can
# read and delete quarantine/, write staged/ and write its own logs, and
# nothing else: no VPC, so no route to the database; no other prefix, so
# nothing published; no secret in its environment, because it has none.
#
# **Two writers for the code, as for the seeder** (modules/seeder).
# Terraform creates the function from a committed placeholder that refuses
# every event (placeholder/), and deploy.yml uploads the real package after
# the infrastructure job and before the release, waiting until Lambda
# reports the update Successful. Terraform ignores the code from then on,
# so an apply never rolls the sanitiser back to the placeholder.
#
# The placeholder is a committed zip rather than an archive_file because
# the plan and the apply run on different runners: a zip archive_file
# writes during the plan is not on the runner that applies the saved plan,
# and the create fails there. tests/gates/test_image_sanitiser.py asserts
# the zip holds exactly placeholder/handler.py. To rebuild it after editing
# that file:  cd placeholder && rm image-sanitiser.zip && zip -X image-sanitiser.zip handler.py
#
# **Cost**: priced as `image_lambda` in ../../main.tf's cost model.

locals {
  # deploy.yml and the deploy role (infra/bootstrap/deploy_role.tf) name
  # the function the same way; tests/gates/test_image_sanitiser.py holds
  # the three together.
  sanitiser_name = "${var.name_prefix}-image-sanitiser"
}

# Under /shikkhokplus/, not /aws/lambda/: the workload boundary and the
# infrastructure role's grants are both scoped to this project's groups.
resource "aws_cloudwatch_log_group" "sanitiser" {
  name              = "/shikkhokplus/${var.name_prefix}/image-sanitiser"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "sanitiser" {
  name = local.sanitiser_name
  # Under /shikkhokplus/ and carrying the workload boundary, as every role
  # the infrastructure role creates must [OPS-2].
  path                 = "/shikkhokplus/"
  permissions_boundary = var.permissions_boundary_arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
      # Only this account's Lambda service may assume it -- the
      # confused-deputy guard.
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

# Exactly what the handler does, and nothing more: read and delete the
# upload, write the variants and the result, write its own log lines.
resource "aws_iam_role_policy" "sanitiser" {
  name = "image-sanitiser"
  role = aws_iam_role.sanitiser.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadAndRemoveUploads"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.media.arn}/quarantine/*"]
      },
      {
        Sid      = "WriteVariants"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.media.arn}/staged/*"]
      },
      {
        Sid      = "OwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.sanitiser.arn}:*"]
      },
    ]
  })
}

resource "aws_lambda_function" "sanitiser" {
  function_name = local.sanitiser_name
  description   = "Decodes hub photo uploads and re-encodes them as WebP variants."
  role          = aws_iam_role.sanitiser.arn

  # The package is handler.py at the zip's root with Pillow beside it,
  # built for this platform by `make lambda-image`.
  runtime       = "python3.12"
  handler       = "handler.handler"
  architectures = ["arm64"]
  filename      = "${path.module}/placeholder/image-sanitiser.zip"

  # A 40-megapixel RGBA decode is 160 MB before the resize copies; 1 GB
  # holds it with room, and Lambda's CPU share grows with memory. The
  # handler bounds the rest of the work: a JPEG is decoded at the smallest
  # scale the 1600 variant allows, and each smaller variant is resized
  # from the next larger rather than from the full decode.
  memory_size = 1024
  timeout     = 30

  # **No reserved concurrency**, by decision on 2026-11-21. Reserving any
  # needs the account's concurrency quota to exceed 10 by the reservation,
  # because AWS keeps 10 unreserved; this account's quota is below 12, so
  # the earlier reservation of 2 failed the apply with
  # InvalidParameterValueException. What that reservation did, nothing
  # else does: the sanitiser now shares the account pool, so a burst of
  # uploads runs as many decoders at once as the account allows rather
  # than queueing behind two. Per-decode cost is still bounded -- the
  # memory and timeout above, and the handler's 40-megapixel decode limit
  # -- and uploads are bounded upstream by the per-owner photo quota and
  # its daily ceiling (app/hub/media/quota.py).

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.sanitiser.name
  }

  lifecycle {
    # deploy.yml owns the code after the first apply; see the header.
    ignore_changes = [filename, source_code_hash]
  }

  depends_on = [
    aws_iam_role_policy.sanitiser,
    aws_cloudwatch_log_group.sanitiser,
  ]
}

# **One attempt per upload, and no event older than five minutes** [R7b].
# Lambda retries a failed asynchronous invocation twice by default, so an
# upload built to time out or exhaust memory would hold one of the two
# slots three times over (about 90 seconds) and delay every honest upload
# behind it. A failure is logged and not retried: the upload keeps no
# result.json, and the API's `complete` settles a photo with no result
# after 20 minutes as unreadable [R7c]. A throttled event older than five
# minutes is dropped on the same terms.
resource "aws_lambda_function_event_invoke_config" "sanitiser" {
  function_name                = aws_lambda_function.sanitiser.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 300
}

# S3 may invoke the function, for this bucket in this account only.
resource "aws_lambda_permission" "s3_invokes_sanitiser" {
  statement_id   = "S3InvokesForQuarantine"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.sanitiser.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.media.arn
  source_account = data.aws_caller_identity.current.account_id
}

# Every object created under quarantine/, and nothing else: the sanitiser's
# own writes go to staged/ and never re-trigger it.
resource "aws_s3_bucket_notification" "quarantine" {
  bucket = aws_s3_bucket.media.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.sanitiser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "quarantine/"
  }

  # S3 checks it may invoke the function when the notification is saved.
  depends_on = [aws_lambda_permission.s3_invokes_sanitiser]
}
