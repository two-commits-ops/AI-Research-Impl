"""Local text-to-speech via Kokoro-82M (Apache 2.0), running on Apple Silicon
through mlx-audio. Fully local, no API key, no account.

The model is loaded once at import time and reused for every call — loading
from HF cache takes well under a second, but reloading it per request would
add that cost to every single narration/answer.
"""
import os
import shutil
import tempfile
import threading
import wave

from mlx_audio.tts.generate import generate_audio, load_model

MODEL_ID = "prince-canuma/Kokoro-82M"
_model = None
# One shared MLX model instance is reused across every call (loading it
# per-request would be far slower) — but concurrent inference calls into
# that SAME instance from different threads is a real crash risk (native
# memory corruption, not a Python exception you can catch). This app calls
# into Kokoro from several threads at once by design (background prefetch
# for the current/next page, plus whatever the browser just asked for
# directly), so every call is serialized through this lock rather than
# relying on it never actually overlapping.
_model_lock = threading.Lock()

# A curated subset of Kokoro's ~50 voices, presented as "tones" rather than
# raw voice ids — this is the "theme" picker in the UI.
TONES = {
    "warm": "af_heart",
    "calm": "af_nova",
    "bright": "af_bella",
    "deep": "am_onyx",
    "classic": "am_michael",
}
DEFAULT_TONE = "warm"


def _get_model():
    global _model
    if _model is None:
        _model = load_model(MODEL_ID)
    return _model


def _generate_chunks(text: str, tmp_prefix: str, tone: str) -> list[str]:
    """Runs Kokoro once and returns every chunk file it wrote, in order.

    Kokoro silently splits long text into multiple `_000`, `_001`, ...
    files on its own (a real limit on how much it will synthesize in one
    go) — a caller that only reads `_000` quietly loses the rest of the
    narration. This was a real bug here: a ~100-word page was split into a
    26.6s and a 6.1s clip, and only the first was ever played, so playback
    always stopped a sentence or two before the end. Collecting every
    chunk fixes that.
    """
    if not text.strip():
        text = "..."
    voice = TONES.get(tone, TONES[DEFAULT_TONE])
    with _model_lock:
        generate_audio(
            text=text,
            model=_get_model(),
            voice=voice,
            file_prefix=tmp_prefix,
            audio_format="wav",
            save=True,
            verbose=False,
        )
    chunks = []
    i = 0
    while os.path.exists(f"{tmp_prefix}_{i:03d}.wav"):
        chunks.append(f"{tmp_prefix}_{i:03d}.wav")
        i += 1
    return chunks


def synthesize(text: str, out_path: str, tone: str = DEFAULT_TONE) -> None:
    """Writes narration audio for `text` to `out_path` (a single .wav
    file) — used where only one clip makes sense (fillers, Q&A answers,
    the document overview). Concatenates every chunk Kokoro produced.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        chunks = _generate_chunks(text, os.path.join(tmp_dir, "out"), tone)
        if len(chunks) == 1:
            shutil.move(chunks[0], out_path)
            return
        with wave.open(out_path, "wb") as out_wav:
            for i, chunk_path in enumerate(chunks):
                with wave.open(chunk_path) as chunk_wav:
                    if i == 0:
                        out_wav.setparams(chunk_wav.getparams())
                    out_wav.writeframes(chunk_wav.readframes(chunk_wav.getnframes()))


def synthesize_segments(text: str, out_dir: str, prefix: str, tone: str = DEFAULT_TONE) -> list[dict]:
    """One model call per page, but returns EVERY chunk Kokoro produced as
    its own segment — not collapsed into one file. The frontend already
    plays a segment list back-to-back, so a long page plays in full
    (no more silently-dropped final chunk), and it's also what makes
    paragraph-by-paragraph highlighting possible later: each segment is a
    natural break point, not an arbitrary mid-sentence cut.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        chunk_paths = _generate_chunks(text, os.path.join(tmp_dir, "out"), tone)
        segments = []
        for i, chunk_path in enumerate(chunk_paths):
            filename = f"{prefix}_{i}.wav"
            shutil.move(chunk_path, os.path.join(out_dir, filename))
            segments.append({"text": text if i == 0 else "", "filename": filename})
        return segments
