"""Regional Bedrock Converse with schema-constrained output and no executable model tools."""
from __future__ import annotations

import asyncio
import copy
import json
import logging

from botocore.exceptions import BotoCoreError, ClientError
from jsonschema import Draft202012Validator, ValidationError

from ..config import get_settings
from .reasoner import BASE_RULES, Reasoner, ReasonerRefused, ReasonerResult, ReasonerUnavailable

log = logging.getLogger("meetsaathi.reasoner")


def provider_schema(schema: dict) -> dict:
    """Bedrock rejects numeric/string bounds and maxItems; enforce those locally after generation."""
    out = copy.deepcopy(schema)

    def visit(node):
        if isinstance(node, dict):
            for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
                      "minLength", "maxLength", "maxItems", "pattern"):
                node.pop(k, None)
            if node.get("minItems", 0) > 1:
                node.pop("minItems")
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(out)
    return out


class BedrockReasoner(Reasoner):
    def __init__(self, *, client=None):
        s = get_settings()
        self.model = s.bedrock_model_id or ""
        self.region = s.aws_region
        self._client = client

    @property
    def version(self):
        return f"bedrock:{self.model}"

    def available(self):
        # Inference profiles can route content outside the configured region. Accept only regional
        # foundation model IDs / ARNs, until destination-region verification is implemented.
        model = self.model
        if model.startswith("arn:"):
            parts = model.split(":", 5)
            regional = len(parts) == 6 and parts[3] == self.region and parts[5].startswith("foundation-model/")
        else:
            regional = bool(model) and not model.startswith(("us.", "eu.", "apac.", "global.", "in."))
        return regional and self.region in get_settings().allowed_region_set()

    async def structured(self, *, task, system_extra, data_blocks, instruction, schema, effort="low", max_tokens=4000):
        if not self.available():
            raise ReasonerUnavailable("Bedrock regional model not configured for an allowed region")
        from ..aws import client as aws_client

        s = get_settings()
        # JSON keeps any delimiter-looking transcript strings inside a data value.
        content = json.dumps({"untrusted_data": data_blocks, "task": instruction}, ensure_ascii=False, default=str)
        request = dict(modelId=self.model, system=[{"text": BASE_RULES + "\n" + system_extra}],
                       messages=[{"role": "user", "content": [{"text": content}]}],
                       inferenceConfig={"maxTokens": max_tokens},
                       outputConfig={"textFormat": {"type": "json_schema", "structure": {"jsonSchema": {
                           "name": "meetsaathi_response", "schema": json.dumps(provider_schema(schema))}}}})
        try:
            client = self._client or aws_client("bedrock-runtime", region=self.region, timeout=s.reasoner_timeout_s)
            response = await asyncio.to_thread(client.converse, **request)
        except (BotoCoreError, ClientError) as e:
            raise ReasonerUnavailable(f"Bedrock failed: {type(e).__name__}") from e
        stop = response.get("stopReason")
        if stop in ("guardrail_intervened", "content_filtered", "refusal"):
            raise ReasonerRefused("Bedrock declined")
        if stop != "end_turn":
            raise ReasonerUnavailable("Bedrock response incomplete")
        try:
            text = "".join(b["text"] for b in response["output"]["message"]["content"] if "text" in b)
            data = json.loads(text)
            Draft202012Validator(schema).validate(data)
        except (KeyError, TypeError, ValueError, ValidationError) as e:
            raise ReasonerUnavailable("Bedrock returned an invalid structured response") from e
        usage = response.get("usage", {})
        log.info("reasoner task=%s model=%s in=%s out=%s", task, self.model, usage.get("inputTokens", 0), usage.get("outputTokens", 0))
        return ReasonerResult(data, self.model, usage.get("inputTokens", 0), usage.get("outputTokens", 0))
