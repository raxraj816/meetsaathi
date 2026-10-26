"""Initialize Secrets Manager from Terraform bootstrap output; never prints or writes secret values locally.

Run with an approved AWS operator role after infrastructure creation, before the first migration.
Idempotent after partial failure: encryption/signing keys and runtime DB passwords are preserved.
Managed RDS master-password rotation is copied into the migration secret each run.
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError


def read_secret(client, arn):
    try:
        return json.loads(client.get_secret_value(SecretId=arn)["SecretString"])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise


def prepare(config: dict, owner: dict, existing: dict | None) -> tuple[dict, dict]:
    stored = dict(existing or {})
    for key in ("MS_APP_DB_PASSWORD", "MS_WORKER_DB_PASSWORD"):
        stored.setdefault(key, secrets.token_urlsafe(48))
    stored.setdefault("MS_JWT_SECRET", secrets.token_urlsafe(64))
    stored.setdefault("MS_MASTER_KEY_B64", base64.b64encode(secrets.token_bytes(32)).decode())
    host, port, name = config["database_host"], int(config["database_port"]), config["database_name"]

    def url(user, password):
        return f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{quote(name, safe='')}"

    stored["MS_DATABASE_APP_URL"] = url("ms_app", stored["MS_APP_DB_PASSWORD"])
    stored["MS_DATABASE_WORKER_URL"] = url("ms_worker", stored["MS_WORKER_DB_PASSWORD"])
    stored["MS_DATABASE_OWNER_URL"] = url(owner["username"], owner["password"])
    runtime = {k: stored[k] for k in ("MS_DATABASE_APP_URL", "MS_DATABASE_WORKER_URL", "MS_JWT_SECRET", "MS_MASTER_KEY_B64")}
    return runtime, stored


def bootstrap(config, client):
    owner = read_secret(client, config["owner_secret_arn"])
    if not owner:
        raise RuntimeError("RDS managed owner secret is unavailable")
    migration = read_secret(client, config["migration_secret_arn"])
    runtime = read_secret(client, config["runtime_secret_arn"])
    if runtime and not migration:
        raise RuntimeError("Runtime secret exists without migration credentials; restore the migration secret before continuing")
    if runtime and any(runtime.get(k) != migration.get(k) for k in runtime):
        raise RuntimeError("Runtime and migration secrets disagree; reconcile before continuing")
    desired, stored = prepare(config, owner, migration)
    # Store DB passwords and master keys first, so a second write failure cannot lose generated credentials.
    client.put_secret_value(SecretId=config["migration_secret_arn"], SecretString=json.dumps(stored))
    client.put_secret_value(SecretId=config["runtime_secret_arn"], SecretString=json.dumps(desired))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outputs", help="terraform output -json file (contains resource identifiers only)")
    args = parser.parse_args()
    with open(args.outputs) as f:
        config = json.load(f)["bootstrap"]["value"]
    bootstrap(config, boto3.client("secretsmanager", region_name=config["region"]))
    print("Runtime and migration secrets initialized; secret values were not printed.")


if __name__ == "__main__":
    main()
