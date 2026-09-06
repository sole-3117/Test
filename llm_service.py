import os
import asyncio
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def _sync_generate(system_prompt: str, user_prompt: str) -> str:
    if not client:
        return "Xatolik: GEMINI_API_KEY topilmadi."
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                "temperature": 0.7
            }
        )
        return response.text.strip() if response.text else "Natija bo'sh qaytdi."
    except Exception as e:
        return f"Gemini API xatoligi: {e}"

async def ask_agent(system_prompt: str, user_prompt: str) -> str:
    """Asinxron ipda Gemini chaqiruvi"""
    return await asyncio.to_thread(_sync_generate, system_prompt, user_prompt)
