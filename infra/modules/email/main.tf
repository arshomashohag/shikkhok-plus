# Transactional email through Amazon SES: one-time verification codes.
#
# **One identity per environment, on that environment's own zone.** Both
# environments share one AWS account and one region (us-east-1), but not
# one domain: staging's zone is shikkhokplus.<apex> and production's
# shikkhokplus-prod.<apex> (infra/main.tf, [OPS-10]). So each environment
# verifies, signs for and sends from its own domain --
# no-reply@shikkhokplus.<apex> and no-reply@shikkhokplus-prod.<apex> --
# and every resource here is per environment: the identity, its DNS
# records, the configuration set, the alarms, the SMTP user and its
# parameters. Nothing is shared, so two environments' applies cannot
# fight over one resource, and neither state holds the other's sender.
#
# Sending from the APEX instead (no-reply@<apex>) was rejected: one
# identity two states would both need to own, DNS records in the apex
# zone that serves other projects (which the CI roles may not write --
# bootstrap's OnlyOurRecordNames), and a production sender that staging
# could impersonate.
#
# **What IS shared, because SES makes it account-and-region-wide:** the
# sandbox and its lift (production access is requested once per region,
# by hand -- infra/README.md), the account-level suppression list and the
# account's sending quota. A staging send counts against production's
# quota. At this volume that is a non-issue, stated so it is not a
# surprise.
#
# **SMTP, not the API, and an IAM user, not a role.** The API runs in a
# container on a host whose IMDS hop limit is 1 (modules/app/main.tf), so
# the container cannot reach the instance role -- deliberately, so a
# compromised container cannot take the host's credentials. It sends
# through the SES SMTP interface (STARTTLS on 587) with the SMTP
# credentials of the user below, which can do one thing: send from
# no-reply@<this domain> through this configuration set.
#
# Cost [OC-4]: SES is USD 0.10 per 1,000 messages; infra/main.tf counts it
# at the daily ceiling. Deliberately absent, because each bills monthly
# whatever the volume: dedicated IPs (USD 24.95/month each) and Virtual
# Deliverability Manager. The alarms are two standard alarms.

locals {
  from_address = "${var.from_local_part}@${var.domain_name}"

  # The MAIL FROM (envelope sender, Return-Path) domain. A subdomain of
  # the From domain, so SPF aligns under DMARC's relaxed alignment.
  mail_from_domain = "bounce.${var.domain_name}"

  smtp_host = "email-smtp.${var.aws_region}.amazonaws.com"

  identity_arn          = "arn:aws:ses:${var.aws_region}:${var.account_id}:identity/${var.domain_name}"
  configuration_set_arn = "arn:aws:ses:${var.aws_region}:${var.account_id}:configuration-set/${aws_sesv2_configuration_set.email.configuration_set_name}"
}

# ---------------------------------------------------------------------
# The configuration set: reputation metrics, suppression, TLS
# ---------------------------------------------------------------------

resource "aws_sesv2_configuration_set" "email" {
  configuration_set_name = "${var.name_prefix}-email"

  # Bounce and complaint rates for THIS configuration set, published to
  # CloudWatch -- what the two alarms below watch. Free.
  reputation_options {
    reputation_metrics_enabled = true
  }

  sending_options {
    sending_enabled = true
  }

  # An address that hard-bounced or complained is not mailed again: the
  # cheapest protection the bounce and complaint rates have.
  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }

  # **TLS to the receiving server is required, not opportunistic.** The
  # message carries a one-time code; a receiver that cannot do TLS gets
  # no code rather than a code in clear on the wire. Every large mailbox
  # provider supports it; the trade-off is a rare small provider that
  # does not, whose user cannot sign in by email.
  delivery_options {
    tls_policy = "REQUIRE"
  }

  # No vdm_options: Virtual Deliverability Manager bills per message on
  # top of sending, for dashboards this volume does not need.
}

# ---------------------------------------------------------------------
# The identity: the domain, Easy DKIM, a custom MAIL FROM
# ---------------------------------------------------------------------

resource "aws_sesv2_email_identity" "domain" {
  email_identity = var.domain_name

  # **Every message goes through the configuration set**, whether or not
  # the application sends the X-SES-CONFIGURATION-SET header. The SMTP
  # user's policy cannot require a configuration set (SES has no
  # condition key for it); a default on the identity does the same job.
  configuration_set_name = aws_sesv2_configuration_set.email.configuration_set_name

  # Easy DKIM: SES generates and rotates the key pair; the three CNAMEs
  # below delegate the public keys to it.
  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }
}

# The domain verifies once these resolve -- typically minutes, up to 72
# hours. Until then SES refuses to send from it.
resource "aws_route53_record" "dkim" {
  count = 3

  zone_id = var.zone_id
  name    = "${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  email_identity   = aws_sesv2_email_identity.domain.email_identity
  mail_from_domain = local.mail_from_domain

  # While the MX below is missing or not yet propagated, SES falls back to
  # its own amazonses.com MAIL FROM rather than refusing to send. Mail
  # still goes out, DKIM-aligned; only SPF alignment is lost meanwhile.
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}

# Where receivers return bounces and complaints: SES's feedback endpoint
# for this region.
resource "aws_route53_record" "mail_from_mx" {
  zone_id = var.zone_id
  name    = local.mail_from_domain
  type    = "MX"
  ttl     = 1800
  records = ["10 feedback-smtp.${var.aws_region}.amazonses.com"]
}

resource "aws_route53_record" "mail_from_spf" {
  zone_id = var.zone_id
  name    = local.mail_from_domain
  type    = "TXT"
  ttl     = 1800
  records = ["v=spf1 include:amazonses.com ~all"]
}

# **DMARC, at p=none to start.** The project zone is this stack's own and
# held no DMARC record. p=none asks receivers to apply no policy -- it
# changes no delivery outcome -- and exists so the domain HAS a published
# policy, which large receivers now expect of bulk and transactional
# senders alike. Moving to p=quarantine is a one-line change once real
# traffic has shown DKIM and SPF aligned. No rua= reporting address:
# nobody would read the aggregate reports today, and an address here is
# a mailbox that has to exist.
resource "aws_route53_record" "dmarc" {
  zone_id = var.zone_id
  name    = "_dmarc.${var.domain_name}"
  type    = "TXT"
  ttl     = 1800
  records = ["v=DMARC1; p=none"]
}

# ---------------------------------------------------------------------
# Alarms: bounce and complaint rate, to the environment's alert topic
# ---------------------------------------------------------------------
#
# AWS places an account under review at a 5% bounce rate or a 0.1%
# complaint rate, and may pause sending at 10% or 0.5%. Each alarm fires
# BELOW the review threshold, so there is time to act before AWS does.
#
# Per configuration set (the `ses:configuration-set` dimension), so a
# staging problem is attributed to staging. AWS's review acts on the
# account-wide rate, which both environments feed; at one sender per
# environment the two coincide closely enough. No data -- no mail sent
# yet -- is not an incident.
locals {
  reputation_alarms = {
    bounce-rate = {
      metric      = "Reputation.BounceRate"
      threshold   = 0.04
      description = "SES bounce rate at or over 4% for this environment's mail. AWS reviews the account at 5%."
    }
    complaint-rate = {
      metric      = "Reputation.ComplaintRate"
      threshold   = 0.0008
      description = "SES complaint rate at or over 0.08% for this environment's mail. AWS reviews the account at 0.1%."
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "reputation" {
  for_each = local.reputation_alarms

  alarm_name          = "${var.name_prefix}-ses-${each.key}"
  alarm_description   = each.value.description
  namespace           = "AWS/SES"
  metric_name         = each.value.metric
  dimensions          = { "ses:configuration-set" = aws_sesv2_configuration_set.email.configuration_set_name }
  statistic           = "Maximum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = each.value.threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  ok_actions          = [var.alarm_topic_arn]
}

# ---------------------------------------------------------------------
# The sender: an IAM user whose only power is this one From address
# ---------------------------------------------------------------------
#
# **A long-lived credential, accepted deliberately.** Everything else in
# this project authenticates with short-lived role credentials. The API
# container cannot: the IMDS hop limit of 1 keeps the instance role out of
# its reach, and that is a control worth more than avoiding one static
# key. What bounds this key instead:
#
#   * its policy allows ses:SendRawEmail -- the action SES's SMTP
#     interface authorizes -- on this identity and this configuration set
#     only, and only with From: no-reply@<this domain>. It cannot read,
#     list or change anything, nor send from any other address or domain;
#   * it carries bootstrap's shikkhokplus-email-sender-boundary-<env>, a
#     ceiling of the same one action, so even a widened inline policy
#     could not make it more; the infrastructure role may create or edit a
#     user only under that boundary;
#   * it lives in SSM SecureStrings and the runtime env, the same places
#     as the JWT and OTP keys, readable by the same deploy role and host;
#   * the daily ceiling (SHIKKHOKPLUS_GLOBAL_DAILY_EMAIL) bounds what the
#     application sends, and the reputation alarms above report abuse.
#
# A leaked key lets its holder send mail as no-reply@<this domain> until
# it is rotated -- phishing from our domain, and a reputation hit. That is
# the residual risk.
#
# **Rotation.** Raise `smtp_credential_generation` below by one in a pull
# request and deploy. The apply creates the new key before deleting the
# old one (IAM allows two per user), rewrites both SSM parameters, and the
# release job of the same run writes them into the runtime env and
# replaces the host. Email sign-in fails for the minutes between the
# apply and the new host serving; schedule it outside classroom hours,
# like any production deploy. After a suspected leak, deactivate the old
# key in the IAM console first, then rotate.
locals {
  smtp_credential_generation = 1
}

resource "terraform_data" "smtp_credential_generation" {
  input = local.smtp_credential_generation
}

resource "aws_iam_user" "smtp" {
  name                 = "${var.name_prefix}-ses-smtp"
  path                 = "/shikkhokplus/"
  permissions_boundary = var.sender_boundary_arn

  tags = { Role = "ses-smtp-sender" }
}

data "aws_iam_policy_document" "smtp_send" {
  statement {
    sid     = "SendFromNoReplyOnly"
    effect  = "Allow"
    actions = ["ses:SendRawEmail"]

    # Both ARNs: when a message names a configuration set, SES authorizes
    # the send against the identity AND the configuration set.
    resources = [local.identity_arn, local.configuration_set_arn]

    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [local.from_address]
    }
  }
}

resource "aws_iam_user_policy" "smtp_send" {
  name   = "ses-send"
  user   = aws_iam_user.smtp.name
  policy = data.aws_iam_policy_document.smtp_send.json
}

resource "aws_iam_access_key" "smtp" {
  user = aws_iam_user.smtp.name

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [terraform_data.smtp_credential_generation]
  }
}

# ---------------------------------------------------------------------
# Published where deploy.yml reads them into the runtime env
# ---------------------------------------------------------------------
#
# On the admin edge secret's terms (modules/admin): SecureStrings under
# the account's default aws/ssm key, decrypted only through SSM, under
# this environment's own path, so the deploy role reads them without
# reading Terraform state [OPS-3]. The username is an access key id --
# not a secret alone, but half of a credential, so encrypted too.
resource "aws_ssm_parameter" "smtp_username" {
  name        = "/shikkhokplus/${var.name_prefix}/ses-smtp-username"
  type        = "SecureString"
  value       = aws_iam_access_key.smtp.id
  description = "SES SMTP username (the sender user's access key id). deploy.yml writes it as SHIKKHOKPLUS_SES_SMTP_USERNAME."
}

resource "aws_ssm_parameter" "smtp_password" {
  name        = "/shikkhokplus/${var.name_prefix}/ses-smtp-password"
  type        = "SecureString"
  value       = aws_iam_access_key.smtp.ses_smtp_password_v4
  description = "SES SMTP password, derived for ${var.aws_region}. deploy.yml writes it as SHIKKHOKPLUS_SES_SMTP_PASSWORD."
}

# The three non-secret values the application needs, published so the
# deploy never derives a domain or a name Terraform already decided.
resource "aws_ssm_parameter" "email_from" {
  name        = "/shikkhokplus/${var.name_prefix}/email-from"
  type        = "String"
  value       = "${var.from_display_name} <${local.from_address}>"
  description = "The From header. The SMTP user may send from this address only."
}

resource "aws_ssm_parameter" "configuration_set" {
  name        = "/shikkhokplus/${var.name_prefix}/ses-configuration-set"
  type        = "String"
  value       = aws_sesv2_configuration_set.email.configuration_set_name
  description = "The SES configuration set the application names in X-SES-CONFIGURATION-SET."
}

resource "aws_ssm_parameter" "smtp_host" {
  name        = "/shikkhokplus/${var.name_prefix}/ses-smtp-host"
  type        = "String"
  value       = local.smtp_host
  description = "The SES SMTP endpoint for the identity's region (STARTTLS on 587)."
}
