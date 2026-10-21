"""Local ASR helper (faster-whisper on CPU, PyAV decoding).

Uses `BILI_ASR_MODEL` when set (a CTranslate2 model directory, or a model size
name such as "small"); otherwise falls back to the local cache dir if present,
then to faster-whisper's automatic download of "small".
"""

from __future__ import annotations

import os
import time

_MODEL_CACHE: dict = {}
_WARNED_AUTO = False
_MODEL_NAMES = {
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v1",
    "large-v2",
    "large-v3",
    "distil-small.en",
    "distil-medium.en",
    "distil-large-v2",
    "distil-large-v3",
}


def _decode_16k(path: str, sampling_rate: int = 16000):
    import av
    import numpy as np

    with av.open(path, mode="r") as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sampling_rate)
        chunks = []
        for frame in container.decode(stream):
            for out_frame in resampler.resample(frame):
                chunks.append(out_frame.to_ndarray())
        for out_frame in resampler.resample(None):
            chunks.append(out_frame.to_ndarray())
    if not chunks:
        return np.zeros(0, dtype="float32")
    arr = np.concatenate([chunk.reshape(-1) for chunk in chunks])
    return arr.astype("float32") / 32768.0


def _resolve_model_source(model: str) -> str:
    """Return a model dir / size name accepted by faster-whisper."""
    global _WARNED_AUTO
    if os.path.isdir(model):
        return model
    if model in _MODEL_NAMES:
        return model
    if not _WARNED_AUTO:
        _WARNED_AUTO = True
        print(
            f"[asr] 未找到本地模型 {model}，自动下载 faster-whisper 'small' "
            f"（可用 BILI_ASR_MODEL 指定本地 CTranslate2 目录）",
            flush=True,
        )
    return "small"


def _get_model(model_dir: str):
    key = str(model_dir)
    if key not in _MODEL_CACHE:
        from faster_whisper import WhisperModel

        source = _resolve_model_source(key)
        _MODEL_CACHE[key] = WhisperModel(
            source,
            device="cpu",
            compute_type="int8",
            cpu_threads=int(os.environ.get("BILI_ASR_THREADS", os.cpu_count() or 8)),
        )
    return _MODEL_CACHE[key]


def transcribe(path: str, model_dir: str, language: str = "zh", log=print):
    """Transcribe a media file; returns [{t, text}, ...]."""
    audio = _decode_16k(path)
    duration = len(audio) / 16000
    model = _get_model(model_dir)
    beam = int(os.environ.get("BILI_ASR_BEAM", "1"))
    segments, _info = model.transcribe(
        audio,
        language=language,
        beam_size=beam,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
        initial_prompt="以下是一段中文财经、时事或历史评论节目。",
    )
    items = []
    started = time.time()
    last_report = 0.0
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        items.append({"t": round(float(seg.start), 1), "text": text})
        if seg.end - last_report > 180:
            last_report = seg.end
            log(f"    asr {seg.end/60:.1f}/{duration/60:.1f} min ({time.time()-started:.0f}s)")
    return items
