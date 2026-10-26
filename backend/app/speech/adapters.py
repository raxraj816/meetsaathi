"""Provider-neutral speech adapters (master 8.3). Each adapter exposes version, region and health.
An adapter outside the tenant's allowed processing regions is never used and never silently replaced
(UNI-022): callers get `available() == False` and surface a truthful degraded state.

Implemented providers:
* OpenAICompatibleAsr - any server implementing POST /audio/transcriptions with verbose_json + word/segment
  timestamps (hosted Whisper-class APIs or a self-hosted faster-whisper server).
* HttpDiarizer       - a self-hosted NVIDIA Nemotron 3 diarization service using the contract in
  docs/integrations/diarizer-contract.md (anonymous speakers only; never identity).
"""
from __future__ import annotations

import math
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from ..config import get_settings


class SpeechUnavailable(Exception):
    pass


@dataclass
class Word:
    text: str
    start_ms: int
    end_ms: int


@dataclass
class AsrSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None
    language: str | None = None
    words: list[Word] = field(default_factory=list)


@dataclass
class StreamResult:
    result_id: str
    segment: AsrSegment
    is_partial: bool


@dataclass
class SpeakerTurn:
    speaker: str
    start_ms: int
    end_ms: int
    confidence: float | None
    overlap: bool = False


@dataclass
class DiarizationResult:
    turns: list[SpeakerTurn]
    model_version: str
    speaker_count_estimate: int | None
    max_supported: int


class AsrEngine:
    name = "none"
    version = "none"
    region = ""
    supports_streaming = False

    async def stream(self, packets: AsyncIterator[bytes], *, sample_rate: int, offset_ms: int,
                     language: str | None, on_result: Callable[[StreamResult], Awaitable[None]]) -> None:
        raise SpeechUnavailable("Streaming ASR provider not configured")

    def available(self) -> bool:
        return False

    async def transcribe(self, wav: bytes, *, offset_ms: int, language: str | None) -> list[AsrSegment]:
        raise SpeechUnavailable("ASR provider not configured")


class OpenAICompatibleAsr(AsrEngine):
    name = "openai-compatible"

    def __init__(self) -> None:
        s = get_settings()
        self.base_url = (s.asr_base_url or "").rstrip("/")
        self.api_key = s.asr_api_key
        self.model = s.asr_model
        self.version = f"{self.name}:{self.model}"
        self.region = s.asr_region

    def available(self) -> bool:
        return bool(self.base_url) and self.region in get_settings().allowed_region_set()

    async def transcribe(self, wav: bytes, *, offset_ms: int, language: str | None) -> list[AsrSegment]:
        if not self.available():
            raise SpeechUnavailable("ASR provider not available in an allowed region")
        data = {"model": self.model, "response_format": "verbose_json",
                "timestamp_granularities[]": ["segment", "word"]}
        if language and language != "auto":
            data["language"] = language.split("-")[0]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(f"{self.base_url}/audio/transcriptions", headers=headers,
                                      files={"file": ("audio.wav", wav, "audio/wav")}, data=data)
        except httpx.HTTPError as e:
            raise SpeechUnavailable(f"ASR transport error: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise SpeechUnavailable(f"ASR HTTP {r.status_code}")
        return parse_verbose_json(r.json(), offset_ms)


def parse_verbose_json(body: dict, offset_ms: int) -> list[AsrSegment]:
    lang = body.get("language")
    words = [Word(w.get("word", "").strip(), offset_ms + int(float(w["start"]) * 1000), offset_ms + int(float(w["end"]) * 1000))
             for w in body.get("words") or [] if "start" in w and "end" in w]
    out: list[AsrSegment] = []
    for seg in body.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if float(seg.get("no_speech_prob", 0.0)) > 0.6:
            continue  # likely hallucinated text over non-speech
        start = offset_ms + int(float(seg.get("start", 0)) * 1000)
        end = offset_ms + int(float(seg.get("end", 0)) * 1000)
        if end <= start:
            end = start + 1
        lp = seg.get("avg_logprob")
        conf = None if lp is None else max(0.0, min(1.0, math.exp(float(lp))))
        seg_words = [w for w in words if w.start_ms >= start - 50 and w.end_ms <= end + 50]
        out.append(AsrSegment(start, end, text, conf, lang, seg_words))
    if not out and (body.get("text") or "").strip() and not body.get("segments"):
        out.append(AsrSegment(offset_ms, offset_ms + 1, body["text"].strip(), None, lang, words))
    return out


class Diarizer:
    version = "none"
    region = ""
    max_supported = 0

    def available(self) -> bool:
        return False

    async def diarize(self, wav: bytes, *, session_key: str, offset_ms: int) -> DiarizationResult:
        raise SpeechUnavailable("diarizer not configured")


class HttpDiarizer(Diarizer):
    def __init__(self) -> None:
        s = get_settings()
        self.url = (s.diarizer_url or "").rstrip("/")
        self.region = s.diarizer_region
        self.max_supported = s.diarizer_max_speakers
        self.version = "nemotron-3-diarization:http"

    def available(self) -> bool:
        return bool(self.url) and self.region in get_settings().allowed_region_set()

    async def diarize(self, wav: bytes, *, session_key: str, offset_ms: int) -> DiarizationResult:
        if not self.available():
            raise SpeechUnavailable("diarizer not available in an allowed region")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(f"{self.url}/v1/diarize", files={"audio": ("audio.wav", wav, "audio/wav")},
                                      data={"stream_key": session_key, "stream_offset_ms": str(offset_ms),
                                            "max_speakers": str(self.max_supported)})
        except httpx.HTTPError as e:
            raise SpeechUnavailable(f"diarizer transport error: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise SpeechUnavailable(f"diarizer HTTP {r.status_code}")
        body = r.json()
        turns = [SpeakerTurn(str(t["speaker"]), offset_ms + int(t["start_ms"]), offset_ms + int(t["end_ms"]),
                             t.get("confidence"), bool(t.get("overlap", False))) for t in body.get("turns", [])]
        return DiarizationResult(turns, body.get("model_version", self.version), body.get("speaker_count_estimate"),
                                 int(body.get("max_speakers_supported", self.max_supported)))


_asr: AsrEngine | None = None
_diarizer: Diarizer | None = None


def get_asr() -> AsrEngine:
    global _asr
    if _asr is None:
        if get_settings().asr_provider == "amazon-transcribe":
            from .transcribe import AmazonTranscribeAsr

            _asr = AmazonTranscribeAsr()
        else:
            _asr = OpenAICompatibleAsr()
    return _asr


def get_diarizer() -> Diarizer:
    global _diarizer
    if _diarizer is None:
        _diarizer = HttpDiarizer() if get_settings().diarizer_url else Diarizer()
    return _diarizer


def set_speech_providers(asr: AsrEngine | None = None, diarizer: Diarizer | None = None) -> None:
    """Dependency injection point (used by tests with an explicit test audio source only; master task 5)."""
    global _asr, _diarizer
    _asr = asr
    _diarizer = diarizer
