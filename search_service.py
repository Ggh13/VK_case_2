import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import requests
import torch
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("search")
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "static"

load_dotenv(PROJECT_ROOT / ".env")

COLLECTION_NAME = "telegram_posts"
EMBED_MODEL_NAME = "intfloat/multilingual-e5-small"

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


log.info("Подключение к Qdrant %s:%s...", QDRANT_HOST, QDRANT_PORT)
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
log.info("Загрузка эмбеддера %s...", EMBED_MODEL_NAME)
embedder = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())

article_count = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    for _ in range(30):
        try:
            qdrant.get_collections()
            break
        except Exception:
            time.sleep(1)
    log.info("Qdrant доступен")

    json_path = DATA_DIR / "telegram_posts.jsonl"
    log.info("Парсинг свежих новостей NewsAPI...")
    from src.parsing import parse_news
    parse_news.main()

    log.info("Удаление старой коллекции %s...", COLLECTION_NAME)
    if qdrant.collection_exists(COLLECTION_NAME):
        qdrant.delete_collection(COLLECTION_NAME)

    posts = []
    with open(json_path, "r", encoding="utf-8") as f:
        for line in f:
            posts.append(json.loads(line))
    log.info("Загружено %d статей для индексации", len(posts))

    dim = embedder.get_embedding_dimension()
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    BATCH_SIZE = 64
    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        texts = [f"passage: {p['text']}" for p in batch]
        vectors = embedder.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        points = [
            PointStruct(id=int(p["id"]), vector=vec.tolist(), payload=p)
            for p, vec in zip(batch, vectors)
        ]
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)

    count = qdrant.count(collection_name=COLLECTION_NAME)
    global article_count
    article_count = count.count
    log.info("Индексация завершена: %d документов в Qdrant", article_count)

    if os.getenv("SKIP_OLLAMA_LOAD") != "1":
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
            models = [m["name"] for m in resp.json().get("models", [])]
            if not any(OLLAMA_MODEL in m for m in models):
                log.info("Модель %s не найдена, загрузка...", OLLAMA_MODEL)
                pull = requests.post(
                    f"{OLLAMA_BASE_URL}/api/pull",
                    json={"name": OLLAMA_MODEL},
                    stream=True,
                    timeout=300,
                )
                for _ in pull.iter_lines():
                    pass
                log.info("Модель %s загружена", OLLAMA_MODEL)
        except requests.RequestException as e:
            log.warning("Ollama недоступна: %s. RAG будет недоступен.", e)
    yield


app = FastAPI(title="Поиск по новостям", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    log.info(">>> %s %s", request.method, request.url.path)
    response = await call_next(request)
    log.info("<<< %s %s -> %s", request.method, request.url.path, response.status_code)
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/status")
def get_status():
    return {"articles": article_count, "collection": COLLECTION_NAME}



def vector_search(query: str, top_k: int) -> list[dict]:
    text = f"query: {query}"
    vec = embedder.encode(text, normalize_embeddings=True).tolist()
    hits = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vec,
        limit=top_k,
        with_payload=True,
    ).points

    results = []
    for h in hits:
        p = h.payload
        snippet = p["text"][:500].replace("\n", " ")
        results.append(
            {
                "score": round(h.score, 5),
                "id": p["id"],
                "date": p["date"],
                "text": snippet,
                "url": p["url"],
            }
        )
    return results


RAG_SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай на русском языке на вопрос пользователя, "
    "используя информацию из приложенных документов (новостей). "
    "Если документы не содержат ответа — скажи об этом прямо, не выдумывай."
)


def run_ask(query: str, top_n: int) -> dict:
    results = vector_search(query, top_n)

    context = "\n\n".join(
        f"[{i+1}] {r['text']}\n(ссылка: {r['url']})" for i, r in enumerate(results)
    )
    user_prompt = f"Документы:\n{context}\n\nВопрос пользователя: {query}"

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json()["message"]["content"]
    except requests.RequestException as e:
        answer = f"Ошибка при обращении к Ollama: {e}"

    return {"answer": answer, "sources": results}


@app.get("/search")
def search_endpoint(request: Request, q: str = Query(...), top_n: int = Query(10)):
    log.info("search | q=%s top_n=%d client=%s", q, top_n, request.client.host if request.client else "?")
    results = vector_search(q, top_n)
    log.info("search | q=%s results=%d", q, len(results))
    return {"query": q, "results": results}


@app.get("/ask")
def ask_endpoint(request: Request, q: str = Query(...), top_n: int = Query(5)):
    log.info("ask    | q=%s top_n=%d client=%s", q, top_n, request.client.host if request.client else "?")
    result = run_ask(q, top_n)
    log.info("ask    | q=%s sources=%d answer_len=%d", q, len(result["sources"]), len(result["answer"]))
    return {"query": q, **result}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
