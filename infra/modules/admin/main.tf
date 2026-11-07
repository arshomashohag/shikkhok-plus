# The platform admin surface: its own hostname, its own distribution, and
# reachable only from an IP allowlist.
#
# **Why a hostname of its own.** The admin API (/v1/admin/*) used to be one
# more path on the public API host, protected only by who was signed in. An
# admin account is the one whose stolen session sees every teacher on the
# platform, so it gets a second, independent requirement that a stolen
# token cannot carry: the request must come from an allowlisted network.
# CloudFront is the only place that requirement can be expressed for free
# -- WAF would cost USD 5/month plus rules, against a USD 50 ceiling
# [OC-4] -- and a CloudFront Function can only gate a distribution's
# behaviours, so the admin surface needs a distribution of its own. The
# public API distribution answers /v1/admin* with 404 (modules/cdn).
#
# The request flow, for a viewer on an allowlisted IPv4 address:
#
#   admin.<zone>/            -> admin-gate (IP check, SPA rewrite) -> bucket
#   admin.<zone>/v1/admin/*  -> admin-gate (IP check) -> origin.<zone>,
#                               with X-Origin-Secret (nginx) and
#                               X-Admin-Edge (the application) added
#
# and for anyone else, a 403 from the edge on every path.
#
# **Three locks on the admin API, each independent of the others:**
#
#   1. the allowlist here, on CloudFront's own view of the viewer address;
#   2. X-Admin-Edge, a secret only this distribution sends, which the
#      application requires on every admin route -- so the API host, or
#      the origin reached any other way, cannot serve one;
#   3. the application's own allowlist check on X-Client-Address, which
#      nginx always overwrites with CloudFront-Viewer-Address -- so a
#      request that somehow carried the edge secret from elsewhere is still
#      refused off the list. (SHIKKHOKPLUS_ADMIN_ALLOWED_CIDRS, the same
#      list, written into the runtime env by deploy.yml.)
#
# Then the admin's own sign-in and second factor, which none of the above
# replaces.
#
# **Cost: nothing measurable**, as for the public site: one more
# distribution, certificate and CloudFront Function inside their free
# tiers, a bucket holding a few hundred kilobytes, and SSM Standard
# parameters, which are free. The cost model in ../../main.tf says so with
# its own 0.00 line.

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.70"
      configuration_aliases = [aws.us_east_1]
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  admin_fqdn       = "${var.admin_subdomain}.${var.domain_name}"
  bucket_origin_id = "shikkhokplus-admin-ui"
  api_origin_id    = "shikkhokplus-origin"
}

# ---------------------------------------------------------------------
# The edge secret
# ---------------------------------------------------------------------

# **What proves a request came through THIS distribution.** X-Origin-Secret
# cannot: the API distribution sends the same value, so nginx cannot tell
# the two apart. This one is sent only on the admin distribution's
# /v1/admin/* behaviour, and the application refuses an admin route
# without it -- which is what makes the API host's 404 one lock of two
# rather than the only one.
#
# Alphanumeric, like the origin secret, so it survives every hop
# (CloudFront header, SSM, runtime env file) without quoting.
resource "random_password" "edge_secret" {
  length  = 48
  special = false
}

# Published where deploy.yml reads it into the runtime env
# (SHIKKHOKPLUS_ADMIN_EDGE_SECRET), on exactly the origin secret's terms
# (modules/app/secrets.tf): a SecureString under the account's default
# aws/ssm key, decrypted only through SSM. The deploy role may read this
# one parameter and no other secret of Terraform's.
resource "aws_ssm_parameter" "edge_secret" {
  name        = "/shikkhokplus/${var.name_prefix}/admin-edge-secret"
  type        = "SecureString"
  value       = random_password.edge_secret.result
  description = "X-Admin-Edge value the admin distribution sends and the API requires on /v1/admin/*."
}

# ---------------------------------------------------------------------
# The bucket: the built admin UI
# ---------------------------------------------------------------------

resource "aws_s3_bucket" "admin" {
  # Account-suffixed, as the web and site buckets are: S3 names are
  # global, and the infrastructure role may create only
  # `shikkhokplus-*-admin-*` (infra/bootstrap/main.tf).
  bucket = "${var.name_prefix}-admin-${data.aws_caller_identity.current.account_id}"

  tags = { Role = "admin-ui" }
}

resource "aws_s3_bucket_public_access_block" "admin" {
  bucket = aws_s3_bucket.admin.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-S3 rather than KMS: OAC reads SSE-S3 objects with no key policy, and
# the bucket holds a built UI bundle -- no data, no secret. Everything the
# admin sees comes from the API, behind the same allowlist.
resource "aws_s3_bucket_server_side_encryption_configuration" "admin" {
  bucket = aws_s3_bucket.admin.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "admin" {
  name                              = "${var.name_prefix}-admin"
  description                       = "CloudFront reads the admin UI bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_s3_bucket_policy" "admin" {
  bucket = aws_s3_bucket.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read only, only this distribution -- so the bucket cannot be
        # read around the allowlist, by URL or by another distribution.
        # No s3:ListBucket: a missing key answers 403, which the SPA
        # rewrite keeps off every client route.
        Sid       = "CloudFrontReadsTheAdminUi"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.admin.arn}/*"
        Condition = {
          StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.admin.arn }
        }
      },
      {
        # TLS only [OPS-4], as every bucket here.
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.admin.arn, "${aws_s3_bucket.admin.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.admin]
}

# ---------------------------------------------------------------------
# The certificate, us-east-1
# ---------------------------------------------------------------------

# Its own certificate, not a SAN on the API's: a distribution takes exactly
# one, and adding a name to the API's would replace the certificate the
# API is served with.
resource "aws_acm_certificate" "admin" {
  provider = aws.us_east_1

  domain_name       = local.admin_fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "admin_validation" {
  for_each = {
    for option in aws_acm_certificate.admin.domain_validation_options :
    option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  }

  zone_id = var.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
  # Validation CNAMEs only, under random `_<hash>.` labels -- the one
  # place allow_overwrite is safe, as in modules/cdn and modules/site.
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "admin" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.admin.arn
  validation_record_fqdns = [for r in aws_route53_record.admin_validation : r.fqdn]
}

# ---------------------------------------------------------------------
# Edge behaviour
# ---------------------------------------------------------------------

# The allowlist, the X-Admin-Edge scrub and the SPA fallback, in one
# function because a behaviour takes one viewer-request function. See the
# source; tested from functions/admin-gate.test.mjs.
#
# **The CIDRs are rendered into the code**, so changing the allowlist is a
# Terraform apply that republishes the function -- seconds, not a deploy
# of the application. jsonencode() of a validated list of IPv4 CIDR
# strings, so nothing a variable holds can become code.
resource "aws_cloudfront_function" "admin_gate" {
  name    = "${var.name_prefix}-admin-gate"
  runtime = "cloudfront-js-2.0"
  comment = "Admin host: IPv4 allowlist, X-Admin-Edge scrub, SPA fallback"
  publish = true
  code = templatefile("${path.module}/functions/admin-gate.js.tftpl", {
    allowed_cidrs_json = jsonencode(var.admin_allowed_cidrs)
  })
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewerExceptHostHeader"
}

# Both behaviours. The UI is a bundle with no third-party anything, but its
# CSP is a meta tag the web build owns (as the web client's is); this
# header adds only the directives a meta tag cannot carry or that must hold
# whatever the bundle says: no framing, no plugins, no <base> hijack.
resource "aws_cloudfront_response_headers_policy" "admin" {
  name    = "${var.name_prefix}-admin-security"
  comment = "Admin host security headers"

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
    # An admin URL names screens like /teachers/<id>; nothing about it
    # should travel to wherever a link leads.
    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }
    content_security_policy {
      content_security_policy = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
      override                = true
    }
  }

  custom_headers_config {
    # The 403 a crawler gets says nothing, but a crawler on an allowlisted
    # network -- a link preview from a work chat -- would otherwise be free
    # to index what it saw.
    items {
      header   = "X-Robots-Tag"
      value    = "noindex, nofollow"
      override = true
    }
  }
}

# ---------------------------------------------------------------------
# The distribution
# ---------------------------------------------------------------------

resource "aws_cloudfront_distribution" "admin" {
  enabled             = true
  comment             = "${var.name_prefix} platform admin"
  aliases             = [local.admin_fqdn]
  default_root_object = "index.html"
  http_version        = "http2and3"

  # **IPv4 only, and that is the allowlist's precondition.** With IPv6 off
  # here and no AAAA record below, every viewer reaches this distribution
  # over IPv4, so CloudFront's view of the viewer address is always a
  # dotted quad and admin_allowed_cidrs only has to hold IPv4 CIDRs. An
  # admin on a dual-stack network then connects over its IPv4 address --
  # the one an operator can actually find out and pin -- rather than over
  # a privacy-extension IPv6 address that changes daily.
  is_ipv6_enabled = false

  # PriceClass_All is a latency decision, as for the API and the site: the
  # cheaper classes leave out the Asian edges. Free-tier traffic either way.
  price_class = "PriceClass_All"

  origin {
    domain_name              = aws_s3_bucket.admin.bucket_regional_domain_name
    origin_id                = local.bucket_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.admin.id
  }

  # **The API origin, exactly as the API distribution reaches it**
  # (modules/cdn): the origin's name, https-only against its real Let's
  # Encrypt certificate, TLS 1.2.
  origin {
    domain_name = var.origin_fqdn
    origin_id   = local.api_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    # nginx refuses anything without it (modules/app/user_data.sh.tftpl).
    custom_header {
      name  = "X-Origin-Secret"
      value = var.origin_secret
    }

    # The application refuses an admin route without it. A custom origin
    # header REPLACES a viewer-sent header of the same name, so a viewer
    # cannot supply or override it; the function also deletes any viewer
    # copy before the request goes on.
    custom_header {
      name  = "X-Admin-Edge"
      value = random_password.edge_secret.result
    }
  }

  # **The admin API.** Caches nothing: every admin response is
  # authenticated and specific to the person asking. Forwards every viewer
  # header, cookie and query string except Host -- the same policy as the
  # API distribution, which is what delivers CloudFront-Viewer-Address to
  # nginx, from which it sets X-Client-Address for the application's own
  # allowlist check and rate limits.
  ordered_cache_behavior {
    path_pattern           = "/v1/admin/*"
    target_origin_id       = local.api_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    cache_policy_id            = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.all_viewer.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.admin.id
    compress                   = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.admin_gate.arn
    }
  }

  # **The admin UI.** Same files for everyone, so cached: nothing in the
  # key, hashed assets uploaded immutable and index.html no-cache, and the
  # deploy invalidates /* so a release is visible at once. Caching cannot
  # leak past the allowlist: the function runs at viewer-request, before
  # the cache is consulted.
  default_cache_behavior {
    target_origin_id       = local.bucket_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]

    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.admin.id
    compress                   = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.admin_gate.arn
    }
  }

  # **No custom_error_response**, deliberately. Error mappings apply to the
  # whole distribution, so mapping S3's 403 to index.html would also
  # rewrite the API's own 403s into a page; the function's rewrite handles
  # client routes instead.

  restrictions {
    geo_restriction {
      # The IP allowlist is the restriction. A country list would be a
      # strictly weaker copy of it.
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.admin.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Role = "admin"
  }
}

# ---------------------------------------------------------------------
# DNS: A only
# ---------------------------------------------------------------------

# **An A record and no AAAA**, matching is_ipv6_enabled = false above: a
# client never learns an IPv6 address for this name, so it never tries one.
# No allow_overwrite: if anything already held this name the apply must
# fail rather than quietly take it.
resource "aws_route53_record" "admin" {
  zone_id = var.zone_id
  name    = local.admin_fqdn
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.admin.domain_name
    zone_id                = aws_cloudfront_distribution.admin.hosted_zone_id
    evaluate_target_health = false
  }
}
