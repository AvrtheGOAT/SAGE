"""
mic_check.py: find the right microphone and sensitivity for SAGE.

Run from C:\\SAGE\\voice:   python mic_check.py
  1. lists every microphone (set MIC_DEVICE in .env to the number you want)
  2. measures the room (stay quiet), then your voice (talk normally)
  3. suggests MIC_SENSITIVITY for this room
  4. transcribes one test sentence so you can check speed and accuracy
"""
import time

import numpy as np
import sounddevice as sd

import audio_io
import config

RATE, BLOCK = config.SAMPLE_RATE, int(config.BLOCK_SECONDS * config.SAMPLE_RATE)

print("Microphones on this laptop:")
default_in = sd.default.device[0]
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        print(f"  [{i}] {d['name']}{'   <- Windows default' if i == default_in else ''}")
dev = audio_io.mic_device()
print(f"\nTesting: [{dev if dev is not None else default_in}] "
      f"{sd.query_devices(dev if dev is not None else default_in)['name']}  (change with MIC_DEVICE in .env)\n")


def measure(seconds, label):
    levels = []
    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK, device=dev) as s:
        end = time.time() + seconds
        while time.time() < end:
            chunk, _ = s.read(BLOCK)
            rms = float(np.sqrt(np.mean(chunk[:, 0] ** 2)))
            levels.append(rms)
            bar = "#" * min(50, int(rms * 1000))
            print(f"\r  {label:<14} {rms:.4f} |{bar:<50}|", end="", flush=True)
    print()
    return np.array(levels)


input("Step 1: stay QUIET for 3 seconds. Press Enter to start...")
quiet = measure(3, "room noise")
input("Step 2: talk NORMALLY for 4 seconds, as Kamala would (e.g. 'haan, maine dawai le li'). Press Enter...")
voice = measure(4, "your voice")

room = float(np.percentile(quiet, 30)) + 1e-4
speech = float(np.percentile(voice, 80))
ratio = speech / room
print(f"\nRoom noise: {room:.4f}   Your voice: {speech:.4f}   Voice is {ratio:.1f}x louder than the room")
if speech < 0.002:
    print("=> The mic barely hears you. It may be muted, too far away, or the wrong device: pick another MIC_DEVICE.")
elif ratio < 2:
    print("=> Too noisy to tell your voice from the room. Move the mic closer to your mouth, use a headset,")
    print("   or find a quieter corner. SAGE will struggle here.")
else:
    suggest = round(max(2.0, min(6.0, ratio * 0.45)), 1)
    print(f"=> Put this in voice\\.env:   MIC_SENSITIVITY={suggest}")
    print("   (lower = picks up softer speech; higher = ignores more background noise)")

if input("\nStep 3: test speech recognition too? (y/n) ").strip().lower() == "y":
    audio_io.load_models()
    print("Say one sentence now...")
    print("SAGE heard:", repr(audio_io.listen(8)))
    print("If it was slow, try WHISPER_MODEL=base (faster) in .env. If the language was wrong,")
    print("set WHISPER_LANGUAGE=hi (Hindi/Hinglish) or WHISPER_LANGUAGE=en (English).")
