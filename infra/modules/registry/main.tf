# The container registry.
#
# **Why a registry at all, when the host could `docker build`.** It
# could, and deploy/README.md said so -- but that breaks three things
# team.md affirms. Rollback stops being "redeploy the previous tag"
# and becomes "check out an old SHA and rebuild", which produces a
# DIFFERENT artifact from the one that was tested. The deployed image
# stops being identifiable, so "is this CVE in what we shipped" has no
# answer. And the build CI verified is not the build that runs.
#
# **ECR rather than GHCR**, at roughly USD 0.10/month for this image
# count. GHCR is free but needs a long-lived pull token on the host,
# and this project removed every static credential it had: the CI role
# is OIDC, the shell is SSM. A never-expiring token would be the only
# static secret left, guarding the one thing that is not secret --
# our own application image.
#
# ECR authenticates through the instance profile the host already
# carries for SSM, so no new credential exists anywhere.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

resource "aws_ecr_repository" "backend" {
  name = "${var.name_prefix}-backend"

  # The load-bearing line. A mutable tag means `:abc123` can be
  # overwritten, so a SHA stops identifying an artifact and a rollback
  # can silently fetch something new. With immutability a tag IS the
  # artifact, which is what makes the affirmed rollback practice true
  # rather than aspirational.
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    # Free, and it reads the layers we actually ship rather than the
    # lockfile we believe we ship.
    scan_on_push = true
  }
}

# Storage is billed per GB. An arm64 Python image is around 200MB and
# a deploy per working day fills a GB a month, so this is what keeps
# the cost at pennies rather than creeping.
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 10 images; a rollback never needs more"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
