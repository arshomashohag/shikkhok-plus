# Provider and version pinning.
#
# **Both the Terraform version and the provider are pinned to a minor
# range, not left open.** An unpinned provider means `terraform apply`
# can behave differently on two machines a week apart, which is the
# same class of defect as an unpinned Python dependency: the scanners
# scan a version range rather than the build.

terraform {
  # >= 1.10, not ~> 1.9. The backend below uses `use_lockfile`, which
  # 1.9 does not have -- and a runner pinned to 1.9 would fail at init
  # with a message about an unexpected attribute rather than about the
  # version. Stating the real floor turns that into a clear refusal.
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # **Remote state, because CI applies.** Local state in a runner is
  # discarded when the job ends, so the next run would not know which
  # resources exist and would try to create a Lightsail instance that
  # is already there.
  #
  # The bucket is created by infra/bootstrap, which is the one thing
  # run from a laptop -- state and credentials cannot bootstrap
  # themselves.
  #
  # `use_lockfile` is S3-native locking (Terraform 1.10+), which
  # replaces the DynamoDB table older setups needed. One fewer resource
  # to provision, pay for and secure.
  #
  # The bucket name is supplied by `-backend-config` rather than
  # hardcoded, because S3 names are globally unique across all of AWS
  # and a fork of this repository cannot use the same one.
  backend "s3" {
    key          = "phase1/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "shikkhokplus"
      Environment = var.environment
      ManagedBy   = "terraform"
      # So a cost report can answer "what is the backend costing" without
      # anyone remembering which resources are ours [OC-4].
      CostCenter = "shikkhokplus-backend"
    }
  }
}

# CloudFront requires its ACM certificate in us-east-1, whatever region
# everything else runs in. This alias exists for that one reason and is
# used by exactly one resource.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "shikkhokplus"
      Environment = var.environment
      ManagedBy   = "terraform"
      CostCenter  = "shikkhokplus-backend"
    }
  }
}
