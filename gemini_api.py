"""
Jarvis bot uchun Google Gemini (Nano Banana) rasm generatsiyasi wrapper'i.
Interactions API orqali ishlaydi: https://ai.google.dev/gemini-api/docs/interactions-overview
"""
from __future__ import annotations

import base64
import os

import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class GeminiNotConfigured(Exception):
    """GEMINI_API_KEY muhit o'zgaruvchisi o'rnatilmagan bo'lsa ko'tariladi."""


def generate_image(prompt: str, aspect_ratio: str = "1:1") -> bytes:
    """Berilgan matn (prompt) asosida rasm generatsiya qiladi, PNG/JPEG bytes qaytaradi.

    aspect_ratio: masalan "1:1" (kvadrat, Telegram post uchun qulay), "16:9", "9:16".
    Xato bo'lsa yoki GEMINI_API_KEY yo'q bo'lsa, tegishli Exception ko'taradi — chaqiruvchi
    (bot.py) buni ushlab, foydalanuvchiga tushunarli xabar berishi kerak.
    """
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured("GEMINI_API_KEY muhit o'zgaruvchisi o'rnatilmagan.")

    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    body = {
        "model": GEMINI_IMAGE_MODEL,
        "input": [{"type": "text", "text": prompt}],
        "response_format": {"type": "image", "aspect_ratio": aspect_ratio},
    }
    resp = requests.post(INTERACTIONS_URL, headers=headers, json=body, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    for step in data.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if block.get("type") == "image" and block.get("data"):
                return base64.b64decode(block["data"])

    raise ValueError("Gemini javobida rasm topilmadi (steps ichida 'image' bloki yo'q).")
