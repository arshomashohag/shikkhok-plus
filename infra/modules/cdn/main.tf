# CloudFront, ACM and Route53.
#
# **Caching is DISABLED, and that is the correct configuration rather
# than a limitation.** 1 of this API's 11 routes is safely cacheable and
# it is the health check: everything else requires a Bearer token, and
# a cached authenticated response is a cross-teacher data leak -- the
# exact risk this project names as its top one.
#
# So what does CloudFront earn at USD 0.00 on the permanent free tier
# (1 TB and 10M requests/month, which 100 teachers will not approach)?
#
#   * **Free TLS.** An ACM certificate costs nothing with CloudFront.
#     On Lightsail alone it is certbot plus a renewal cron nobody
#     checks until it has already expired.
#   * **A stable hostname.** The origin IP can be replaced without a
#     DNS change, which is what makes "redeploy the previous tag" a
#     rollback rather than a migration.
#   * **TLS 1.2 minimum, enforced at the edge** for every client.
#   * **Shield Standard**, included, against L3/L4 floods.
#   * **Caching becomes available later without re-architecture** --
#     when U6 ships marksheets or any static asset arrives, it is a
#     cache-policy change rather than a new component.

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.70"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

# **The zone is PASSED IN, not looked up.** The caller creates it, and
# a data-source lookup here would race that creation: on a first apply
# the zone does not exist yet when the lookup runs, and Terraform
# fails with "no matching Route53Zone found" rather than ordering
# itself. Taking the id as an input makes the dependency explicit.

locals {
  api_fqdn = "${var.api_subdomain}.${var.domain_name}"
}

# **us-east-1, always.** CloudFront reads its certificate from there
# whatever region everything else runs in, and a certificate in the
# wrong region fails at association with a message that does not say
# so.
resource "aws_acm_certificate" "api" {
  provider = aws.us_east_1

  domain_name       = local.api_fqdn
  validation_method = "DNS"

  lifecycle {
    # Replace before destroying: deleting a certificate still attached
    # to a distribution takes the API down for the length of the
    # replacement.
    create_before_destroy = true
  }
}

resource "aws_route53_record" "acm_validation" {
  for_each = {
    for option in aws_acm_certificate.api.domain_validation_options :
    option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  }

  zone_id         = var.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "api" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
}

# The secret CloudFront sends to the origin. Managed as its own
# resource so the header name is in one place and the value comes from
# the app module -- the origin and the CDN cannot disagree about it.
resource "aws_cloudfront_distribution" "api" {
  enabled         = true
  comment         = "${var.name_prefix} API"
  aliases         = [local.api_fqdn]
  is_ipv6_enabled = true

  # **PriceClass_100 is not a saving here, it is a latency decision.**
  # The free tier covers this traffic either way. 100 includes
  # North America and Europe but NOT Asia -- which for a Bangladeshi
  # audience would route every request through a distant edge. All is
  # correct for this product.
  price_class = "PriceClass_All"

  origin {
    domain_name = var.origin_ip
    origin_id   = "lightsail-origin"

    custom_origin_config {
      http_port  = 80
      https_port = 443
      # **https-only.** The origin presents a self-signed certificate
      # which CloudFront does not validate for a custom origin, but the
      # hop is still encrypted -- and it carries an Authorization
      # header on every authenticated request.
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    # What makes "through the CDN only" enforceable on a Lightsail
    # origin. CloudFront's 214 origin-facing CIDRs do not fit in a
    # Lightsail firewall rule (the limit is 5), so a CIDR allowlist is
    # not merely worse here -- it cannot be expressed at all.
    custom_header {
      name  = "X-Origin-Secret"
      value = var.origin_secret
    }
  }

  default_cache_behavior {
    target_origin_id       = "lightsail-origin"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    # CachingDisabled. An AWS-managed policy rather than a hand-rolled
    # one, so "cached nothing" cannot drift into "cached something"
    # through a forgotten TTL.
    cache_policy_id = data.aws_cloudfront_cache_policy.disabled.id

    # AllViewerExceptHostHeader forwards every header, cookie and query
    # string to the origin -- including Authorization, without which no
    # authenticated route works at all. It excludes Host so the origin
    # sees its own hostname rather than the CDN's.
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id

    compress = true
  }

  restrictions {
    geo_restriction {
      # No geo restriction. The audience is Bangladeshi but teachers
      # travel, and a restriction that locks out a real user abroad is
      # a support burden for no security gain -- the API is
      # authenticated.
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn = aws_acm_certificate_validation.api.certificate_arn
    ssl_support_method  = "sni-only"
    # TLS 1.2 minimum for every client, enforced at the edge.
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Role = "cdn"
  }
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewerExceptHostHeader"
}

# An ALIAS record, not CNAME. An alias costs nothing to resolve, works
# at the zone apex if the API ever moves there, and does not add a
# lookup hop.
resource "aws_route53_record" "api" {
  zone_id = var.zone_id
  name    = local.api_fqdn
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.api.domain_name
    zone_id                = aws_cloudfront_distribution.api.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "api_ipv6" {
  zone_id = var.zone_id
  name    = local.api_fqdn
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.api.domain_name
    zone_id                = aws_cloudfront_distribution.api.hosted_zone_id
    evaluate_target_health = false
  }
}
