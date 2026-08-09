"""
Jarvis bot uchun OpenAI GPT Image (gpt-image-1) rasm generatsiyasi wrapper'i.
API: https://platform.openai.com/docs/api-reference/images
"""
from __future__ import annotations

import base64
import os

import requests

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
IMAGES_URL = "https://api.openai.com/v1/images/generations"

# Telegram post uchun eng yaqin qo'llab-quvvatlanadigan o'lcham (kvadratga yaqin)
_SIZE_BY_ASPECT = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
}


class OpenAINotConfigured(Exception):
    """OPENAI_API_KEY muhit o'zgaruvchisi o'rnatilmagan bo'lsa ko'tariladi."""


def generate_image(prompt: str, aspect_ratio: str = "1:1") -> bytes:
    """Berilgan matn (prompt) asosida rasm generatsiya qiladi, PNG bytes qaytaradi.

    aspect_ratio: masalan "1:1" (kvadrat, Telegram post uchun qulay), "16:9", "9:16".
    Xato bo'lsa yoki OPENAI_API_KEY yo'q bo'lsa, tegishli Exception ko'taradi — chaqiruvchi
    (bot.py) buni ushlab, foydalanuvchiga tushunarli xabar berishi kerak.
    """
    if not OPENAI_API_KEY:
        raise OpenAINotConfigured("OPENAI_API_KEY muhit o'zgaruvchisi o'rnatilmagan.")

    size = _SIZE_BY_ASPECT.get(aspect_ratio, "1024x1024")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    resp = requests.post(IMAGES_URL, headers=headers, json=body, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("data") or []
    if items and items[0].get("b64_json"):
        return base64.b64decode(items[0]["b64_json"])

    raise ValueError("OpenAI javobida rasm topilmadi (data ichida 'b64_json' yo'q).")
