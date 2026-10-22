"""Decode PCM WAV containers and normalize model input to mono 16 kHz."""

import io
import math
import wave

import numpy as np


def decode_waveform(audio: bytes, sample_rate: int = 16000) -> np.ndarray:
    channels, width = 1, 2
    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        with wave.open(io.BytesIO(audio), "rb") as wav:
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            audio = wav.readframes(wav.getnframes())
    if sample_rate <= 0 or channels <= 0:
        raise ValueError("Invalid audio sample rate or channel count")
    if width == 1:
        waveform = (np.frombuffer(audio, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif width in (2, 4):
        waveform = np.frombuffer(audio, dtype=f"<i{width}").astype(np.float32) / (2 ** (width * 8 - 1))
    elif width == 3:
        octets = np.frombuffer(audio, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        values = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
        values = (values ^ 0x800000) - 0x800000
        waveform = values.astype(np.float32) / 8388608
    else:
        raise ValueError(f"Unsupported PCM sample width: {width}")
    waveform = waveform.reshape(-1, channels).mean(axis=1)
    if sample_rate != 16000 and waveform.size:
        from scipy.signal import resample_poly

        divisor = math.gcd(sample_rate, 16000)
        waveform = resample_poly(waveform, 16000 // divisor, sample_rate // divisor)
    return np.ascontiguousarray(waveform, dtype=np.float32)
