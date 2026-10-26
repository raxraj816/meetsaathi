"""Run migrations before promoting API/worker task definitions, with service rollback on failure."""
from __future__ import annotations

import argparse
import json

import boto3


def deploy(config, ecs, *, api_count=2, worker_count=2):
    cluster = config["cluster"]
    migration = ecs.run_task(cluster=cluster, taskDefinition=config["migration_task"], launchType="FARGATE",
        networkConfiguration={"awsvpcConfiguration": {"subnets": config["private_subnet_ids"],
                              "securityGroups": [config["task_security_group_id"]], "assignPublicIp": "DISABLED"}})
    if migration.get("failures") or not migration.get("tasks"):
        raise RuntimeError("Migration task could not start")
    arn = migration["tasks"][0]["taskArn"]
    ecs.get_waiter("tasks_stopped").wait(cluster=cluster, tasks=[arn], WaiterConfig={"Delay": 10, "MaxAttempts": 90})
    task = ecs.describe_tasks(cluster=cluster, tasks=[arn])["tasks"][0]
    containers = [c for c in task.get("containers", []) if c["name"] == "migrate"]
    if not containers or containers[0].get("exitCode") != 0:
        raise RuntimeError("Migration failed; services were not promoted. Inspect metadata-only migration logs.")
    services = ecs.describe_services(cluster=cluster, services=[config["api_service"], config["worker_service"]])["services"]
    previous = {s["serviceName"]: (s["taskDefinition"], s["desiredCount"]) for s in services}
    if len(previous) != 2:
        raise RuntimeError("Expected API and worker services")
    try:
        for kind, count in (("api", api_count), ("worker", worker_count)):
            ecs.update_service(cluster=cluster, service=config[f"{kind}_service"], taskDefinition=config[f"{kind}_task"], desiredCount=count)
        ecs.get_waiter("services_stable").wait(cluster=cluster, services=list(previous), WaiterConfig={"Delay": 15, "MaxAttempts": 60})
        current = ecs.describe_services(cluster=cluster, services=list(previous))["services"]
        for service in current:
            kind = "api" if service["serviceName"] == config["api_service"] else "worker"
            if service["taskDefinition"] != config[f"{kind}_task"] or service["runningCount"] != service["desiredCount"]:
                raise RuntimeError("Service rolled back or did not reach the requested revision")
    except Exception:
        for name, (definition, count) in previous.items():
            ecs.update_service(cluster=cluster, service=name, taskDefinition=definition, desiredCount=count)
        raise
    print("Migrations succeeded; API and worker services are stable on the requested revisions.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outputs")
    parser.add_argument("--api-count", type=int, default=2)
    parser.add_argument("--worker-count", type=int, default=2)
    args = parser.parse_args()
    with open(args.outputs) as f:
        outputs = json.load(f)
    deploy(outputs["deployment"]["value"], boto3.client("ecs", region_name=outputs["bootstrap"]["value"]["region"]),
           api_count=args.api_count, worker_count=args.worker_count)


if __name__ == "__main__":
    main()
