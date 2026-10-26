resource "aws_wafv2_web_acl" "api" {
  name  = local.name
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  rule {
    name     = "per-ip-request-rate"
    priority = 1
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit                 = 2000
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.name}-rate-limit"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "auth-rate"
    priority = 0
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit                 = 100
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
        scope_down_statement {
          byte_match_statement {
            field_to_match {
              uri_path {}
            }
            positional_constraint = "STARTS_WITH"
            search_string         = "/v1/auth/"
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.name}-auth-rate"
      sampled_requests_enabled   = false
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = local.name
    sampled_requests_enabled   = false
  }
}
resource "aws_wafv2_web_acl_association" "api" {
  resource_arn = aws_lb.api.arn
  web_acl_arn  = aws_wafv2_web_acl.api.arn
}
locals {
  alarms = {
    api_5xx          = { namespace = "AWS/ApplicationELB", metric = "HTTPCode_Target_5XX_Count", statistic = "Sum", threshold = 5, comparison = "GreaterThanOrEqualToThreshold", dimensions = { LoadBalancer = aws_lb.api.arn_suffix } }
    api_latency      = { namespace = "AWS/ApplicationELB", metric = "TargetResponseTime", statistic = "Average", threshold = 3, comparison = "GreaterThanThreshold", dimensions = { LoadBalancer = aws_lb.api.arn_suffix } }
    dead_letters     = { namespace = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", statistic = "Maximum", threshold = 1, comparison = "GreaterThanOrEqualToThreshold", dimensions = { QueueName = aws_sqs_queue.dead.name } }
    backlog_age      = { namespace = "AWS/SQS", metric = "ApproximateAgeOfOldestMessage", statistic = "Maximum", threshold = 300, comparison = "GreaterThanThreshold", dimensions = { QueueName = aws_sqs_queue.jobs.name } }
    database_storage = { namespace = "AWS/RDS", metric = "FreeStorageSpace", statistic = "Minimum", threshold = 10737418240, comparison = "LessThanThreshold", dimensions = { DBInstanceIdentifier = aws_db_instance.main.identifier } }
    database_cpu     = { namespace = "AWS/RDS", metric = "CPUUtilization", statistic = "Average", threshold = 85, comparison = "GreaterThanThreshold", dimensions = { DBInstanceIdentifier = aws_db_instance.main.identifier } }
    unhealthy_api    = { namespace = "AWS/ApplicationELB", metric = "HealthyHostCount", statistic = "Minimum", threshold = 1, comparison = "LessThanThreshold", dimensions = { LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix } }
  }
}
resource "aws_cloudwatch_metric_alarm" "main" {
  for_each            = local.alarms
  alarm_name          = "${local.name}-${each.key}"
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  statistic           = each.value.statistic
  threshold           = each.value.threshold
  comparison_operator = each.value.comparison
  dimensions          = each.value.dimensions
  period              = 60
  evaluation_periods  = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  ok_actions          = [var.alarm_topic_arn]
}
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = local.name
  dashboard_body = jsonencode({ widgets = [
    { type = "metric", x = 0, y = 0, width = 12, height = 6, properties = { title = "API requests / errors", region = var.region, period = 60, stat = "Sum", metrics = [
      ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.api.arn_suffix],
      ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.api.arn_suffix]
    ] } },
    { type = "metric", x = 12, y = 0, width = 12, height = 6, properties = { title = "Queue backlog / DLQ", region = var.region, period = 60, stat = "Maximum", metrics = [
      ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.jobs.name],
      ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.dead.name],
      ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.jobs.name]
    ] } }
  ] })
}
