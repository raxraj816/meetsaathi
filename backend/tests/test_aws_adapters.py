"""Exercise real AWS SDK request validation with Stubber; never contact an AWS account."""
from __future__ import annotations

import io
import asyncio
import json
import uuid
from types import SimpleNamespace

import boto3
import httpx
import pytest
from amazon_transcribe.model import Alternative, Item, Result, Transcript, TranscriptEvent
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.config import get_settings
from app.intelligence.bedrock import BedrockReasoner, provider_schema
from app.intelligence.reasoner import ReasonerRefused, ReasonerUnavailable
from app.security.crypto import encrypt_object
from app.speech.adapters import OpenAICompatibleAsr, SpeechUnavailable
from app.speech.audio import pcm_to_wav
from app.speech.transcribe import AmazonTranscribeAsr
from app.storage import ObjectStore, S3ObjectStore


def aws(service):
    return boto3.client(service, region_name="ap-south-1", aws_access_key_id="test", aws_secret_access_key="test")


@pytest.fixture
def aws_settings(monkeypatch):
    s = get_settings()
    for key, value in {"aws_region": "ap-south-1", "allowed_regions": "ap-south-1", "s3_bucket": "test-audio",
                       "s3_kms_key_id": "alias/test-audio", "bedrock_model_id": "anthropic.claude-sonnet-4-5-20250929-v1:0",
                       "transcribe_enabled": True}.items():
        monkeypatch.setattr(s, key, value)
    return s


@pytest.mark.parametrize("key", ["../objects-other/stolen", "/tmp/stolen", "a/../stolen", "", ".", "a//b", "a\\b"])
def test_local_storage_rejects_unsafe_keys(tmp_path, key):
    with pytest.raises(ValueError):
        ObjectStore(str(tmp_path / "objects")).put(uuid.uuid4(), key, b"secret")


def test_local_storage_rejects_symlink_escape_and_encrypts(tmp_path):
    store = ObjectStore(str(tmp_path / "objects"))
    (store.root / "escape").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        store.put(uuid.uuid4(), "escape/stolen", b"secret")
    tenant = uuid.uuid4()
    store.put(tenant, "safe/object", b"secret")
    assert b"secret" not in (store.root / "safe/object").read_bytes()
    assert store.get(tenant, "safe/object") == b"secret"
    assert not list((store.root / "safe").glob(".upload-*"))


def test_s3_encryption_kms_and_read(aws_settings):
    client = aws("s3")
    tenant, key = uuid.uuid4(), "t/test/s/session/audio/000.pcm"
    blob = encrypt_object(tenant, key, b"private audio")
    with Stubber(client) as stub:
        stub.add_response("put_object", {}, {"Bucket": "test-audio", "Key": key, "Body": ANY,
                          "ServerSideEncryption": "aws:kms", "SSEKMSKeyId": "alias/test-audio",
                          "ContentType": "application/octet-stream"})
        stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(blob), len(blob))}, {"Bucket": "test-audio", "Key": key})
        store = S3ObjectStore(client=client)
        store.put(tenant, key, b"private audio")
        assert store.get(tenant, key) == b"private audio"
        stub.assert_no_pending_responses()


def test_s3_purge_all_versions_and_markers_with_exact_boundary(aws_settings):
    client = aws("s3")
    with Stubber(client) as stub:
        stub.add_response("list_object_versions", {"IsTruncated": True, "NextKeyMarker": "folder/a",
                          "NextVersionIdMarker": "v1", "Versions": [{"Key": "folder/a", "VersionId": "v1"}]},
                          {"Bucket": "test-audio", "Prefix": "folder/"})
        stub.add_response("list_object_versions", {"IsTruncated": False,
                          "Versions": [{"Key": "folder/a", "VersionId": "v2"}],
                          "DeleteMarkers": [{"Key": "folder/a", "VersionId": "marker"}]},
                          {"Bucket": "test-audio", "Prefix": "folder/", "KeyMarker": "folder/a", "VersionIdMarker": "v1"})
        stub.add_response("delete_objects", {}, {"Bucket": "test-audio", "Delete": {"Objects": [
                          {"Key": "folder/a", "VersionId": "v1"}, {"Key": "folder/a", "VersionId": "v2"},
                          {"Key": "folder/a", "VersionId": "marker"}], "Quiet": True}})
        assert S3ObjectStore(client=client).delete_prefix("folder") == 3
        stub.assert_no_pending_responses()


def test_s3_purge_partial_error_is_failure(aws_settings):
    client = aws("s3")
    with Stubber(client) as stub:
        stub.add_response("list_object_versions", {"Versions": [{"Key": "audio", "VersionId": "v1"},
                                                                {"Key": "audio-other", "VersionId": "v2"}]})
        stub.add_response("delete_objects", {"Errors": [{"Key": "audio", "Code": "AccessDenied"}]},
                          {"Bucket": "test-audio", "Delete": {"Objects": [{"Key": "audio", "VersionId": "v1"}], "Quiet": True}})
        with pytest.raises(RuntimeError, match="purge incomplete"):
            S3ObjectStore(client=client).delete("audio")


SCHEMA = {"type": "object", "properties": {"answer": {"type": "string", "maxLength": 12}},
          "required": ["answer"], "additionalProperties": False}


def bedrock_response(text, stop="end_turn"):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": stop,
            "usage": {"inputTokens": 5, "outputTokens": 7, "totalTokens": 12}, "metrics": {"latencyMs": 15}}


async def call_reasoner(client):
    return await BedrockReasoner(client=client).structured(task="test", system_extra="", data_blocks={"untrusted_conversation_data": []},
                                                         instruction="Answer", schema=SCHEMA)


async def test_bedrock_converse_schema_validated_by_actual_sdk(aws_settings):
    client = aws("bedrock-runtime")
    with Stubber(client) as stub:
        stub.add_response("converse", bedrock_response('{"answer":"supported"}'),
                          {"modelId": aws_settings.bedrock_model_id, "system": ANY, "messages": ANY,
                           "inferenceConfig": {"maxTokens": 4000}, "outputConfig": {"textFormat": {"type": "json_schema",
                           "structure": {"jsonSchema": {"name": "meetsaathi_response", "schema": json.dumps(provider_schema(SCHEMA))}}}}})
        result = await call_reasoner(client)
        assert result.data == {"answer": "supported"} and result.input_tokens == 5
        assert SCHEMA["properties"]["answer"]["maxLength"] == 12  # caller schema remains authoritative


@pytest.mark.parametrize("text,stop,error", [('no JSON', "end_turn", ReasonerUnavailable),
    ('{"answer":"longer than allowed"}', "end_turn", ReasonerUnavailable),
    ('{"answer":"ok"}', "max_tokens", ReasonerUnavailable),
    ('{"answer":"ok"}', "content_filtered", ReasonerRefused)])
async def test_bedrock_rejects_bad_output(aws_settings, text, stop, error):
    client = aws("bedrock-runtime")
    with Stubber(client) as stub:
        stub.add_response("converse", bedrock_response(text, stop))
        with pytest.raises(error):
            await call_reasoner(client)


@pytest.mark.parametrize("model", ["us.anthropic.model", "global.anthropic.model", "in.anthropic.model",
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.model",
    "arn:aws:bedrock:ap-south-1:123456789012:inference-profile/anything"])
def test_bedrock_disallows_unverified_inference_destinations(aws_settings, monkeypatch, model):
    monkeypatch.setattr(aws_settings, "bedrock_model_id", model)
    assert not BedrockReasoner().available()


async def test_transcribe_concurrent_pcm_and_final_results(aws_settings):
    input_stream = SimpleNamespace(chunks=[], ended=False)

    async def send_audio_event(*, audio_chunk):
        input_stream.chunks.append(audio_chunk)

    async def end_stream():
        input_stream.ended = True

    input_stream.send_audio_event, input_stream.end_stream = send_audio_event, end_stream
    alt = Alternative("Hello there", [Item(0.0, 0.1, "pronunciation", "Hello", confidence=0.9)], [])

    async def output():
        yield TranscriptEvent(Transcript([Result("r1", 0, 0.1, True, [alt])]))
        while not input_stream.ended:
            await asyncio.sleep(0)
        yield TranscriptEvent(Transcript([Result("r1", 0, 0.1, False, [alt], language_code="en-IN")]))
        yield TranscriptEvent(Transcript([Result("r1", 0, 0.1, False, [alt])]))  # idempotent result ID

    class Client:
        async def start_stream_transcription(self, **params):
            assert params["language_code"] == "en-IN" and params["media_sample_rate_hz"] == 16000
            return SimpleNamespace(input_stream=input_stream, output_stream=output())

    pcm = b"\x01\x00" * 1600
    segments = await AmazonTranscribeAsr(client=Client()).transcribe(pcm_to_wav(pcm, 16000), offset_ms=1000, language="en")
    assert input_stream.ended and b"".join(input_stream.chunks) == pcm
    assert len(segments) == 1 and segments[0].text == "Hello there"
    assert segments[0].start_ms == 1000 and segments[0].end_ms == 1100
    assert segments[0].words[0].start_ms == 1000 and segments[0].confidence == 0.9


async def test_transcribe_region_gate_never_creates_client(aws_settings, monkeypatch):
    monkeypatch.setattr(aws_settings, "allowed_regions", "eu-west-1")
    with pytest.raises(SpeechUnavailable, match="allowed region"):
        await AmazonTranscribeAsr().transcribe(b"", offset_ms=0, language=None)


async def test_compatible_asr_real_multipart_encoding(monkeypatch):
    """httpx 0.28 rejects a list of tuples as data on AsyncClient; exercise the actual encoder."""
    s = get_settings()
    monkeypatch.setattr(s, "asr_base_url", "https://asr.example.invalid")
    monkeypatch.setattr(s, "asr_region", next(iter(s.allowed_region_set())))

    async def handler(request):
        body = await request.aread()
        assert b'filename="audio.wav"' in body
        assert body.count(b'name="timestamp_granularities[]"') == 2
        return httpx.Response(200, json={"segments": [{"start": 0, "end": 0.1, "text": "Hi"}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = await OpenAICompatibleAsr().transcribe(pcm_to_wav(b"\0\0" * 1600, 16000), offset_ms=0, language="en-IN")
    assert result[0].text == "Hi"

async def test_transcribe_delivers_drafts_while_audio_is_still_open(aws_settings):
    sent, ended, continue_input = asyncio.Event(), asyncio.Event(), asyncio.Event()
    chunks, results = [], []
    alt = Alternative("Live words", [Item(0.0, 0.1, "pronunciation", "Live", confidence=.9)], [])

    async def send_audio_event(*, audio_chunk):
        chunks.append(audio_chunk)
        sent.set()

    async def end_stream():
        ended.set()

    async def output():
        await sent.wait()
        yield TranscriptEvent(Transcript([Result("live", 0, .1, True, [alt])]))
        await ended.wait()
        yield TranscriptEvent(Transcript([Result("live", 0, .2, False, [alt])]))
        yield TranscriptEvent(Transcript([Result("live", 0, .2, False, [alt])]))
        yield TranscriptEvent(Transcript([Result("live", 0, .2, True, [alt])]))

    class Client:
        async def start_stream_transcription(self, **kw):
            assert kw["language_code"] is None and kw["identify_multiple_languages"] is True
            assert kw["language_options"] == ["en-IN", "hi-IN"]
            return SimpleNamespace(input_stream=SimpleNamespace(send_audio_event=send_audio_event, end_stream=end_stream),
                                   output_stream=output())

    async def packets():
        yield b'\0\0' * 1600
        await continue_input.wait()
        yield b'\1\0' * 1600

    async def on_result(r):
        results.append(r)
        if r.is_partial:
            assert not ended.is_set()
            continue_input.set()

    await AmazonTranscribeAsr(client=Client()).stream(packets(), sample_rate=16000, offset_ms=2000,
                                                    language="auto", on_result=on_result)
    assert [r.is_partial for r in results] == [True, False]
    assert len(chunks) == 2 and results[-1].segment.end_ms == 2200


async def test_transcribe_early_eof_cancels_input_and_closes_stream(aws_settings):
    sent, ended = asyncio.Event(), asyncio.Event()

    async def send_audio_event(**kw):
        sent.set()

    async def end_stream():
        ended.set()

    async def output():
        await sent.wait()
        if False:
            yield None

    class Client:
        async def start_stream_transcription(self, **kw):
            return SimpleNamespace(input_stream=SimpleNamespace(send_audio_event=send_audio_event, end_stream=end_stream),
                                   output_stream=output())

    async def packets():
        yield b'\0\0' * 1600
        await asyncio.Event().wait()

    async def unused(r):
        pytest.fail("No result was sent")

    with pytest.raises(SpeechUnavailable):
        await asyncio.wait_for(AmazonTranscribeAsr(client=Client()).stream(
            packets(), sample_rate=16000, offset_ms=0, language=None, on_result=unused), 1)
    assert ended.is_set()


async def test_transcribe_missing_final_drain_times_out(aws_settings, monkeypatch):
    ended = asyncio.Event()
    monkeypatch.setattr(aws_settings, "speech_timeout_s", .03)

    async def send_audio_event(**kw):
        pass

    async def end_stream():
        ended.set()

    async def output():
        await asyncio.Event().wait()
        if False:
            yield None

    class Client:
        async def start_stream_transcription(self, **kw):
            return SimpleNamespace(input_stream=SimpleNamespace(send_audio_event=send_audio_event, end_stream=end_stream),
                                   output_stream=output())

    async def packets():
        yield b'\0\0' * 1600

    async def unused(r):
        pass

    with pytest.raises(SpeechUnavailable):
        await AmazonTranscribeAsr(client=Client()).stream(packets(), sample_rate=16000, offset_ms=0,
                                                        language=None, on_result=unused)
    assert ended.is_set()
