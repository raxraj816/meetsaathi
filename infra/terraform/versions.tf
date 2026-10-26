terraform {
  required_version = ">= 1.6, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  # Supply an encrypted, access-controlled S3 backend via -backend-config; see deployment runbook.
  backend "s3" {}
}
provider "aws" {
  region = var.region
  default_tags { tags = { Product = "MeetSaathi", Environment = var.environment, ManagedBy = "Terraform" } }
}
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }
locals {
  name = "meetsaathi-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
}
