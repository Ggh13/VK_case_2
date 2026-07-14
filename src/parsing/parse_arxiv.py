import time
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path

ARXIV_API_URL = "http://export.arxiv.org/api/query"

def fetch_batch(category: str, start: int, batch_size: int = 100) -> list[dict]:
    params = {
        "search_query": f"cat:{category}",
        "start": start,
        "max_results": batch_size,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    for attempt in range(3):
        try:
            resp = requests.get(ARXIV_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            print(f"  retry {attempt+1}/3 after error: {e}")
            time.sleep(5)
    else:
        return []

    soup = BeautifulSoup(resp.content, "xml")
    entries = []

    for entry in soup.find_all("entry"):
        arxiv_id = entry.find("id").text.strip()
        title = entry.find("title").text.strip().replace("\n", " ")
        summary = entry.find("summary").text.strip().replace("\n", " ")
        published = entry.find("published").text.strip()
        
        authors = [author.find("name").text for author in entry.find_all("author")]
        
        primary_cat_el = entry.find("primary_category")
        primary_cat = primary_cat_el.get("term") if primary_cat_el else category
        
        pdf_link = None
        for link in entry.find_all("link"):
            if link.get("title") == "pdf":
                pdf_link = link.get("href")
                break

        entries.append(
            {
                "id": arxiv_id,
                "title": title,
                "abstract": summary,
                "authors": authors,
                "category": primary_cat,
                "published": published,
                "pdf_url": pdf_link,
                "url": arxiv_id,
            }
        )
    return entries


def fetch_corpus(category: str, target_count: int, out_path: str, batch_size: int = 100, delay_sec: float = 3.0):
    seen_ids = set()
    written = 0
    start = 0

    with open(out_path, "w", encoding="utf-8") as f:
        while written < target_count:
            print(f"Fetching start={start} (собрано {written}/{target_count})")
            batch = fetch_batch(category, start, batch_size)
            
            if not batch:
                print("Пустой батч")
                break

            for doc in batch:
                if doc["id"] in seen_ids:
                    continue
                seen_ids.add(doc["id"])
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                written += 1

            start += batch_size
            time.sleep(delay_sec)

    print(f"Всего документов: {written}. Файл: {out_path}")


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    DATA_DIR = PROJECT_ROOT / "data"
    DATA_DIR.mkdir(exist_ok=True)

    CATEGORY = "cs.CL"
    TARGET_COUNT = 8000
    OUT_PATH = str(DATA_DIR / "arxiv_corpus.jsonl")

    fetch_corpus(CATEGORY, TARGET_COUNT, OUT_PATH)