"""Deployment ordering and secret preservation are tested without cloud side effects."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def module(name):
    path = Path(__file__).resolve().parents[2] / "infra" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_bootstrap_preserves_runtime_keys_after_partial_failure():
    bootstrap = module("bootstrap_secrets")
    config = {"database_host": "database.internal", "database_port": 5432, "database_name": "meetsaathi"}
    owner = {"username": "owner", "password": "a/password:with@special#characters"}
    runtime, stored = bootstrap.prepare(config, owner, None)
    again, rotated = bootstrap.prepare(config, owner | {"password": "rotated"}, stored)
    assert runtime == again
    assert stored["MS_APP_DB_PASSWORD"] == rotated["MS_APP_DB_PASSWORD"]
    assert stored["MS_DATABASE_OWNER_URL"] != rotated["MS_DATABASE_OWNER_URL"]
    assert "a%2Fpassword%3Awith%40special%23characters" in stored["MS_DATABASE_OWNER_URL"]
    assert "MS_DATABASE_OWNER_URL" not in runtime


class ECS:
    def __init__(self, migration_ok=True, service_ok=True):
        self.updates = []
        self.migration_ok = migration_ok
        self.service_ok = service_ok
        self.describes = 0

    def run_task(self, **kwargs):
        return {"tasks": [{"taskArn": "migration"}]}

    def get_waiter(self, kind):
        return self

    def wait(self, **kwargs):
        pass

    def describe_tasks(self, **kwargs):
        return {"tasks": [{"containers": [{"name": "migrate", "exitCode": 0 if self.migration_ok else 1}]}]}

    def describe_services(self, **kwargs):
        self.describes += 1
        return {"services": [{"serviceName": kind, "taskDefinition": ("old-" if self.describes == 1 or not self.service_ok else "new-") + kind,
                              "desiredCount": 2, "runningCount": 2} for kind in ("api", "worker")]}

    def update_service(self, **kwargs):
        self.updates.append(kwargs)


DEPLOYMENT = {"cluster": "cluster", "migration_task": "migrate", "private_subnet_ids": ["subnet"],
              "task_security_group_id": "sg", "api_service": "api", "worker_service": "worker", "api_task": "new-api", "worker_task": "new-worker"}


def test_failed_migration_never_promotes_services():
    ecs = ECS(migration_ok=False)
    with pytest.raises(RuntimeError, match="Migration failed"):
        module("deploy").deploy(DEPLOYMENT, ecs)
    assert not ecs.updates


def test_healthy_deploy_promotes_after_migration():
    ecs = ECS()
    module("deploy").deploy(DEPLOYMENT, ecs)
    assert [u["taskDefinition"] for u in ecs.updates] == ["new-api", "new-worker"]


def test_failed_service_promotion_rolls_back_both_services():
    ecs = ECS(service_ok=False)
    with pytest.raises(RuntimeError, match="rolled back"):
        module("deploy").deploy(DEPLOYMENT, ecs)
    assert [u["taskDefinition"] for u in ecs.updates] == ["new-api", "new-worker", "old-api", "old-worker"]
