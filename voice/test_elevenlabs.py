"""Run: python test_elevenlabs.py
Lists the voices on your ElevenLabs account, then speaks a test line in English and Hindi.
If something fails it prints ElevenLabs' own explanation instead of a bare error code."""
import requests

import audio_io
import config

key = config.ELEVENLABS_API_KEY
if not key:
    raise SystemExit("ELEVENLABS_API_KEY is empty. Put it in voice\\.env (no quotes, no spaces).")
if key != key.strip() or key.startswith(("'", '"')):
    raise SystemExit("ELEVENLABS_API_KEY has spaces or quotes around it in .env. Remove them and try again.")

print(f"Using key ending in ...{key[-4:]}")

# 1. List voices (needs the 'Voices: Read' permission on the key)
r = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}, timeout=15)
if r.ok:
    print("\nVoices on your account (copy a voice_id into ELEVENLABS_VOICE_ID):")
    for v in r.json().get("voices", []):
        labels = v.get("labels") or {}
        print(f"  {v['voice_id']}  {v['name']:<22} {labels.get('gender', '')} {labels.get('accent', '')}")
else:
    print(f"\nCouldn't list voices (HTTP {r.status_code}). ElevenLabs says:\n  {r.text[:400]}")
    print("  -> If it mentions permissions, edit the key on elevenlabs.io and give it 'Voices: Read'.")
    print("  -> You can still copy a voice ID from the website: Voices > ... menu > Copy voice ID.")

# 2. Speak a test line with the voice in .env (needs the 'Text to Speech' permission)
print(f"\nTesting voice {config.ELEVENLABS_VOICE_ID} with model {config.ELEVENLABS_MODEL}...")
for line in ["Good morning! Did you take your BP tablet?", "नमस्ते! क्या आपने अपनी दवाई ले ली?"]:
    try:
        audio_io._play_mp3(audio_io._elevenlabs_synth(line))
        print(f"  OK: {line}")
    except Exception as e:
        print(f"  Speech failed: {e}")
        print("  -> HTTP 401/403: key wrong or missing 'Text to Speech' permission. "
              "HTTP 404/400 mentioning voice: the voice ID isn't on your account.")
        break
else:
    print("\nDone. If that sounded right, set TTS_ENGINE=elevenlabs and run main.py")
