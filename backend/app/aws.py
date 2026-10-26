"""AWS clients use the default credential chain (ECS task roles in deployed environments).

No static credentials or endpoint overrides are accepted from requests. Creation is lazy so an
unconfigured integration cannot contact credential metadata services while the app starts.
"""
from __future__ import annotations

import boto3
from botocore.config import Config

from .config import get_settings


def client(service: str, *, region: str | None = None, timeout: float = 30):
    return boto3.client(service, region_name=region or get_settings().aws_region,
                        config=Config(connect_timeout=5, read_timeout=timeout,
                                      retries={"mode": "standard", "max_attempts": 2}))
