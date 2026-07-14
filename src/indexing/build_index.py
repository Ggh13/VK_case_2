import json
import os
from pathlib import Path

import torch
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

IN_PATH = DATA_DIR / "telegram_posts.jsonl"
COLLECTION_NAME = "telegram_posts"
EMBED_MODEL_NAME = "intfloat/multilingual-e5-small"

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

BATCH_SIZE = 64


def get_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def main():
    if not IN_PATH.exists():
        print(f"Файл {IN_PATH} не найден. Сначала запусти parse_telegram.py")
        return

    print(f"Загрузка постов из {IN_PATH}...")
    posts = []
    with open(IN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            posts.append(json.loads(line))
    print(f"Загружено {len(posts)} постов")

    device = get_device()
    print(f"Загрузка эмбеддера {EMBED_MODEL_NAME} (device={device})...")
    model = SentenceTransformer(EMBED_MODEL_NAME, device=device)
    dim = model.get_embedding_dimension()

    print(f"Подключение к Qdrant {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    if client.collection_exists(COLLECTION_NAME):
        print(f"Удаление существующей коллекции {COLLECTION_NAME}...")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    print("Создание эмбеддингов и загрузка в Qdrant...")
    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        texts = [f"passage: {p['text']}" for p in batch]
        vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

        points = [
            PointStruct(
                id=int(p["id"]),
                vector=vec.tolist(),
                payload={
                    "id": p["id"],
                    "date": p["date"],
                    "text": p["text"],
                    "url": p["url"],
                },
            )
            for p, vec in zip(batch, vectors)
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"  {min(i + BATCH_SIZE, len(posts))}/{len(posts)}")

    count = client.count(collection_name=COLLECTION_NAME)
    client.close()
    print(f"Готово! Индекс создан: {count.count} документов в Qdrant")


if __name__ == "__main__":
    main()
