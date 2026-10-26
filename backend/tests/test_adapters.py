"""Provider adapter contracts that don't need a network: response parsing, alignment, silence gating."""
from __future__ import annotations

from app.speech.adapters import AsrSegment, DiarizationResult, SpeakerTurn, parse_verbose_json
from app.speech.aligner import UNASSIGNED, align, speaker_alias
from app.speech.audio import pcm_to_wav, quality_label, rms_dbfs, speech_likely

from .conftest import silence_pcm, tone_pcm

VERBOSE_JSON = {  # shape of an OpenAI-compatible /audio/transcriptions verbose_json response
    "task": "transcribe", "language": "english", "duration": 6.0, "text": "We need per-customer keys. Thanks.",
    "segments": [
        {"id": 0, "seek": 0, "start": 0.24, "end": 2.9, "text": " We need per-customer keys.", "tokens": [1, 2],
         "temperature": 0.0, "avg_logprob": -0.21, "compression_ratio": 1.1, "no_speech_prob": 0.01},
        {"id": 1, "seek": 300, "start": 3.1, "end": 3.6, "text": " Thanks.", "tokens": [3], "temperature": 0.0,
         "avg_logprob": -1.9, "compression_ratio": 0.9, "no_speech_prob": 0.92},
    ],
    "words": [{"word": "We", "start": 0.24, "end": 0.4}, {"word": "need", "start": 0.4, "end": 0.7},
              {"word": "Thanks", "start": 3.1, "end": 3.6}],
}


def test_verbose_json_parsing_offsets_confidence_and_hallucination_filter():
    segs = parse_verbose_json(VERBOSE_JSON, offset_ms=10_000)
    assert len(segs) == 1  # second segment has no_speech_prob 0.92 -> dropped as likely hallucination
    s = segs[0]
    assert (s.start_ms, s.end_ms, s.text) == (10_240, 12_900, "We need per-customer keys.")
    assert 0.75 < s.confidence < 0.85 and s.language == "english"
    assert [w.text for w in s.words] == ["We", "need"]


def test_aligner_dominant_speaker_overlap_unassigned_and_own_voice():
    seg_a = AsrSegment(0, 2000, "first", 0.9)
    seg_b = AsrSegment(2000, 4000, "both talking", 0.9)
    seg_c = AsrSegment(6000, 7000, "our tts", 0.9)
    seg_d = AsrSegment(9000, 9500, "nobody", 0.9)
    diar = DiarizationResult([SpeakerTurn("spk_0", 0, 3200, 0.9), SpeakerTurn("spk_1", 2600, 4000, 0.8),
                              SpeakerTurn("spk_0", 6000, 7000, 0.9)], "nemotron-test", 2, 8)
    out = align([seg_a, seg_b, seg_c, seg_d], diar, tts_windows=[{"start_ms": 5900, "end_ms": 7100}])
    assert [o.segment.text for o in out] == ["first", "both talking", "nobody"]  # own TTS never becomes a participant
    assert out[0].speaker == "spk_0" and not out[0].overlap
    assert out[1].overlap and out[1].speaker_confidence < 0.6  # overlap => provisional, reduced confidence
    assert out[2].speaker == UNASSIGNED
    known: dict[str, str] = {}
    assert [speaker_alias(x, known) for x in ("spk_7", "spk_2", "spk_7", UNASSIGNED)] == ["Speaker A", "Speaker B", "Speaker A", "Unassigned"]


def test_no_diarizer_means_unassigned_never_named():
    out = align([AsrSegment(0, 1000, "hello", 0.9)], None, [])
    assert out[0].speaker == UNASSIGNED and out[0].speaker_confidence is None


def test_silence_gate_and_quality_labels():
    assert not speech_likely(silence_pcm())
    assert speech_likely(tone_pcm())
    assert quality_label(rms_dbfs(silence_pcm())) == "SILENT_OR_BLOCKED"
    wav = pcm_to_wav(tone_pcm(500), 16000)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
