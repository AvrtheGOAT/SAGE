"""Quick check that your Gemini key works before running the full assistant: python test_gemini.py"""
from google import genai
import config

if not config.GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY is empty - put it in your .env file")
client = genai.Client(api_key=config.GEMINI_API_KEY)
r = client.models.generate_content(model=config.GEMINI_MODEL, contents="Say 'SAGE is online' and nothing else.")
print(f"[{config.GEMINI_MODEL}] {r.text}")
