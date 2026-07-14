import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CHANNEL = "sergunov_prod"
BASE_URL = f"https://t.me/s/{CHANNEL}"
OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "telegram_posts.jsonl"
DELAY_SEC = 1.5
MAX_POSTS = None


def fetch_page(before: int | None = None) -> str | None:
    url = BASE_URL if before is None else f"{BASE_URL}?before={before}"
    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  Ошибка запроса: {e}")
        return None


def parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    messages = soup.select(".tgme_widget_message")
    posts = []
    for msg in messages:
        data_post = msg.get("data-post", "")
        parts = data_post.split("/")
        if len(parts) != 2:
            continue
        post_id = parts[1]

        text_node = msg.select_one(".tgme_widget_message_text")
        text = text_node.get_text("\n", strip=True) if text_node else ""

        if not text:
            continue

        date_node = msg.select_one("time")
        published_at = date_node.get("datetime") if date_node else None

        views_node = msg.select_one(".tgme_widget_message_views")
        views = views_node.get_text(strip=True) if views_node else None

        posts.append({
            "id": post_id,
            "date": published_at,
            "text": text,
            "url": f"https://t.me/{data_post}",
            "views": views,
        })
    return posts


def get_oldest_post_id(posts: list[dict]) -> int | None:
    ids = [int(p["id"]) for p in posts]
    return min(ids) if ids else None


def main():
    OUT_PATH.parent.mkdir(exist_ok=True)

    all_posts: list[dict] = []
    before: int | None = None
    page = 0

    print(f"Парсинг канала @{CHANNEL}...")

    while True:
        page += 1
        print(f"Страница {page} (before={before})...")

        html = fetch_page(before)
        if not html:
            break

        posts = parse_page(html)
        if not posts:
            print("Постов нет — завершаем")
            break

        new_count = 0
        for p in posts:
            if p["id"] not in {x["id"] for x in all_posts}:
                all_posts.append(p)
                new_count += 1

        print(f"  +{new_count} новых постов (всего: {len(all_posts)})")

        if MAX_POSTS and len(all_posts) >= MAX_POSTS:
            all_posts = all_posts[:MAX_POSTS]
            break

        oldest = get_oldest_post_id(posts)
        if oldest is None or oldest == before:
            break
        before = oldest

        time.sleep(DELAY_SEC)

    all_posts.sort(key=lambda p: int(p["id"]))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for p in all_posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"\nГотово! Собрано {len(all_posts)} постов")
    print(f"Файл: {OUT_PATH}")


if __name__ == "__main__":
    main()
