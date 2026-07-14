# Новостной поиск (NewsAPI + RAG)

Поисковый сервис по новостям: парсинг через NewsAPI, векторный поиск (Qdrant), RAG-ответы через локальную LLM (Ollama). Запуск в Docker Compose.

## Архитектура

```
Клиент (браузер / curl)
      │
      ▼
FastAPI (search_service.py)
      │
      ├── Qdrant (HNSW, cosine similarity)
      └── Ollama (llama3.2:3b) — только для /ask
```

- **Парсинг**: `src/parsing/parse_news.py` — получает top-headlines через NewsAPI
- **Индексация**: `src/indexing/build_index.py` — эмбеддер `intfloat/multilingual-e5-small`, запись в Qdrant
- **Сервис поиска**: `search_service.py` — FastAPI с `/search` и `/ask`, веб-интерфейс на `/`

## Запуск через Docker

### Требования
- Docker + Docker Compose

### Быстрый старт

1. Сборка и запуск:
   ```bash
   docker compose up -d
   ```

2. Парсинг новостей (первый раз или для обновления данных):
   ```bash
   docker compose run --rm app python src/parsing/parse_news.py
   ```

3. Индексация в Qdrant (после каждого парсинга):
   ```bash
   docker compose run --rm app python src/indexing/build_index.py
   ```

4. Перезапустить app чтобы он подхватил новые данные:
   ```bash
   docker compose restart app
   ```

5. Открыть в браузере: **http://localhost:8000/**

### Остановка

```bash
docker compose down
```

Удалить данные Qdrant и Ollama (опционально):
```bash
docker compose down -v
```

### Перезапуск после изменений кода

```bash
docker compose up -d --build
```

## API

### `GET /search?q=<запрос>&top_n=10`
Векторный поиск по новостям. Возвращает top-N результатов с score, date, text, url.

```bash
curl "http://localhost:8000/search?q=technology&top_n=5"
```

### `GET /ask?q=<запрос>&top_n=5`
RAG-ответ: находит top-N новостей и формирует ответ через Ollama на русском языке.

```bash
curl "http://localhost:8000/ask?q=последние%20новости%20технологий"
```

## Переменные окружения (`.env`)

| Переменная        | По умолчанию      | Описание                      |
|-------------------|-------------------|-------------------------------|
| `NEWS_LANGUAGE`   | `en`              | Язык новостей (en, ru, ...)   |
| `NEWS_COUNTRY`    | `us`              | Страна новостей (us, ru, ...) |

## Технологии

| Компонент          | Технология                          |
|--------------------|-------------------------------------|
| Векторный поиск    | Qdrant (HNSW, cosine)              |
| Эмбеддинги         | `intfloat/multilingual-e5-small`   |
| LLM                | Ollama, `llama3.2:3b`              |
| Веб-сервис         | FastAPI + Uvicorn                  |
| Источник данных    | NewsAPI (top-headlines)            |
