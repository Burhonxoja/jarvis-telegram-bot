"""
Jarvis bot uchun Notion API wrapper.
Notion-Version: 2025-09-03 (data source asosidagi so'rovlar uchun).
"""
from __future__ import annotations  # Python 3.9 bilan moslik uchun (str | None yozuvi)

import os
import requests

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_VERSION = "2025-09-03"
BASE_URL = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

# --- Data source ID'lar (Jarvis — Boshqaruv Markazi ichidagi bazalar) ---
# Muhim: shu ID'lar endi muhit o'zgaruvchilaridan o'qiladi (standart qiymat — hozirgi ARK
# Hospital/Shovkat aka ishlatayotgan asl workspace). Shu tufayli YANGI MIJOZ uchun butunlay
# alohida nusxa ochish uchun kodni FORK qilish shart emas: mijozning o'z Notion shabloni
# (dublikat qilingan) + o'z Telegram boti bilan yangi Railway xizmati yaratib, faqat quyidagi
# DS_... muhit o'zgaruvchilarini (va NOTION_TOKEN, TELEGRAM_TOKEN va h.k.ni) shu mijozning
# workspace'iga mos qiymatlarga sozlash kifoya — bir xil kod, turli sozlamalar.
DS_XODIMLAR = os.environ.get("DS_XODIMLAR", "8651b767-340e-4471-8b4f-4fb37434406a")
DS_VAZIFALAR = os.environ.get("DS_VAZIFALAR", "3a611241-9e55-4f21-8903-1c28f3639b1b")
DS_YONALISHLAR = os.environ.get("DS_YONALISHLAR", "9a0b19fa-3721-46d9-8ef1-2d83eb8163ec")
DS_MOLIYA = os.environ.get("DS_MOLIYA", "234cfa8f-aa6b-4c8f-a7f9-cf4de3c08fa4")
DS_KONTENT_REJA = os.environ.get("DS_KONTENT_REJA", "6ec4eac1-2ba4-4cca-b0f7-864e20368ea6")
DS_BILIM_BAZASI = os.environ.get("DS_BILIM_BAZASI", "3c38be56-e7be-401f-833a-f99b39174400")
DS_LEADLAR = os.environ.get("DS_LEADLAR", "98e6a8ef-edf7-4e26-b7c7-c1edbb8307dc")
DS_KANAL_SHABLONLARI = os.environ.get("DS_KANAL_SHABLONLARI", "b95e2add-0722-4539-b358-a9cf7b08b834")
DS_LOYIHALAR = os.environ.get("DS_LOYIHALAR", "91ed2d9f-28d8-49c1-aa79-24ad92ab3318")


def query_data_source(data_source_id: str, filter_obj: dict | None = None, page_size: int = 50) -> list[dict]:
    """Berilgan data source'dan sahifalarni qaytaradi (filtrlash bilan yoki filtrsiz)."""
    url = f"{BASE_URL}/data_sources/{data_source_id}/query"
    body: dict = {"page_size": page_size}
    if filter_obj:
        body["filter"] = filter_obj
    resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def update_page_property(page_id: str, properties: dict) -> dict:
    """Sahifa (qator) propertylarini yangilaydi. Masalan: {'Status': {'select': {'name': 'Tasdiqlandi'}}}"""
    url = f"{BASE_URL}/pages/{page_id}"
    resp = requests.patch(url, headers=HEADERS, json={"properties": properties}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_page(data_source_id: str, properties: dict) -> dict:
    """Berilgan data source ichida yangi sahifa (qator) yaratadi."""
    url = f"{BASE_URL}/pages"
    body = {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
    }
    resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_page(page_id: str) -> dict:
    url = f"{BASE_URL}/pages/{page_id}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_comment(page_id: str, text: str) -> dict:
    """Sahifaga (masalan, bitta vazifaga) izoh/komment qo'shadi (Notion sahifa kommentariyasi)."""
    url = f"{BASE_URL}/comments"
    body = {
        "parent": {"page_id": page_id},
        "rich_text": [{"text": {"content": text}}],
    }
    resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def archive_page(page_id: str) -> dict:
    """Sahifani Notion'ning arxiviga (trash) ko'chiradi — o'chirish o'rniga, kerak bo'lsa Notion'dan qaytarish mumkin."""
    url = f"{BASE_URL}/pages/{page_id}"
    resp = requests.patch(url, headers=HEADERS, json={"archived": True}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_comments(page_id: str) -> list[dict]:
    """Berilgan sahifadagi (masalan, vazifadagi) barcha izohlarni qaytaradi (yaratilgan tartibda)."""
    url = f"{BASE_URL}/comments"
    resp = requests.get(url, headers=HEADERS, params={"block_id": page_id}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


# --- Property qiymatlarini o'qishni osonlashtiruvchi yordamchi funksiyalar ---

def get_title(page: dict, prop_name: str) -> str:
    prop = page.get("properties", {}).get(prop_name, {})
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts)


def get_rich_text(page: dict, prop_name: str) -> str:
    prop = page.get("properties", {}).get(prop_name, {})
    parts = prop.get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts)


def get_select(page: dict, prop_name: str) -> str | None:
    prop = page.get("properties", {}).get(prop_name, {})
    sel = prop.get("select")
    return sel.get("name") if sel else None


def get_status(page: dict, prop_name: str) -> str | None:
    prop = page.get("properties", {}).get(prop_name, {})
    st = prop.get("status")
    return st.get("name") if st else None


def get_date(page: dict, prop_name: str) -> str | None:
    prop = page.get("properties", {}).get(prop_name, {})
    d = prop.get("date")
    return d.get("start") if d else None


def get_url(page: dict, prop_name: str) -> str | None:
    prop = page.get("properties", {}).get(prop_name, {})
    return prop.get("url")


def get_number(page: dict, prop_name: str) -> float | None:
    prop = page.get("properties", {}).get(prop_name, {})
    return prop.get("number")


def get_checkbox(page: dict, prop_name: str) -> bool:
    prop = page.get("properties", {}).get(prop_name, {})
    return bool(prop.get("checkbox"))


def get_relation_ids(page: dict, prop_name: str) -> list[str]:
    prop = page.get("properties", {}).get(prop_name, {})
    rel = prop.get("relation", [])
    return [r["id"] for r in rel]


# --- Xodimlar bilan ishlash ---

def find_employee_by_name(name: str) -> dict | None:
    """Ism bo'yicha xodimni topadi (aniq moslik, keyin qisman moslik bilan qayta uradi)."""
    results = query_data_source(
        DS_XODIMLAR, filter_obj={"property": "Ism", "title": {"equals": name}}
    )
    if results:
        return results[0]
    results = query_data_source(
        DS_XODIMLAR, filter_obj={"property": "Ism", "title": {"contains": name}}
    )
    return results[0] if results else None


def find_employee_by_chat_id(chat_id: int) -> dict | None:
    results = query_data_source(
        DS_XODIMLAR, filter_obj={"property": "Telegram", "rich_text": {"equals": str(chat_id)}}
    )
    return results[0] if results else None


def register_employee_chat_id(employee_page_id: str, chat_id: int) -> None:
    update_page_property(employee_page_id, {"Telegram": {"rich_text": [{"text": {"content": str(chat_id)}}]}})


# --- Telegram kanal xaritasi (Kontent-Reja'dagi "Kanal" nomidan haqiqiy Telegram kanaliga) ---
# Ikki usulda sozlanadi:
# 1) CHANNEL_MAP_JSON — bitta muhit o'zgaruvchisida to'liq JSON xarita, masalan:
#    {"Mening kanalim": "@mening_kanalim", "Boshqa kanal": "-1001234567890"}
#    Bu — YANGI MIJOZ uchun alohida nusxa ochganda, kodni o'zgartirmasdan, faqat shu
#    bitta muhit o'zgaruvchisini sozlash orqali istalgan sondagi/nomdagi kanalni ulash imkonini beradi.
# 2) CHANNEL_MAP_JSON sozlanmagan bo'lsa — orqaga moslik uchun eski alohida
#    CHANNEL_UROLOG_SHOVKAT / CHANNEL_ARK_HOSPITAL / CHANNEL_18_NATIJALAR o'zgaruvchilari ishlatiladi.
import json as _json

if os.environ.get("CHANNEL_MAP_JSON"):
    try:
        CHANNEL_MAP = _json.loads(os.environ["CHANNEL_MAP_JSON"])
    except ValueError:
        CHANNEL_MAP = {}
else:
    CHANNEL_MAP = {
        "Telegram - Urolog Shovkat": os.environ.get("CHANNEL_UROLOG_SHOVKAT"),
        "Telegram - ARK Hospital": os.environ.get("CHANNEL_ARK_HOSPITAL"),
        "Telegram - 18+ Natijalar": os.environ.get("CHANNEL_18_NATIJALAR"),
    }


def get_channel_footer(kanal: str) -> str:
    """"📋 Kanal Shablonlari" bazasidan shu kanalning 'Post oxiri shabloni' (imzo/footer)
    matnini oladi. Topilmasa bo'sh satr qaytaradi."""
    try:
        results = query_data_source(
            DS_KANAL_SHABLONLARI, filter_obj={"property": "Kanal", "title": {"equals": kanal}}
        )
    except Exception:
        return ""
    if not results:
        return ""
    return get_rich_text(results[0], "Post oxiri shabloni") or ""
