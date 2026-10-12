"""Audio capture, loading and feature extraction (no network, no surprises)."""

from __future__ import annotations

import math
import struct
import wave
from collections.abc import Sequence
from typing import NamedTuple

DEFAULT_SAMPLE_RATE = 16_000


class AudioBuffer(NamedTuple):
    samples: Sequence[float]   # normalized to [-1.0, 1.0]
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0


# --------------------------------------------------------------------------- #
# capture / io
# --------------------------------------------------------------------------- #

def load(path: str) -> AudioBuffer:
    """Load a wav/flac/... file, converting with ffmpeg if needed."""
    try:
        return _load_wav(path)
    except wave.Error:
        return _load_with_ffmpeg(path)


def _load_wav(path: str) -> AudioBuffer:
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise wave.Error("not 16-bit PCM")

    fmt = f"<{len(frames) // 2}h"
    ints = struct.unpack(fmt, frames[: len(frames) // 2 * 2])
    if channels > 1:
        ints = tuple(
            sum(ints[i : i + channels]) / channels
            for i in range(0, len(ints), channels)
        )
    samples = [s / 32768.0 for s in ints]
    if rate != DEFAULT_SAMPLE_RATE:
        samples = _resample(samples, rate, DEFAULT_SAMPLE_RATE)
        rate = DEFAULT_SAMPLE_RATE
    return AudioBuffer(samples, rate)


def _resample(samples: Sequence[float], src: int, dst: int) -> list[float]:
    if src == dst or not samples:
        return list(samples)
    ratio = dst / src
    n_out = int(len(samples) * ratio)
    out: list[float] = []
    for i in range(n_out):
        pos = i / ratio
        i0 = int(pos)
        i1 = min(i0 + 1, len(samples) - 1)
        frac = pos - i0
        out.append(samples[i0] * (1 - frac) + samples[i1] * frac)
    return out


def _load_with_ffmpeg(path: str) -> AudioBuffer:
    import os
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found; install it or pass a 16-bit WAV")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
             "-ac", "1", "-ar", str(DEFAULT_SAMPLE_RATE), out],
            check=True,
        )
        return _load_wav(out)
    finally:
        os.unlink(out)


def record(seconds: float, sample_rate: int = DEFAULT_SAMPLE_RATE) -> AudioBuffer:
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:  # pragma: no cover - hardware path
        raise RuntimeError(
            "recording needs the 'sounddevice' + 'numpy' extras: pip install -e '.[audio]'"
        ) from exc

    frames = int(seconds * sample_rate)
    raw = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    samples = np.asarray(raw, dtype="float32").reshape(-1)
    return AudioBuffer([float(x) for x in samples], sample_rate)


def save_wav(buffer: AudioBuffer, path: str) -> None:
    ints = [int(max(-1.0, min(1.0, s)) * 32767) for s in buffer.samples]
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(buffer.sample_rate)
        wf.writeframes(struct.pack(f"<{len(ints)}h", *ints))


# --------------------------------------------------------------------------- #
# features
# --------------------------------------------------------------------------- #

def rms(buffer: AudioBuffer) -> float:
    if not buffer.samples:
        return 0.0
    return math.sqrt(sum(s * s for s in buffer.samples) / len(buffer.samples))


def zero_crossing_rate(buffer: AudioBuffer) -> float:
    samples = list(buffer.samples)
    if len(samples) < 2:
        return 0.0
    crossings = sum(
        1 for a, b in zip(samples, samples[1:], strict=False) if (a >= 0) != (b >= 0)
    )
    return crossings / (len(samples) - 1)


def _fft_mag(buffer: AudioBuffer) -> list[float]:
    """Naive DFT magnitude (only used when numpy is unavailable)."""
    n = min(len(buffer.samples), 4096)
    if n < 8:
        return []
    step = max(1, len(buffer.samples) // n)
    data = buffer.samples[::step][:n]
    mags = []
    for k in range(n // 2):
        re = im = 0.0
        for t, x in enumerate(data):
            ang = 2 * math.pi * k * t / n
            re += x * math.cos(ang)
            im -= x * math.sin(ang)
        mags.append(math.hypot(re, im))
    return mags


def _spectrum(buffer: AudioBuffer) -> tuple[list[float], float]:
    try:
        import numpy as np

        data = np.asarray(buffer.samples, dtype=float)
        if data.size < 8:
            return [], buffer.sample_rate
        window = np.hanning(data.size)
        spec = np.abs(np.fft.rfft(data * window))
        freqs = np.fft.rfftfreq(data.size, 1.0 / buffer.sample_rate)
        return spec.tolist(), float(freqs[1] - freqs[0]) if len(freqs) > 1 else 0.0
    except ImportError:
        mags = _fft_mag(buffer)
        bin_hz = (buffer.sample_rate / 2) / len(mags) if mags else 0.0
        return mags, bin_hz


def peak_frequency(buffer: AudioBuffer) -> float:
    mags, bin_hz = _spectrum(buffer)
    if not mags or bin_hz == 0:
        return 0.0
    return mags.index(max(mags)) * bin_hz


def spectral_centroid(buffer: AudioBuffer) -> float:
    mags, bin_hz = _spectrum(buffer)
    total = sum(mags)
    if total <= 0:
        return 0.0
    return sum(i * bin_hz * m for i, m in enumerate(mags)) / total


def spectral_flatness(buffer: AudioBuffer) -> float:
    """1.0 = broadband noise (rain/stream), 0.0 = tonal (a bird whistle)."""
    mags, _ = _spectrum(buffer)
    mags = [m + 1e-9 for m in mags]
    if not mags:
        return 0.0
    arith = sum(mags) / len(mags)
    geo = math.exp(sum(math.log(m) for m in mags) / len(mags))
    return geo / arith


def band_energies(buffer: AudioBuffer, bands: int = 16) -> list[float]:
    """Log-spaced band energies (dB, peak-normalized) — an acoustic fingerprint.

    Used to build offline embeddings so we can find "a sound like this one"
    without any cloud service.
    """
    mags, _ = _spectrum(buffer)
    if not mags:
        return [0.0] * bands
    n = len(mags)
    edges = [int((n - 1) * (i / bands) ** 2) for i in range(bands + 1)]
    out: list[float] = []
    for i in range(bands):
        lo = edges[i]
        hi = max(lo + 1, edges[i + 1])
        band = mags[lo:hi]
        energy = sum(band) / len(band) if band else 0.0
        out.append(10 * math.log10(energy + 1e-9))
    peak = max(out) if out else 0.0
    return [round(v - peak, 4) for v in out]


def spectrogram_png(buffer: AudioBuffer, path: str) -> str | None:
    try:
        import matplotlib
        import numpy as np
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    data = np.asarray(buffer.samples, dtype=float)
    if data.size < 512:
        return None
    fig, ax = plt.subplots(figsize=(8, 2.5), dpi=110)
    ax.specgram(data, Fs=buffer.sample_rate, NFFT=1024, noverlap=768, cmap="magma")
    ax.set_xlabel("seconds")
    ax.set_ylabel("Hz")
    ax.set_title("WanderEar · soundscape")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path