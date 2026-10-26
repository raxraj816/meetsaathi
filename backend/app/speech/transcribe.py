"""Persistent Amazon Transcribe HTTP/2 stream with paced PCM and concurrent hypotheses.

Provider partials are explicitly distinguished from final evidence. The durable coordinator owns
replay, lease fencing, capture-clock offsets and permission checks; this adapter owns transport.
"""
from __future__ import annotations

import asyncio
import io
import wave

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler

from ..config import get_settings
from .adapters import AsrEngine, AsrSegment, SpeechUnavailable, StreamResult, Word


def language_parameters(language: str | None) -> dict:
    s = get_settings()
    options = list(dict.fromkeys(x.strip() for x in s.transcribe_language_options.split(",") if x.strip()))
    code = language or s.transcribe_language_code
    if code.lower() == "auto":
        prefixes = [x.split("-")[0].lower() for x in options]
        if not 2 <= len(options) <= 5 or len(set(prefixes)) != len(prefixes) or any("-" not in x for x in options):
            raise SpeechUnavailable("Auto language detection needs two to five configured distinct languages")
        return {"language_code": None, "identify_multiple_languages": True, "language_options": options}
    if "-" not in code:
        # Public/native sessions use short tags such as 'en'. Choose a dialect only from explicit
        # operator configuration, never from device locale or an assumed processing region.
        if s.transcribe_language_code.lower().startswith(code.lower() + "-"):
            return {"language_code": s.transcribe_language_code}
        candidates = {x for x in options if x.lower().startswith(code.lower() + "-")}
        if len(candidates) != 1:
            raise SpeechUnavailable("Session language requires an explicitly configured dialect")
        code = candidates.pop()
    return {"language_code": code}


class AmazonTranscribeAsr(AsrEngine):
    name = "amazon-transcribe"
    version = "amazon-transcribe:streaming-v2"
    supports_streaming = True

    def __init__(self, *, client=None) -> None:
        self.region = get_settings().aws_region
        self._client = client

    def available(self) -> bool:
        s = get_settings()
        return s.transcribe_enabled and self.region in s.allowed_region_set()

    async def transcribe(self, wav: bytes, *, offset_ms: int, language: str | None) -> list[AsrSegment]:
        if not self.available():
            raise SpeechUnavailable("Amazon Transcribe is not enabled in an allowed region")
        with wave.open(io.BytesIO(wav), "rb") as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != "NONE":
                raise SpeechUnavailable("Transcribe requires mono PCM16")
            rate = audio.getframerate()
            pcm = audio.readframes(audio.getnframes())
        if not pcm:
            return []
        results = []

        async def packets():
            yield pcm

        async def collect(result):
            if not result.is_partial:
                results.append(result.segment)

        await self.stream(packets(), sample_rate=rate, offset_ms=offset_ms, language=language, on_result=collect)
        return sorted(results, key=lambda x: x.start_ms)

    async def stream(self, packets, *, sample_rate: int, offset_ms: int, language: str | None, on_result) -> None:
        if not self.available():
            raise SpeechUnavailable("Amazon Transcribe is not enabled in an allowed region")
        if sample_rate < 8000 or sample_rate > 48000:
            raise SpeechUnavailable("Unsupported PCM sample rate")
        s = get_settings()
        params = language_parameters(language)
        code = params["language_code"]
        params.update({"media_sample_rate_hz": sample_rate, "media_encoding": "pcm",
                  "enable_partial_results_stabilization": True, "partial_results_stability": "medium"}
        )
        final_ids: set[str] = set()
        input_done = asyncio.Event()

        class Collector(TranscriptResultStreamHandler):
            async def handle_transcript_event(self, event):
                for result in event.transcript.results:
                    if not result.alternatives:
                        continue
                    alt = result.alternatives[0]
                    if not (alt.transcript or "").strip() or result.start_time is None or result.end_time is None:
                        continue
                    start, end = offset_ms + round(result.start_time * 1000), offset_ms + round(result.end_time * 1000)
                    rid = result.result_id or f"{start}:{end}"
                    if end <= start or start < offset_ms or rid in final_ids:
                        continue
                    words = [Word(i.content, offset_ms + round(i.start_time * 1000), offset_ms + round(i.end_time * 1000))
                             for i in alt.items or [] if i.item_type == "pronunciation" and i.content
                             and i.start_time is not None and i.end_time is not None]
                    confidences = [i.confidence for i in alt.items or [] if i.confidence is not None]
                    seg = AsrSegment(start, end, alt.transcript.strip(),
                                     sum(confidences) / len(confidences) if confidences else None,
                                     result.language_code or code, words)
                    await on_result(StreamResult(rid, seg, result.is_partial))
                    if not result.is_partial:
                        final_ids.add(rid)

        stream = None
        try:
            async with asyncio.timeout(s.asr_stream_max_s + s.speech_timeout_s + s.asr_stream_idle_s):
                client = self._client or TranscribeStreamingClient(region=self.region)
                async with asyncio.timeout(s.speech_timeout_s):
                    stream = await client.start_stream_transcription(**params)

                async def send():
                    size = sample_rate // 10 * 2  # 100 ms, even PCM sample boundaries
                    deadline = asyncio.get_running_loop().time()
                    try:
                        async for pcm in packets:
                            if len(pcm) % 2:
                                raise SpeechUnavailable("Incomplete PCM sample")
                            # A capture/upload pause must not cause a catch-up burst into AWS.
                            deadline = max(deadline, asyncio.get_running_loop().time())
                            for pos in range(0, len(pcm), size):
                                await asyncio.sleep(max(0, deadline - asyncio.get_running_loop().time()))
                                part = pcm[pos:pos + size]
                                async with asyncio.timeout(s.speech_timeout_s):
                                    await stream.input_stream.send_audio_event(audio_chunk=part)
                                deadline += len(part) / (sample_rate * 2)
                    finally:
                        input_done.set()
                        async with asyncio.timeout(min(5, s.speech_timeout_s)):
                            await stream.input_stream.end_stream()

                async def receive():
                    await Collector(stream.output_stream).handle_events()
                    if not input_done.is_set():
                        raise SpeechUnavailable("Transcribe closed before input drained")

                async def drain_timeout():
                    await input_done.wait()
                    await asyncio.sleep(s.speech_timeout_s)
                    raise SpeechUnavailable("Transcribe did not drain final results")

                async with asyncio.TaskGroup() as tasks:
                    watchdog = tasks.create_task(drain_timeout())
                    tasks.create_task(send())
                    receiver = tasks.create_task(receive())
                    await receiver
                    watchdog.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise SpeechUnavailable(f"Transcribe failed: {type(e).__name__}") from e
