"""
Jarvis bot uchun Notion API wrapper.
Notion-Version: 2025-09-03 (data source asosidagi so'rovlar uchun).
"""
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
DS_XODIMLAR = "8651b767-340e-4471-8b4f-4fb37434406a"
DS_VAZIFALAR = "3a611241-9e55-4f21-8903-1c28f3639b1b"
DS_YONALISHLAR = "9a0b19fa-3721-46d9-8ef1-2d83eb8163ec"
DS_MOLIYA = "234cfa8f-aa6b-4c8f-a7f9-cf4de3c08fa4"
DS_KONTENT_REJA = "6ec4eac1-2ba4-4cca-b0f7-864e20368ea6"
DS_BILIM_BAZASI = "3c38be56-e7be-401f-833a-f99b39174400"
DS_LEADLAR = "98e6a8ef-edf7-4e26-b7c7-c1edbb8307dc"
DS_KANAL_SHABLONLARI = "b95e2add-0722-4539-b358-a9cf7b08b834"


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
