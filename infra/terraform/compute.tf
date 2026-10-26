locals {
  tasks          = toset(["api", "worker", "migrate"])
  runtime_keys   = ["MS_DATABASE_APP_URL", "MS_DATABASE_WORKER_URL", "MS_JWT_SECRET", "MS_MASTER_KEY_B64"]
  migration_keys = concat(local.runtime_keys, ["MS_DATABASE_OWNER_URL", "MS_APP_DB_PASSWORD", "MS_WORKER_DB_PASSWORD"])
  environment = {
    MS_ENV                     = var.environment
    MS_AWS_REGION              = var.region
    MS_PROCESSING_REGION       = var.region
    MS_ALLOWED_REGIONS         = var.region
    MS_REASONER_REGION         = var.region
    MS_ASR_REGION              = var.region
    MS_DIARIZER_REGION         = var.region
    MS_EMBEDDING_REGION        = var.region
    MS_OBJECT_STORE_BACKEND    = "s3"
    MS_S3_BUCKET               = aws_s3_bucket.objects.id
    MS_S3_KMS_KEY_ID           = aws_kms_key.data.arn
    MS_QUEUE_BACKEND           = "sqs"
    MS_SQS_QUEUE_URL           = aws_sqs_queue.jobs.url
    MS_RUN_INLINE_WORKER       = "false"
    MS_REASONER_PROVIDER       = "bedrock"
    MS_BEDROCK_MODEL_ID        = var.bedrock_model_id
    MS_ASR_PROVIDER            = "amazon-transcribe"
    MS_TRANSCRIBE_ENABLED      = tostring(var.transcribe_enabled)
    MS_DIARIZER_URL            = var.diarizer_url
    MS_TELEMETRY_ENABLED       = "true"
    MS_TELEMETRY_OTLP_ENDPOINT = "http://localhost:4318"
  }
}
resource "aws_ecr_repository" "backend" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.data.arn
  }
}
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 30
}
resource "aws_cloudwatch_log_group" "metrics" {
  name              = "/meetsaathi/${var.environment}/metrics"
  retention_in_days = 30
}
resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}
resource "aws_iam_role" "execution" {
  for_each           = local.tasks
  name               = "${local.name}-${each.key}-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "execution" {
  for_each   = local.tasks
  role       = aws_iam_role.execution[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role_policy" "secrets" {
  for_each = local.tasks
  role     = aws_iam_role.execution[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = each.key == "migrate" ? aws_secretsmanager_secret.migration.arn : aws_secretsmanager_secret.runtime.arn },
    { Effect = "Allow", Action = ["kms:Decrypt"], Resource = aws_kms_key.data.arn,
    Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com" } } }
  ] })
}
resource "aws_iam_role" "task" {
  for_each           = local.tasks
  name               = "${local.name}-${each.key}-task"
  assume_role_policy = aws_iam_role.execution[each.key].assume_role_policy
}
resource "aws_iam_role_policy" "runtime" {
  for_each = toset(["api", "worker"])
  role     = aws_iam_role.task[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion"], Resource = "${aws_s3_bucket.objects.arn}/t/*" },
    { Effect = "Allow", Action = ["s3:ListBucket", "s3:ListBucketVersions"], Resource = aws_s3_bucket.objects.arn,
    Condition = { StringLike = { "s3:prefix" = ["t/*"] } } },
    { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.data.arn },
    { Effect = "Allow", Action = ["transcribe:StartStreamTranscription"], Resource = "*",
    Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } },
    { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"], Resource = "*" },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = "${aws_cloudwatch_log_group.metrics.arn}:*" }
    ], var.bedrock_model_arn == "" ? [] : [
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = var.bedrock_model_arn,
    Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } }
    ], each.key == "worker" ? [
    { Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.jobs.arn }
  ] : []) })
}
resource "aws_ecs_task_definition" "main" {
  for_each                 = local.tasks
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode(concat([merge({
    name             = each.key, image = var.image, essential = true, user = "10001", readonlyRootFilesystem = true,
    cpu              = 384, memory = 768,
    portMappings     = each.key == "api" ? [{ containerPort = 8080, protocol = "tcp" }] : [],
    environment      = [for key, value in merge(local.environment, { MS_TELEMETRY_SERVICE_NAME = "meetsaathi-${each.key}" }) : { name = key, value = value }],
    secrets          = each.key == "migrate" ? [for key in local.migration_keys : { name = key, valueFrom = "${aws_secretsmanager_secret.migration.arn}:${key}::" }] : [for key in local.runtime_keys : { name = key, valueFrom = "${aws_secretsmanager_secret.runtime.arn}:${key}::" }],
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.app.name, awslogs-region = var.region, awslogs-stream-prefix = each.key } },
    linuxParameters  = { initProcessEnabled = true, capabilities = { drop = ["ALL"] } },
    stopTimeout      = 120
    command          = each.key == "migrate" ? tolist(["python", "-m", "app.migrate"]) : each.key == "worker" ? tolist(["python", "-m", "app.workers.runner"]) : tolist(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"])
    }, each.key == "api" ? {
    healthCheck = { command = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/v1/ready', timeout=3)"], interval = 30, timeout = 5, retries = 3, startPeriod = 30 }
    } : {})], each.key == "migrate" ? [] : [{
    name             = "telemetry", image = var.collector_image, essential = false, cpu = 128, memory = 256,
    command          = ["--config=/etc/meetsaathi/collector.yaml"],
    environment      = [{ name = "AWS_REGION", value = var.region }, { name = "MS_METRICS_LOG_GROUP", value = aws_cloudwatch_log_group.metrics.name }],
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.app.name, awslogs-region = var.region, awslogs-stream-prefix = "telemetry-${each.key}" } }
  }]))
}
resource "aws_lb" "api" {
  name                       = local.name
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.public[*].id
  idle_timeout               = 120
  drop_invalid_header_fields = true
  enable_deletion_protection = var.environment == "prod"
}
resource "aws_lb_target_group" "api" {
  name                 = local.name
  port                 = 8080
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 60
  health_check {
    path     = "/v1/ready"
    matcher  = "200"
    interval = 30
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
resource "aws_ecs_service" "api" {
  lifecycle { ignore_changes = [task_definition, desired_count] }
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main["api"].arn
  desired_count   = var.services_enabled ? var.api_count : 0
  launch_type     = "FARGATE"
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8080
  }
  depends_on = [aws_lb_listener.https, aws_iam_role_policy.secrets, aws_iam_role_policy.runtime]
}
resource "aws_ecs_service" "worker" {
  lifecycle { ignore_changes = [task_definition, desired_count] }
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main["worker"].arn
  desired_count   = var.services_enabled ? var.worker_count : 0
  launch_type     = "FARGATE"
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  depends_on = [aws_iam_role_policy.secrets, aws_iam_role_policy.runtime]
}
