# The public site (site/): a private bucket behind its OWN distribution,
# at the zone apex and www.
#
# **Its own distribution, not a third set of behaviours on the API's.**
# The web client shares the API's distribution because it calls /v1 on the
# origin it was loaded from (cdn/web.tf). The site calls nothing: it is
# static HTML with no script, so sharing would buy no same-origin benefit
# and would cost a lot of caution. The API's default behaviour caches
# nothing on purpose, and every cached path added to that distribution is
# one more pattern that must never match an API route. Here the DEFAULT
# behaviour can cache for a year, because nothing behind it is dynamic.
#
# **The one exception is /hub/*: the public hub pages, served by the API.**
# The default behaviour (the bucket) still has no API behind it. The
# /hub/* behaviour reaches only the credential-less, GET-only `/hub/*`
# slice of the API, which receives no cookies and only the viewer-address
# header (plus the origin secret the host requires of every request). It
# is a separate, ordered behaviour with its own short-lived cache policy,
# so the year-long policy below never applies to it, and the API
# distribution answers /hub* 404 (cdn/functions/hub-block.js) so the pages
# have exactly one public front door.
#
# **And /m/*: approved hub photos, from the media bucket** (modules/media).
# A third origin, read through its own Origin Access Control, where the
# media bucket's policy lets this distribution read public/* and nothing
# else. GET and HEAD only, cached a year by the managed CachingOptimized
# policy -- a photo's URL carries a fresh 128-bit key per approval, so a
# changed photo is a new URL and a takedown deletes the object and
# invalidates the old one. Its own response headers (below) make each
# response inert whatever bytes it holds.
#
# **Cached at the edge for a year, and a release is still visible at once.**
# The cache policy below honours whatever Cache-Control the object carries
# (min 0, max a year). deploy.yml uploads:
#
#   * hashed assets/*        public, max-age=31536000, immutable
#   * HTML, sitemap, robots  public, max-age=300, s-maxage=31536000
#
# so the edge keeps every object for a year, browsers keep assets for a
# year (a changed asset is a new URL, site/build.mjs) and revalidate pages
# after five minutes, and the deploy invalidates /* so the edges drop the
# old pages the moment a release lands. Origin fetches -- the only thing
# that costs money or latency from Bangladesh to us-east-1 -- happen once
# per object per edge per release.
#
# Files are written by deploy.yml, not by Terraform: the build is an
# artifact of a commit, as the web client's is.
#
# **Cost: nothing measurable.** CloudFront, ACM and CloudFront Functions
# sit inside their permanent free tiers at this traffic, and the bucket
# holds well under a megabyte. The cost model in ../../main.tf says so with
# its own 0.00 line rather than leaving the absence unexplained.

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.70"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  # The zone apex is the site: shikkhokplus.<apex> in staging,
  # shikkhokplus-prod.<apex> in production. Nothing else holds the apex
  # of the project zone -- the API, the UI and the origin are all
  # sub-names (api., app., origin.).
  site_fqdn = var.domain_name
  www_fqdn  = "www.${var.domain_name}"
  origin_id = "shikkhokplus-site"
  # The hub origin is the API host's own name, the FQDN the API
  # distribution uses: nginx requires the origin secret on every request,
  # so this second door must present it too.
  hub_origin_id     = "shikkhokplus-hub-api"
  hub_query_strings = ["q", "district", "upazila", "subject", "level", "page"]
  # The hub's photo bucket (modules/media), read through OAC at /m/*.
  media_origin_id = "shikkhokplus-media"
}

# ---------------------------------------------------------------------
# The bucket
# ---------------------------------------------------------------------

resource "aws_s3_bucket" "site" {
  # Account-suffixed, as the config and web buckets are: S3 names are
  # global, and the infrastructure role may create only
  # `shikkhokplus-*-site-*` (infra/bootstrap/main.tf).
  bucket = "${var.name_prefix}-site-${data.aws_caller_identity.current.account_id}"

  tags = { Role = "public-site" }
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-S3 rather than KMS: OAC reads SSE-S3 objects with no key policy, and
# the bucket holds a public marketing site, nothing secret.
resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.name_prefix}-site"
  description                       = "CloudFront reads the public site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read only, only this distribution. No s3:ListBucket, so a
        # missing key answers 403 rather than 404 -- which is why the
        # distribution maps BOTH to the 404 page.
        Sid       = "CloudFrontReadsTheSite"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.site.arn}/*"
        Condition = {
          StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.site.arn }
        }
      },
      {
        # TLS only [OPS-4], as every bucket here.
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.site]
}

# ---------------------------------------------------------------------
# The certificate: apex and www, us-east-1
# ---------------------------------------------------------------------

# **Its own certificate, not a SAN on the API's.** A distribution takes
# exactly one certificate, and the site has its own distribution. Keeping
# the two apart also means a change to the site's names can never replace
# the certificate the API is served with.
resource "aws_acm_certificate" "site" {
  provider = aws.us_east_1

  domain_name               = local.site_fqdn
  subject_alternative_names = [local.www_fqdn]
  validation_method         = "DNS"

  lifecycle {
    # The new certificate is issued and attached before the old one goes.
    create_before_destroy = true
  }
}

resource "aws_route53_record" "site_validation" {
  for_each = {
    for option in aws_acm_certificate.site.domain_validation_options :
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
  # place allow_overwrite is safe, as in modules/cdn.
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for r in aws_route53_record.site_validation : r.fqdn]
}

# ---------------------------------------------------------------------
# Edge behaviour: routing, caching, headers
# ---------------------------------------------------------------------

# www -> apex, /faq -> /faq/, /faq/ -> /faq/index.html. See the source;
# tested from site/test/site-router.test.mjs.
resource "aws_cloudfront_function" "site_router" {
  name    = "${var.name_prefix}-site-router"
  runtime = "cloudfront-js-2.0"
  comment = "Public site: www redirect and directory indexes"
  publish = true
  code    = file("${path.module}/functions/site-router.js")
}

# **The origin's Cache-Control decides, within [0, one year].** Not the
# managed CachingOptimized policy: its max TTL is a year too, but its
# DEFAULT is a day, and its name says nothing about honouring the
# s-maxage the deploy sets. A policy written here states the contract the
# deploy relies on. default_ttl applies only to an object uploaded with no
# Cache-Control at all, which the deploy never does.
#
# Nothing varies the response, so nothing is in the key: no cookie, no
# header, no query string. A query string in the key would let anyone
# mint uncached URLs (/?x=1, /?x=2, ...) that each reach the bucket.
resource "aws_cloudfront_cache_policy" "site" {
  name        = "${var.name_prefix}-site"
  comment     = "Public site: honour origin Cache-Control, up to a year"
  min_ttl     = 0
  default_ttl = 86400
  max_ttl     = 31536000

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# /hub/* query-string allowlist and normalisation. See the source; tested
# from functions/hub-query.test.mjs.
resource "aws_cloudfront_function" "hub_query" {
  name    = "${var.name_prefix}-hub-query"
  runtime = "cloudfront-js-2.0"
  comment = "Public hub: query-string allowlist, normalisation, /hub redirect"
  publish = true
  code    = file("${path.module}/functions/hub-query.js")
}

# **The API's Cache-Control decides, within [0, one hour].** The hub pages
# set their own (owner and batch pages s-maxage=600, search s-maxage=300,
# sitemap s-maxage=3600); the one-hour ceiling is a backstop against a
# header that asks for more. default_ttl applies only to a response with
# no Cache-Control, which the hub never sends.
#
# Only the six allowed query strings are in the key, and hub-query.js has
# already refused everything else and collapsed repeats, so the key space
# is bounded. No header and no cookie is in the key: in particular
# CloudFront-Viewer-Address, which the origin policy forwards for the
# per-IP rate limit, must stay out of it or every client would get a
# private cache.
resource "aws_cloudfront_cache_policy" "hub" {
  name        = "${var.name_prefix}-site-hub"
  comment     = "Public hub: honour origin Cache-Control, up to an hour"
  min_ttl     = 0
  default_ttl = 60
  max_ttl     = 3600

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "whitelist"
      query_strings {
        items = local.hub_query_strings
      }
    }
  }
}

# What the origin receives beyond the cache key: the viewer's address (a
# CloudFront-generated header, so it must be named here to be forwarded)
# and the same query strings. No cookie, no Authorization. The origin keys
# its 120/minute per-IP rate limit on CloudFront-Viewer-Address.
resource "aws_cloudfront_origin_request_policy" "hub" {
  name    = "${var.name_prefix}-site-hub"
  comment = "Public hub: the viewer address and the allowed query strings only"

  cookies_config {
    cookie_behavior = "none"
  }
  headers_config {
    header_behavior = "whitelist"
    headers {
      items = ["CloudFront-Viewer-Address"]
    }
  }
  query_strings_config {
    query_string_behavior = "whitelist"
    query_strings {
      items = local.hub_query_strings
    }
  }
}

# **A strict policy, because the site can afford one.** No script at all
# (site/test/build.test.mjs refuses a <script> tag, an inline handler and
# an inline style), so the CSP is default-src 'none' plus exactly what
# the pages load from their own origin. Unlike the web client, which needs
# a meta CSP built from the API origin, this header is the whole policy
# for the static pages.
#
# **override = false on the CSP, so the API's wins on /hub/*.** The hub
# pages set their own CSP (they need form-action 'self' for the search
# form, which this one forbids). An origin-supplied header is kept when
# override is false; the bucket sends none, so the static pages still get
# the policy below. The other headers keep override = true.
resource "aws_cloudfront_response_headers_policy" "site" {
  name    = "${var.name_prefix}-site-security"
  comment = "Public site security headers"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      # Not includeSubDomains: sent from the zone apex, it would commit
      # every name under the project zone, present and future, to
      # HTTPS-only for a year. That is a decision for the whole zone, not
      # for this module; api. and app. carry their own HSTS already.
      include_subdomains = false
      preload            = false
      override           = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    content_security_policy {
      content_security_policy = join("; ", [
        "default-src 'none'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
        "upgrade-insecure-requests",
      ])
      override = false
    }
  }

  custom_headers_config {
    items {
      header   = "Permissions-Policy"
      value    = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()"
      override = true
    }
    items {
      header   = "Cross-Origin-Opener-Policy"
      value    = "same-origin"
      override = true
    }
  }
}

# ---------------------------------------------------------------------
# Hub photos: /m/* from the media bucket
# ---------------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "media" {
  name                              = "${var.name_prefix}-media"
  description                       = "CloudFront reads approved hub photos"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# /m/{key}/{w}.webp -> public/{key}/{w}.webp, and 404 for any other shape.
# See the source; tested from functions/media-path.test.mjs. The ONLY
# function on /m/*: the site router's redirects mean nothing to an image.
resource "aws_cloudfront_function" "media_path" {
  name    = "${var.name_prefix}-media-path"
  runtime = "cloudfront-js-2.0"
  comment = "Hub photos: /m/ to the bucket's public/ prefix, one key shape only"
  publish = true
  code    = file("${path.module}/functions/media-path.js")
}

# The managed policy, as the web client's /ui/ paths use: nothing in the
# key but the path (no cookie, header or query string), a year at most. A
# photo's URL is never reused for different bytes, so nothing here needs to
# honour an origin Cache-Control.
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

# **Every /m/* response is an inert image.** The bytes were re-encoded to
# WebP by the sanitiser and stored as image/webp, but the headers do not
# rely on it: nosniff stops a browser second-guessing the type, and a CSP
# of default-src 'none' plus sandbox means that even a document somehow
# served from here could run nothing and load nothing. Cached a
# year and immutable in browsers too, for the reason the cache policy gives.
resource "aws_cloudfront_response_headers_policy" "images" {
  name    = "${var.name_prefix}-site-images"
  comment = "Hub photos: immutable, nosniff, sandboxed"

  security_headers_config {
    content_type_options {
      override = true
    }
    content_security_policy {
      content_security_policy = "default-src 'none'; sandbox"
      override                = true
    }
  }

  # **No Content-Type here.** The type is the object's own: the sanitiser
  # writes every variant as image/webp and the approval copy keeps it, each
  # tested where it is set. Forcing it at the edge would also stamp
  # image/webp on the site's HTML 404 page whenever a missing photo falls
  # through to it, and CloudFront's support for overriding Content-Type
  # in a response headers policy could not be confirmed before an apply.
  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "public, max-age=31536000, immutable"
      override = true
    }
  }
}

# ---------------------------------------------------------------------
# The distribution
# ---------------------------------------------------------------------

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "${var.name_prefix} public site"
  aliases             = [local.site_fqdn, local.www_fqdn]
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  http_version        = "http2and3"

  # **PriceClass_All is a latency decision, not a cost one**, exactly as
  # for the API: the cheaper classes leave out the Asian edges, which would
  # serve a Bangladeshi audience from Europe. Free-tier traffic either way.
  price_class = "PriceClass_All"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = local.origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  # The media bucket, for approved hub photos only: OAC-signed, and the
  # bucket's policy admits this distribution to public/* alone.
  origin {
    domain_name              = var.media_bucket_regional_domain
    origin_id                = local.media_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id
  }

  # The API, for the public hub only. https-only, with a real certificate
  # on the origin (see the API distribution's origin for why), and the
  # secret header nginx requires of every request.
  origin {
    domain_name = var.api_origin_fqdn
    origin_id   = local.hub_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = "X-Origin-Secret"
      value = var.origin_secret
    }
  }

  # GET and HEAD only: the hub is read-only, and a write method never
  # reaches the origin from here. Ordered ahead of the bucket default; the
  # bare /hub needs its own pattern because "/hub/*" does not match it, and
  # hub-query.js redirects it to /hub/en.
  dynamic "ordered_cache_behavior" {
    for_each = ["/hub", "/hub/*"]
    content {
      path_pattern           = ordered_cache_behavior.value
      target_origin_id       = local.hub_origin_id
      viewer_protocol_policy = "redirect-to-https"

      allowed_methods = ["GET", "HEAD"]
      cached_methods  = ["GET", "HEAD"]

      cache_policy_id            = aws_cloudfront_cache_policy.hub.id
      origin_request_policy_id   = aws_cloudfront_origin_request_policy.hub.id
      response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id
      compress                   = true

      function_association {
        event_type   = "viewer-request"
        function_arn = aws_cloudfront_function.hub_query.arn
      }
    }
  }

  # Approved hub photos. GET and HEAD only; ordered ahead of the bucket
  # default, and disjoint from /hub*. Not compressed: WebP already is.
  ordered_cache_behavior {
    path_pattern           = "/m/*"
    target_origin_id       = local.media_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]

    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.images.id
    compress                   = false

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.media_path.arn
    }
  }

  default_cache_behavior {
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]

    cache_policy_id            = aws_cloudfront_cache_policy.site.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id
    compress                   = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.site_router.arn
    }
  }

  # **A private bucket answers a missing key 403**, not 404 (the policy
  # grants no ListBucket), so both become the site's own 404 page with a
  # real 404 status -- a crawler must not index "not found" as a page.
  # Cached for a minute only: a page that is missing now may exist after
  # the next deploy, and the deploy's invalidation does not reach cached
  # error responses for paths it never names.
  #
  # **This is distribution-wide, so it covers /hub/* too.** A hub 404 (a
  # draft, missing or suspended page) is deliberately served as the site's
  # 404 page with a real 404 status: still one uniform answer, so no
  # existence oracle, and the 60 s error TTL matches the hub's own
  # s-maxage=60 on its 404s. A missing photo under /m/* (S3's 403 for a key
  # it does not hold) becomes the same 404 page; a malformed /m/ path never
  # reaches S3 (media-path.js answers it). The cost: nginx's 403 for an
  # origin-secret mismatch is masked the same way and surfaces as a 404 on
  # /hub/*, which is why the deploy smoke must assert 200 on /hub/en
  # through the site host, not merely "not a 5xx".
  dynamic "custom_error_response" {
    for_each = [403, 404]
    content {
      error_code            = custom_error_response.value
      response_code         = 404
      response_page_path    = "/404.html"
      error_caching_min_ttl = 60
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Role = "public-site"
  }
}

# ---------------------------------------------------------------------
# DNS: the apex and www, A and AAAA
# ---------------------------------------------------------------------

# Alias records: free to resolve, and the only kind of record that works at
# a zone apex (a CNAME cannot sit beside the zone's SOA and NS). No
# allow_overwrite: if anything already held these names the apply must
# fail rather than quietly take them.
resource "aws_route53_record" "site" {
  for_each = {
    for pair in setproduct([local.site_fqdn, local.www_fqdn], ["A", "AAAA"]) :
    "${pair[0]} ${pair[1]}" => { name = pair[0], type = pair[1] }
  }

  zone_id = var.zone_id
  name    = each.value.name
  type    = each.value.type

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
