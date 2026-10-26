output "bootstrap" {
  value = {
    region               = var.region
    database_host        = aws_db_instance.main.address
    database_port        = aws_db_instance.main.port
    database_name        = aws_db_instance.main.db_name
    owner_secret_arn     = aws_db_instance.main.master_user_secret[0].secret_arn
    runtime_secret_arn   = aws_secretsmanager_secret.runtime.arn
    migration_secret_arn = aws_secretsmanager_secret.migration.arn
  }
}
output "deployment" {
  value = {
    cluster                = aws_ecs_cluster.main.name
    api_service            = aws_ecs_service.api.name
    worker_service         = aws_ecs_service.worker.name
    migration_task         = aws_ecs_task_definition.main["migrate"].arn
    api_task               = aws_ecs_task_definition.main["api"].arn
    worker_task            = aws_ecs_task_definition.main["worker"].arn
    private_subnet_ids     = aws_subnet.private[*].id
    task_security_group_id = aws_security_group.tasks.id
    repository_url         = aws_ecr_repository.backend.repository_url
    alb_dns_name           = aws_lb.api.dns_name
    alb_zone_id            = aws_lb.api.zone_id
  }
}
