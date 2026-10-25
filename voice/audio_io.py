"""Microphone capture (energy-based endpointing), Whisper STT, and TTS (ElevenLabs / Edge / offline).
Audio stays in RAM and is discarded after transcription. Nothing is written to disk."""
import asyncio
import io
import queue
import re

import av
import numpy as np
import pyttsx3
import requests
import sounddevice as sd
from faster_whisper import WhisperModel

import config

_whisper = None
_noise_floor = 0.01


def mic_device():
    """MIC_DEVICE can be a device number or part of its name; empty = system default."""
    d = config.MIC_DEVICE
    if not d:
        return None
    if d.isdigit():
        return int(d)
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and d.lower() in dev["name"].lower():
            return i
    print(f"[mic] MIC_DEVICE '{d}' not found; using the default microphone. Run mic_check.py to see the list.")
    return None


def load_models():
    global _whisper
    print(f"[stt] loading Whisper '{config.WHISPER_MODEL}' (first run downloads it)...")
    _whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    dev = mic_device()
    name = sd.query_devices(dev if dev is not None else sd.default.device[0])["name"]
    print(f"[mic] using: {name}")
    calibrate_noise()


def calibrate_noise(seconds: float = 1.5):
    """Measure room noise. Uses the quieter blocks, so a cough or a word during calibration doesn't skew it."""
    global _noise_floor
    audio = sd.rec(int(seconds * config.SAMPLE_RATE), samplerate=config.SAMPLE_RATE,
                   channels=1, dtype="float32", device=mic_device())
    sd.wait()
    block = int(config.BLOCK_SECONDS * config.SAMPLE_RATE)
    rms = [float(np.sqrt(np.mean(audio[i:i + block] ** 2))) for i in range(0, len(audio) - block, block)]
    _noise_floor = float(np.percentile(rms, 30)) + 1e-4 if rms else 0.01
    print(f"[mic] room noise = {_noise_floor:.4f}  (speech threshold = {_start_threshold(_noise_floor):.4f})")
    if _noise_floor < 0.0003:
        print("[mic] almost no signal from the microphone: check it's not muted, or set MIC_DEVICE (python mic_check.py)")


from collections import deque

_recent = deque(maxlen=10)   # last ~1 s of sound between sentences, to track the room as it changes


def _room_level():
    """Current room noise: the quieter part of the last second (speech is louder and comes in bursts)."""
    if len(_recent) >= 5:
        return max(float(np.percentile(_recent, 20)), 1e-4)
    return _noise_floor


def _start_threshold(room=None):
    return max((room or _room_level()) * config.MIC_SENSITIVITY, 0.008)


def _stop_threshold(room):
    # Hysteresis: once you're talking, a softer level still counts as speech, so pauses
    # between words don't cut you off.
    return max(room * (1 + (config.MIC_SENSITIVITY - 1) * 0.5), 0.005)


def record_utterance(wait_for_speech: float = config.LISTEN_WAIT_SECONDS) -> np.ndarray | None:
    """Wait up to `wait_for_speech` s for speech to start, then record until silence.
    Returns float32 mono audio at 16 kHz, or None if nobody spoke."""
    global _noise_floor
    block = int(config.BLOCK_SECONDS * config.SAMPLE_RATE)
    q: queue.Queue = queue.Queue()

    def cb(indata, frames, t, status):
        q.put(indata[:, 0].copy())

    pre_roll = []                     # keep ~0.3 s before speech so the first syllable isn't clipped
    chunks, waited, total, loud_run, silent_time = [], 0.0, 0.0, 0, 0.0
    started, room_at_start = False, None
    speech_levels = deque(maxlen=15)  # last 1.5 s while recording
    print(f"[mic] listening (up to {wait_for_speech:.0f}s)...")
    with sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=block, callback=cb, device=mic_device()):
        while True:
            chunk = q.get()
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if not started:
                waited += config.BLOCK_SECONDS
                pre_roll = (pre_roll + [chunk])[-3:]
                room = _room_level()
                loud = rms > _start_threshold(room)
                _recent.append(rms)           # learn the room continuously (adapts within ~1 s if it gets louder)
                loud_run = loud_run + 1 if loud else 0
                if loud_run >= 2:              # 0.2 s of sound: real speech, not a click or a bump
                    started, room_at_start = True, room
                    chunks = list(pre_roll)
                    continue
                if waited >= wait_for_speech - 1e-6:
                    print("[mic] off (no speech heard)")
                    return None
                continue
            chunks.append(chunk)
            total += config.BLOCK_SECONDS
            speech_levels.append(rms)
            stop = _stop_threshold(room_at_start)
            if len(speech_levels) >= 10:
                # If the room itself got louder, steady background sound still counts as "you stopped talking".
                stop = max(stop, float(np.percentile(speech_levels, 20)) * 1.25)
            silent_time = 0.0 if rms > stop else silent_time + config.BLOCK_SECONDS
            if silent_time >= config.SILENCE_TO_STOP - 1e-6:
                break
            if total >= config.MAX_UTTERANCE_SECONDS:
                print("[mic] stopped at the time limit: the room may be too noisy. Try a higher MIC_SENSITIVITY in .env")
                break
    tail = int(config.SILENCE_TO_STOP / config.BLOCK_SECONDS)
    _recent.extend(list(speech_levels)[-tail:])   # the quiet tail tells us the current room level
    _noise_floor = _room_level()
    print(f"[mic] off ({total:.1f}s recorded)")
    return np.concatenate(chunks)


# Whisper sometimes "hears" these during silence or noise; never treat them as the user speaking.
_PHANTOMS = {"thank you", "thank you.", "thanks for watching", "thanks for watching!", "you", "bye", "bye.",
             "subtitles by the amara.org community", ".", "...", "धन्यवाद", "शुक्रिया"}


def _prompt():
    """Hint the vocabulary SAGE expects, which makes short replies far more accurate."""
    meds = ", ".join(r.label for r in config.REMINDERS)
    return f"Yes, I took my {meds}. Haan, le li. Nahi. Help me. Bachao. Good morning, SAGE."


def transcribe(audio: np.ndarray) -> str:
    import time
    t0 = time.time()
    opts = dict(beam_size=1, vad_filter=True, without_timestamps=True, condition_on_previous_text=False,
                initial_prompt=_prompt(), no_speech_threshold=0.6)
    segments, info = _whisper.transcribe(audio, language=config.WHISPER_LANGUAGE, **opts)
    text = " ".join(s.text.strip() for s in segments).strip()
    # Whisper often mistakes spoken Hindi for Urdu and writes it in Urdu script; redo it as Hindi.
    if config.WHISPER_LANGUAGE is None and info.language == "ur":
        segments, _ = _whisper.transcribe(audio, language="hi", **opts)
        text = " ".join(s.text.strip() for s in segments).strip()
    if text.lower().strip() in _PHANTOMS:
        text = ""
    lang = config.WHISPER_LANGUAGE or info.language
    print(f"[stt] {time.time() - t0:.1f}s ({lang}): {text or '(nothing clear)'}")
    return text


def listen(wait_for_speech: float = config.LISTEN_WAIT_SECONDS) -> str:
    audio = record_utterance(wait_for_speech)
    if audio is None:
        return ""
    text = transcribe(audio)
    del audio  # privacy: raw audio is dropped immediately
    return text


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _speak_offline(text: str):
    # Re-init each time: avoids pyttsx3's known hang on repeated runAndWait() on Windows
    engine = pyttsx3.init()
    engine.setProperty("rate", 150)  # slower speech for elderly users
    engine.say(text)
    engine.runAndWait()
    engine.stop()


async def _edge_synth(text: str, voice: str) -> bytes:
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate="-10%", connect_timeout=5)
    data = b""
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            data += chunk["data"]
    return data


def _play_mp3(data: bytes, rate: int = 24000):
    container = av.open(io.BytesIO(data))
    resampler = av.AudioResampler(format="flt", layout="mono", rate=rate)
    parts = []
    for frame in container.decode(audio=0):
        for f in resampler.resample(frame):
            parts.append(f.to_ndarray().reshape(-1))
    for f in resampler.resample(None):  # flush
        parts.append(f.to_ndarray().reshape(-1))
    container.close()
    if parts:
        sd.play(np.concatenate(parts), rate)
        sd.wait()


_tts_cache: dict[str, bytes] = {}  # repeated phrases ("Yes?", reminders) cost credits only once


def _elevenlabs_synth(text: str) -> bytes:
    if text in _tts_cache:
        return _tts_cache[text]
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
        json={
            "text": text,
            "model_id": config.ELEVENLABS_MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": config.ELEVENLABS_SPEED},
        },
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
    if len(text) <= 80:  # only cache short, likely-repeated phrases
        _tts_cache[text] = r.content
    return r.content


def speak(text: str):
    print(f"SAGE: {text}")
    if config.TTS_ENGINE == "elevenlabs":
        try:
            _play_mp3(_elevenlabs_synth(text))
            return
        except Exception as e:
            print(f"[tts] ElevenLabs failed ({e}); trying the free online voice")
    if config.TTS_ENGINE in ("edge", "elevenlabs"):
        voice = config.TTS_VOICE_HI if _DEVANAGARI.search(text) else config.TTS_VOICE_EN
        try:
            _play_mp3(asyncio.run(_edge_synth(text, voice)))
            return
        except Exception as e:
            print(f"[tts] online voice failed ({e}); using offline voice")
    _speak_offline(text)
