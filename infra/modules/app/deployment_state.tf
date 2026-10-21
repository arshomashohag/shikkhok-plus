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

# **The marker the pipeline compares against to decide whether to
# apply infrastructure.**
#
# Written by the apply job, on success only. Read by the plan job.
#
# It exists here rather than being created on first write so the read
# has something to find: a missing parameter and a parameter holding
# "none" both mean "nothing applied yet", and having the resource
# declared means `terraform destroy` removes it too rather than
# leaving a marker claiming infrastructure that no longer exists.
resource "aws_ssm_parameter" "infra_applied_sha" {
  name  = "/shikkhokplus/${var.name_prefix}/infra-applied-sha"
  type  = "String"
  value = "none"

  description = "Commit whose infra/ was last applied. Written by the deploy pipeline."

  lifecycle {
    # The pipeline owns this value. An apply that reset it would make
    # the next deploy re-apply infrastructure it had already applied.
    ignore_changes = [value]
  }
}
