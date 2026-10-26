"""PCM helpers: WAV framing and signal level used to avoid sending silence to ASR (Whisper-class models
hallucinate text on silence; master J3 "do not hallucinate remote voices")."""
from __future__ import annotations

import io
import math
import struct
import wave


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def rms_dbfs(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return -120.0
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    acc = 0.0
    for v in samples:
        acc += v * v
    rms = math.sqrt(acc / n)
    return -120.0 if rms <= 0 else 20 * math.log10(rms / 32768.0)


def speech_likely(pcm: bytes, threshold_dbfs: float = -50.0) -> bool:
    return rms_dbfs(pcm) > threshold_dbfs


def quality_label(dbfs: float) -> str:
    if dbfs < -55:
        return "SILENT_OR_BLOCKED"
    if dbfs < -42:
        return "POOR"
    return "GOOD"
