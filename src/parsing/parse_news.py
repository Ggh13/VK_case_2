import json
import os
from pathlib import Path

import requests

NEWSAPI_KEY = "77189746e3c14597ae54b75cfc386309"
OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "telegram_posts.jsonl"
PAGE_SIZE = 200
LANGUAGE = os.getenv("NEWS_LANGUAGE", "en")
COUNTRY = os.getenv("NEWS_COUNTRY", "us")


def main():
    OUT_PATH.parent.mkdir(exist_ok=True)

    print(f"Загрузка последних {PAGE_SIZE} новостей (NewsAPI)...")

    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={
            "apiKey": NEWSAPI_KEY,
            "country": COUNTRY,
            "pageSize": PAGE_SIZE,
            "language": LANGUAGE,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "ok":
        print(f"Ошибка API: {data.get('message', 'неизвестная')}")
        return

    articles = data.get("articles", [])
    print(f"Получено {len(articles)} статей")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for i, article in enumerate(articles):
            title = (article.get("title") or "").strip()
            description = (article.get("description") or "").strip()
            content = (article.get("content") or "").strip()

            text_parts = [title]
            if description:
                text_parts.append(description)
            full_text = "\n\n".join(text_parts)

            if not full_text:
                continue

            doc = {
                "id": str(i + 1),
                "date": article.get("publishedAt") or "",
                "text": full_text,
                "url": article.get("url") or "",
            }
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"Готово! Сохранено {len(articles)} статей")
    print(f"Файл: {OUT_PATH}")


if __name__ == "__main__":
    main()
