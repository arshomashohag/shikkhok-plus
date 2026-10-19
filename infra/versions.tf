# Provider and version pinning.
#
# **Both the Terraform version and the provider are pinned to a minor
# range, not left open.** An unpinned provider means `terraform apply`
# can behave differently on two machines a week apart, which is the
# same class of defect as an unpinned Python dependency: the scanners
# scan a version range rather than the build.

terraform {
  required_version = "~> 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # State is LOCAL by default, and that is a deliberate Phase 1 choice
  # rather than an oversight -- see infra/README.md. A solo operator
  # with one workstation does not need S3 plus DynamoDB locking, and an
  # unused state bucket is a thing to secure for no benefit.
  #
  # Uncomment when a second person or a CI runner applies:
  #
  # backend "s3" {
  #   bucket       = "shikkhokplus-tfstate"
  #   key          = "phase1/terraform.tfstate"
  #   region       = "ap-south-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
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
