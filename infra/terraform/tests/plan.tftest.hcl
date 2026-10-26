mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["ap-south-1a", "ap-south-1b"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  override_resource {
    target = aws_db_instance.main
    values = { master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:ap-south-1:123456789012:secret:test-owner-ABCDEF", kms_key_id = "test", secret_status = "active" }] }
  }
}
variables {
  environment     = "staging"
  certificate_arn = "arn:aws:acm:ap-south-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
  alarm_topic_arn = "arn:aws:sns:ap-south-1:123456789012:alerts"
  image           = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/meetsaathi@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  collector_image = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/collector@sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
run "bootstrap_plan" {
  command = plan
  assert {
    condition     = aws_ecs_service.api.desired_count == 0 && aws_ecs_service.worker.desired_count == 0
    error_message = "Bootstrap must not run services before secrets and migrations exist."
  }
  assert {
    condition     = aws_db_instance.main.publicly_accessible == false && aws_db_instance.main.storage_encrypted && aws_db_instance.main.backup_retention_period == 35
    error_message = "Database must be private, encrypted and recoverable."
  }
}
run "reject_mutable_image" {
  command = plan
  variables { image = "example.com/backend:latest" }
  expect_failures = [var.image]
}
