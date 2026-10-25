"""Central config for the SAGE voice assistant. Everything is overridable via .env."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Reminder:
    time: str   # "HH:MM"
    kind: str   # "medicine" or "checkin"
    label: str  # e.g. "BP tablet"


def _parse_reminders(raw: str) -> list[Reminder]:
    out = []
    for item in filter(None, (s.strip() for s in raw.split(";"))):
        t, kind, label = (p.strip() for p in item.split("|"))
        out.append(Reminder(t, kind, label))
    return out


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:5000").rstrip("/")
DEVICE_ID = os.getenv("DEVICE_ID", "sage-home-01")
DEVICE_KEY = os.getenv("DEVICE_KEY", "")   # must match DEVICE_KEY in backend/.env

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE") or None

# Language for SAGE's own fixed phrases (reminders, "Yes?", etc.): "en" or "hi"
APP_LANGUAGE = os.getenv("APP_LANGUAGE", "en")

# Text-to-speech:
#   "elevenlabs" = most natural voice, English + Hindi (falls back to edge, then offline)
#   "edge"       = natural free online voices with Hindi support (falls back to offline)
#   "offline"    = Windows built-in voices only (English)
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge")

# ElevenLabs (used when TTS_ENGINE=elevenlabs)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # replace with a voice you pick
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")         # fast, multilingual incl. Hindi
ELEVENLABS_SPEED = float(os.getenv("ELEVENLABS_SPEED", "0.9"))                 # 0.7-1.2; slower suits elderly users
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-IN-NeerjaNeural")
TTS_VOICE_HI = os.getenv("TTS_VOICE_HI", "hi-IN-SwaraNeural")

REMINDERS = _parse_reminders(os.getenv("REMINDERS", ""))
REMINDER_MAX_ATTEMPTS = int(os.getenv("REMINDER_MAX_ATTEMPTS", "3"))
REMINDER_RETRY_SECONDS = int(os.getenv("REMINDER_RETRY_SECONDS", "120"))

# Audio capture
SAMPLE_RATE = 16000          # Whisper expects 16 kHz mono
BLOCK_SECONDS = 0.1

# Microphone: leave MIC_DEVICE empty for the Windows default, or put the number / part of the name
# that  python mic_check.py  shows (e.g. MIC_DEVICE=1  or  MIC_DEVICE=Realtek)
MIC_DEVICE = os.getenv("MIC_DEVICE", "").strip()
# How much louder than the room your voice must be to count as speech. Lower = more sensitive.
# 2.5 suits a quiet room; try 3.5-5 in a noisy hall. mic_check.py suggests a value.
MIC_SENSITIVITY = float(os.getenv("MIC_SENSITIVITY", "3.0"))
# How long the mic stays on (all overridable in .env)
LISTEN_WAIT_SECONDS = float(os.getenv("LISTEN_WAIT_SECONDS", "10"))        # wait for you to START talking
SILENCE_TO_STOP = float(os.getenv("SILENCE_TO_STOP", "2.0"))               # pause length that ENDS your sentence
MAX_UTTERANCE_SECONDS = float(os.getenv("MAX_UTTERANCE_SECONDS", "30"))    # hard cap on one sentence
FOLLOWUP_SECONDS = float(os.getenv("FOLLOWUP_SECONDS", "8"))               # keep listening after SAGE replies (0 = off)
REMINDER_LISTEN_SECONDS = float(os.getenv("REMINDER_LISTEN_SECONDS", "15"))  # wait for a reply to a reminder
