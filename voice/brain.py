"""The reasoning layer: Gemini with function calling, plus offline fallbacks so safety
features still work when the internet/API is down or the free-tier limit is hit."""
import re
from datetime import datetime

from google import genai
from google.genai import types

import backend_client
import config
from phrases import t

client = genai.Client(api_key=config.GEMINI_API_KEY)

SYSTEM_PROMPT = """You are SAGE, a warm, patient voice companion for an elderly person living at home in India.
Your replies are spoken aloud by text-to-speech, so:
- Use 1-2 short, simple sentences. No lists, emojis, or markdown.
- Reply in the same language the person used. If they speak Hindi or Hinglish, reply in simple Hindi
  written in Devanagari script (so the Hindi voice can read it). If they speak English, reply in English.

Safety rules:
- If the person says they fell, are hurt, can't breathe, have chest pain, feel very unwell, or ask for help
  urgently, call trigger_emergency immediately. This alerts their family, who decide whether to call an
  ambulance. Never say you have called an ambulance yourself.
- Never diagnose or give medical or dosing advice. For health worries, suggest telling family or their doctor.
- If they say they took a medicine, call log_medicine_taken.
- If they tell you how they are feeling in a morning check-in, call log_checkin.

Current local time: {now}."""

TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="trigger_emergency",
        description="Immediately alert the family/caregiver. Use for falls, injury, breathing trouble, "
                    "chest pain, or any urgent request for help. Family decides on calling an ambulance.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"reason": types.Schema(type="STRING", description="Short reason, e.g. 'reported a fall'")},
            required=["reason"],
        ),
    ),
    types.FunctionDeclaration(
        name="log_medicine_taken",
        description="Record that the person confirmed taking a medicine.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"medicine": types.Schema(type="STRING")},
            required=["medicine"],
        ),
    ),
    types.FunctionDeclaration(
        name="log_checkin",
        description="Record the outcome of a daily check-in.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"mood": types.Schema(type="STRING", enum=["good", "okay", "unwell"])},
            required=["mood"],
        ),
    ),
])

# Unambiguous phrases that trigger an alert locally, before (and regardless of) the API.
EMERGENCY_PATTERNS = [
    r"\bemergency\b", r"\bambulance\b", r"\bbachao\b",
    r"\bi (have )?fallen\b", r"\bi fell\b", r"\bgir (gaya|gayi)\b",
    r"\bcan'?t breathe\b", r"\bchest pain\b",
    # Devanagari (Whisper writes Hindi speech this way)
    r"बचाओ", r"एम्बुलेंस", r"इमरजेंसी", r"गिर गया", r"गिर गई", r"गिर गयी", r"सीने में दर्द", r"सांस नहीं",
]

_history: list[types.Content] = []  # text-only turns, so trimming never breaks function-call pairs
MAX_HISTORY_TURNS = 8


def _text(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part.from_text(text=text)])


def _run_tool(name: str, args: dict) -> str:
    if name == "trigger_emergency":
        backend_client.post_event("emergency", reason=args.get("reason", ""), source="voice")
        return "Family has been alerted."
    if name == "log_medicine_taken":
        backend_client.post_event("medicine_confirmed", medicine=args.get("medicine", ""), source="voice")
        return "Logged."
    if name == "log_checkin":
        backend_client.post_event("checkin_completed", mood=args.get("mood", "okay"))
        return "Logged."
    return "Unknown tool."


def is_obvious_emergency(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in EMERGENCY_PATTERNS)


def respond(user_text: str, context: str | None = None) -> str:
    """Send one user utterance to Gemini, run any functions it calls, return the spoken reply.
    `context` tells the model what just happened (e.g. 'this is the morning check-in')."""
    content = f"[{context}] {user_text}" if context else user_text
    contents = _history + [_text("user", content)]
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(now=datetime.now().strftime("%A %d %B, %I:%M %p")),
        tools=[TOOLS],
        max_output_tokens=1024,  # headroom: thinking tokens count toward this on newer models
    )

    try:
        for _ in range(3):  # at most 3 function-call round-trips per utterance
            resp = client.models.generate_content(model=config.GEMINI_MODEL, contents=contents, config=cfg)
            calls = resp.function_calls or []
            if not calls:
                break
            contents.append(resp.candidates[0].content)  # keep the model turn as-is (preserves thought signatures)
            contents.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=c.name, response={"result": _run_tool(c.name, dict(c.args or {}))})
                for c in calls
            ]))
        reply = (resp.text or "").strip() or "Okay."
    except Exception as e:  # network down, 429 rate limit, bad key, etc.
        print(f"[brain] Gemini error: {e}")
        # Offline fallback: still honour a plain cry for help
        if re.search(r"\bhelp\b|\bmadad\b|मदद|बचाओ", user_text.lower()):
            backend_client.post_event("emergency", reason="asked for help (offline mode)", source="voice")
            return t("offline_help")
        return t("offline_error")

    _history.extend([_text("user", content), _text("model", reply)])
    del _history[:-2 * MAX_HISTORY_TURNS]
    return reply


YES = r"\b(yes|yeah|haan|ha|han|done|took|taken|le li|le liya|kha li|kha liya)\b|हाँ|हां|ले ली|ले लिया|खा ली|खा लिया"
NO = r"\b(no|nahi|nahin|not yet|abhi nahi|forgot|bhool)\b|नहीं|नही|अभी नहीं|भूल"


def classify_confirmation(text: str) -> str:
    """Return 'yes', 'no', or 'unclear' for a reminder reply. Keyword-first (fast, offline,
    saves free-tier quota); Gemini only for ambiguous answers."""
    t = text.lower()
    if re.search(NO, t):
        return "no"
    if re.search(YES, t):
        return "yes"
    try:
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction="Classify whether the reply confirms the medicine was taken. "
                                   "Answer with exactly one word: yes, no, or unclear.",
                max_output_tokens=256,
            ),
        )
        word = (resp.text or "").strip().lower().rstrip(".")
        return word if word in {"yes", "no", "unclear"} else "unclear"
    except Exception:
        return "unclear"
