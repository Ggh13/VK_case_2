const API_BASE = "";
let mode = "search";

const queryInput = document.getElementById("query");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const hintEl = document.getElementById("hint");
const resultsEl = document.getElementById("results");
const modeSearchBtn = document.getElementById("mode-search");
const modeAskBtn = document.getElementById("mode-ask");
const badgeEl = document.getElementById("article-count");

fetch(`${API_BASE}/status`).then(r => r.json()).then(d => {
  badgeEl.textContent = `${d.articles} статей`;
}).catch(() => {
  badgeEl.textContent = "ошибка загрузки";
});

function setMode(newMode) {
  mode = newMode;
  modeSearchBtn.classList.toggle("active", mode === "search");
  modeAskBtn.classList.toggle("active", mode === "ask");
  hintEl.textContent =
    mode === "search"
      ? "Найдет новости по вашему запросу, отсортирует по релевантности"
      : "ИИ ответит на вопрос на основе найденных новостей";
  resultsEl.className = mode === "search" ? "results-grid" : "ask-layout";
}

modeSearchBtn.addEventListener("click", () => setMode("search"));
modeAskBtn.addEventListener("click", () => setMode("ask"));

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function truncateText(text, maxLen = 500) {
  if (text.length <= maxLen) return escapeHtml(text);
  const cut = text.slice(0, maxLen);
  const lastSpace = cut.lastIndexOf(" ");
  const display = lastSpace > maxLen * 0.8 ? cut.slice(0, lastSpace) : cut;
  return `${escapeHtml(display)}…`;
}

function renderPostCard(post) {
  return `
    <div class="post-card">
      <div class="meta">
        <span class="score">score ${post.score}</span>
        <span>${formatDate(post.date)}</span>
      </div>
      <div class="text">${truncateText(post.text)}</div>
      <a class="post-link" href="${post.url}" target="_blank" rel="noopener">
        Читать источник →
      </a>
    </div>
  `;
}

function renderSourceCard(source) {
  return `
    <div class="source-card">
      <div class="date">${formatDate(source.date)} · score ${source.score}</div>
      <div class="snippet">${truncateText(source.text, 200)}</div>
      <a class="source-link" href="${source.url}" target="_blank" rel="noopener">
        Читать источник →
      </a>
    </div>
  `;
}

function setLoading(loading) {
  if (loading) {
    submitBtn.disabled = true;
    statusEl.innerHTML = `<span class="spinner"></span>${
      mode === "ask" ? "Ищу документы и жду ответ модели…" : "Поиск…"
    }`;
  } else {
    submitBtn.disabled = false;
    statusEl.textContent = "";
  }
}

function setError(msg) {
  statusEl.textContent = `Ошибка: ${msg}`;
}

async function runSearch(query) {
  const res = await fetch(
    `${API_BASE}/search?q=${encodeURIComponent(query)}&top_n=20`
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();

  if (data.results.length === 0) {
    resultsEl.innerHTML = `<div class="empty-state"><p>Ничего не найдено. Попробуйте другой запрос.</p></div>`;
    return;
  }

  resultsEl.innerHTML = data.results.map(renderPostCard).join("");
}

async function runAsk(query) {
  const res = await fetch(
    `${API_BASE}/ask?q=${encodeURIComponent(query)}&top_n=5`
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();

  resultsEl.innerHTML = `
    <div class="answer-box">
      <span class="label">Ответ модели</span>
      <div class="content">${escapeHtml(data.answer)}</div>
    </div>
    <div class="sources-panel">
      <div class="label">Источники (${data.sources.length})</div>
      ${data.sources.map(renderSourceCard).join("")}
    </div>
  `;
}

async function handleSubmit() {
  const query = queryInput.value.trim();
  if (!query) return;

  setLoading(true);
  resultsEl.innerHTML = "";

  try {
    if (mode === "search") {
      await runSearch(query);
    } else {
      await runAsk(query);
    }
  } catch (err) {
    setError(err.message);
  } finally {
    setLoading(false);
  }
}

submitBtn.addEventListener("click", handleSubmit);
queryInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleSubmit();
});
