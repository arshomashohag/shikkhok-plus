# The web client (web/): a private bucket, served by THIS distribution
# under /ui/.
#
# **Same distribution, same hostname as the API, on purpose.** The PWA
# calls /v1 on the origin it was loaded from, so it needs no CORS, the
# API keeps SHIKKHOKPLUS_WEB_ORIGINS unset, and the bearer token never
# travels to a second origin. A separate distribution would have bought
# none of that and cost a second certificate and a CORS allowlist.
#
# **The bucket is private and reachable only through CloudFront**:
# Origin Access Control signs every origin request, and the bucket
# policy admits the CloudFront service only when the request comes from
# this distribution. No static-website hosting, no public read.
#
# **Nothing here is cached that was not cacheable already.** The
# default behaviour (the API) keeps CachingDisabled; only the /ui paths,
# which serve the same files to everyone and no data, use the managed
# CachingOptimized policy. The deploy uploads hashed assets as
# immutable and index.html, sw.js and the manifest as no-cache, then
# invalidates /ui/*.
#
# Files are written by the deploy workflow (aws s3 sync), not by
# Terraform: the build is an artifact of a commit, like the image tag.

data "aws_caller_identity" "current" {}

locals {
  # The prefix the deploy uploads under, matching the path CloudFront
  # serves: /ui/index.html is the object ui/index.html.
  web_prefix = "ui"

  # Empty ui_subdomain means no separate hostname: the UI is still at
  # https://<api host>/ui/.
  ui_fqdn = var.ui_subdomain == "" ? "" : "${var.ui_subdomain}.${var.domain_name}"
}

resource "aws_s3_bucket" "web" {
  # Account-suffixed, as the config bucket is: S3 names are global.
  bucket = "${var.name_prefix}-web-${data.aws_caller_identity.current.account_id}"

  tags = { Role = "web-client" }
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket = aws_s3_bucket.web.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-S3 rather than KMS: OAC reads SSE-S3 objects with no key policy,
# and the bucket holds the public app bundle, nothing secret.
resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.name_prefix}-web"
  description                       = "CloudFront reads the web client bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read only, only the UI prefix, only this distribution.
        Sid       = "CloudFrontReadsTheWebClient"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.web.arn}/${local.web_prefix}/*"
        Condition = {
          StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.api.arn }
        }
      },
      {
        # TLS only [OPS-4], as every bucket here.
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.web.arn, "${aws_s3_bucket.web.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.web]
}

# SPA fallback and the /ui -> /ui/ redirect. See the source.
resource "aws_cloudfront_function" "ui_router" {
  name    = "${var.name_prefix}-ui-router"
  runtime = "cloudfront-js-2.0"
  comment = "Web client: client-side routes to index.html"
  publish = true
  code    = file("${path.module}/functions/ui-router.js")
}

# Only when the UI has a hostname of its own. See the source.
resource "aws_cloudfront_function" "ui_host_root" {
  count = local.ui_fqdn == "" ? 0 : 1

  name    = "${var.name_prefix}-ui-host-root"
  runtime = "cloudfront-js-2.0"
  comment = "UI hostname root redirects to /ui/; API untouched"
  publish = true
  code    = templatefile("${path.module}/functions/ui-host-root.js.tftpl", { ui_fqdn = local.ui_fqdn })
}

# Security headers on the web client's responses only.
#
# The page carries its own Content-Security-Policy in a <meta> tag,
# generated from the API origin at build time. A meta CSP cannot set
# frame-ancestors, so this header adds the directives only a header can
# carry. Browsers enforce both policies, so the header can only tighten
# what the meta allows, never loosen it.
resource "aws_cloudfront_response_headers_policy" "web" {
  name    = "${var.name_prefix}-web-security"
  comment = "Web client security headers"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = false
      preload                    = false
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }
    content_security_policy {
      content_security_policy = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
      override                = true
    }
  }
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}
